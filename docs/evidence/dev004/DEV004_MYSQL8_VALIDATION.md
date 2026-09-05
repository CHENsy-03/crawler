# DEV-004 MySQL 8 Validation

Date: 2026-09-05

Environment:

- MySQL version: 8.0.46 (local isolated Docker container, mysql:8.0 image)
- sql_mode: ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION
- Target databases: crawler_dev004_fresh_b2, crawler_dev004_legacy_b2, crawler_dev004_perf_b2
- Migration files:
  - migrations/mysql/0001_articles_task_articles_v2.sql
  - migrations/mysql/0002_v1_0_v1_1_22_entities.sql
  - migrations/mysql/0002_v1_0_v1_1_22_entities.down.sql

Migration SHA-256:

- 0002 up: 3CA22A8E40893C076F249430A866DB2F013646C68D1C0D8750A3A39C31357909
- 0002 down: 3C2BD3427E51611F06F20249E2A73EF983B645D907A34B01C901AF89DB3B44AE

B5 current migration SHA-256:

- 0002 up: E3D4F29B32E22F729C0BFA3D6D46CA241123A6D79698593E8461D219034028FD
- 0002 down: 10F19669E73CFC5F4BE8C6D8DA0741330C2EBD47127B238D92C654A3C1396ED6
- migrations/mysql/README.md: 8E10D726A39499C394B1C8B1D1C79D183D71E1A3F2E72B866B10EC1C1AB6A8AC

B6 current migration SHA-256:

- 0002 up: A8DD04A9D581875F77D612DAC4C87BFFE79BCCCBC97050659807C1D45F286834
- 0002 down: 4840BE6107AF1CB06D713A628FBB25D24E7F0646742DEC9193FE97BCD719B7B5
- migrations/mysql/README.md: 7EA519F4B77B24AAF52DC91F0F38F39019B0FB462A41D5EC35B65E4F689AA593

Historical B3/B4/B5 migration hashes refer only to those versions and must not be confused with the B6 final SQL.

This file records the B3, B4, and B5 validation history in one evidence document.

## Historical Scope Deviation (B4)

Fact: B4 executed against crawler_dev004_fresh_b4, crawler_dev004_legacy_b4, crawler_dev004_perf_b4, and crawler_dev004_guard_b4. crawler_dev004_guard_b4 was not in the B4 authorization list.

Disposition:

- Status: ACCEPTED_HISTORICAL_SCOPE_DEVIATION_NON_PRECEDENTIAL
- The deviation is not rewritten as authorized.
- The database contained only isolated synthetic test data and was cleaned.
- The technical validation results are not overturned.
- Later tasks may not use this as a basis to expand database scope.
- B5 and R4 may only use their own explicitly listed three databases.

## Fresh Forward

1. Created crawler_dev004_fresh_b2.
2. Executed 0001; articles and task_articles were empty.
3. Executed 0002 up; exit code 0.
4. Result: 24 tables present, 22 target tables plus legacy 0001 articles/task_articles.
5. All 21 non-audit primary keys are CHAR(26) CHARACTER SET ascii COLLATE ascii_bin.
6. AuditLog.audit_log_id is BIGINT UNSIGNED NOT NULL AUTO_INCREMENT.
7. All declared FKs were created without errno 3780; child task_id columns use CHAR(26) ascii ascii_bin and reference crawl_task.task_id.

Foreign key task compatibility:

- task_attempt.task_id -> crawl_task.task_id
- task_stage.task_id -> crawl_task.task_id
- task_event.task_id -> crawl_task.task_id
- search_candidate.task_id -> crawl_task.task_id
- task_article.task_id -> crawl_task.task_id
- checkpoint.task_id -> crawl_task.task_id

## Fresh Rollback

1. Inserted one admin sentinel row.
2. Executed 0002 down; exit code 1, error DEV004_B3_DOWN_FAIL_TARGET_NOT_EMPTY.
3. Confirmed target tables and sentinel remained unchanged.
4. Deleted the sentinel.
5. Executed 0002 down; exit code 0.
6. Result: exactly articles and task_articles remain, both empty, with 0001 structure intact.

