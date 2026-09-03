# 通用型爬虫数据模型

本文定义 MySQL 逻辑模型、Redis Streams、DuckDB、原始文件卷和审计日志的目标设计，覆盖 20 个核心实体。当前实现仅部分覆盖，本文不构成实现完成声明。

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

- 职责：管理员账号、密码 hash 与 bootstrap 状态。
- 主键：`admin_id`
- 唯一：`username`
- 核心字段：username、password_hash、bootstrap_state、created_at、updated_at
- 状态：INITIALIZING、ACTIVE、DISABLED
- 索引：username
- 关系：Session、APIToken、ReviewDecision 归属该管理员
- 权威：MySQL
- 保留：与账号同生命周期

### Session

- 职责：浏览器登录会话与 CSRF 关联。
- 主键：`session_id`
- 唯一：`session_token_hash`
- 核心字段：admin_id、token_hash、csrf_token_hash、idle_expires_at、absolute_expires_at、revoked_at
- 状态：ACTIVE、IDLE_EXPIRED、ABSOLUTE_EXPIRED、REVOKED
- 索引：admin_id、absolute_expires_at
- 关系：Admin 1:N Session
- 权威：MySQL
- 保留：失效后 30 天

### APIToken

- 职责：外部 API Token 元数据与吊销状态。
- 主键：`token_id`
- 唯一：`token_hash`
- 核心字段：admin_id、name、token_hash、scopes、expires_at、rotated_from、revoked_at
- 状态：ACTIVE、EXPIRED、REVOKED
- 索引：admin_id、expires_at
- 关系：Admin 1:N APIToken
- 权威：MySQL
- 保留：吊销/过期后 90 天

### CrawlTask

- 职责：采集任务生命周期、调度状态和重试来源。
- 主键：`task_id`
- 唯一：`task_id`
- 核心字段：site_code、keywords、mode、status、stage、progress、attempt_count、limit_snapshot、policy_id、created_at、updated_at、timed_out_at
- 状态：DRAFT、PENDING_CONFIRMATION、QUEUED、RUNNING、RETRY_WAIT、RECOVERING、CANCELLING、SUCCEEDED、PARTIAL_SUCCEEDED、FAILED、CANCELLED、TIMED_OUT
- 执行阶段：DISCOVERY、FETCH、PARSE、SCORE、FILTER、DEDUP、PERSIST；EXPORT 不属 CrawlTask 阶段
- 索引：status、created_at、site_code
- 关系：1:N TaskAttempt、TaskStage、TaskEvent、SearchCandidate、TaskArticle、Checkpoint；retry_of_task_id 可引用旧 CrawlTask
- 权威：MySQL
- 保留：结构化 180 天

### TaskAttempt

- 职责：一次 Worker 执行尝试与 heartbeat。
- 主键：`attempt_id`
- 唯一：`(task_id, attempt_no)`
- 核心字段：task_id、attempt_no、status、checkpoint_id、heartbeat_expires_at、started_at、ended_at
- 状态：RUNNING、LOST、SUCCEEDED、FAILED、CANCELLED
- 索引：task_id、heartbeat_expires_at
- 关系：CrawlTask 1:N TaskAttempt
- 权威：MySQL
- 保留：180 天

### TaskStage

- 职责：CrawlTask 执行阶段进度。
- 主键：`stage_id`
- 唯一：`(task_id, stage, started_at)`
- 核心字段：task_id、stage、status、progress、last_event_id、started_at、ended_at
- 状态：PENDING、RUNNING、SUCCEEDED、FAILED
- 索引：task_id、stage
- 关系：CrawlTask 1:N TaskStage
- 权威：MySQL
- 保留：180 天

### TaskEvent

- 职责：任务事件和断档校验的业务记录。
- 主键：`event_id`
- 唯一：`(task_id, event_id)`
- 核心字段：task_id、event_type、payload_json、created_at
- 状态：事件记录，无状态
- 索引：task_id、event_id、created_at
- 关系：CrawlTask 1:N TaskEvent；Redis Streams 为消费载体
- 权威：MySQL（业务权威）；Redis Streams 只是实时传递和消费载体，不并列作为业务权威
- 保留：90 天

### SearchCandidate

