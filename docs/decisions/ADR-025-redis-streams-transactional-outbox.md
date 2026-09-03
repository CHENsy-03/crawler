# ADR-025: Redis Streams 与 Transactional Outbox

**状态：** Accepted
**日期：** 2026-09-03
**关联：** PD-034、PD-036、PD-037、PD-089；ADR-006、ADR-008、ADR-009

## Context

当前 Go/Python 队列使用 Redis list 和 BRPOP/LPUSH，消息采用版本化 JSON envelope，但缺少 Redis Streams、consumer groups、ACK、pending reclaim、Transactional Outbox 和 dead-letter 重放机制。冻结产品决策要求 Redis Streams 作为任务与事件总线，Transactional Outbox 保证数据库写入和消息发布一致。

## Decision

目标消息架构冻结为：

- Redis Streams + Consumer Groups 作为任务与事件传递方式。
- 交付语义为 at-least-once，消费者必须按幂等键处理重复。
- 每条消息使用显式 ACK；失败消息进入 pending，支持受控 reclaim。
- 持久化业务变化前先写 Transactional Outbox，由 dispatcher 发布到 Streams。
- 超过重试上限的消息进入 dead-letter，支持人工受控重放。
- 消息保留显式 event version，禁止运行时猜测版本。
- 单分区内按写入顺序消费；跨分区/跨主题不承诺全局严格顺序。

## Consequences

- 当前 Redis list 分类为 CURRENT_CONFLICT。
- 迁移期间不能保留双队列语义分叉；必须提供兼容或停机切换策略。
- 所有 Go/Python 生产消费者必须实现幂等入库和显式 ACK。
- MySQL 权威写入由 Go 控制面协调，Python 交付结果，不直接双写。
- DuckDB 只接收分析/导出数据，不作为消息或任务状态权威。
- 本 BUILD 不修改任何队列代码、`docker-compose.yml` 或 Redis 协议 fixture。

## Alternatives

- 继续使用 Redis list：无 consumer group、无 ACK/pending reclaim，无法满足可靠性决策，不采用。
- Redis Pub/Sub：消息易丢失、无持久化，不采用。
- 外部 MQ：超出 V1 单机内部部署边界，不采用。
- 每服务独立队列且不做 outbox：无法保证数据库与消息一致性，不采用。

## Migration

1. 冻结 Streams 消息主题、envelope 和幂等键。
2. 先建立 outbox 表与 dispatcher 合同。
3. 以双消费者或受控切换方式迁移 Python/Go 生产路径。
4. 完成 pending reclaim、dead-letter 和 replay 测试后再移除 list 路径。
5. Redis list 作为历史实现保留记录，不作为目标架构。

## Current Status

- CURRENT_CONFLICT：Redis list BRPOP/LPUSH
- TARGET_V1：Redis Streams + Consumer Groups + Transactional Outbox
- 当前队列代码未迁移，本文是目标决策，不是完成证明。

## References

- `docs/PRODUCT_DESIGN_V1.0.md`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- ADR-006、ADR-008、ADR-009
