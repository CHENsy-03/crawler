# 通用型爬虫数据模型

本文定义 MySQL 逻辑模型、Redis Streams、DuckDB、原始文件卷和审计日志的目标设计。当前实现仅部分覆盖，本文不构成实现完成声明。

## 1. 数据权威原则

- MySQL 是结构化业务数据权威存储。
- Redis Streams 用于任务与事件传递，不作为业务查询权威。
- DuckDB 用于分析、查询加速和导出，不写入任务状态权威。
- 原始页面和附件进入不可变文件卷，使用内容寻址或不可变路径。
- Python 通过版本化事件交付结果，不直接写权威业务表。
- Go 控制面消费事件并执行 MySQL 权威写入。
- 所有删除使用软删除或保留期清理，不物理破坏证据链。

## 2. 实体定义

### Admin

- 主键：`admin_id`
- 唯一：`username`
- 核心字段：username、password_hash、bootstrap_state、created_at、updated_at
- 状态：INITIALIZING、ACTIVE、DISABLED
- 索引：username
- 权威：MySQL
- 保留：与账号同生命周期

### Session

- 主键：`session_id`
- 唯一：`session_token_hash`
- 核心字段：admin_id、token_hash、csrf_token_hash、idle_expires_at、absolute_expires_at、revoked_at
- 状态：ACTIVE、IDLE_EXPIRED、ABSOLUTE_EXPIRED、REVOKED
- 索引：admin_id、absolute_expires_at
- 权威：MySQL
- 保留：失效后 30 天

### APIToken

- 主键：`token_id`
- 唯一：`token_hash`
- 核心字段：admin_id、name、token_hash、scopes、expires_at、rotated_from、revoked_at
- 状态：ACTIVE、EXPIRED、REVOKED
- 索引：admin_id、expires_at
- 权威：MySQL
- 保留：吊销/过期后 90 天

### CrawlTask

- 主键：`task_id`
- 唯一：`task_id`
- 核心字段：site_code、keywords、mode、status、stage、progress、attempt_count、limit_snapshot、policy_id、created_at、updated_at、timed_out_at
- 状态：DRAFT、PENDING_CONFIRMATION、QUEUED、RUNNING、RETRY_WAIT、RECOVERING、CANCELLING、SUCCEEDED、PARTIAL_SUCCEEDED、FAILED、CANCELLED、TIMED_OUT
- 索引：status、created_at、site_code
- 权威：MySQL
- 保留：结构化 180 天

### TaskAttempt

- 主键：`attempt_id`
- 唯一：`(task_id, attempt_no)`
- 核心字段：task_id、attempt_no、status、checkpoint_id、heartbeat_expires_at、started_at、ended_at
- 状态：RUNNING、LOST、SUCCEEDED、FAILED、CANCELLED
- 索引：task_id、heartbeat_expires_at
- 权威：MySQL
- 保留：180 天

### TaskStage

- 主键：`stage_id`
- 唯一：`(task_id, stage, started_at)`
- 核心字段：task_id、stage、status、progress、last_event_id、started_at、ended_at
- 状态：PENDING、RUNNING、SUCCEEDED、FAILED
- 索引：task_id、stage
- 权威：MySQL
- 保留：180 天

### TaskEvent

- 主键：`event_id`
- 唯一：`(task_id, event_id)`
- 核心字段：task_id、event_type、payload_json、created_at
- 状态：事件记录，无状态
- 索引：task_id、event_id、created_at
- 权威：MySQL（用于断档校验）与 Redis Streams（实时）
- 保留：90 天

### SearchCandidate

- 主键：`candidate_id`
- 唯一：`(task_id, normalized_url_hash)`
- 核心字段：task_id、discovery_source、site_code、normalized_url、normalized_url_hash、confidence、evidence_json、status、created_at
- 状态：DISCOVERED、QUEUED、FETCHED、FAILED、DUPLICATE
- 索引：task_id、normalized_url_hash、status
- 权威：MySQL
- 保留：180 天

### FetchArtifact