- 职责：搜索发现候选与证据。
- 主键：`candidate_id`
- 唯一：`(task_id, normalized_url_hash)`
- 核心字段：task_id、discovery_source、site_code、normalized_url、normalized_url_hash、confidence、evidence_json、status、created_at
- 状态：DISCOVERED、QUEUED、FETCHED、FAILED、DUPLICATE
- 索引：task_id、normalized_url_hash、status
- 关系：CrawlTask 1:N SearchCandidate；TaskArticle 可引用候选
- 权威：MySQL
- 保留：180 天

### FetchArtifact

- 职责：抓取产物元数据与不可变存储引用。
- 主键：`artifact_id`
- 唯一：`artifact_storage_key`
- 核心字段：candidate_id、storage_key、content_hash、content_type、byte_size、fetched_at、checksum
- 状态：PENDING、SAVED、FAILED
- 索引：candidate_id、content_hash
- 关系：SearchCandidate 1:N FetchArtifact
- 权威：MySQL 元数据 + 文件卷内容
- 保留：原始内容/附件 30 天，安全证据永久

### Article

- 职责：稳定文章身份。
- 主键：`article_id`
- 唯一：`identity_url_hash` 或明确的稳定 `article_key`
- 核心字段：identity_url、identity_url_hash、article_key、canonical_url、title、latest_version_id、created_at
- 状态：稳定文章身份，不以 content_hash 区分身份
- 索引：identity_url_hash、article_key
- 关系：Article 1:N ArticleVersion，经 TaskArticle 关联任务
- 权威：MySQL
- 保留：180 天

### ArticleVersion

- 职责：Article 的不可变正文版本。
- 主键：`article_version_id`
- 唯一：`(article_id, content_hash)`；`version_no` 在同一 article_id 内唯一
- 核心字段：article_id、version_no、content_hash、content_storage_ref、raw_evidence_ref、extraction_info_json、created_at
- 状态：ACTIVE、SUPERSEDED
- 索引：article_id、version_no
- 关系：Article 1:N ArticleVersion；TaskArticle、ReviewDecision 可引用正文版本
- 权威：MySQL
- 保留：180 天

### TaskArticle

- 职责：任务命中结果与正文版本之间的关联。
- 主键：`task_article_id`
- 唯一：`(task_id, hit_id)` 作为幂等键
- 核心字段：task_id、hit_id、candidate_id、article_id、article_version_id、query_term、score、matched_evidence_json、result_status、created_at
- 状态：ACCEPTED、REVIEW_REQUIRED、IRRELEVANT、EXTRACT_FAILED、UNSUPPORTED_FORMAT
- 索引：task_id、hit_id、article_id、result_status
- 关系：关联 CrawlTask、SearchCandidate、Article、ArticleVersion
- 权威：MySQL
- 保留：180 天

### ReviewDecision

- 职责：审核结论的 append-only 记录。
- 主键：`decision_id`
- 唯一：`(task_article_id, article_version_id, admin_id, decided_at)`
- 核心字段：task_article_id、article_version_id、admin_id、decision、comment、evidence_snapshot、created_at
- 状态：无状态，append-only
- 索引：article_id、admin_id、created_at
- 关系：引用 TaskArticle 与 ArticleVersion，不覆盖原始证据或正文版本
- 权威：MySQL
- 保留：永久（审核结论）

### ExportJob

- 职责：独立异步导出任务。
- 主键：`job_id`
- 唯一：`job_id`
- 核心字段：task_id/filter_snapshot、format、status、file_storage_key、expires_at、created_at、finished_at
- 状态：PENDING、RUNNING、SUCCEEDED、FAILED、EXPIRED
- 索引：created_at、status
- 关系：可引用任务或筛选快照；独立于 CrawlTask 阶段
- 权威：MySQL + 导出文件卷
- 保留：导出文件 7 天或按策略扩展

### Site

- 职责：站点能力与安全策略引用。
- 主键：`site_code`
- 唯一：`site_code`
- 核心字段：name、capabilities_json、enabled、plugin_policy、security_policy_id、created_at、updated_at
- 状态：ACTIVE、DISABLED、MIGRATION_PENDING
- 索引：site_code、enabled
- 关系：CrawlTask/SearchCandidate 引用 site_code；站点引用安全 policy
- 权威：MySQL
- 保留：站点配置生命周期，审计永久

