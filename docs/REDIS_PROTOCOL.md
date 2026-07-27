# Redis 跨运行时消息协议

## 1. 协议目标

定义 Go 与 Python 之间通过 Redis 队列交换的版本化 JSON 消息契约。所有消息共用一组公共信封字段，业务字段由 type 区分。

## 2. 版本规则

- 当前版本为 v1，protocol_version 固定为 "1.0"。
- 兼容的字段增补允许向后兼容。
- 不兼容的变更必须提升主版本号。

## 3. 公共信封

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| protocol_version | string | 是 | 固定为 "1.0" |
| task_id | string | 是 | 采集任务 ID |
| message_id | string | 是 | 消息唯一 ID |
| timestamp | string | 是 | RFC3339 UTC |
| type | string | 是 | search/url/html/result/error |

## 4. SearchMessage

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| site | string | 是 | |
| keyword | string | 是 | |
| level | int | 否 | 搜索深度 |
| max_pages | int | 否 | 必须为正整数 |
队列：crawler:search

约束说明：
- max_pages 必须为正整数，默认值 1。
- API 请求中传 0 时，在消息产生前规范化为 1。
- CLI 默认值为 1。
- 负数请求无效，应在入口层返回 400 Bad Request。

## 5. URLMessage

| 字段 | 类型 | 必填 |
|------|------|------|
| url | string | 是 |
| site | string | 是 |
| keyword | string | 是 |
| level | int | 否 |
队列：crawler:url

## 6. HTMLMessage

| 字段 | 类型 | 必填 |
|------|------|------|
| url | string | 是 |
| site | string | 是 |
| keyword | string | 是 |
| level | int | 否 |
| title | string | 否 |
| html | string | 是 |
队列：crawler:html

## 7. ResultMessage

| 字段 | 类型 | 必填 |
|------|------|------|
| site | string | 是 |
| keyword | string | 是 |
| level | int | 否 |
| url | string | 是 |
| title | string | 否 |
| publish_date | string | 否 |
| content | string | 否 |
| summary | string | 否 |
| score | int | 是 |
| matched_keywords | array[string] | 是 |
队列：crawler:result

## 8. ErrorMessage

| 字段 | 类型 | 必填 |
|------|------|------|
| stage | string | 是 |
| url | string | 否 |
| error_code | string | 是 |
| error | string | 是 |
| retryable | bool | 否 |
队列：crawler:error

## 9a. SearchDoneMessage

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| site | string | 是 | 站点 key |
| keyword | string | 是 | 搜索关键词 |
| url_count | int | 是 | 本次搜索推送的 URL 总数 |
| level | int | 否 | 搜索深度 |

队列：crawler:event

Python Search Worker 在完成所有 URLMessage 推送后，发送一次 SearchDoneMessage，
通知 Go 侧搜索阶段已结束及预期结果总数。
当前限制：一个任务严格对应一条 SearchDoneMessage。
将来一个任务对应多个关键词时，需按 message_id 聚合。

## 9. 队列与生产消费关系

| type | 队列 | 生产者 | 消费者 | 状态 |
|------|------|--------|--------|------|
| search | crawler:search | Go | Python | 已实施 |
| url | crawler:url | Python | Go | 目标未切换 |
| html | crawler:html | Go | Python | 当前已运行 |
| result | crawler:result | Python | Go | 当前已运行 |
| error | crawler:error | Go/Python | Go | 当前已运行 |

## 10. 字段类型约束

- timestamp 使用 RFC3339 UTC。
- task_id 由 Go 在任务创建时生成。
- message_id 每条消息唯一。
- score、level 为 JSON number。
- retryable 为 JSON boolean。
- 不设置 omitempty，空值也出现在序列化输出中。

## 11. 当前旧协议兼容状态

v1 模型当前仅作为目标协议定义，尚未接入运行队列。

现有 queue.HTMLPayload、api/server.py 和 parser/redis_worker.py 继续使用旧消息格式。TASK-004 不改变现有 Redis 生产者、消费者或队列名称。

| 差异项 | 旧协议 | v1 协议 |
|--------|--------|---------|
| 时间字段 | time | timestamp |
| 公共信封 | 无 | 5 字段信封 |
| 消息类型 | 单一 HTMLPayload | 5 种独立类型 |
| type 字段 | 无 | 每条消息必有 |
| 必填校验 | 无 | 有契约测试 |
| omitempty | 部分字段省略 | 全部输出 |

## 12. 后续迁移顺序

1. 定义 v1 结构体和测试（TASK-004 已完成）
2. 新增 crawler:search 队列
3. 调整 crawler:url 生产者/消费者
4. 升级 html 和 error 消息格式
5. 升级 result 消息格式
6. 废弃旧 HTMLPayload
