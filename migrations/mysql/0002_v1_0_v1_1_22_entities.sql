-- DEV-004 B4: V1.0 + V1.1 22-entity target data model (MySQL 8.0+)
-- Scope: schema migration only; non-empty legacy data is rejected before DDL.
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

DROP TEMPORARY TABLE IF EXISTS dev004_b6_up_strict_guard;
CREATE TEMPORARY TABLE dev004_b6_up_strict_guard (
    guard_value VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    UNIQUE KEY DEV004_B6_UP_FAIL_STRICT_MODE_NOT_ACTIVE (guard_value)
) ENGINE=InnoDB;
INSERT INTO dev004_b6_up_strict_guard (guard_value) VALUES ('__dev004_b6_strict_base__');
INSERT INTO dev004_b6_up_strict_guard (guard_value)
SELECT IF(FIND_IN_SET('STRICT_ALL_TABLES', @@SESSION.sql_mode) > 0, '__dev004_b6_strict_pass__', '__dev004_b6_strict_base__');
DROP TEMPORARY TABLE dev004_b6_up_strict_guard;

DROP TEMPORARY TABLE IF EXISTS dev004_b6_up_version_guard;
CREATE TEMPORARY TABLE dev004_b6_up_version_guard (
    guard_value VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    UNIQUE KEY DEV004_B6_UP_FAIL_UNSUPPORTED_MYSQL_VERSION (guard_value)
) ENGINE=InnoDB;
INSERT INTO dev004_b6_up_version_guard (guard_value) VALUES ('__dev004_b6_version_base__');
INSERT INTO dev004_b6_up_version_guard (guard_value)
SELECT IF(@dev004_b6_supported = 1, '__dev004_b6_version_pass__', '__dev004_b6_version_base__');
DROP TEMPORARY TABLE dev004_b6_up_version_guard;

DROP TEMPORARY TABLE IF EXISTS dev004_b4_up_guard;
CREATE TEMPORARY TABLE dev004_b4_up_guard (
    guard_ok CHAR(1) NOT NULL,
    DEV004_B4_UP_FAIL_UNSUPPORTED_PREDECESSOR INT NOT NULL,
    DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH INT NOT NULL,
    DEV004_B4_UP_FAIL_LEGACY_NOT_EMPTY INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_UNSUPPORTED_PREDECESSOR)
SELECT 'X', NULL
FROM information_schema.tables
WHERE table_schema = DATABASE()
HAVING COUNT(*) <> 2
    OR COALESCE(SUM(table_name = 'articles'), 0) <> 1
    OR COALESCE(SUM(table_name = 'task_articles'), 0) <> 1
    OR COALESCE(SUM(table_name NOT IN ('articles', 'task_articles')), 0) <> 0;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH)
SELECT 'X', NULL
FROM (
    SELECT COUNT(*) AS actual, COALESCE(SUM(column_name IN ('id','article_key','identity_url','identity_url_hash','canonical_url','final_url','title','publish_date','source','summary','content','content_hash','extraction_method','first_seen_at','last_seen_at')), 0) AS matches
      FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = 'articles'
) s
WHERE s.actual <> 15 OR s.matches <> 15;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH)
SELECT 'X', NULL
FROM (
    SELECT COUNT(*) AS actual, COALESCE(SUM(column_name IN ('id','protocol_version','task_id','hit_id','plan_id','article_id','result_hash','result_message_id','result_timestamp','original_query','query_term','requested_url','final_url','canonical_url','title','publish_date','source','summary','content_hash','score','matched_evidence','status','extraction_method','created_at')), 0) AS matches
      FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = 'task_articles'
) s
WHERE s.actual <> 24 OR s.matches <> 24;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH)
SELECT 'X', NULL
FROM (
    SELECT COUNT(DISTINCT index_name) AS idx_count
      FROM information_schema.statistics
     WHERE table_schema = DATABASE() AND table_name = 'articles'
       AND index_name IN ('PRIMARY','uq_articles_article_key','idx_articles_identity_url_hash','idx_articles_content_hash','idx_articles_publish_date')
) s
WHERE s.idx_count <> 5;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH)
SELECT 'X', NULL
FROM (
    SELECT COUNT(DISTINCT index_name) AS idx_count
      FROM information_schema.statistics
     WHERE table_schema = DATABASE() AND table_name = 'task_articles'
       AND index_name IN ('PRIMARY','uq_task_articles_task_hit','idx_task_articles_task_status','idx_task_articles_article_id','idx_task_articles_plan_id','idx_task_articles_content_hash')
) s
WHERE s.idx_count <> 6;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH)
SELECT 'X', NULL
FROM (
    SELECT COUNT(*) AS fk_count
      FROM information_schema.key_column_usage
     WHERE table_schema = DATABASE()
       AND constraint_name = 'fk_task_articles_article'
       AND table_name = 'task_articles'
       AND referenced_table_name = 'articles'
) s
WHERE s.fk_count <> 1;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_LEGACY_NOT_EMPTY)
SELECT 'X', NULL FROM articles LIMIT 1;

