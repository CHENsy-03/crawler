import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = dirname(fileURLToPath(import.meta.url));
const casesPath = resolve(here, "../../tests/fixtures/sse_v1_cases.json");
const schemaDir = resolve(here, "../../go-spider/openapi/v1/sse");
const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);

function newValidator() {
  const ajv = new Ajv2020({
    strict: true,
    // export_finished uses required inside allOf/not against root-level properties.
    strictRequired: false,
    allErrors: true,
    validateSchema: true,
  });
  addFormats(ajv);
  return ajv;
}

export function compileSseSchema(schema) {
  return newValidator().compile(schema);
}

export async function resolveSseSchema(schemaRef) {
  if (schemaRef && typeof schemaRef === "object") {
    return schemaRef;
  }
  return JSON.parse(await readFile(resolve(schemaDir, schemaRef), "utf8"));
}

function expectedConstraintHit(expect, errors) {
  return errors.some((e) => {
    if (e.keyword !== expect.keyword) {
      return false;
    }
    if (expect.instancePath && e.instancePath !== expect.instancePath) {
      return false;
    }
    if (expect.missingProperty && e.params?.missingProperty !== expect.missingProperty) {
      return false;
    }
    return true;
  });
}

export async function runSseCase(c) {
  let valid = false;
  let errors = [];
  try {
    const validate = compileSseSchema(await resolveSseSchema(c.schema));
    valid = validate(c.data);
    errors = validate.errors ?? [];
  } catch (err) {
    return { kind: "load_compile_fail", name: c.name, error: err, errors: [] };
  }
  if (c.valid && !valid) {
    return { kind: "valid_case_failed", name: c.name, errors };
  }
  if (!c.valid && valid) {
    return { kind: "invalid_case_passed", name: c.name, errors: [] };
  }
  if (!c.valid && c.expect && !expectedConstraintHit(c.expect, errors)) {
    return { kind: "expected_constraint_missed", name: c.name, errors };
  }
  return { kind: "ok", name: c.name, errors };
}

function reportFailure(result) {
  if (result.kind === "load_compile_fail") {
    console.error(`LOAD/COMPILE FAIL ${result.name}: ${result.error?.message ?? String(result.error)}`);
  } else if (result.kind === "valid_case_failed") {
    console.error(`FAIL valid case ${result.name}: ${JSON.stringify(result.errors)}`);
  } else if (result.kind === "invalid_case_passed") {
    console.error(`FAIL invalid case ${result.name}: expected rejection`);
  } else {
    console.error(`FAIL invalid case ${result.name}: expected constraint not hit: ${JSON.stringify(result.errors)}`);
  }
}

export async function runSseCases(cases) {
  let failures = 0;
  for (const c of cases) {
    const result = await runSseCase(c);
    if (result.kind !== "ok") {
      failures++;
      reportFailure(result);
    }
  }
  return failures;
}

async function verifyFailureModes(cases) {
  let failures = 0;
  const validSource = cases.find((c) => c.valid);
  if (!validSource) {
    console.error("VERIFY FAIL no valid fixture case available");
    return 1;
  }

  const corrupted = {
    ...validSource,
    name: `in-memory valid-case failure (${validSource.name})`,
    data: { ...validSource.data, event_version: "corrupted" },
  };
  let result;
  try {
    result = await runSseCase(corrupted);
  } catch (err) {
    failures++;
    console.error(`VERIFY FAIL in-memory valid-case variant raised ${err?.name ?? "error"}: ${err?.message ?? err}`);
    return failures;
  }
  if (result.kind !== "valid_case_failed" || result.errors.length === 0) {
    failures++;
    console.error(`VERIFY FAIL expected valid_case_failed with instance errors; got ${result.kind}`);
  } else {
    console.log(`VERIFY OK in-memory valid-case failure: ${result.name}; errors=${JSON.stringify(result.errors)}`);
  }

  const sourceSchema = await resolveSseSchema(validSource.schema);
  const invalidSchema = { ...sourceSchema, type: "not-a-valid-json-schema-type" };
  const invalidSchemaCase = {
    name: "in-memory invalid schema",
    schema: invalidSchema,
    valid: false,
    data: validSource.data,
  };
  result = await runSseCase(invalidSchemaCase);
  if (result.kind !== "load_compile_fail") {
    failures++;
    console.error(`VERIFY FAIL expected load/compile failure; got ${result.kind}`);
  } else {
    console.log(`VERIFY OK in-memory invalid schema: ${result.name}; ${result.error?.message ?? ""}`);
  }
  return failures;
}

async function main() {
  const cases = JSON.parse(await readFile(casesPath, "utf8"));
  if (process.argv.includes("--verify-failure-modes")) {
    const failures = await verifyFailureModes(cases.cases);
    if (failures) {
      console.error(`Failure-mode verification failed: ${failures}`);
      process.exitCode = 1;
    }
    return;
  }

  const failures = await runSseCases(cases.cases);
  if (failures) {
    process.exit(1);
  }
  console.log(`SSE cases passed: ${cases.cases.length}`);
}

if (isMain) {
  await main();
}
