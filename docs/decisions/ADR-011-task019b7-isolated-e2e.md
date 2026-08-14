# ADR-011：TASK-019B7 一次性隔离 Redis/MySQL E2E

**状态：** completed

**日期：** 2026-08-13

**关联：** TASK-019B-7，ADR-008/009/010 保持有效

## 验证环境

- Docker Client/Server：29.6.2
- Docker Desktop：4.83.0
- Docker Compose：v5.3.1
- Docker context：desktop-linux，OSType linux，Architecture x86_64
- MySQL 镜像：mysql:8.0
- Redis 镜像：redis:7-alpine
- 使用唯一 Compose project name，全部资源项目作用域隔离。
- 宿主机仅绑定 `127.0.0.1` 随机端口；密码为每次随机十六进制，仅存在于当前进程环境变量。

## 验证结果

1. Legacy AutoMigrate 在空库中只创建 `article/task/crawl_log`，未创建 `articles/task_articles/tasks/crawl_logs`。
2. B5 migration 在同一隔离库中连续执行两次，两次均成功，验证 `CREATE TABLE IF NOT EXISTS` 幂等。
3. Migration 后 `article/task/crawl_log/articles/task_articles` 五表真实并存。
4. 正式 `crawler:result → PopResultDispatch → StartResultConsumer → PersistArticleResultV2 → MySQL` 路径通过真实 Redis/MySQL 验证。
5. accepted 长正文完整写入 `articles.content`，无截断，content_hash 一致，task_articles 正确关联。
6. 同 `(task_id, hit_id)` 幂等重放不产生重复行，也不重复创建 articles。
7. 冲突结果返回 `ErrArticleResultConflict`，原记录不变，不生成冲突正文的孤立 articles。
8. 同一 URL 不同 hit_id 均持久化，不被旧 URL 去重吞掉。
9. accepted/review_required/irrelevant/extract_failed/unsupported_format 全部写入 task_articles；空正文结果 article_id 为 NULL。
10. legacy v1 ResultMessage 仍写入旧 `article` 表并更新旧 task；v1 不写入 articles/task_articles。
11. 非法版本消息被拒绝，合法 barrier 随后成功，消费者未退出。
12. 测试结束时精确 Compose 项目的容器、网络、卷残留均为 0。

## 边界

- migration 仍不属于生产自动启动流程。
- Redis List BRPOP 仍没有 ACK、重试、死信或背压；消息在持久化前已出队，数据库瞬时失败可能丢失消息。
- 本轮使用一次性隔离测试数据库，不代表已批准对任何现有数据库执行 migration。