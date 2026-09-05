-- DEV-004 B4 rollback for the 22-entity target data model.
-- Down executes only when target tables are empty and 0001 tables remain intact.
-- Session temporary guard only; no stored routines, markers, triggers, or events.

SET @dev004_b6_version_text = VERSION();
SET @dev004_b6_version_comment = @@version_comment;
SET @dev004_b6_version_body = SUBSTRING_INDEX(@dev004_b6_version_text, '-', 1);
SET @dev004_b6_major = CAST(SUBSTRING_INDEX(@dev004_b6_version_body, '.', 1) AS UNSIGNED);
SET @dev004_b6_minor = CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@dev004_b6_version_body, '.', 2), '.', -1) AS UNSIGNED);
SET @dev004_b6_patch = CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@dev004_b6_version_body, '.', 3), '.', -1) AS UNSIGNED);
SET @dev004_b6_is_mariadb = IF(LOWER(@dev004_b6_version_text) LIKE '%mariadb%' OR LOWER(@dev004_b6_version_comment) LIKE '%mariadb%', 1, 0);
SET @dev004_b6_supported = IF(@dev004_b6_major = 8 AND @dev004_b6_minor = 0 AND @dev004_b6_patch >= 16 AND @dev004_b6_is_mariadb = 0, 1, 0);

SET SESSION sql_mode = IF(
    FIND_IN_SET('STRICT_ALL_TABLES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'STRICT_ALL_TABLES')
);

DROP TEMPORARY TABLE IF EXISTS dev004_b6_down_strict_guard;
CREATE TEMPORARY TABLE dev004_b6_down_strict_guard (
    guard_value VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    UNIQUE KEY DEV004_B6_DOWN_FAIL_STRICT_MODE_NOT_ACTIVE (guard_value)
) ENGINE=InnoDB;
INSERT INTO dev004_b6_down_strict_guard (guard_value) VALUES ('__dev004_b6_strict_base__');
INSERT INTO dev004_b6_down_strict_guard (guard_value)
SELECT IF(FIND_IN_SET('STRICT_ALL_TABLES', @@SESSION.sql_mode) > 0, '__dev004_b6_strict_pass__', '__dev004_b6_strict_base__');
DROP TEMPORARY TABLE dev004_b6_down_strict_guard;

DROP TEMPORARY TABLE IF EXISTS dev004_b6_down_version_guard;
CREATE TEMPORARY TABLE dev004_b6_down_version_guard (
    guard_value VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    UNIQUE KEY DEV004_B6_DOWN_FAIL_UNSUPPORTED_MYSQL_VERSION (guard_value)
) ENGINE=InnoDB;
INSERT INTO dev004_b6_down_version_guard (guard_value) VALUES ('__dev004_b6_version_base__');
INSERT INTO dev004_b6_down_version_guard (guard_value)
SELECT IF(@dev004_b6_supported = 1, '__dev004_b6_version_pass__', '__dev004_b6_version_base__');
DROP TEMPORARY TABLE dev004_b6_down_version_guard;

DROP TEMPORARY TABLE IF EXISTS dev004_b4_down_guard;
CREATE TEMPORARY TABLE dev004_b4_down_guard (
    guard_ok CHAR(1) NOT NULL,
    DEV004_B4_DOWN_FAIL_UNSUPPORTED_TARGET INT NOT NULL,
    DEV004_B4_DOWN_FAIL_LEGACY_NOT_EMPTY INT NOT NULL,
    DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_UNSUPPORTED_TARGET)
SELECT 'X', NULL
FROM information_schema.tables
WHERE table_schema = DATABASE()
HAVING COUNT(*) <> 24
    OR COALESCE(SUM(table_name = 'articles'), 0) <> 1
    OR COALESCE(SUM(table_name = 'task_articles'), 0) <> 1
    OR COALESCE(SUM(table_name IN ('admin','api_token','article','article_version','audit_log','checkpoint','crawl_task','dead_letter','export_job','fetch_artifact','global_block_entry','idempotency_record','outbox_event','plugin','review_decision','search_candidate','session','site','task_article','task_attempt','task_event','task_stage')), 0) <> 22
    OR COALESCE(SUM(table_name NOT IN ('admin','api_token','article','article_version','articles','audit_log','checkpoint','crawl_task','dead_letter','export_job','fetch_artifact','global_block_entry','idempotency_record','outbox_event','plugin','review_decision','search_candidate','session','site','task_article','task_articles','task_attempt','task_event','task_stage')), 0) <> 0;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_UNSUPPORTED_TARGET)
SELECT 'X', NULL
FROM information_schema.columns
WHERE table_schema = DATABASE() AND extra LIKE '%auto_increment%'
HAVING COUNT(*) <> 3
    OR COALESCE(SUM(table_name = 'audit_log'), 0) <> 1
    OR COALESCE(SUM(table_name <> 'audit_log' AND table_name NOT IN ('articles','task_articles')), 0) <> 0;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_UNSUPPORTED_TARGET)
