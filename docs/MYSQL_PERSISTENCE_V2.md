# MySQL ArticleResultV2 持久化合同

**状态：** 合同已固化，未接入生产消费者

**关联：** TASK-019B-5，ADR-008

## 1. 并存策略

- 旧 `article/task/crawl_log` 表保留不变，继续服务 legacy/v1。
- 新增 `articles/task_articles` 两张 v2 独立表，只服务未来 ArticleResultV2。
- 旧 `article` 与新 `articles` 可暂时并存；不 DROP、RENAME、TRUNCATE、DELETE 旧数据，不自动回填。
- 当前 Go AutoMigrate 不包含 `ArticleV2/TaskArticleV2`，新表不会自动创建。

## 2. identity_url

- `canonical_url` 非空时使用 `canonical_url`。
- `canonical_url` 为空时使用 `final_url`。
- 不使用 `requested_url` 作为文章身份。
- 不发起网络请求，不在存储层重写 URL。

## 3. identity_url_hash 与 article_key

- `identity_url_hash = SHA-256(identity_url.encode("utf-8"))`，64 位小写十六进制。
- `article_key = SHA-256(identity_url.encode("utf-8") + b"\n" + content_hash.encode("ascii"))`，64 位小写十六进制。
- `article_key` 同时包含 URL 身份和正文版本；相同 URL 但正文变化会生成新版本，不覆盖历史正文。
- 标题、摘要、时间、source 不参与 `article_key`。

## 4. articles 与 task_articles 职责

- `articles` 保存“确定 URL 身份 + 确定正文版本”：正文、摘要、标题、来源、日期、提取方法。
- `task_articles` 保存“某个任务命中的一条 ArticleResultV2 结果”：score、status、matched_evidence、查询来源。
- `articles` 不保存 score/status/evidence/requested_url/原始 HTML/附件。
- `task_articles` 保留 accepted/review_required/irrelevant/extract_failed/unsupported_format 全部状态。

## 5. 空正文

- `content` 或 `content_hash` 为空时不创建 `articles` 记录。
- `task_articles.article_id` 为 NULL，但任务结果仍必须保留。
- 覆盖 extract_failed、unsupported_format 及未来无正文合法结果。

## 6. matched_evidence

- 使用 MySQL JSON 列，`NOT NULL`。
- 空集合必须保存为 `[]`，不得为 `null`。
- 保持 B1 稳定顺序，不使用 map 生成 canonical fingerprint。

## 7. result_hash

固定字段顺序结构体序列化后计算 SHA-256，包含：

1. task_id
2. hit_id
3. plan_id
4. original_query
5. query_term
6. requested_url
7. final_url
8. canonical_url
9. title
10. publish_date
11. source
12. summary
13. content_hash
14. score
15. matched_evidence
16. status
17. extraction_method

不包含 message_id、timestamp、content 全文、数据库 ID 和各类 created/last_seen 时间。

## 8. 幂等重放与冲突

- 相同 `(task_id, hit_id)` 且 `result_hash` 相同：视为幂等重放，返回 `Replayed=true`，不创建第二条记录，不覆盖。
- 相同 `(task_id, hit_id)` 且 `result_hash` 不同：返回 `ErrArticleResultConflict`，不覆盖旧结果，整个事务回滚。
- `message_id/timestamp` 变化但业务字段不变：result_hash 不变，仍视为幂等重放。

## 9. 事务边界

- `MySQLStore.PersistArticleResultV2` 在单个 GORM 事务内执行。
- 任意 article/task_articles 写入失败或冲突均回滚整个事务。
- 不调用 UpdateTask、不修改 article_count、不消费 Redis、不发布错误消息、不重试、不写死信。

## 10. 安全与存储边界

- 正文使用 LONGTEXT，不截断。
- 不保存原始 HTML 或附件。
- `publish_date` 空值映射 NULL；非法日期拒绝，不使用当前时间伪造。
- `result_timestamp` 使用消息 RFC3339 时间；非法 timestamp 拒绝。

## 11. 当前状态

- 新增迁移文件：`migrations/mysql/0001_articles_task_articles_v2.sql`。
- `config/schema.sql` 末尾追加等价 v2 表 bootstrap 定义。
- 本轮未执行真实 MySQL 迁移。
- ArticleResultV2 仍发布到 `crawler:result`，Go v2 生产消费者尚未接入。
- 下一步接线前必须先验证迁移，再进行 TASK-019B-6。
- 当前检查点不可部署。

## 12. TASK-019B-6 接线状态

- `crawler:result` 正式 Worker 已使用 `PopResultDispatch()` 显式分流。
- `2.0` 消息严格解码为 ArticleResultV2 并调用 `MySQLStore.PersistArticleResultV2()`。
- v2 不经过旧 SaveArticle、旧 URL 去重、UpdateTask 或 article_count。
- 当前没有 ACK、重试、死信和背压；BRPOP 后数据库瞬时失败可能丢失消息，该风险由 TASK-021 处理。
- migration 仍未在真实 MySQL 执行；真实 Redis→MySQL E2E 等待 TASK-019B-7。

## 13. TASK-019B-6R 表名冲突修复

- 旧 GORM 模型显式返回 singular 表名：article、task、crawl_log。
- v2 模型保持 articles、task_articles。
- 五个表名互不冲突；未启用全局 SingularTable。
- AutoMigrate 仍只处理 legacy 三模型，B5 migration 独立执行。
- 历史 plural 表在部署前必须人工审计，本轮未连接或修改真实数据库。

## 14. TASK-019B-7 隔离 E2E 验证完成

- 真实一次性 MySQL/Redis 环境验证通过：legacy singular 表、v2 表并存，migration 连续执行两次成功。
- 正式结果消费者到 `PersistArticleResultV2` 的真实路径通过。
- replay、conflict rollback、全部状态、legacy/v1 共存、非法版本隔离均通过。
- 精确 Compose 资源清理为 0；migration 仍未自动执行。

## 15. TASK-019B-8/8R 持久化验收

- 本地全链 E2E 验证 URLMessageV2 到 articles/task_articles 的真实持久化。
- accepted/review_required/irrelevant/extract_failed 均落库；空正文 article_id 为 NULL。
- 多 hit 共享同一 articles 记录；重复投递不产生重复行。
- migration 仍独立显式执行，未自动接入生产启动。