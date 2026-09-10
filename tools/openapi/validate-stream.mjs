import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");
const streamSchemaDir = resolve(repoRoot, "protocol/streams/v3");
const capacitySchemaDir = resolve(repoRoot, "protocol/control/v1");
const streamCasesPath = resolve(repoRoot, "tests/fixtures/redis_stream_v3_cases.json");
const capacityCasesPath = resolve(repoRoot, "tests/fixtures/capacity_state_v1_cases.json");

const streamSchemaFiles = [
  "envelope.schema.json",
  "search_requested.schema.json",
  "url.schema.json",
  "html.schema.json",
  "result.schema.json",
  "error.schema.json",
];

async function loadJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function loadSchema(ajv, dir, file) {
  const schema = await loadJson(resolve(dir, file));
  ajv.addSchema(schema, file);
}

function numberFailure(field, failure, reason, token = null) {
  return { ok: false, field, failure, reason, token };
}

// Parse the original JSON number token without converting it through Number.
export function exactRawInteger(raw, spec) {
  if (!spec || typeof spec.field !== "string" || !Number.isInteger(spec.min) || !Number.isInteger(spec.max) || spec.min > spec.max) {
    return { ok: false, field: spec?.field ?? null, failure: "invalid_metadata", reason: "invalid numberCheck metadata" };
  }
  const field = spec.field;
  const leaf = field.split(".").pop();
  const match = raw.match(new RegExp(`"${leaf}":\\s*([^,}\\]\\s]+)`));
  if (!match) {
    return { ok: false, field, failure: "token_missing", reason: "raw number token could not be located" };
  }
  const token = match[1];
  if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(token)) {
    return numberFailure(field, "not_a_number", "raw token is not a JSON number", token);
  }
  try {
    const negative = token.startsWith("-");
    let rest = negative ? token.slice(1) : token;
    const exponentParts = rest.split(/[eE]/);
    rest = exponentParts[0];
    const exponent = exponentParts.length === 2 ? Number(exponentParts[1]) : 0;
    const dot = rest.indexOf(".");
    let digits = rest;
    let fracLength = 0;
    if (dot >= 0) {
      digits = rest.slice(0, dot) + rest.slice(dot + 1);
      fracLength = rest.length - dot - 1;
    }
    const scale = exponent - fracLength;
    let value;
    if (scale >= 0) {
      value = BigInt(digits) * 10n ** BigInt(scale);
    } else {
      const denominator = 10n ** BigInt(-scale);
      const numerator = BigInt(digits);
      if (numerator % denominator !== 0n) {
        return numberFailure(field, "not_integer", "raw token is not a mathematical integer", token);
      }
      value = numerator / denominator;
    }
    if (negative) {
      value = -value;
    }
    if (value < BigInt(spec.min) || value > BigInt(spec.max)) {
      return numberFailure(field, "out_of_range", "raw integer is outside the approved range", token);
    }
    return { ok: true, field, value: value.toString(), token };
  } catch (err) {
    return { ok: false, field, failure: "checker_error", reason: err.message };
  }
}

async function evaluateCase(ajv, cases, c) {
  const schemaFile = c.schema ?? cases.schema;
  const layers = c.layer ?? [];
  if (!c.numberCheck && !layers.some((layer) => ["json", "schema", "exact_number"].includes(layer))) {
    return { status: "not_applicable", name: c.name };
  }
  let instance;
  try {
    instance = c.raw ? JSON.parse(c.raw) : c.data;
  } catch (err) {
    return { status: "rejected", layer: "json", reason: err.message, name: c.name };
  }

  if (c.numberCheck) {
    const number = exactRawInteger(c.raw, c.numberCheck);
    if (!number.ok) {
      if (["token_missing", "invalid_metadata", "checker_error"].includes(number.failure)) {
        return {
          status: "tool_failure",
          stage: "number_check",
          field: number.field,
          reason: `${number.failure}: ${number.reason}`,
          name: c.name,
        };
      }
      return {
        status: "rejected",
        layer: "exact_number",
        failure: number.failure,
        field: number.field,
        reason: number.reason,
        token: number.token,
        name: c.name,
      };
    }
  }

  let validate;
  try {
    validate = ajv.getSchema(schemaFile);
    if (!validate) {
      throw new Error(`schema not registered: ${schemaFile}`);
    }
  } catch (err) {
    return { status: "tool_failure", stage: "schema_compile", reason: err.message, name: c.name };
  }
  const valid = validate(instance);
  if (!valid) {
    return { status: "rejected", layer: "schema", errors: validate.errors, name: c.name };
  }
  return { status: "accepted", name: c.name };
}