### Plugin

- 职责：插件注册、版本和启停状态。
- 主键：`plugin_id`
- 唯一：`(plugin_key, version)`
- 核心字段：plugin_key、version、type、enabled、registered_at、last_audited_at
- 状态：REGISTERED、ENABLED、DISABLED、DEPRECATED
- 索引：plugin_key、version、enabled
- 关系：Site 可引用 plugin policy/version；插件记录为历史审计
- 权威：MySQL
- 保留：插件注册与版本历史永久

### OutboxEvent

- 职责：与业务事务一致的待发布事件。
- 主键：`outbox_event_id`
- 唯一：`(aggregate_type, aggregate_id, event_key)`
- 核心字段：event_type、event_version、payload_json、status、attempt_count、next_attempt_at、dispatched_at
- 状态：PENDING、DISPATCHED、FAILED、DEAD
- 索引：status、next_attempt_at
- 关系：对应业务事务 aggregate；由 dispatcher 发布到 Redis Streams
- 权威：MySQL
- 保留：90 天

### AuditLog

- 职责：关键操作与安全事件审计。
- 主键：`audit_log_id`
- 唯一：审计事件自增 id
- 核心字段：actor_type、actor_id、action、resource_type、resource_id、before_json、after_json、ip_scope、created_at
- 状态：append-only
- 索引：created_at、actor_id、resource_type
- 关系：引用 actor 和 resource，不建立强外键以避免破坏证据链
- 权威：MySQL
- 保留：永久

### DeadLetter

- 职责：超过重试上限的失败事件。
- 主键：`dead_letter_id`
- 唯一：`(stream, message_id)`
- 核心字段：stream、message_id、payload_json、error_code、attempt_count、status、replay_count、created_at
- 状态：OPEN、REPLAYED、RESOLVED、DISCARDED
- 索引：status、created_at
- 关系：对应 Stream 和 message_id，可关联原事件
- 权威：MySQL
- 保留：90 天或人工裁决

### Checkpoint

- 职责：任务阶段恢复点。
- 主键：`checkpoint_id`
- 唯一：`(task_id, checkpoint_key)`
- 核心字段：task_id、stage、checkpoint_key、state_json、created_at、updated_at
- 状态：ACTIVE、APPLIED、SUPERSEDED
- 索引：task_id、checkpoint_key
- 关系：CrawlTask/TaskAttempt 引用
- 权威：MySQL
- 保留：任务结束后 30 天
## 3. 关系与生命周期

- Admin 1:N Session、APIToken、ReviewDecision。
- CrawlTask 1:N TaskAttempt、TaskStage、TaskEvent、SearchCandidate、TaskArticle、Checkpoint。
- SearchCandidate 1:N FetchArtifact。
- Article 1:N ArticleVersion。
- CrawlTask N:N Article 经 TaskArticle 关联；TaskArticle 关联 SearchCandidate、Article、ArticleVersion。
- TaskArticle 保存本任务 query、score、matched_evidence 和 result_status，不复制或覆盖 ArticleVersion 正文权威。
- ReviewDecision 引用 ArticleVersion 和 TaskArticle，不覆盖原始证据。
- OutboxEvent 独立于业务事务表，由 dispatcher 发布到 Redis Streams。
- DeadLetter 与 Streams message_id 对应，支持受控重放。

任务终态不允许被迟到事件覆盖；状态迁移以 TaskEvent 和任务状态机为准。

重试保留原任务终态不变，创建新 CrawlTask，新任务记录 retry_of_task_id，从 DRAFT 或 PENDING_CONFIRMATION 进入流程。

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

### 9.1 当前 migration 差距

- 当前 `articles/task_articles` migration 属于 CURRENT_PARTIAL。
- 尚无完整 ArticleVersion 目标表。
- 本轮不修改 migration。
- 后续实施必须通过新版本 migration 完成，不得篡改已存在 migration 历史。
- Python 不直接写权威业务表；TaskArticle/ArticleVersion/ReviewDecision 的权威写入由 Go 控制面协调。
