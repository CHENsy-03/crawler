-- Crawler Database Schema (MySQL 8.0+)

CREATE DATABASE IF NOT EXISTS crawler_db
    DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE crawler_db;

CREATE TABLE IF NOT EXISTS article (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    url              VARCHAR(1000) NOT NULL,
    title            VARCHAR(500),
    summary          TEXT,
    content          LONGTEXT,
    publish_time     DATETIME,
    province         VARCHAR(100),
    site             VARCHAR(200),
    keyword          VARCHAR(200),
    score            INT DEFAULT 0,
    matched_keywords VARCHAR(500),
    crawl_time       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    detail_fetched   TINYINT(1) DEFAULT 0,
    source_type      VARCHAR(50),
    status           VARCHAR(20) DEFAULT 'new',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_url_hash (MD5(url)),
    INDEX idx_site (site),
    INDEX idx_keyword (keyword),
    INDEX idx_publish_time (publish_time),
    INDEX idx_score (score),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS task (
    id          VARCHAR(32) PRIMARY KEY,
    keyword     VARCHAR(200),
    site        VARCHAR(100),
    status      VARCHAR(32) DEFAULT 'created',
    article_count INT DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS crawl_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    url         VARCHAR(1000) NOT NULL,
    status      SMALLINT NOT NULL,
    cost_ms     INT DEFAULT 0,
    error       TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_url (url(255)),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- TASK-019B-5 v2 tables: articles / task_articles (MySQL 8.0+)
-- These tables are NOT auto-migrated by the current Go store and are NOT yet
-- connected to a production consumer.
-- ============================================================================

CREATE TABLE IF NOT EXISTS articles (
    id                 BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    article_key        CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    identity_url       VARCHAR(2048) NOT NULL,
    identity_url_hash  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    canonical_url      VARCHAR(2048) NOT NULL,
    final_url          VARCHAR(2048) NOT NULL,
    title              VARCHAR(500) NOT NULL,
    publish_date       DATE NULL,
    source             VARCHAR(500) NOT NULL,
    summary            TEXT NOT NULL,
    content            LONGTEXT NOT NULL,
    content_hash       CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    extraction_method  VARCHAR(32) NOT NULL,
    first_seen_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_seen_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_articles_article_key (article_key),
    KEY idx_articles_identity_url_hash (identity_url_hash),
    KEY idx_articles_content_hash (content_hash),
    KEY idx_articles_publish_date (publish_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS task_articles (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    protocol_version    VARCHAR(8) NOT NULL,
    task_id             VARCHAR(128) NOT NULL,
    hit_id              VARCHAR(128) NOT NULL,
    plan_id             VARCHAR(128) NOT NULL,
    article_id          BIGINT UNSIGNED NULL,
    result_hash         CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    result_message_id   VARCHAR(128) NOT NULL,
    result_timestamp    DATETIME(6) NOT NULL,
    original_query      VARCHAR(500) NOT NULL,
    query_term          VARCHAR(500) NOT NULL,
    requested_url       VARCHAR(2048) NOT NULL,
    final_url           VARCHAR(2048) NOT NULL,
    canonical_url       VARCHAR(2048) NOT NULL,
    title               VARCHAR(500) NOT NULL,
    publish_date        DATE NULL,
    source              VARCHAR(500) NOT NULL,
    summary             TEXT NOT NULL,
    content_hash        CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    score               INT UNSIGNED NOT NULL,
    matched_evidence    JSON NOT NULL,
    status              VARCHAR(32) NOT NULL,
    extraction_method   VARCHAR(32) NOT NULL,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_task_articles_task_hit (task_id, hit_id),
    KEY idx_task_articles_task_status (task_id, status),
    KEY idx_task_articles_article_id (article_id),
    KEY idx_task_articles_plan_id (plan_id),
    KEY idx_task_articles_content_hash (content_hash),
    CONSTRAINT fk_task_articles_article FOREIGN KEY (article_id)
        REFERENCES articles (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