function judgeCase(c, actual) {
  if (actual.status === "tool_failure") {
    return { ok: false, reason: `${actual.stage}: ${actual.reason}` };
  }
  if (actual.status === "not_applicable") {
    return c.valid ? { ok: false, reason: "valid case has no formal Node validation layer" } : { ok: true };
  }
  if (c.valid) {
    return actual.status === "accepted"
      ? { ok: true }
      : { ok: false, reason: `expected accepted, got ${actual.status}/${actual.layer ?? ""}` };
  }
  if (actual.status !== "rejected") {
    return { ok: false, reason: "expected rejection, got accepted" };
  }
  const expect = c.expect ?? {};
  if (expect.layer && actual.layer !== expect.layer) {
    return { ok: false, reason: `expected layer ${expect.layer}, got ${actual.layer}` };
  }
  if (expect.failure && actual.failure !== expect.failure) {
    return { ok: false, reason: `expected failure ${expect.failure}, got ${actual.failure}` };
  }
  if (expect.field && actual.field !== expect.field) {
    return { ok: false, reason: `expected field ${expect.field}, got ${actual.field}` };
  }
  return { ok: true };
}

export async function validateCases(ajv, cases) {
  let failures = 0;
  const results = [];
  for (const c of cases.cases) {
    const actual = await evaluateCase(ajv, cases, c);
    const verdict = judgeCase(c, actual);
    results.push({ expectedValid: c.valid, actual, verdict });
    if (!verdict.ok) {
      failures++;
      console.error(`CASE FAIL ${c.name}: ${verdict.reason}; actual=${JSON.stringify(actual)}`);
    }
  }
  return { failures, results };
}

export async function createStreamValidator() {
  const ajv = new Ajv2020({ strict: true, allErrors: true, validateSchema: true });
  addFormats(ajv);
  for (const file of streamSchemaFiles) {
    await loadSchema(ajv, streamSchemaDir, file);
  }
  const capacitySchema = await loadJson(resolve(capacitySchemaDir, "capacity_state.schema.json"));
  ajv.addSchema(capacitySchema, "capacity_state.schema.json");
  return ajv;
}

function summarize(results) {
  const summary = { accepted: 0, notApplicable: 0, jsonRejected: 0, exactNumberRejected: 0, schemaRejected: 0, toolFailures: 0 };
  for (const item of results) {
    if (item.actual.status === "accepted") summary.accepted++;
    else if (item.actual.status === "not_applicable") summary.notApplicable++;
    else if (item.actual.status === "tool_failure") summary.toolFailures++;
    else if (item.actual.layer === "json") summary.jsonRejected++;
    else if (item.actual.layer === "exact_number") summary.exactNumberRejected++;
    else if (item.actual.layer === "schema") summary.schemaRejected++;
  }
  return summary;
}

async function main() {
  const ajv = await createStreamValidator();
  const streamCases = await loadJson(streamCasesPath);
  const capacityCases = await loadJson(capacityCasesPath);
  const stream = await validateCases(ajv, streamCases);
  const capacity = await validateCases(ajv, capacityCases);
  const failures = stream.failures + capacity.failures;
  if (failures) {
    process.exit(1);
  }
  const s = summarize(stream.results);
  const c = summarize(capacity.results);
  console.log(`Stream v3 cases: accepted=${s.accepted} notApplicable=${s.notApplicable} jsonRejected=${s.jsonRejected} exactNumberRejected=${s.exactNumberRejected} schemaRejected=${s.schemaRejected} toolFailures=${s.toolFailures}`);
  console.log(`Capacity v1 cases: accepted=${c.accepted} notApplicable=${c.notApplicable} jsonRejected=${c.jsonRejected} exactNumberRejected=${c.exactNumberRejected} schemaRejected=${c.schemaRejected} toolFailures=${c.toolFailures}`);
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  await main();
}
