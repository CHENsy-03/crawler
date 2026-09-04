# ADR-008：ArticleResultV2 MySQL 持久化合同

**状态：** accepted

**日期：** 2026-08-13

**关联：** TASK-019B-5，TASK-019B-1 已完成

## 背景

TASK-019B-1 至 019B-4 已建立 ArticleResultV2 协议和 Python 生产发布链，但 MySQL 尚无对应的 v2 持久化合同。旧 `article` 表仍服务 legacy/v1，不能直接复用；ArticleResultV2 的 URL 身份、正文版本、任务命中结果、幂等重放和冲突语义需要独立模型。

## 决策

1. 保留旧 `article/task/crawl_log` 表，新增独立 v2 表 `articles/task_articles`。
2. `identity_url` 固定选择 canonical_url 优先，否则 final_url；不使用 requested_url。
3. `identity_url_hash = SHA-256(identity_url)`；`article_key = SHA-256(identity_url + "\n" + content_hash)`。
4. `articles` 保存 URL 身份 + 正文版本；`task_articles` 保存任务结果和全部状态。
5. 空正文不创建 `articles` 记录，`task_articles.article_id` 为 NULL。
6. `matched_evidence` 使用 JSON NOT NULL，空集合输出 `[]`。
7. `result_hash` 使用固定字段顺序结构体序列化后 SHA-256，不包含 message_id/timestamp/content 全文。
8. 相同 `(task_id, hit_id)` + 相同 result_hash 为幂等重放；不同 result_hash 为 `ErrArticleResultConflict`。
9. 持久化在单事务中完成；任意错误或冲突回滚，不更新任务状态、不修改 article_count。
10. 不对 `task_id` 建立物理外键，避免绑定 legacy task 生命周期合同；`article_id` 外键 `ON DELETE/UPDATE RESTRICT`。
11. 新增 `MySQLStore.PersistArticleResultV2` 但本轮不接入 queue/worker/API/CLI。
12. 不自动执行迁移；新增 `migrations/mysql/0001_articles_task_articles_v2.sql`，并在 `config/schema.sql` 末尾追加等价 bootstrap。
13. 不保存原始 HTML、附件、requested_url 到 `articles`。
14. 真实迁移与生产消费者接线推迟到 TASK-019B-6。

## 不采用的方案

- 直接复用旧 `article` 表：无法表达 URL 身份 + 正文版本和任务级结果，且会破坏 legacy/v1。
- 将 `articles` 与 `task_articles` 合并为单表：任务结果和正文版本职责不同，版本扩展会污染任务记录。
- 使用 map 构造 result_hash：顺序不稳定，无法满足确定性幂等。
- 对 `task_id` 建立物理外键：当前 task 生命周期合同由 TASK-021 统一。
- 在 B5 接入生产消费者：本轮只固化可调用但未被调用的存储合同。

## 影响

- Go store 包新增 `ArticleV2/TaskArticleV2` 模型、`BuildArticleResultV2Records` 和 `PersistArticleResultV2`。
- 旧 store、旧表、旧迁移和旧 Python MySQL 模块保持不变。
- 后续 TASK-019B-6 可基于此合同接通 `crawler:result` 显式版本分流与事务持久化。

## TASK-019B-6R 补充记录

- 旧 GORM 模型现在显式映射 `article/task/crawl_log`。
- `ArticleV2/TaskArticleV2` 保持 `articles/task_articles`。
- 不启用全局 SingularTable；AutoMigrate 仍只管理 legacy 三模型。
- B5 migration 未修改、未自动执行；历史 plural 表需人工审计。