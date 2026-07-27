# Crawler Platform — Data Model v1.0

> 本文档定义 Python DuckDB 与 Go MySQL 共享的数据模型。
> Go 阶段直接复用，不再重新设计。

---

## 1. articles — 文章主表

| # | Field | DuckDB Type | MySQL Type | Description |
|---|-------|-------------|------------|-------------|
| 1 | url | TEXT | VARCHAR(1000) | 文章URL (主键, UNIQUE) |
| 2 | url_hash | VARCHAR(32) | VARCHAR(32) | url的MD5值，用于快速查找 |
| 3 | title | TEXT | VARCHAR(500) | 文章标题 |
| 4 | summary | TEXT | TEXT | 摘要（前500字） |
| 5 | content | TEXT | LONGTEXT | 正文内容 |
| 6 | province | TEXT | VARCHAR(100) | 省份（从站名推断） |
| 7 | site | TEXT | VARCHAR(200) | 来源站点名 |
| 8 | keyword | TEXT | VARCHAR(200) | 搜索关键词 |
| 9 | publish_time | VARCHAR(32) | DATETIME | 发布时间 |
| 10 | crawl_time | TIMESTAMP | TIMESTAMP | 抓取时间（默认NOW） |
| 11 | score | INTEGER | INT | 评分 |
| 12 | matched_keywords | VARCHAR | VARCHAR(500) | 命中的关键词列表（分号分隔） |
| 13 | detail_fetched | BOOLEAN | TINYINT(1) | 是否已抓取全文详情 |
| 14 | status | INTEGER | INT | 状态: 0=new, 1=parsed |

**Indexes:** `publish_time`, `keyword`, `score`, `site`

**Go GORM tag example:**
```go
URL string `gorm:"type:varchar(1000);not null;uniqueIndex:idx_url,length:32"`
```

---

## 2. crawl_log — 抓取日志

| # | Field | DuckDB Type | MySQL Type | Description |
|---|-------|-------------|------------|-------------|
| 1 | url | TEXT | VARCHAR(1000) | 请求URL |
| 2 | status | INTEGER | INT | HTTP状态码 (200/403/500...) |
| 3 | cost_ms | INTEGER | INT | 耗时（毫秒） |
| 4 | retry | INTEGER | INT | 重试次数 |
| 5 | error | TEXT | TEXT | 错误信息 |
| 6 | error_type | VARCHAR(20) | VARCHAR(20) | 错误分类: network/rate_limit/forbidden/server_error/client_error |
| 7 | crawl_time | TIMESTAMP | TIMESTAMP | 请求时间 |

**Indexes:** `url`, `status`, `crawl_time`

---

## 3. task — 搜索任务

| # | Field | DuckDB Type | MySQL Type | Description |
|---|-------|-------------|------------|-------------|
| 1 | id | TEXT | VARCHAR(32) | 任务ID (主键, UUID前8位) |
| 2 | keyword | TEXT | VARCHAR(200) | 搜索关键词 |
| 3 | site | TEXT | VARCHAR(100) | 目标站点key |
| 4 | status | TEXT | VARCHAR(20) | 状态: created/running/completed/failed |
| 5 | article_count | INTEGER | INT | 最终入库文章数 |
| 6 | created_at | TIMESTAMP | TIMESTAMP | 创建时间 |

---

## 4. statistics — 聚合统计（日报）

| # | Field | DuckDB Type | MySQL Type | Description |
|---|-------|-------------|------------|-------------|
| 1 | id | INTEGER | BIGINT | 自增ID |
| 2 | date | DATE | DATE | 统计日期 (UNIQUE) |
| 3 | total_articles | INTEGER | INT | 总文章数 |
| 4 | total_requests | INTEGER | INT | 总请求数 |
| 5 | success_count | INTEGER | INT | 成功数 |
| 6 | fail_count | INTEGER | INT | 失败数 |
| 7 | avg_latency_ms | REAL | FLOAT | 平均延迟（毫秒） |
| 8 | top_keyword | VARCHAR | VARCHAR(200) | 当日最多关键词 |
| 9 | top_site | VARCHAR | VARCHAR(200) | 当日最多站点 |
| 10 | created_at | TIMESTAMP | TIMESTAMP | 生成时间 |

---

## 5. Python ↔ Go 字段映射

| Article Dict Key | articles Column | Notes |
|-----------------|-----------------|-------|
| `url` | url | |
| `title` | title | |
| `summary` | summary | |
| `content` | content | |
| `publish_date` | publish_time | Python用`publish_date`, DB用`publish_time` |
| `site` | site | Pipeline补齐, 不用依赖插件 |
| `province` | province | Pipeline自动推断 |
| `source_keywords[0]` | keyword | 取第一个关键词 |
| `score` | score | Scorer输出 |
| `matched_keywords` | matched_keywords | 分号连接 |
| `source_keywords` | — | Python内部用, 不存DB |

---

## 6. Go GORM AutoMigrate

```go
db.AutoMigrate(&Article{}, &Task{}, &CrawlLog{}, &Statistic{})
```

MySQL 会自动建表；DuckDB 通过 Python `CREATE TABLE IF NOT EXISTS` 建表。
两边 schema 通过本文档保持同步。
