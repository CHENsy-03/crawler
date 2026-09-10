# ADR-028: DEV-005 v3 Redis Stream message protocol

**状态：** accepted

**日期：** 2026-09-09

**关联：** ADR-025、ADR-026、DEV-002、DEV-004、DEV-005

## Context

V1.0 §13.2 要求 Redis 内部消息使用公共信封并显式区分
`protocol_version/type/payload`；V1.1 §9 要求 Stream 消息携带固定
`work_class`。现有 Python/Go v1/v2 消息没有这些公共字段，
不能在不破坏旧消息语义的前提下原位增加必填字段。

## Decision

本 ADR 仅记录 owner 批准的 DEV-005 首轮契约选择，不属于冻结 DOCX 原文：

1. 五类业务 Stream 消息使用独立 v3 信封，
   `protocol_version` 固定为字符串 `"3.0"`。
2. 外层 `type` 与 canonical `event_type` 一致：
   `search_requested`、`url`、`html`、`result`、`error`。
   v3 result 不使用 `article_result` alias。
3. canonical dictionary `contract_version` 从 `1.1` 更新为 `1.2`；
   这是字典版本，不是产品基线版本，不修改冻结 DOCX。
4. 保留全部旧 canonical 记录，仅新增五条
   `STREAM_MESSAGE/version="3"` 记录。
5. capacity 使用独立 `internal_control` v1 payload，
   不套用业务 Stream v3 信封。
6. v3 html 使用内部受控 artifact 引用；
   result 不自动增加 `artifact_ref`。

## Version relationship

canonical `events[].version` 是事件/payload 主版本数字；
wire `protocol_version` 是 `主.次` 字符串。对 v3 不兼容变更，
两者同时为 `3` / `"3.0"`。旧 v1/v2 canonical 记录保持原值，
不降级为历史。

## Identifier boundary

`task_id`、`event_id`、`aggregate_id` 是实体/业务聚合 ID，
按 ADR-026 使用 canonical ULID。`message_id`、`causation_id`、
`correlation_id`、`idempotency_key` 不是实体主键，
使用独立 opaque 字符规则；不把全部字符串机械套用 ULID。

## Artifact boundary

v3 html 使用 `artifact_ref/checksum/content_type/byte_size`：

- `artifact_ref` 是内部不可变对象引用，解析为 FetchArtifact.storage_key
  语义，不接受绝对路径或路径穿越；不是外部 evidence_handle。
- `checksum` 是所引用对象原始字节 SHA-256 小写十六进制；
  不是规范化正文 content_hash。
- 本轮只验证引用格式、字段关系和边界，不验证真实文件存在、
  授权、大小或内容哈希。

## B2 artifact_ref grammar

v3 html 的 `artifact_ref` 统一为内部、相对、正斜杠分隔的受控对象键：

- 只允许段字符 `[A-Za-z0-9._:-]`，段之间使用单个 `/`。
- 拒绝空白、反斜杠、绝对路径、盘符前缀、空路径段和尾随斜杠。
- 拒绝独立 `.` / `..` 路径段；文件名内部含 `..`（如 `a..b`）允许。
- 不做 URL 解码或路径规范化后再接受；schema/Python/Go 对同一字符串同判。

## B2 numeric strategy

- JSON 数字按数学整数语义处理；`1`、`1.0`、`1e0` 对整数字段同判。
- Python 使用 `decimal.Decimal` 精确解析；Go 使用原始 token 转
  `math/big.Rat`，不先转 float64。
- 非标准 JSON `NaN/Infinity/-Infinity` 在 JSON 解析层拒绝。
- `matched_evidence.weight` 必须有限且非负；编码出口禁止 NaN/Infinity。

owner 已批准以下传输边界（2026-09-09）。这是 DEV-005 协议传输边界，
不是冻结 DOCX 原文新增：

| 字段 | 范围 | 来源 |
|---|---|---|
| attempt_no | 0..4294967295 | TaskAttempt/TaskStage `INT UNSIGNED` |
| level | 0..4294967295 | 本次 owner 批准的传输边界；不代表允许实际爬取该深度 |
| score | 0..4294967295 | 结果表 `INT UNSIGNED` |
| byte_size | 0..20971520 | V1.0 detail/附件 20 MiB 上限 |
| state_version | 1..9007199254740991 | 本次 owner 批准的传输边界；是状态修订号，不是 schema 版本 |
| emergency_reserve_bytes | 1..9007199254740991 | 本次 owner 批准的传输边界；默认值/切换/耗尽仍服从联合基线 |

`level` 上界不授权执行对应深度；`state_version` 不因数值增大被解释为
未知 schema 版本；紧急配额字段不代表生产者可自行提高配额或优先级。

## Baseline alignment record

- `attempt_no`：V1.0 §13.2 规定非负整数，§9.5 规定同一任务单调递增；
  DEV-004 TaskAttempt/TaskStage 使用 `(task_id, attempt_no)` 且列为
  `INT UNSIGNED`。未发现独立业务上界冲突；传输上界与存储边界一致，
  不改变任务 attempt 语义。
- `score`：当前 v3 result payload 的 `score` 对应现有 ArticleResultV2/
  TaskArticle 结果分数字段，不是未来的 quality_score 0-100；
  结果列类型为 `INT UNSIGNED`。未发现该映射冲突。
- `byte_size`：V1.0 的 20 MiB 属于 detail/附件 body profile，
  V1.1 禁止在队列中复制 20 MiB 原始 bytes；当前 v3 html 引用的正是
  detail/fetch artifact。该上限不是对任意未来 artifact 类型的通用证明；
  其他 artifact 类型需单独 profile。

## Work class and capacity

- 固定映射：`crawler:search/search_requested=ROOT`，
  `crawler:url/url=ROOT`，`crawler:html/html=CONTINUATION`，
  `crawler:result/result=CONTINUATION`，
  `crawler:error/error=TERMINAL`。
- 业务消息不得携带自授权容量字段。
- 磁盘状态、state_version 与紧急配额由 capacity control v1 承载，
  不由普通业务消息冒充。

## Delivery semantics

- 同一 Stream entry 重投不改写原始消息体。
- claim/处理重试不自动修改消息体中的 attempt_no；
  attempt_no 非负整数，来源与 delivery/处理尝试相关，
  不等于 TaskAttempt。
- 人工重放使用新 message_id，保留 original_message_id/replay_no；
  本轮只记录约束，完整重放实现属于 DEV-105。
- Go 业务副作用与 Outbox 同事务提交后才 ACK；
  Python 下游 XADD 与上游 ACK 必须满足已批准原子交接不变量。

## Runtime boundary

本轮不接线 producer/consumer，不替换旧 worker，不改变旧搜索、
解析、评分与持久化运行行为。Redis Streams、MySQL、Outbox、
claim/reclaim、dead-letter 和 real-time capacity 仍是后续运行时任务。
