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

### publish_date 字段约束

- 字符串字段，表示文章的**来源发布日期**，与 crawl_time（抓取时间）语义不同。
- 推荐格式：YYYY-MM-DD（如 2026-07-27）。
- Go 端同时兼容 RFC3339 格式。
- 空字符串表示来源页面未提供有效发布日期。
- 非法格式值不会导致流水线失败，该字段将被视为未知（nil）。
队列：crawler:result

## 8. ErrorMessage

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| stage | string | 是 | search/download/parse/store |
| site | string | 是 | 站点 key |
| keyword | string | 是 | 搜索关键词 |
| level | int | 否 | 搜索深度 |
| url | string | 否 | 搜索错误允许空 |
| error_code | string | 是 | SEARCH_FAILED / DOWNLOAD_FAILED / PARSE_FAILED / STORE_FAILED |
| error | string | 是 | 可读错误信息 |
| retryable | bool | 否 | 错误性质标识 |
队列：crawler:error

| 字段 | 类型 | 必填 |
|------|------|------|
| stage | string | 是 |
| url | string | 否 |
| error_code | string | 是 |
| error | string | 是 |
| retryable | bool | 否 |

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

---

## 13. v2 协议（TASK-015）

### 13.1 版本规则

- v1 `protocol_version` 固定为 `"1.0"`。
- v2 `protocol_version` 固定为 `"2.0"`，新增 `target_url + keywords[]` 契约。
- 版本必须显式出现在每条 Redis 消息的 envelope 中。禁止根据 `target_url`、`keywords` 等字段组合静默猜测版本。
- 缺失版本返回确定性错误 `protocol_version is required`；未知版本返回确定性错误 `unsupported protocol_version "..."`。

### 13.2 v2 公共信封

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| protocol_version | string | 是 | 固定为 "2.0" |
| task_id | string | 是 | 采集任务 ID |
| message_id | string | 是 | 消息唯一 ID |
| timestamp | string | 是 | RFC3339 UTC |

示例：

```json
{
  "protocol_version": "2.0",
  "task_id": "task-015",
  "message_id": "msg-015",
  "timestamp": "2026-07-31T00:00:00Z"
}
```

### 13.3 SearchRequested v2

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| type | string | 是 | 固定为 "search_requested" |
| target_url | string | 是 | 绝对 http/https URL，必须有有效 host |
| keywords | array[string] | 是 | 规范化后至少一个非空白关键词 |
| level | int | 否 | 默认值 0 |
| max_pages | int | 否 | 默认值 1；负数在协议层拒绝，0 由入口层规范化为 1 |

完整示例：

```json
{
  "protocol_version": "2.0",
  "task_id": "task-015",
  "message_id": "msg-015",
  "timestamp": "2026-07-31T00:00:00Z",
  "type": "search_requested",
  "target_url": "https://example.gov.cn/search",
  "keywords": ["低空经济", "无人机"],
  "level": 1,
  "max_pages": 5
}
```

缺失 `level`/`max_pages` 时两端使用相同默认值（`level=0`、`max_pages=1`）；显式 `null` 两端一致拒绝。

### 13.4 target_url 校验

- scheme 按 URL 标准大小写无关比较，只接受 `http`/`https`。
- 必须包含有效 host。
- 拒绝前后空白：`" https://x"`、`"https://x "` 均返回明确错误，不静默裁剪。
- 端口必须是 0-65535 的整数；拒绝 `:abc`、`:99999`、尾随空端口 `https://x:`。
- 畸形 IPv6 authority（如 `https://[::1`、`https://[invalid]`）统一返回 `INVALID_TARGET_URL`，不泄漏原生 `ValueError`。
- 拒绝相对 URL、缺失 host、空字符串、全空白字符串、只有 userinfo 没有 host 的 URL。
- 本任务不扩展 SSRF、内网地址或 DNS 安全策略。

### 13.5 关键词规范化