Fresh 0001 structure fingerprint before and after full up/down cycle:

- articles before: 15E853703E3924D5AAB96456E339E4491B4B39D78783E8862A0D4D7F4E72766F
- task_articles before: A99E28BCA8A2AAAFED6691819F1610EA14C57218C3001619D56809BB52CF0FDF
- articles after: 15E853703E3924D5AAB96456E339E4491B4B39D78783E8862A0D4D7F4E72766F
- task_articles after: A99E28BCA8A2AAAFED6691819F1610EA14C57218C3001619D56809BB52CF0FDF

## Legacy Fail-Closed

Config/schema.sql representative legacy state:

- Tables: article, task, crawl_log, articles, task_articles.
- Sentinel rows: 1 article, 1 articles, 1 task_articles.
- article content SHA-256: c7a054597f6be783f07ab3d804a4030c40b47cb8c58b85214619e5b823bd0f18
- articles content SHA-256: 97210d4671487662adb55ac0370f1547fca7a8c92466094dd3dea7cfd074b5ab

0002 up result: exit code 1, DEV004_B3_UP_FAIL_UNSUPPORTED_TABLE_STATE, before permanent DDL.

After failure: row counts and both content SHA-256 values unchanged; no target 22 table created.

AutoMigrate singular article shape:

- Tables: article, task, crawl_log.
- One article sentinel with content SHA-256 d8f35ecd0783254ffcf725da0a1b5c58451b10367d50b425fabb7c625544ced7.

0002 up result: exit code 1, DEV004_B3_UP_FAIL_UNSUPPORTED_TABLE_STATE; no DDL changes.

## 100k/200k Explain

crawler_dev004_perf_b2 data:

- article rows: 100000
- task_article rows: 200000
- review_state distribution: NONE 66666, PENDING_REVIEW 66667, REVIEWED 66667
- result_status distribution: accepted 40000, review_required 40000, irrelevant 40000, extract_failed 40000, unsupported_format 40000

Queries all used the intended narrow indexes and no large JSON/content join:

1. Default list: idx_task_article_task_persisted, no filesort, actual 20 rows.
2. Relevance sort: idx_task_article_task_relevance, covering index, actual 20 rows.
3. Review state filter: idx_task_article_task_review, covering index, actual 20 rows.
4. Result status filter: idx_task_article_task_status, covering index, actual 20 rows.
5. Keyset/deep pagination: idx_task_article_task_persisted covering range scan, actual 20 rows.
6. Article detail read: PRIMARY const lookup, actual 1 row.

### Full Explain SQL

Q1 default list, expected `idx_task_article_task_persisted`:

```sql
SELECT task_article_id, persisted_at, result_status
FROM task_article
WHERE task_id = ?
ORDER BY persisted_at DESC, task_article_id DESC
LIMIT 20;
```

Parameter types: task_id CHAR(26) ascii_bin.

Q2 relevance sort, expected `idx_task_article_task_relevance`:

```sql
SELECT task_article_id, relevance_score
FROM task_article
WHERE task_id = ?
ORDER BY relevance_score DESC, task_article_id DESC
LIMIT 20;
```

Q3 review state filter, expected `idx_task_article_task_review`:

```sql
SELECT task_article_id, review_state, persisted_at
FROM task_article
WHERE task_id = ? AND review_state = ?
ORDER BY persisted_at DESC, task_article_id DESC
LIMIT 20;
```

Parameter types: task_id CHAR(26) ascii_bin, review_state VARCHAR(32).

Q4 result status filter, expected `idx_task_article_task_status`:

```sql
SELECT task_article_id, result_status, persisted_at
FROM task_article
WHERE task_id = ? AND result_status = ?
ORDER BY persisted_at DESC, task_article_id DESC
LIMIT 20;
```

Parameter types: task_id CHAR(26) ascii_bin, result_status VARCHAR(32).

Q5 keyset/deep pagination, expected `idx_task_article_task_persisted`:

