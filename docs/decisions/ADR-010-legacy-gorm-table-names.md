# ADR-010：Legacy GORM 显式 singular 表名

**状态：** accepted

**日期：** 2026-08-13

**关联：** TASK-019B-6R，ADR-008/009 保持有效

## 问题来源

- 旧 `Article/Task/CrawlLog` 未实现 `TableName()`。
- `NewMySQLStore` 未配置 `SingularTable`。
- GORM 默认命名策略会生成 `articles/tasks/crawl_logs`。
- B5 的 `ArticleV2` 显式返回 `articles`，`TaskArticleV2` 返回 `task_articles`。
- 因此旧 `Article` 与 `ArticleV2` 在无显式表名时会冲突到 `articles`。

## 决策

1. 为旧模型增加显式值接收者 TableName：
   - `Article → article`
   - `Task → task`
   - `CrawlLog → crawl_log`
2. 不启用全局 `SingularTable`，避免影响其他未来模型并保持显式合同。
3. 不修改 `ArticleV2/TaskArticleV2` 表名。
4. 不修改 AutoMigrate 参数：仍只迁移 `Article/Task/CrawlLog`。
5. 不修改旧结构体字段、tag、方法签名或 API。
6. 不自动处理历史 plural 表；不 DROP/RENAME/ALTER/回填。
7. B5 migration 仍必须显式、独立执行，且不能自动接入。
8. TASK-019B-7 只使用全新一次性隔离数据库，不处理历史数据。

## 影响

- 五个模型表名互不冲突：article、task、crawl_log、articles、task_articles。
- `config/schema.sql`、Python MySQL 模块和 Go GORM 模型表名一致。
- 在目标 MySQL 上仍须人工审计是否已存在历史 plural 表。