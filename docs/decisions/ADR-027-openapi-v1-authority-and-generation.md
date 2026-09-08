# ADR-027: OpenAPI V1 Authority and Generation

**状态：** accepted

**日期：** 2026-09-07

## Context

DEV-003 freezes the external `/api/v1` contract. Prior contract material lived in
`docs/API_CONTRACT.md` as a human-readable draft. The project needs one machine-readable
authority and a bounded generation/validation plan.

## Decision

- Authoritative OpenAPI file: `go-spider/openapi/v1/openapi.yaml`
- OpenAPI version: 3.1.0
- Server URL: `/api/v1`
- JSON Schema dialect: `https://json-schema.org/draft/2020-12/schema`
- Six external SSE payload schemas live under `go-spider/openapi/v1/sse/`
- 43-operation contract matrix lives under `tests/fixtures/openapi_v1_contract.json`
- `docs/API_CONTRACT.md` is human-readable navigation only

Successful JSON responses use concrete DTO schemas; `data` never resolves to an
unconstrained object. Results uses page/cursor mutual exclusion and contract
extensions that are checked by Go tests.

Last-Event-ID is defined only on `streamTaskEvents`. REST status/stage/decision
fields use canonical DEV-002 domain enums. Review creation returns 200 and
TaskLimits uses a candidate maximum of 10000.

`export_finished` treats `download_url` and `error_code` as mutually exclusive
by field presence; a value of `null` still means the field is present.

UpdateSite and UpdatePlugin are Session-only. Public bootstrap validates a
one-time token and uses `unauthorized/401` for invalid tokens; API Token scope
failures use `security_policy_rejected/403`.

## Export Finished Event Semantics (DEV-003 Owner Decision)

The project owner approved the following DEV-003 event contract choice for
`export_finished`: the event fires only when the export generation process ends.
Valid payload states are `SUCCEEDED` and `FAILED`. `EXPIRED`, `PENDING`, and
`RUNNING` are not valid event payload states. This is a DEV-003 contract decision
and is not claimed to be original frozen DOCX wording. ExportJob resources may
still return `EXPIRED`, and expired downloads use HTTP 410 `export_expired`.

`audit_log_id` remains an internal MySQL identity and is not exposed through the
public audit response DTO.

Go owns contract and schema validation. SSE payload validation uses Ajv with
JSON Schema 2020-12 and local schemas. No remote `$ref` is allowed.

## Generation

- Generator status: `DEFERRED_UNTIL_AUDITED_PATCHED_RELEASE`
- Generated types drift: `N/A_NO_COMMITTED_GENERATED_CONSUMER`
- No TypeScript generation is run in this BUILD
- Future generator input is the canonical local OpenAPI file only
- Future generated artifacts must be committed only when a real consumer exists

## Rollback

Revert the OpenAPI and schema files before implementing API handlers. Removing the
schema files does not change legacy runtime behavior.

## Security Consequences

The OpenAPI file does not implement authentication or authorization. Security
requirements are declarations for contract and client generation; runtime
enforcement remains an API implementation concern.