```sql
SELECT task_article_id, persisted_at
FROM task_article
WHERE task_id = ?
  AND persisted_at <= ?
  AND (
    persisted_at < ?
    OR (
      persisted_at = ?
      AND task_article_id < ?
    )
  )
ORDER BY persisted_at DESC, task_article_id DESC
LIMIT 20;
```

Parameter types: task_id CHAR(26) ascii_bin, persisted_at DATETIME(6) bounds, task_article_id CHAR(26) ascii_bin cursor.

Q6 article detail read, expected PRIMARY:

```sql
SELECT article_id, identity_url
FROM article
WHERE article_id = ?
```

Parameter type: article_id CHAR(26) ascii_bin.

## DEV-004 B4 Revalidation

MySQL version: 8.0.46. Databases used: crawler_dev004_fresh_b4, crawler_dev004_legacy_b4, crawler_dev004_perf_b4, crawler_dev004_guard_b4. crawler_dev004_guard_b4 is marked UNAUTHORIZED_AT_EXECUTION and is not presented as authorized.

Guard implementation: session TEMPORARY TABLE only. Migration files contain no CREATE PROCEDURE, DROP PROCEDURE, CALL, DELIMITER, GROUP_CONCAT, SIGNAL, trigger, event, or permanent guard table.

State matrix:

- A empty database up: exit 1, error Column DEV004_B4_UP_FAIL_UNSUPPORTED_PREDECESSOR cannot be null; no raw 1146; 0 target tables; 0 routines/triggers/events/guard tables.
- B exact empty 0001 up: exit 0; 24 tables; six task_id FKs use CHAR(26) ascii ascii_bin; no residual guard.
- C 0001 non-empty up: exit 1, error DEV004_B4_UP_FAIL_LEGACY_NOT_EMPTY; sentinel content hash unchanged; no target tables.
- D config/schema.sql empty up: exit 1 unsupported predecessor; no target tables. With sentinel: exit 1; article content hash c7a054597f6be783f07ab3d804a4030c40b47cb8c58b85214619e5b823bd0f18 unchanged.
- E AutoMigrate singular up: exit 1 unsupported predecessor; article content hash d8f35ecd0783254ffcf725da0a1b5c58451b10367d50b425fabb7c625544ced7 unchanged.
- F partial target up: exit 1 unsupported predecessor; partial admin remains; no extra target table or guard.
- G down with target data: exit 1 target-not-empty; structure and data unchanged. After cleanup down: exit 0; exactly articles/task_articles remain with unchanged fingerprints. Down on pure 0001, legacy singular, and partial target: exit 1 unsupported target.
- H retry: after a failed guard on one connection, a new connection with corrected exact 0001 state completed up with exit 0; no temporary guard residual.
- I performance: 100000 Article and 200000 TaskArticle; six EXPLAIN ANALYZE queries all used intended narrow indexes.

## DEV-004 B5 Revalidation

MySQL version: 8.0.46. B5 created exactly crawler_dev004_fresh_b5, crawler_dev004_legacy_b5, and crawler_dev004_perf_b5. No fourth database was created.

Version and strict-mode capability:

- VERSION() returned 8.0.46
- Migration version guard passed for 8.0.46
- Initial SESSION sql_mode was set to empty for validation
- Migration enabled STRICT_ALL_TABLES before guard creation
- @@SESSION.sql_mode after migration: STRICT_ALL_TABLES
- No SET GLOBAL sql_mode and no server configuration change
- information_schema.check_constraints contains chk_global_block_match_type, chk_global_block_reason_code, chk_global_block_status, chk_global_block_legal_evidence
- Invalid match_type insert was rejected: Check constraint chk_global_block_match_type is violated
- LEGAL_REQUEST with null evidence was rejected: Check constraint chk_global_block_legal_evidence is violated

State results:

- Empty database under empty SESSION sql_mode: up exit 1 with unsupported predecessor; no DDL or persistent objects
- Exact empty 0001 under empty SESSION sql_mode: up exit 0; 24 tables; no residual guard
- 0001 non-empty under empty SESSION sql_mode: up exit 1 legacy-not-empty; sentinel and content hash unchanged
- Legacy singular under empty SESSION sql_mode: up exit 1 unsupported predecessor; down exit 1 unsupported target
- Retry on new connection after state correction: up exit 0
- 100000 Article and 200000 TaskArticle: six EXPLAIN ANALYZE queries used expected narrow indexes
- Cleanup removed exactly the three B5 databases plus the task-created container and volume