- `keywords` 必须是 JSON 数组；字符串、对象、tuple 等非数组输入一律拒绝，返回 `INVALID_KEYWORD`。
- `keywords` 数组中的每个元素必须是字符串；JSON `null` 元素非法，不会按空白项移除。
- 对每个关键词执行首尾空白裁剪。
- 空字符串和全空白字符串不作为有效关键词，v2 列表中可直接移除。
- 按规范化后的字符串精确去重，不做大小写折叠。
- 保留首次出现顺序。
- 规范化后为空或值为 `null` 时返回明确错误。
- 示例：`[" 低空经济 ", "无人机", "低空经济", "   "]` -> `["低空经济", "无人机"]`。

### 13.6 必填字段、可选字段与未知字段

- 所有消息必须包含 `protocol_version`、`task_id`、`message_id`、`timestamp`。
- v1 必填：`type=search`、`site`、`keyword`；`site`/`keyword` 必须是非空字符串，缺失、null、空串、纯空白、非字符串均拒绝；可选：`level`、`max_pages`。
- v2 必填：`type=search_requested`、`target_url`、`keywords`；可选：`level`、`max_pages`。
- 未知字段两端一致拒绝并返回明确错误。
- v1 payload 携带 `target_url`、`keywords` 等 v2 专属字段时两端一致拒绝。
- v2 payload 携带 `site`、`profile`、`keyword` 等 v1 专属字段时两端一致拒绝。
- 缺失版本返回 `protocol_version is required`；未知版本返回 `unsupported protocol_version`。

### 13.7 SearchPlan/SearchHit 空集合规则

- `SearchPlan.query_params`、`SearchScope.allowed_path_prefixes`、`SearchDiscovery.evidence`、`SearchHit.matched_keywords` 是可选集合字段。
- 缺失、显式 `null` 或 nil 在解码后统一归一化为空容器。
- SearchPlan/SearchHit 的整数字段显式 `null` 一律拒绝；字段缺失仍遵守各自的必填、可选和默认值规则。
- map 空值输出 `{}`，list/slice 空值输出 `[]`，协议 JSON 不输出 `null`。
- Go 直接 `json.Marshal` 零值结构体和 Python `to_dict()`/`to_json()` 行为一致。
- 必填集合字段不会因该规则变成可选。

### 13.8 确定性 plan_id

- 参与字段：protocol_version、strategy、endpoint、http_method、query_params、request_body_template、pagination、selectors、scope、discovery、created_from。
- 排除字段：plan_id、status、created_at、expires_at、invalid_reason。
- canonical 规则：UTF-8、键稳定排序、紧凑分隔符、无末尾换行。
- `<`、`>`、`&` 不进行 HTML 转义。
- U+2028、U+2029 统一输出为小写形式 `\u2028`、`\u2029`。
- 哈希算法：SHA-256，十六进制小写。
- Go 与 Python 对同一 canonical 输入必须得到相同 plan_id。
- 共用 fixture：`workspace/crawler/tests/fixtures/redis_protocol_v2.json`，其中包含 Unicode canonical 与硬编码预期 ID。

### 13.9 API 冲突矩阵

| 请求版本 | 字段组合 | 结果 |
| --- | --- | --- |
| 缺失版本 | 旧 v1 `site` + 字符串 `keywords` | 固定映射 v1 |
| 缺失版本 | `target_url` 或数组 `keywords` | 400，明确要求 v2 协议版本 |
| "1.0" | v1 字段 | v1 |
| "1.0" | `target_url` 或数组 `keywords` | 400 字段冲突 |
| "2.0" | v2 字段 | v2 |
| "2.0" | `site`、`profile`、`keyword` | 400 字段冲突 |
| 未知版本 | 任意 | 400 unsupported protocol version |
| 正确版本 | 缺少必填字段 | 400 必填字段错误 |
| 任意 | 未知字段 | 400 明确未知字段错误 |
| v1 | 同时存在 `site` 与 `profile` | 400 site and profile are mutually exclusive |
