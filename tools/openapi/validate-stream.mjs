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

function skipJSONWhitespace(raw, index) {
  while (index < raw.length && (raw[index] === " " || raw[index] === "\t" || raw[index] === "\n" || raw[index] === "\r")) {
    index++;
  }
  return index;
}

function parseJSONStringToken(raw, index) {
  if (raw[index] !== '"') {
    return null;
  }
  let cursor = index + 1;
  while (cursor < raw.length) {
    if (raw[cursor] === "\\") {
      cursor += 2;
      continue;
    }
    if (raw[cursor] === '"') {
      const token = raw.slice(index, cursor + 1);
      return { token, value: JSON.parse(token), end: cursor + 1 };
    }
    cursor++;
  }
  return null;
}

function parseJSONNumberToken(raw, index) {
  const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(raw.slice(index));
  if (!match) {
    return null;
  }
  const token = match[0];
  const end = index + token.length;
  if (end < raw.length && ![" ", "\t", "\n", "\r", ",", "}", "]"].includes(raw[end])) {
    return null;
  }
  return { token, end };
}

function skipJSONValue(raw, index) {
  index = skipJSONWhitespace(raw, index);
  if (raw[index] === '"') {
    return parseJSONStringToken(raw, index)?.end ?? null;
  }
  if (raw[index] === "{") {
    index = skipJSONWhitespace(raw, index + 1);
    if (raw[index] === "}") return index + 1;
    while (index < raw.length) {
      const key = parseJSONStringToken(raw, index);
      if (!key) return null;
      index = skipJSONWhitespace(raw, key.end);
      if (raw[index] !== ":") return null;
      index = skipJSONWhitespace(raw, index + 1);
      index = skipJSONValue(raw, index);
      if (index === null) return null;
      index = skipJSONWhitespace(raw, index);
      if (raw[index] === "}") return index + 1;
      if (raw[index] !== ",") return null;
      index = skipJSONWhitespace(raw, index + 1);
    }
    return null;
  }
  if (raw[index] === "[") {
    index = skipJSONWhitespace(raw, index + 1);
    if (raw[index] === "]") return index + 1;
    while (index < raw.length) {
      index = skipJSONValue(raw, index);
      if (index === null) return null;
      index = skipJSONWhitespace(raw, index);
      if (raw[index] === "]") return index + 1;
      if (raw[index] !== ",") return null;
      index = skipJSONWhitespace(raw, index + 1);
    }
    return null;
  }
  for (const literal of ["true", "false", "null"]) {
    if (raw.startsWith(literal, index)) {
      return index + literal.length;
    }
  }
  return parseJSONNumberToken(raw, index)?.end ?? null;
}

// Locate a value by full object path while preserving the original number token.
export function locateJSONValue(raw, path) {
  if (!Array.isArray(path) || path.length === 0) {
    return { status: "invalid_metadata", reason: "path must be a non-empty array" };
  }
  function locateAt(index, remaining) {
    index = skipJSONWhitespace(raw, index);
    if (raw[index] !== "{") {
      return { status: "missing" };
    }
    let found = { status: "missing" };
    index = skipJSONWhitespace(raw, index + 1);
    if (raw[index] === "}") return found;
    while (index < raw.length) {
      const key = parseJSONStringToken(raw, index);
      if (!key) return { status: "syntax_error", reason: "invalid object key" };
      index = skipJSONWhitespace(raw, key.end);
      if (raw[index] !== ":") return { status: "syntax_error", reason: "missing object colon" };
      const valueStart = skipJSONWhitespace(raw, index + 1);
      if (key.value === remaining[0]) {
        if (remaining.length === 1) {
          if (raw[valueStart] === '"') {
            const stringValue = parseJSONStringToken(raw, valueStart);
            if (!stringValue) return { status: "syntax_error", reason: "invalid string value" };
            found = { status: "not_number", token: stringValue.token };
          } else {
            const numberValue = parseJSONNumberToken(raw, valueStart);
            if (numberValue) {
              found = { status: "found", token: numberValue.token };
            } else {
              const end = skipJSONValue(raw, valueStart);
              if (end === null) return { status: "syntax_error", reason: "invalid value" };
              found = { status: "not_number", token: raw.slice(valueStart, end) };
            }
          }
        } else {
          const nested = locateAt(valueStart, remaining.slice(1));
          if (nested.status !== "missing") {
            found = nested;
          }
        }
      }
      index = skipJSONValue(raw, valueStart);
      if (index === null) return { status: "syntax_error", reason: "invalid value" };
      index = skipJSONWhitespace(raw, index);
      if (raw[index] === "}") return found;
      if (raw[index] !== ",") return { status: "syntax_error", reason: "invalid object separator" };
      index = skipJSONWhitespace(raw, index + 1);
    }
    return { status: "syntax_error", reason: "unterminated object" };
  }
  try {
    return locateAt(skipJSONWhitespace(raw, 0), path);
  } catch (err) {
    return { status: "syntax_error", reason: err.message };
  }
}

// Parse the original JSON number token without converting it through Number.
export function exactRawInteger(raw, spec) {
  if (!spec || typeof spec.field !== "string" || !Number.isInteger(spec.min) || !Number.isInteger(spec.max) || spec.min > spec.max) {
    return { ok: false, field: spec?.field ?? null, failure: "invalid_metadata", reason: "invalid numberCheck metadata" };
  }
  const field = spec.field;
  const located = locateJSONValue(raw, field.split("."));
  if (located.status === "missing") {
    return { ok: false, field, failure: "token_missing", reason: "raw number token could not be located" };
  }
  if (located.status === "syntax_error") {
    return { ok: false, field, failure: "checker_error", reason: located.reason };
  }
  if (located.status === "not_number") {
    return numberFailure(field, "not_a_number", "raw token is not a JSON number", located.token);
  }
  const token = located.token;
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

export function validateLocatorCases(cases) {
  let failures = 0;
  const results = [];
  for (const c of cases.locator_cases ?? []) {
    const actual = locateJSONValue(c.raw, c.field.split("."));
    let ok = actual.status === c.expect.status;
    if (ok && Object.hasOwn(c.expect, "token")) {
      ok = actual.token === c.expect.token;
    }
    if (!ok) {
      failures++;
      console.error(`LOCATOR CASE FAIL ${c.name}: expected=${JSON.stringify(c.expect)} actual=${JSON.stringify(actual)}`);
    }
    results.push({ name: c.name, expected: c.expect, actual, ok });
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
  const locator = validateLocatorCases(streamCases);
  const failures = stream.failures + capacity.failures + locator.failures;
  if (failures) {
    process.exit(1);
  }
  const s = summarize(stream.results);
  const c = summarize(capacity.results);
  console.log(`Stream v3 cases: accepted=${s.accepted} notApplicable=${s.notApplicable} jsonRejected=${s.jsonRejected} exactNumberRejected=${s.exactNumberRejected} schemaRejected=${s.schemaRejected} toolFailures=${s.toolFailures}`);
  console.log(`Capacity v1 cases: accepted=${c.accepted} notApplicable=${c.notApplicable} jsonRejected=${c.jsonRejected} exactNumberRejected=${c.exactNumberRejected} schemaRejected=${c.schemaRejected} toolFailures=${c.toolFailures}`);
  console.log(`Locator cases: passed=${locator.results.filter((item) => item.ok).length} failed=${locator.failures}`);
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  await main();
}
