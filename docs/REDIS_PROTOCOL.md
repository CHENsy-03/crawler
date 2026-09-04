# Redis 跨运行时消息协议

## 1. 协议目标

定义 Go 与 Python 之间通过 Redis 队列交换的版本化 JSON 消息契约。所有消息共用一组公共信封字段，业务字段由 type 区分。

## 2. 版本规则

- 当前版本为 v1，protocol_version 固定为 "1.0"。
- v2 使用显式 protocol_version "2.0"，用于 SearchRequested 和 ArticleResult 消息族；v1 保持不变。
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
| url | crawler:url | Python | Go | v2 已切换；v1 legacy 保留 |
| html | crawler:html | Go | Python | 当前已运行 |
| result | crawler:result | Python | Go | 当前已运行 |
| error | crawler:error | Go/Python | Go | 当前已运行 |

- TASK-017 v2 主链向 `crawler:url` 发布正式 `URLMessage`（无旧 `time`）；Go 通过 `PopURL()`/`pop()` 中的生产 `json.Unmarshal` 读取共同字段，契约测试使用 go-redis hook 注入 BRPOP 结果；v1 legacy 旧消息路径保留且未修改。

## 10. 字段类型约束

- timestamp 使用 RFC3339 UTC。
- task_id 由 Go 在任务创建时生成。
- message_id 每条消息唯一。
- score、level 为 JSON number。
- retryable 为 JSON boolean。
- 不设置 omitempty，空值也出现在序列化输出中。

## 11. 当前旧协议兼容状态

v1 模型当前仅作为目标协议定义，尚未接入运行队列。

现有 queue.HTMLPayload、api/server.py（内联 Parser 已于 TASK-019B-4D 退役）和 parser/redis_worker.py（已于 TASK-019B-4C 退役）当时继续使用旧消息格式。TASK-004 不改变现有 Redis 生产者、消费者或队列名称。

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
- 共用 fixture：`tests/fixtures/redis_protocol_v2.json`，该路径相对于当前 Git 仓库根目录，其中包含 Unicode canonical 与硬编码预期 ID。
- Go 与 Python 协议测试共同引用这一份 canonical fixture；不得复制或移动 fixture。

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



## 14. ArticleResult v2 消息族

TASK-019B-1 冻结 ArticleResult v2 协议合同，protocol_version=2.0。
TASK-019B-2 已把 Python v2 orchestrator 生产侧切换为 URLMessageV2 发布。TASK-019B-3 已接通 Go 严格解码、单次下载与 HTMLMessageV2 扇出；仍无任务结束合同，当前检查点不可部署。


历史 tests/fixtures/url_message_contract.json 中的 protocol_version=2.0 + site/keyword 属于过渡形态，不再代表正式 URLMessageV2；生产分流入口会拒绝该形态。

所有 v2 消息使用公共信封：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| protocol_version | string | 是 | 固定为 "2.0" |
| task_id | string | 是 | 任务 ID |
| message_id | string | 是 | 消息 ID |
| timestamp | string | 是 | RFC3339 UTC |
| type | string | 是 | url / html / article_result |

版本和 type 必须显式分流，禁止根据字段猜测协议版本。

### 14.1 URLMessageV2

type 固定为 `url`，队列目标仍为 `crawler:url`。

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| hit_id | string | 是 | 非空白 |
| plan_id | string | 是 | 非空白 |
| original_query | string | 是 | 规范化后的用户原始关键词 |
| query_term | string | 是 | 实际执行的原词或扩展词 |
| url | string | 是 | 绝对 HTTP/HTTPS URL |
| title | string | 是 | |
| snippet | string | 是 | 允许空字符串 |
| published_at | string | 是 | 允许空字符串 |
| source | string | 是 | 非空白 |
| level | int | 是 | 非负整数 |

### 14.2 HTMLMessageV2

type 固定为 `html`，队列目标仍为 `crawler:html`。生产格式仅允许 HTML。

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| hit_id | string | 是 | 非空白 |
| plan_id | string | 是 | 非空白 |
| original_query | string | 是 | 非空白 |
| query_term | string | 是 | 非空白 |
| requested_url | string | 是 | 绝对 HTTP/HTTPS URL |
| final_url | string | 是 | 绝对 HTTP/HTTPS URL |
| content_type | string | 是 | text/html 或 application/xhtml+xml，允许合法参数 |
| title | string | 是 | |
| snippet | string | 是 | 允许空字符串 |
| published_at | string | 是 | 允许空字符串 |
| source | string | 是 | 非空白 |
| level | int | 是 | 非负整数 |
| html | string | 是 | 仅作为队列传输内容，不定义为数据库持久化字段 |

### 14.3 MatchedEvidence

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| term | string | 是 | 非空白 |
| origin | string | 是 | original / expanded |
| field | string | 是 | title / summary / content / url |
| weight | number | 是 | 有限非负数 |

序列化顺序固定为 `term、origin、field、weight`；集合为空时输出 `[]`。

### 14.4 ArticleResultV2