- 主键：`artifact_id`
- 唯一：`artifact_storage_key`
- 核心字段：candidate_id、storage_key、content_hash、content_type、byte_size、fetched_at、checksum
- 状态：PENDING、SAVED、FAILED
- 索引：candidate_id、content_hash
- 权威：MySQL 元数据 + 文件卷内容
- 保留：原始内容/附件 30 天，安全证据永久

### Article

- 主键：`article_id`
- 唯一：`(identity_url_hash, content_hash)` 对应 URL 身份和正文版本
- 核心字段：identity_url、identity_url_hash、canonical_url、title、content_hash、extraction_method、raw_evidence_key、created_at
- 状态：无业务状态，正文版本记录
- 索引：identity_url_hash、content_hash
- 权威：MySQL
- 保留：180 天

### ArticleVersion

- 主键：`article_version_id`
- 唯一：`(article_id, version_no)`
- 核心字段：article_id、version_no、content_hash、content_storage_ref、changed_at
- 状态：ACTIVE、SUPERSEDED
- 索引：article_id、version_no
- 权威：MySQL
- 保留：180 天

### ReviewDecision

- 主键：`decision_id`
- 唯一：`(article_id, admin_id, decided_at)`
- 核心字段：article_id、task_article_id、admin_id、decision、comment、evidence_snapshot、created_at
- 状态：无状态，append-only
- 索引：article_id、admin_id、created_at
- 权威：MySQL
- 保留：永久（审核结论）

### ExportJob

- 主键：`job_id`
- 唯一：`job_id`
- 核心字段：task_id/filter_snapshot、format、status、file_storage_key、expires_at、created_at、finished_at
- 状态：PENDING、RUNNING、SUCCEEDED、FAILED、EXPIRED
- 索引：created_at、status
- 权威：MySQL + 导出文件卷
- 保留：导出文件 7 天或按策略扩展

### Site

- 主键：`site_code`
- 唯一：`site_code`
- 核心字段：name、capabilities_json、enabled、plugin_policy、security_policy_id、created_at、updated_at
- 状态：ACTIVE、DISABLED、MIGRATION_PENDING
- 索引：site_code、enabled
- 权威：MySQL
- 保留：站点配置生命周期，审计永久

### Plugin

- 主键：`plugin_id`
- 唯一：`(plugin_key, version)`
- 核心字段：plugin_key、version、type、enabled、registered_at、last_audited_at
- 状态：REGISTERED、ENABLED、DISABLED、DEPRECATED
- 索引：plugin_key、version、enabled
- 权威：MySQL
- 保留：插件注册与版本历史永久

### OutboxEvent

- 主键：`outbox_event_id`
- 唯一：`(aggregate_type, aggregate_id, event_key)`
- 核心字段：event_type、event_version、payload_json、status、attempt_count、next_attempt_at、dispatched_at
- 状态：PENDING、DISPATCHED、FAILED、DEAD
- 索引：status、next_attempt_at
- 权威：MySQL
- 保留：90 天

### AuditLog

- 主键：`audit_log_id`
- 唯一：审计事件自增 id
- 核心字段：actor_type、actor_id、action、resource_type、resource_id、before_json、after_json、ip_scope、created_at
- 状态：append-only
- 索引：created_at、actor_id、resource_type
- 权威：MySQL
- 保留：永久

### DeadLetter

- 主键：`dead_letter_id`
- 唯一：`(stream, message_id)`
- 核心字段：stream、message_id、payload_json、error_code、attempt_count、status、replay_count、created_at
- 状态：OPEN、REPLAYED、RESOLVED、DISCARDED
- 索引：status、created_at
- 权威：MySQL
- 保留：90 天或人工裁决

### Checkpoint

- 主键：`checkpoint_id`
- 唯一：`(task_id, checkpoint_key)`
- 核心字段：task_id、stage、checkpoint_key、state_json、created_at、updated_at
- 状态：ACTIVE、APPLIED、SUPERSEDED
- 索引：task_id、checkpoint_key
- 权威：MySQL
- 保留：任务结束后 30 天
## 3. 关系与生命周期