SELECT 'X', NULL
FROM (
    SELECT e.table_name
      FROM (
        SELECT 'admin' AS table_name, 'admin_id' AS column_name UNION ALL
        SELECT 'session', 'session_id' UNION ALL
        SELECT 'api_token', 'token_id' UNION ALL
        SELECT 'idempotency_record', 'idempotency_record_id' UNION ALL
        SELECT 'crawl_task', 'task_id' UNION ALL
        SELECT 'task_attempt', 'attempt_id' UNION ALL
        SELECT 'task_stage', 'stage_id' UNION ALL
        SELECT 'task_event', 'event_id' UNION ALL
        SELECT 'search_candidate', 'candidate_id' UNION ALL
        SELECT 'fetch_artifact', 'artifact_id' UNION ALL
        SELECT 'article', 'article_id' UNION ALL
        SELECT 'article_version', 'article_version_id' UNION ALL
        SELECT 'task_article', 'task_article_id' UNION ALL
        SELECT 'review_decision', 'decision_id' UNION ALL
        SELECT 'export_job', 'job_id' UNION ALL
        SELECT 'site', 'site_code' UNION ALL
        SELECT 'plugin', 'plugin_id' UNION ALL
        SELECT 'outbox_event', 'outbox_event_id' UNION ALL
        SELECT 'dead_letter', 'dead_letter_id' UNION ALL
        SELECT 'checkpoint', 'checkpoint_id' UNION ALL
        SELECT 'global_block_entry', 'block_entry_id'
      ) e
      LEFT JOIN information_schema.columns c
        ON c.table_schema = DATABASE()
       AND c.table_name = e.table_name
       AND c.column_name = e.column_name
       AND c.data_type = 'char'
       AND c.character_maximum_length = 26
       AND c.character_set_name = 'ascii'
       AND c.collation_name = 'ascii_bin'
       AND c.is_nullable = 'NO'
     WHERE c.column_name IS NULL
     LIMIT 1
) s;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_UNSUPPORTED_TARGET)
SELECT 'X', NULL
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'audit_log'
  AND column_name = 'audit_log_id' AND data_type = 'bigint' AND column_type = 'bigint unsigned'
  AND extra LIKE '%auto_increment%'
HAVING COUNT(*) <> 1;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_UNSUPPORTED_TARGET)
SELECT 'X', NULL
FROM (
    SELECT e.table_name
      FROM (
        SELECT 'admin' AS table_name, 7 AS expected UNION ALL
        SELECT 'session', 8 UNION ALL
        SELECT 'api_token', 9 UNION ALL
        SELECT 'idempotency_record', 12 UNION ALL
        SELECT 'site', 11 UNION ALL
        SELECT 'plugin', 9 UNION ALL
        SELECT 'crawl_task', 19 UNION ALL
        SELECT 'task_attempt', 9 UNION ALL
        SELECT 'task_stage', 11 UNION ALL
        SELECT 'task_event', 6 UNION ALL
        SELECT 'search_candidate', 9 UNION ALL
        SELECT 'article', 7 UNION ALL
        SELECT 'article_version', 8 UNION ALL
        SELECT 'fetch_artifact', 10 UNION ALL
        SELECT 'task_article', 15 UNION ALL
        SELECT 'review_decision', 11 UNION ALL
        SELECT 'export_job', 10 UNION ALL
        SELECT 'outbox_event', 12 UNION ALL
        SELECT 'audit_log', 10 UNION ALL
        SELECT 'dead_letter', 9 UNION ALL
        SELECT 'checkpoint', 9 UNION ALL
        SELECT 'global_block_entry', 14
      ) e
      LEFT JOIN (
        SELECT table_name, COUNT(*) AS actual
          FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name IN ('admin','session','api_token','idempotency_record','site','plugin','crawl_task','task_attempt','task_stage','task_event','search_candidate','article','article_version','fetch_artifact','task_article','review_decision','export_job','outbox_event','audit_log','dead_letter','checkpoint','global_block_entry')
         GROUP BY table_name
      ) a ON a.table_name = e.table_name
     WHERE a.actual IS NULL OR a.actual <> e.expected
     LIMIT 1
) s;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_LEGACY_NOT_EMPTY)
SELECT 'X', NULL FROM articles LIMIT 1;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_LEGACY_NOT_EMPTY)
SELECT 'X', NULL FROM task_articles LIMIT 1;

INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM admin LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM session LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM api_token LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM idempotency_record LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM crawl_task LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM task_attempt LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM task_stage LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM task_event LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM search_candidate LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM fetch_artifact LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM article LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM article_version LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM task_article LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM review_decision LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM export_job LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM site LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM plugin LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM outbox_event LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM audit_log LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM dead_letter LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM checkpoint LIMIT 1;
INSERT INTO dev004_b4_down_guard (guard_ok, DEV004_B4_DOWN_FAIL_TARGET_NOT_EMPTY)
SELECT 'X', NULL FROM global_block_entry LIMIT 1;

DROP TEMPORARY TABLE dev004_b4_down_guard;

DROP TABLE global_block_entry;
DROP TABLE checkpoint;
DROP TABLE dead_letter;
DROP TABLE audit_log;
DROP TABLE outbox_event;
DROP TABLE export_job;
DROP TABLE review_decision;
DROP TABLE task_article;
DROP TABLE article_version;
DROP TABLE article;
DROP TABLE fetch_artifact;
DROP TABLE search_candidate;
DROP TABLE task_event;
DROP TABLE task_stage;
DROP TABLE task_attempt;
DROP TABLE crawl_task;
DROP TABLE plugin;
DROP TABLE site;
DROP TABLE idempotency_record;
DROP TABLE api_token;
DROP TABLE session;
DROP TABLE admin;
