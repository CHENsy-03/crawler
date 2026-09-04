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


---

## 7. TASK-019B-5 命名与并存说明

- 本文件第 1 节的 `articles` 是历史 DuckDB/共享文档表名；MySQL legacy 实际表名为 `article`。
- TASK-019B-5 新增 MySQL v2 独立表：`articles` 与 `task_articles`。
- 旧 `article/task/crawl_log` 表保留不变，继续服务 legacy/v1。
- 新 `articles/task_articles` 只服务未来 ArticleResultV2 持久化合同，本轮未接入生产消费者。

## 8. v2 articles

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT UNSIGNED AUTO_INCREMENT | 主键 |
| article_key | CHAR(64) ASCII BINARY | URL 身份 + 正文版本 |
| identity_url | VARCHAR(2048) | canonical_url 非空时取 canonical_url，否则 final_url |
| identity_url_hash | CHAR(64) ASCII BINARY | identity_url 的 SHA-256 |
| canonical_url | VARCHAR(2048) | 允许空字符串 |
| final_url | VARCHAR(2048) | 最终 URL |
| title | VARCHAR(500) | 标题 |
| publish_date | DATE NULL | 空值存 NULL |
| source | VARCHAR(500) | 来源 |
| summary | TEXT | 摘要 |
| content | LONGTEXT | 完整正文，不截断 |
| content_hash | CHAR(64) ASCII BINARY | 正文 SHA-256 |
| extraction_method | VARCHAR(32) | 提取方法 |
| first_seen_at / last_seen_at | DATETIME(6) | 首次/最近出现 |

索引：`UNIQUE(article_key)`、`identity_url_hash`、`content_hash`、`publish_date`。

## 9. v2 task_articles

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT UNSIGNED AUTO_INCREMENT | 主键 |
| protocol_version | VARCHAR(8) | 固定 2.0 |
| task_id / hit_id | VARCHAR(128) | 唯一组合 `(task_id, hit_id)` |
| plan_id | VARCHAR(128) | 计划 ID |
| article_id | BIGINT UNSIGNED NULL | 空正文时为 NULL |
| result_hash | CHAR(64) ASCII BINARY | 业务结果幂等指纹 |
| result_message_id | VARCHAR(128) | 原始消息 ID |
| result_timestamp | DATETIME(6) | 消息 RFC3339 时间 |
| original_query / query_term | VARCHAR(500) | 查询来源 |
| requested_url / final_url / canonical_url | VARCHAR(2048) | URL 来源 |
| title | VARCHAR(500) | 标题 |
| publish_date | DATE NULL | 发布日期 |
| source | VARCHAR(500) | 来源 |
| summary | TEXT | 摘要 |
| content_hash | CHAR(64) ASCII BINARY | 正文哈希，可空字符串 |
| score | INT UNSIGNED | 评分 |
| matched_evidence | JSON NOT NULL | 空集合为 [] |
| status | VARCHAR(32) | 全部状态均保留 |
| extraction_method | VARCHAR(32) | 提取方法 |
| created_at | DATETIME(6) | 创建时间 |

索引：`UNIQUE(task_id, hit_id)`、`(task_id, status)`、`article_id`、`plan_id`、`content_hash`。`article_id` 外键 `ON DELETE RESTRICT ON UPDATE RESTRICT`；不对 `task_id` 建立物理外键。

## 10. 未来生产接入

- `migrations/mysql/0001_articles_task_articles_v2.sql` 与本文件末尾 v2 表定义等价。
- 本轮未执行真实 MySQL 迁移，也未把 ArticleResultV2 接入生产消费者。
- 接线前必须先验证迁移，并在 TASK-019B-6 接通 Go `crawler:result` 显式版本分流与事务持久化。


## 11. TASK-019B-6R：Go GORM 表名合同

- Go 旧模型显式映射：`Article → article`、`Task → task`、`CrawlLog → crawl_log`。
- Go v2 模型保持：`ArticleV2 → articles`、`TaskArticleV2 → task_articles`。
- 五个表名互不冲突；config/schema.sql、Python MySQL 模块和 Go GORM 表名一致。
- 不启用全局 SingularTable；AutoMigrate 只管理三个 legacy 模型。