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
