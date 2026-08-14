# ADR-009：crawler:result 显式版本分流与 ArticleResultV2 消费者接线

**状态：** accepted

**日期：** 2026-08-13

**关联：** TASK-019B-6，ADR-008 保持有效

## 背景

B5 已建立 `articles/task_articles` 与 `MySQLStore.PersistArticleResultV2` 合同，但 `crawler:result` 仍由旧 `PopResultMessage` 消费，无法区分 legacy/v1 与 ArticleResultV2。需要在不破坏旧路径的前提下，把 v2 消息接到 B5 持久化入口。

## 决策

1. 新增 `PopResultDispatch()`：单次 BRPOP 后按 `protocol_version` 显式分流，不二次读取队列。
2. 完全缺失 `protocol_version` 才进入 legacy；`"1.0"` 进入 v1；`"2.0"` 使用 B1 严格解码。
3. 显式 null、非字符串、未知版本、非法 JSON、非对象 JSON 均拒绝，不默认进入 v1，不回退、不伪造 v1 ErrorMessage。
4. `StartResultConsumer()` 改为调用 `PopResultDispatch()`；`PopResultMessage`/`PopResult` 保留兼容，但不作为生产入口。
5. legacy/v1 继续调用 `consumeResult()`、`SaveArticle()`、旧 URL 去重、UpdateTask 和旧任务完成判断。
6. v2 只调用 `PersistArticleResultV2()`，不调用 `consumeResult()`、`SaveArticle()`、旧 URL 去重或 UpdateTask。
7. v2 不修改旧 task 状态和 `article_count`，不参与旧 SearchDone/Expected/Stored/Failed 判断。
8. 同一 URL 不同 hit_id 分别持久化，不被旧 URL 去重吞掉。
9. accepted/review_required/irrelevant/extract_failed/unsupported_format 全部持久化。
10. `Replayed=true` 视为幂等成功；`ErrArticleResultConflict` 明确记录且不覆盖。
11. 普通持久化错误不终止消费者，不回退 v1。
12. store 不支持 v2 接口时返回明确错误，不 panic。
13. 不新增第二个 `crawler:result` 消费者。
14. 当前没有 ACK、重试、死信和背压；BRPOP 后数据库瞬时失败可能丢失消息，由 TASK-021 处理。
15. migration 仍未在真实 MySQL 执行；API 未切换到新 `articles` 表。
16. 当前检查点不可部署。

## 不采用的方案

- 在 queue 复制一套 v2 验证规则：应复用 B1 严格解码。
- 让 v2 经过旧 URL 去重或任务统计：会丢失多 hit 语义并污染 legacy 合同。
- 扩展现有 taskStore 接口：会迫使所有旧 fake 实现新方法。
- 删除旧 `PopResultMessage/PopResult`：legacy 兼容需要保留。

## 影响

- `crawler:result` 正式链具备 legacy/v1/v2 显式分流。
- v2 已接到 B5 单事务持久化入口。
- 后续 TASK-019B-7 在隔离 Redis/MySQL 环境验证真实迁移和 E2E。