## DEV-004 B6 Revalidation

R4 P1: the previous version guard used CHECK(version_ok=1). MySQL 8.0.0 through 8.0.15 parse but do not enforce CHECK constraints, so 8.0.15 could bypass the version gate and reach permanent DDL.

B6 mechanism:

- Preflight strict and version guards are session TEMPORARY TABLE with named UNIQUE KEY.
- A base value is inserted first.
- A condition-pass value is inserted when the predicate is true.
- When the predicate is false, the base value is inserted again and a named duplicate-key collision fails.
- Preflight guards contain no CHECK and do not depend on sql_mode NULL coercion.
- MariaDB is excluded from both VERSION() and @@version_comment using case-insensitive checks.
- Supported predicate: major=8, minor=0, patch>=16, no MariaDB marker.

False-branch duplicate-key results on MySQL 8.0.46:

- Strict false simulation: ERROR 1062 Duplicate entry '__dev004_b6_strict_base__' for key 'dev004_b6_false_strict.DEV004_B6_UP_FAIL_STRICT_MODE_NOT_ACTIVE'; exit 1
- Version false simulation: ERROR 1062 Duplicate entry '__dev004_b6_version_base__' for key 'dev004_b6_false_version.DEV004_B6_UP_FAIL_UNSUPPORTED_MYSQL_VERSION'; exit 1

Version sample status:

- 8.0.15: rejected by predicate; MYSQL_8_0_15_RUNTIME_NOT_EXECUTED because no local 8.0.15 image was available and network pull was prohibited
- 8.0.16: allowed by predicate
- 8.0.46: allowed and runtime-validated
- 8.0.46-commercial and common suffixes: allowed by body parsing before '-'
- 8.4.x: rejected by predicate
- 9.x: rejected by predicate
- 10.11.x-MariaDB: rejected
- 5.5.5-10.x-MariaDB: rejected
- Numeric 8.0.x disguised with MariaDB marker in VERSION or @@version_comment: rejected by dual-source MariaDB check

Non-circularity proof:

- B6 strict/version guard failure does not use CHECK enforcement.
- It uses only temporary table DDL and duplicate-key enforcement, which exists independently of CHECK and sql_mode.
- The same temporary UNIQUE collision structure was executed on MySQL 8.0.46 with false condition and failed with ERROR 1062.

MySQL 8.0.46 state matrix:

- Empty database non-strict up: exit 1, unsupported predecessor, no persistent objects
- Exact empty 0001 non-strict up: exit 0, 24 tables, strict active
- Initial custom mode NO_ENGINE_SUBSTITUTION,NO_ZERO_DATE: preserved and STRICT_ALL_TABLES appended
- 0001 non-empty up: exit 1, content SHA unchanged
- config/schema.sql legacy up: exit 1 unsupported predecessor
- AutoMigrate singular up/down: exit 1
- Partial target up/down: exit 1
- Target non-empty down: exit 1 target-not-empty
- Cleaned down: exit 0; 0001 fingerprints unchanged
- Pure 0001 down: exit 1 unsupported target
- Retry after guard failure on new connection: up exit 0
- GlobalBlockEntry CHECK constraints exist and invalid match_type plus LEGAL_REQUEST missing evidence are rejected
- 100000 Article and 200000 TaskArticle: six EXPLAIN ANALYZE queries used expected narrow indexes
- Cleanup removed exactly crawler_dev004_fresh_b6, crawler_dev004_legacy_b6, crawler_dev004_perf_b6 and the task container/volume

## Cleanup

- B4 cleanup removed all four databases that were actually used, including crawler_dev004_guard_b4.
- B5 cleanup removes exactly crawler_dev004_fresh_b5, crawler_dev004_legacy_b5, and crawler_dev004_perf_b5; B5 does not create a fourth database.
- No password, connection string, or large test data is retained.
