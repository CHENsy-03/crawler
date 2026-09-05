# V1.0/V1.1 当前权威数据模型

本文是 DEV-004 的当前权威数据模型入口。旧 `docs/DATA_MODEL.md` 保留为 LEGACY_PARTIAL_REFERENCE。

## 1. 实体演进与 ID 契约

- 旧 Markdown：20 类历史快照
- V1.0 DOCX：21 类
- V1.1：新增 GlobalBlockEntry
- 当前联合基线：22 类

21 类非审计实体使用 canonical ULID 主键，数据库类型固定为 `CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL`。AuditLog 是唯一例外，主键为 `BIGINT UNSIGNED NOT NULL AUTO_INCREMENT`，仅作内部单调标识。格式与生成边界见 [ADR-026](decisions/ADR-026-opaque-ulid-identifier-contract.md)。

## 2. 22 类实体与表

| 实体 | 表 | 主键 |
|---|---|---|
| Admin | admin | admin_id |
| Session | session | session_id |
| APIToken | api_token | token_id |
| IdempotencyRecord | idempotency_record | idempotency_record_id |
| CrawlTask | crawl_task | task_id |
| TaskAttempt | task_attempt | attempt_id |
| TaskStage | task_stage | stage_id |
| TaskEvent | task_event | event_id |
| SearchCandidate | search_candidate | candidate_id |
| FetchArtifact | fetch_artifact | artifact_id |
| Article | article | article_id |
| ArticleVersion | article_version | article_version_id |
| TaskArticle | task_article | task_article_id |
| ReviewDecision | review_decision | decision_id |
| ExportJob | export_job | job_id |
| Site | site | site_code |
| Plugin | plugin | plugin_id |
| OutboxEvent | outbox_event | outbox_event_id |
| AuditLog | audit_log | audit_log_id |
| DeadLetter | dead_letter | dead_letter_id |
| Checkpoint | checkpoint | checkpoint_id |
| GlobalBlockEntry | global_block_entry | block_entry_id |

除 AuditLog 外，任何目标表不得出现 AUTO_INCREMENT 主键。

## 3. Migration 文件

- Forward：`migrations/mysql/0002_v1_0_v1_1_22_entities.sql`
- Down：`migrations/mysql/0002_v1_0_v1_1_22_entities.down.sql`
- Fixture：`tests/fixtures/data_model_22_entities.json`
- Go formal model：`go-spider/internal/store/data_model_v1.go`
- Contract test：`go-spider/internal/store/data_model_v1_contract_test.go`
- Migration 执行契约：`migrations/mysql/README.md`

## 4. Migration 安全边界

- 0001 的 `articles` 与 `task_articles` 是保留的 legacy 兼容表，不属于 22 类当前实体。
- 0002 up 只支持 migration 0001 结构精确存在且两表均为空的状态。
- 0002 不支持非空 legacy 数据迁移，也不处理 config/schema.sql 或 AutoMigrate 数据。
- 存在 legacy singular `article`、非空 0001 数据、混合或部分结构时，up 在任何永久 DDL 前 fail closed。
- down 只允许在 22 张目标表为空且 0001 结构完整时执行，只删除 0002 创建的目标表。
- legacy 内容迁移仍是独立阻断项；不可变存储契约尚未冻结。
- schema migration 不等于数据迁移完成。

## 5. 关键设计

- Article 是稳定身份，ArticleVersion 是正文版本。
- TaskArticle 列表索引包含 `(task_id, persisted_at DESC, task_article_id DESC)`、相关性、审核状态和 result_status 四种窄查询形状。
- ArticleVersion 大正文和 JSON 证据不进入列表索引。
- FetchArtifact 使用 retention_class/hold_status 支持 REVIEW_HOLD。
- ReviewDecision 强引用 READY REVIEW_HOLD FetchArtifact，保存 hold_artifact_checksum 与 evidence_schema_version。
- ReviewDecision 对 TaskArticle/ArticleVersion 只保留弱标识，不建立阻止 180 天清理的强 FK。
- AuditLog 是 MySQL 权威持久化实体，不创建 audit_service，不因业务实体删除而级联删除。
- GlobalBlockEntry 使用 match_type、pattern_normalized、reason_code、reason_summary、evidence_ref 和版本化时间字段。

## 6. 当前状态

`FIX_IMPLEMENTED_WAITING_R2`；不表示 API、Streams、dispatcher 或业务状态机已实现。
