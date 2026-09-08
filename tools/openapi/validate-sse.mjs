import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";
import addFormats from "ajv-formats";

const here = dirname(fileURLToPath(import.meta.url));
const casesPath = resolve(here, "../../tests/fixtures/sse_v1_cases.json");
const schemaDir = resolve(here, "../../go-spider/openapi/v1/sse");
const cases = JSON.parse(await readFile(casesPath, "utf8"));
let failures = 0;
for (const c of cases.cases) {
  let valid;
  let errors = [];
  try {
    const schema = JSON.parse(await readFile(resolve(schemaDir, c.schema), "utf8"));
    const ajv = new Ajv({ strict: false, validateSchema: false, allErrors: true });
    addFormats(ajv);
    const validate = ajv.compile(schema);
    valid = validate(c.data);
    errors = validate.errors ?? [];
  } catch (err) {
    failures++;
    console.error(`LOAD/COMPILE FAIL ${c.name}: ${err.message}`);
    continue;
  }
  if (c.valid && !valid) {
    failures++;
    console.error(`FAIL valid case ${c.name}: ${JSON.stringify(validate.errors)}`);
  } else if (!c.valid && valid) {
    failures++;
    console.error(`FAIL invalid case ${c.name}: expected rejection`);
  } else if (!c.valid && c.expect) {
    const hit = errors.some((e) => {
      if (e.keyword !== c.expect.keyword) {
        return false;
      }
      if (c.expect.instancePath && e.instancePath !== c.expect.instancePath) {
        return false;
      }
      if (c.expect.missingProperty && e.params?.missingProperty !== c.expect.missingProperty) {
        return false;
      }
      return true;
    });
    if (!hit) {
      failures++;
      console.error(`FAIL invalid case ${c.name}: expected constraint not hit: ${JSON.stringify(errors)}`);
    }
  }
}
if (failures) {
  process.exit(1);
}
console.log(`SSE cases passed: ${cases.cases.length}`);