- Admin 1:N Session、APIToken、ReviewDecision。
- CrawlTask 1:N TaskAttempt、TaskStage、TaskEvent、SearchCandidate、Checkpoint。
- SearchCandidate 1:N FetchArtifact。
- Article 1:N ArticleVersion；TaskArticle 关联任务与正文版本。
- ReviewDecision 引用 ArticleVersion 和 TaskArticle，不覆盖原始证据。
- OutboxEvent 独立于业务事务表，由 dispatcher 发布到 Redis Streams。
- DeadLetter 与 Streams message_id 对应，支持受控重放。

任务终态不允许被迟到事件覆盖；状态迁移以 TaskEvent 和任务状态机为准。

## 4. Redis Streams 设计

目标主题：

| Stream | Producer | Consumer | 用途 |
|---|---|---|---|
| `crawler:search` | Go dispatcher | Python Search Worker | 搜索和发现请求 |
| `crawler:url` | Python Search Worker | Go/Python fetch 调度 | URL 下载请求 |
| `crawler:fetch` | 抓取调度 | Python Fetch/Playwright Worker | 受控抓取请求 |
| `crawler:html` | 抓取 Worker | Python Parser Worker | 待解析内容 |
| `crawler:result` | Python Worker | Go result consumer | 版本化采集结果 |
| `crawler:error` | Go/Python | 错误处理组件 | 跨阶段错误事件 |

设计约束：

- 每个 Stream 使用一个 Consumer Group；消费者使用显式 `XACK`。
- 消息含 `event_id`、`event_version`、`aggregate_id`、`idempotency_key`。
- 失败消息保留在 pending 中，支持 `XAUTOCLAIM` 或等价受控 reclaim。
- 超过最大处理次数进入 DeadLetter。
- Stream 保留窗口与 TaskEvent/DeadLetter 清理任务一致。
- 单主题内维护追加顺序；跨主题不做全局严格排序。

## 5. Transactional Outbox

- 业务事务与 OutboxEvent 在同一 MySQL 事务写入。
- Dispatcher 轮询 PENDING OutboxEvent，发布到 Redis Streams 后标记 DISPATCHED。
- 发布失败保留 PENDING，指数退避重试。
- 消费者按 idempotency_key 幂等写入，重复消息不产生重复正文或计数。
- OutboxEvent 进入 FAILED/DEAD 后由审计员或受控重放任务处理。

## 6. DuckDB 输入输出

- 输入：MySQL 结构化结果的定期/事件驱动同步、导出查询临时表。
- 输出：分析报表、查询加速、CSV/XLSX/JSON 导出数据。
- DuckDB 不承担任务状态、队列 ACK 或业务事务权威。
- DuckDB 文件位于本地分析卷，可重建，不纳入备份主链。

## 7. 原始文件存储

- 原始页面与附件使用 `sha256/<prefix>/<content_hash>` 或等价不可变路径。
- 文件写入后只读，禁止原地覆盖。
- FetchArtifact 保存 content_hash、content_type、byte_size 和 checksum。
- 删除只针对保留期过期数据，不允许破坏已审核或安全证据。

## 8. 数据保留矩阵

| 数据 | 保留期 |
|---|---|
| 结构化结果 | 180 天 |
| 原始内容/附件 | 30 天 |
| 普通日志 | 90 天 |
| 诊断材料 | 30 天 |
| 安全证据 | 永久 |
| Session/Token 失效记录 | 30/90 天 |
| 审计日志/审核结论 | 永久 |

## 9. 当前实现与目标差异

| 项目 | 当前 | 目标 |
|---|---|---|
| Redis | list BRPOP/LPUSH，CURRENT_CONFLICT | Redis Streams + Consumer Groups |
| Outbox | NOT_STARTED | Transactional Outbox |
| MySQL v2 写入 | Go/Python 历史路径混合 | Go 权威写入协调 |
| DuckDB | 历史 StorageManager 本地分析 | 分析和导出专用 |
| 文件卷 | 无完整不可变策略 | 内容寻址只读文件卷 |