type 固定为 `article_result`，队列目标仍为 `crawler:result`。

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| hit_id | string | 是 | 非空白 |
| plan_id | string | 是 | 非空白 |
| original_query | string | 是 | 非空白 |
| query_term | string | 是 | 非空白 |
| requested_url | string | 是 | 绝对 HTTP/HTTPS URL |
| final_url | string | 是 | 绝对 HTTP/HTTPS URL |
| canonical_url | string | 否 | 空或绝对 HTTP/HTTPS URL |
| title | string | 否 | 允许空字符串 |
| publish_date | string | 否 | 允许空字符串 |
| source | string | 是 | 非空白 |
| summary | string | 否 | 允许空字符串 |
| content | string | 否 | 允许空字符串 |
| content_hash | string | 否 | 正文非空时为正文 UTF-8 的 SHA-256 小写十六进制 |
| score | int | 是 | 非负整数，boolean 不是整数 |
| matched_evidence | array | 是 | 空输出 []，不允许 null |
| status | string | 是 | accepted / review_required / irrelevant / extract_failed / unsupported_format |
| extraction_method | string | 是 | site_selector / cms_rule / ai / density / fallback / pdf / docx / xlsx / none |

显式 null、未知字段、非法 URL、非法状态、非法哈希、非法 score 和非法 evidence 必须两端一致拒绝。


## 15. TASK-019B-4：crawler:html v2 消费与 crawler:result 发布

TASK-019B-4 已接通 Python 侧 v2 详情链：

- 正式链 `workers/parser_worker.py` 是 `crawler:html` 的单 BRPOP 消费者，按 `protocol_version` 显式分流；缺版本与 `1.0` 走 legacy/v1，`2.0` 走 B1 `HTMLMessageV2` 严格解码。`parser/redis_worker.py` 已在 TASK-019B-4C 退役并删除，不再参与任何消息消费。
- 显式 null、非字符串版本、未知版本、非法 JSON、非对象 JSON、未知字段、非法 URL/MIME 均拒绝；解码失败不回退 v1，也不发布 v1 ErrorMessage。
- 每个合法 `HTMLMessageV2` 生成并严格验证一个 `ArticleResultV2`，写入 `crawler:result`。
- `extract_failed/review_required/irrelevant/accepted` 均发布；不静默删除低分、不相关或待复核结果。
- 原始 HTML 仅存在于消息与进程内存中，不写入 ArticleResultV2、文件、MySQL、DuckDB 或附件目录。
- 当前 `crawler:result` 的 Go 持久化消费者尚未接通，当前检查点不可部署。
- B3 Windows Race Detector 已正式通过；B4 未修改 Go 队列或下载代码，也未重复执行 Race Detector。
- TASK-019B-4C 已退役并删除 `parser/redis_worker.py`；`workers/parser_worker.py` 是唯一正式 Python 消费者。

- TASK-019B-4D 已退役 `api/server.py` 内联 Redis Parser；`api/server.py` 不再读取或消费 `crawler:html`。

## 16. TASK-019B-5 存储合同说明

- ArticleResultV2 仍发布到 `crawler:result`。
- Go v2 生产消费者尚未接入；当前 `crawler:result` 仍由旧 ResultMessage v1 路径消费。
- TASK-019B-5 仅建立 `articles/task_articles` 与 `PersistArticleResultV2` 合同，未接线、未执行迁移、不可部署。

## 17. TASK-019B-6：crawler:result 分流已接通

- 正式 Worker 使用单次 `PopResultDispatch()` 显式分流。
- 缺失版本与 `1.0` 继续走旧 v1 ResultMessage 路径。
- `2.0` 严格解码 ArticleResultV2，并调用 `PersistArticleResultV2`。
- v2 不更新旧 task 状态、不修改 article_count、不经过旧 URL 去重。
- `PopResultMessage/PopResult` 保留兼容，但不再作为生产入口。
- 当前无 ACK/重试/死信/背压；BRPOP 后数据库瞬时失败可能丢失消息，由 TASK-021 处理。

## 18. TASK-019B-7 隔离 E2E 结果

- 真实隔离 Redis/MySQL 已验证 `crawler:result` 正式消费者到 `PersistArticleResultV2` 的路径。
- replay、conflict rollback、全部状态、legacy/v1 共存和非法版本隔离均通过。
- BRPOP 仍无 ACK、重试、死信或背压；该风险保留。

## 19. TASK-019B-8/8R 全链验证

- crawler:url 正式分流修复为显式 protocol_version 判定；null/非字符串拒绝且不下载。
- 本地 httptest 到正式 Python parser 再到 Go 持久化路径通过。
- PDF MIME 不产生 HTML/result；非法消息后合法 barrier 贯通。
- Redis BRPOP 仍无 ACK、重试、死信和背压。

## 20. PDF/Office MIME 边界

- v2 下载链仅接受 `text/html` 与 `application/xhtml+xml`。
- PDF/Office MIME 在 Go `FetchHTML` 阶段拒绝，不产生 `crawler:html` 或 `crawler:result`。
- `unsupported_format` 只是协议状态，当前不由正式链生成。
