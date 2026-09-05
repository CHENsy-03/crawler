# MySQL Migration Execution Contract

Target MySQL:

- minimum_supported_mysql=8.0.16
- certified_mysql=8.0.46
- production_mysql=PINNED_TO_CERTIFIED_VERSION
- Family: Oracle MySQL 8.0 only
- MySQL 8.4, MySQL 9.x, and MariaDB are not supported by this contract
- CHECK constraints are enforced starting from 8.0.16 and must be real, not text-only

## Execution Order

- Migrations run strictly in order: 0001, then 0002.
- Each migration file uses one fresh connection.
- All statements in one migration file run on the same connection.
- After success or failure, the connection is closed and discarded.
- Execution contract: stop on first error; no --force; close/discard on failure.
- A failed connection is never returned to a connection pool.

## Error Semantics

- Stop on the first SQL error (stop on first error).
- Do not use mysql --force (no --force).
- Do not continue remaining DDL after a failure.
- Temporary guard tables are cleaned automatically when the connection closes.
- MySQL DDL is not transactional (non-transactional).
- A failure during the permanent DDL phase may leave a partial state.
- Partial-state handling is required before any retry.
- Partial state must be investigated and corrected by a dedicated recovery process or an authorized operator; do not blindly rerun.

## Retry

- Before retry, open a new connection.
- Re-run the full preflight on the new connection.
- Never assume that temporary guard objects from a previous connection remain or should be reused.

## Current Guard Behavior

- 0002 uses a session TEMPORARY TABLE guard only.
- It creates no stored procedure, trigger, event, permanent guard table, or marker.
- Up rejects unsupported predecessor state, structure mismatch, and non-empty legacy rows.
- Down rejects unsupported target state, non-empty legacy rows, and non-empty target rows.
- On success the temporary guard is dropped before the first permanent DDL or DROP.

## SQL Version and Strict Mode Preflight

- Each migration first parses VERSION() into major, minor, and patch.
- Preflight strict/version guards use session TEMPORARY TABLE named UNIQUE KEY collision; they do not use CHECK or sql_mode-dependent NULL coercion.
- Unsupported version fails with a version guard error before any business query or permanent DDL.
- Each migration enables STRICT_ALL_TABLES for its own session while preserving other session modes.
- The migration verifies STRICT_ALL_TABLES is active before creating the NOT NULL guard.
- Migration SQL does not change GLOBAL sql_mode and does not change server configuration.
- The runner must allow SET SESSION sql_mode.
- The runner still must not use --force.
- The strict-mode requirement for formal business connections is a production configuration task, not implemented here.

## CLI Reference (no secrets)

Example:

```text
mysql --default-character-set=utf8mb4 -h <host> -P <port> -u <user> -p <database> < migrations/mysql/0001_articles_task_articles_v2.sql
mysql --default-character-set=utf8mb4 -h <host> -P <port> -u <user> -p <database> < migrations/mysql/0002_v1_0_v1_1_22_entities.sql
mysql --default-character-set=utf8mb4 -h <host> -P <port> -u <user> -p <database> < migrations/mysql/0002_v1_0_v1_1_22_entities.down.sql
```

Never pass --force. Never use the same connection to run the next migration after a failure.

## Status

- production_loader=NOT_STARTED.
- Production MySQL is pinned to certified 8.0.46 until another patch version passes independent compatibility validation.
- This document is a contract for DEV-101 or the future formal migration job.
- No schema migration is described as transactional.