INSERT INTO dev004_b4_up_guard (guard_ok, DEV004_B4_UP_FAIL_LEGACY_NOT_EMPTY)
SELECT 'X', NULL FROM task_articles LIMIT 1;

DROP TEMPORARY TABLE dev004_b4_up_guard;

CREATE TABLE admin (
    admin_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    username VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    bootstrap_state VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (admin_id),
    UNIQUE KEY uq_admin_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE session (
    session_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    admin_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    csrf_token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idle_expires_at DATETIME(6) NOT NULL,
    absolute_expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (session_id),
    UNIQUE KEY uq_session_token_hash (token_hash),
    KEY idx_session_admin_id (admin_id),
    KEY idx_session_absolute_expires (absolute_expires_at),
    CONSTRAINT fk_session_admin FOREIGN KEY (admin_id) REFERENCES admin (admin_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE api_token (
    token_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    admin_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    name VARCHAR(128) NOT NULL,
    token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    scopes JSON NOT NULL,
    expires_at DATETIME(6) NULL,
    rotated_from CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (token_id),
    UNIQUE KEY uq_api_token_hash (token_hash),
    KEY idx_api_token_admin_id (admin_id),
    KEY idx_api_token_expires_at (expires_at),
    CONSTRAINT fk_api_token_admin FOREIGN KEY (admin_id) REFERENCES admin (admin_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_api_token_rotated_from FOREIGN KEY (rotated_from) REFERENCES api_token (token_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE idempotency_record (
    idempotency_record_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_id VARCHAR(128) NOT NULL,
    method VARCHAR(16) NOT NULL,
    path VARCHAR(255) NOT NULL,
    idempotency_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(32) NOT NULL,
    resource_id VARCHAR(128) NULL,
    response_ref VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NOT NULL,
    PRIMARY KEY (idempotency_record_id),
    UNIQUE KEY uq_idempotency_record (actor_type, actor_id, method, path, idempotency_key),
    KEY idx_idempotency_record_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE site (
    site_code CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    site_version INT UNSIGNED NOT NULL DEFAULT 1,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,
    capabilities JSON NOT NULL,
    plugin_policy JSON NOT NULL,
    security_policy_id VARCHAR(128) NOT NULL,
    authorization_basis TEXT NULL,
    robots_handling VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (site_code),
    KEY idx_site_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE plugin (
    plugin_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    plugin_key VARCHAR(128) NOT NULL,
    plugin_version VARCHAR(32) NOT NULL,
    plugin_type VARCHAR(32) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    schema_version VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    registered_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_audited_at DATETIME(6) NULL,
    PRIMARY KEY (plugin_id),
    UNIQUE KEY uq_plugin_key_version (plugin_key, plugin_version),
    KEY idx_plugin_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE crawl_task (
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    site_code CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    site_version INT UNSIGNED NOT NULL,
    keywords JSON NOT NULL,
    mode VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    progress INT UNSIGNED NOT NULL DEFAULT 0,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    limit_snapshot JSON NOT NULL,
    policy_id VARCHAR(128) NOT NULL,
    search_plan_id VARCHAR(128) NULL,
    outcome VARCHAR(32) NULL,
    retry_of_task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    confirmed_at DATETIME(6) NULL,
    started_at DATETIME(6) NULL,
    ended_at DATETIME(6) NULL,
    timed_out_at DATETIME(6) NULL,
    PRIMARY KEY (task_id),
    KEY idx_crawl_task_status_created (status, created_at),
    KEY idx_crawl_task_site (site_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE task_attempt (
    attempt_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    attempt_no INT UNSIGNED NOT NULL,
    status VARCHAR(32) NOT NULL,
    lease_token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    heartbeat_expires_at DATETIME(6) NOT NULL,
    checkpoint_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    started_at DATETIME(6) NULL,
    ended_at DATETIME(6) NULL,
    PRIMARY KEY (attempt_id),
    UNIQUE KEY uq_task_attempt_task_no (task_id, attempt_no),
    KEY idx_task_attempt_heartbeat (heartbeat_expires_at),
    KEY idx_task_attempt_checkpoint (checkpoint_id),
    CONSTRAINT fk_task_attempt_task FOREIGN KEY (task_id) REFERENCES crawl_task (task_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE task_stage (
    stage_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    stage VARCHAR(32) NOT NULL,
    attempt_no INT UNSIGNED NOT NULL,
    status VARCHAR(32) NOT NULL,
    expected INT UNSIGNED NOT NULL DEFAULT 0,
    processed INT UNSIGNED NOT NULL DEFAULT 0,
    succeeded INT UNSIGNED NOT NULL DEFAULT 0,
    failed INT UNSIGNED NOT NULL DEFAULT 0,
    started_at DATETIME(6) NULL,
    ended_at DATETIME(6) NULL,
    PRIMARY KEY (stage_id),
    UNIQUE KEY uq_task_stage_attempt (task_id, stage, attempt_no),
    CONSTRAINT fk_task_stage_task FOREIGN KEY (task_id) REFERENCES crawl_task (task_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE task_event (
    event_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    event_version VARCHAR(16) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_task_event_task_event (task_id, event_id),
    KEY idx_task_event_created (created_at),
    CONSTRAINT fk_task_event_task FOREIGN KEY (task_id) REFERENCES crawl_task (task_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE search_candidate (
    candidate_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    discovery_source VARCHAR(64) NOT NULL,
    normalized_url VARCHAR(2048) NOT NULL,
    normalized_url_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    confidence INT UNSIGNED NOT NULL DEFAULT 0,
    evidence JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (candidate_id),
    UNIQUE KEY uq_search_candidate_task_url (task_id, normalized_url_hash),
    KEY idx_search_candidate_task_status (task_id, status),
    CONSTRAINT fk_search_candidate_task FOREIGN KEY (task_id) REFERENCES crawl_task (task_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE article (
    article_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    article_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    identity_url VARCHAR(2048) NOT NULL,
    identity_url_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    canonical_url VARCHAR(2048) NULL,
    latest_version_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (article_id),
    UNIQUE KEY uq_article_article_key (article_key),
    UNIQUE KEY uq_article_identity_hash (identity_url_hash),
    KEY idx_article_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE article_version (
    article_version_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    article_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    version_no INT UNSIGNED NOT NULL,
    content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    content_storage_ref VARCHAR(512) NOT NULL,
    raw_evidence_ref VARCHAR(512) NULL,
    extraction_info JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (article_version_id),
    UNIQUE KEY uq_article_version_content (article_id, content_hash),
    UNIQUE KEY uq_article_version_no (article_id, version_no),
    CONSTRAINT fk_article_version_article FOREIGN KEY (article_id) REFERENCES article (article_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE fetch_artifact (
    artifact_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    candidate_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    storage_key VARCHAR(512) NOT NULL,
    content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    byte_size BIGINT UNSIGNED NOT NULL,
    retention_class VARCHAR(32) NOT NULL,
    hold_status VARCHAR(32) NOT NULL DEFAULT 'NONE',
    checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    fetched_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (artifact_id),
    UNIQUE KEY uq_fetch_artifact_storage_key (storage_key),
    KEY idx_fetch_artifact_candidate (candidate_id),
    KEY idx_fetch_artifact_retention (retention_class, hold_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE task_article (
    task_article_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    hit_id VARCHAR(128) NOT NULL,
    candidate_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    article_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    article_version_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    original_query VARCHAR(500) NOT NULL,
    query_term VARCHAR(500) NOT NULL,
    relevance_score INT UNSIGNED NOT NULL DEFAULT 0,
    quality_score INT UNSIGNED NOT NULL DEFAULT 0,
    review_state VARCHAR(32) NOT NULL DEFAULT 'NONE',
    result_status VARCHAR(32) NOT NULL,
    persisted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    matched_evidence JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (task_article_id),
    UNIQUE KEY uq_task_article_task_hit (task_id, hit_id),
    KEY idx_task_article_task_persisted (task_id, persisted_at DESC, task_article_id DESC),
    KEY idx_task_article_task_relevance (task_id, relevance_score DESC, task_article_id DESC),
    KEY idx_task_article_task_review (task_id, review_state, persisted_at DESC, task_article_id DESC),
    KEY idx_task_article_task_status (task_id, result_status, persisted_at DESC, task_article_id DESC),
    KEY idx_task_article_article_version (article_version_id),
    CONSTRAINT fk_task_article_task FOREIGN KEY (task_id) REFERENCES crawl_task (task_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_task_article_article FOREIGN KEY (article_id) REFERENCES article (article_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE review_decision (
    decision_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_article_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    article_version_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    admin_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    decision VARCHAR(32) NOT NULL,
    comment TEXT NULL,
    hold_artifact_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    hold_artifact_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    evidence_schema_version VARCHAR(32) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (decision_id),
    UNIQUE KEY uq_review_decision_append (task_article_id, article_version_id, admin_id, created_at),
    KEY idx_review_decision_hold_artifact (hold_artifact_id),
    KEY idx_review_decision_admin (admin_id),
    CONSTRAINT fk_review_decision_hold_artifact FOREIGN KEY (hold_artifact_id) REFERENCES fetch_artifact (artifact_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_review_decision_admin FOREIGN KEY (admin_id) REFERENCES admin (admin_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE export_job (
    job_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NULL,
    format VARCHAR(16) NOT NULL,
    status VARCHAR(32) NOT NULL,
    filter_snapshot JSON NOT NULL,
    file_storage_key VARCHAR(512) NULL,
    manifest JSON NULL,
    expires_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    finished_at DATETIME(6) NULL,
    PRIMARY KEY (job_id),
    KEY idx_export_job_status_created (status, created_at),
    KEY idx_export_job_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE outbox_event (
    outbox_event_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    event_version VARCHAR(16) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME(6) NOT NULL,
    dispatched_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (outbox_event_id),
    UNIQUE KEY uq_outbox_aggregate_event (aggregate_type, aggregate_id, event_key),
    KEY idx_outbox_status_next_attempt (status, next_attempt_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE audit_log (
    audit_log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    actor_type VARCHAR(32) NOT NULL,
    actor_id VARCHAR(128) NULL,
    action VARCHAR(128) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128) NULL,
    before_json JSON NULL,
    after_json JSON NULL,
    request_id VARCHAR(128) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (audit_log_id),
    KEY idx_audit_log_created (created_at),
    KEY idx_audit_log_actor (actor_type, actor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE dead_letter (
    dead_letter_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    stream VARCHAR(128) NOT NULL,
    message_id VARCHAR(128) NOT NULL,
    payload_ref VARCHAR(512) NULL,
    error_code VARCHAR(128) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    replay_count INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (dead_letter_id),
    UNIQUE KEY uq_dead_letter_stream_message (stream, message_id),
    KEY idx_dead_letter_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE checkpoint (
    checkpoint_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    task_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    checkpoint_key VARCHAR(128) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    schema_version VARCHAR(32) NOT NULL,
    state_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (checkpoint_id),
    UNIQUE KEY uq_checkpoint_task_key (task_id, checkpoint_key),
    CONSTRAINT fk_checkpoint_task FOREIGN KEY (task_id) REFERENCES crawl_task (task_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE global_block_entry (
    block_entry_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    match_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    pattern_normalized VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    reason_code VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    reason_summary VARCHAR(255) NOT NULL,
    evidence_ref VARCHAR(512) NULL,
    effective_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NULL,
    created_by CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    active_pattern_key VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin GENERATED ALWAYS AS (CASE WHEN status = 'ACTIVE' THEN pattern_normalized ELSE NULL END) STORED,
    PRIMARY KEY (block_entry_id),
    UNIQUE KEY uq_global_block_active_pattern (match_type, active_pattern_key),
    KEY idx_global_block_status_effective (status, effective_at),
    KEY idx_global_block_match_pattern (match_type, pattern_normalized),
    CONSTRAINT fk_global_block_creator FOREIGN KEY (created_by) REFERENCES admin (admin_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT chk_global_block_match_type CHECK (match_type IN ('EXACT_HOST', 'DOMAIN_SUFFIX', 'IP_CIDR', 'URL_PREFIX')),
    CONSTRAINT chk_global_block_reason_code CHECK (reason_code IN ('LEGAL_REQUEST', 'ROBOTS_DENY', 'OWNER_REQUEST', 'SECURITY_INCIDENT', 'POLICY')),
    CONSTRAINT chk_global_block_status CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    CONSTRAINT chk_global_block_legal_evidence CHECK (reason_code <> 'LEGAL_REQUEST' OR evidence_ref IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
