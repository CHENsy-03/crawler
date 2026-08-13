# SearchPlan Python 执行契约

状态：已冻结，作为 TASK-017E 功能实现的输入契约。

本文件描述 SearchPlan 在 Python Search Worker 内部执行、解析结果并按既有 `crawler:url` 协议输出的规则。

## 1. 架构职责

- SearchPlan 由 Python Search Worker 生成或读取缓存。
- SearchPlan 只在同一个 Python Worker 进程内交接。
- Python 负责执行 SearchPlan。
- Go 不解析、不执行、不消费 SearchPlan。
- SearchPlan 不写入任何 Redis 输出队列。
- SearchPlanCache 仅为生成阶段的内部优化，不是结果交付通道。
- 执行结果继续使用既有 `crawler:url` 和 `URLMessage`。
- 执行错误继续使用既有 `ErrorMessage` 和 `SEARCH_FAILED`。

不新增：

- SearchPlan 结果消息。
- SearchPlan Redis 队列。
- 计划执行队列。
- ACK 队列。
- 新 protocol version。
- 新 `URLMessage` 字段。
- 新 `ErrorMessage` 字段。

## 2. 执行适配器位置与入口

冻结位置：

```text
crawler/search/plan_executor.py
```

冻结 Python 内部入口：

```python
execute_search_plan(
    plan: SearchPlan,
    keywords: tuple[str, ...],
    *,
    fetcher: SearchPlanFetcher,
) -> SearchExecutionResult
```

- `SearchPlanFetcher` 是可注入的 Python HTTP 抽象。
- 测试使用 fake，不访问真实网络。
- `SearchExecutionResult` 是 Python 内部值对象。
- 结果候选至少包含 `url`、`title`、`keyword`。
- 不为这些内部类型增加 JSON 序列化。
- 不创建对应 Go 类型。
- `target_url`、`task_id`、`message_id`、输入 `timestamp` 由 Worker 保存，不写入 SearchPlan。

Worker 调用链：

```text
严格解码 v2 search_requested
→ _generate_v2_plan()
→ execute_search_plan()
→ Worker 将候选映射为现有 URLMessage
→ 发布到现有 crawler:url
→ continue
```

不得进入 legacy `plugin_search()`。

## 3. 可执行计划规则

只有以下状态可执行：

```text
ready
active
```

以下状态不得执行：

```text
draft
expired
invalid
未知状态
```

计划还必须同时满足：

- `strategy` 为 `html_form` 或 `json_api`。
- `http_method` 为 `GET` 或 `POST`。
- `endpoint` 为合法绝对 HTTP/HTTPS URL。
- `pagination` 字段合法。
- `scope` 字段合法。
- 解析所需 selector 完整。
- 至少存在一个 `{keyword}` 占位符。

状态为 `ready/active` 但缺少执行所需字段，应视为上游生成错误，不允许执行器猜测或降级。

## 4. keywords 与模板规则

执行器直接接收严格消息解码后已经规范化的 `tuple[str, ...]`。

规则：

1. 保持输入顺序。
2. 不重新排序。
3. 不新增关键词。
4. 不重新做同义词扩展。
5. 不把 keywords 写入 SearchPlan。
6. 按关键词顺序逐个执行。
7. 同一关键词内按页码升序执行。
8. 最终 URL 去重时第一次出现者获胜。

支持的占位符仅限：

```text
{keyword}
{page}
{page_size}
```

替换范围：

- `query_params` 的字符串值。
- `request_body_template` 的字符串叶节点。

禁止在以下位置替换：

- `endpoint`。
- map/object 的键。
- `selectors`。
- `scope`。
- HTTP header 名称或值。

未知占位符、缺失 `{keyword}` 或未完成替换，一律拒绝执行。

关键词作为逻辑参数值交给 HTTP 客户端，只允许编码一次；不得预先 URL encode 后再次编码。

## 5. GET 与 POST 请求构造

### GET

- `endpoint`：请求 URL。
- `query_params`：复制后进行模板替换。
- `request_body`：不得发送。
- `pagination.page_param`：写入 query params。
- `pagination.page_size_param`：写入 query params。

分页字段由执行器覆盖同名模板值，不能由模板绕过。

### POST + html_form

- `query_params`：作为 URL query。
- `request_body_template`：模板替换后作为 form body。
- Content-Type：`application/x-www-form-urlencoded`。
- 分页字段：写入 form body 顶层。

### POST + json_api

- `query_params`：作为 URL query。
- `request_body_template`：模板替换后作为 JSON body。
- Content-Type：`application/json`。
- 分页字段：写入 JSON body 顶层。

GET 不得发送 body。

POST 时 `request_body_template` 必须是对象；不得接受任意字符串 body。

不得从 legacy `site_cfg` 补齐请求参数。

## 6. 分页规则

当前模型没有分页起点字段，因此冻结：

```text
起始页：1
结束页：pagination.max_pages
页码递增：1
page size：pagination.page_size
```

执行顺序：

```text
keyword[0] page 1..N
keyword[1] page 1..N
……
```

停止条件：

1. 达到 `max_pages`。
2. 当前页成功解析且结果项为空。
3. 请求或解析失败时终止整个执行并返回失败。

不得以“结果数量小于 page_size”作为停止条件。

若 `page_param` 为空：

```text
max_pages 必须等于 1
```

否则计划不可执行，避免重复请求同一页。

`page_size_param` 为空时不注入 page size。

执行器必须先完成请求和解析，得到完整候选集合，再交给 Worker 发布。请求或解析阶段失败时不得发布先前页面的部分结果。

## 7. HTML selector 语义

### html_form

selectors 使用 CSS selector。

必填：

```text
result_item
title
url
```

含义：

- `result_item`：选择结果记录容器。
- `title`：相对每个结果容器选择标题元素并读取规范化文本。
- `url`：相对每个结果容器选择链接元素并读取 `href`。
- `snippet`、`body`：可选，本阶段不进入 URLMessage。

任一必填 selector 为空、无效或无法按规则解析，计划不可执行。

不得自动回退到：

- 所有 `a[href]`。
- 按标签名称猜测。
- 按中文文字猜测。
- `plugins/html.py` 的 site_cfg 启发式分支。

## 8. JSON selector 语义

### json_api

selectors 使用 RFC 6901 JSON Pointer，不使用 JSONPath。

规则：

- `result_item`：从响应根对象定位结果数组。
- `title`：相对单个数组元素定位标题。
- `url`：相对单个数组元素定位 URL。
- `snippet`、`body`：可选。
- `result_item`、`title`、`url` 必填。
- `result_item` 必须解析为数组。
- `title` 和 `url` 必须解析为字符串。

不支持：

- 通配符。
- 递归下降。
- 过滤表达式。
- 脚本表达式。
- 猜测 `items/data/list` 字段。

## 9. URL 解析、规范化和 scope

候选相对 URL 使用实际响应的最终 URL执行 `urljoin`。

只接受：

```text
http
https
```

拒绝：

- `javascript:`
- `data:`
- `file:`
- `ftp:`
- 空 URL
- 含用户名或密码的 URL

规范化规则：

1. scheme 和 hostname 小写。
2. hostname 使用统一 IDNA 表示。
3. 移除 fragment。
4. 移除默认端口。
5. 保留 path。
6. 保留 query，不擅自删除参数。
7. 同一规范化 URL 只保留第一次出现。

scope 校验：

- 候选 hostname 必须等于 `scope.domain`，或是其合法子域。
- 不允许仅通过字符串后缀伪造域名。
- path 必须命中至少一个 `allowed_path_prefixes`。
- path prefix 按路径边界比较，不能让 `/news-old` 误匹配 `/news`。
- 不满足 scope 的候选直接丢弃。
- 不得发布越界 URL。

HTTP endpoint 是否允许请求由 SearchPlan 自身及既有安全校验决定；不得因为候选 scope 规则而自动改写 endpoint。

## 10. URLMessage 映射

v2 成功候选映射到现有 `URLMessage`：

```text
url     = 规范化后的候选 URL
site    = 规范化后的 plan.scope.domain
keyword = 产生该候选的当前 keyword
level   = 0
title   = 解析并规范化后的候选 title
```

规则：

- 不修改 `URLMessage` 模型。
- 不新增 `task_id`、`message_id`、`timestamp`。
- 这些关联字段仅保留在 Worker 日志和既有错误链路中。
- 不把 `target_url` 填入 `site`。
- 不把全部 keywords 拼接到单数 `keyword`。
- 每个候选使用实际产生它的关键词。
- 发布顺序等于执行器输出顺序。
- 跨关键词或跨页面重复 URL 只发布第一次。

## 11. 错误规则

本阶段不新增错误码。

所有 v2 搜索阶段对外错误统一复用：

```text
SEARCH_FAILED
```

内部阶段可在日志中分类：

```text
analysis_failed
no_candidates
no_executable_plan
plan_execution_failed
response_parse_failed
no_eligible_urls
```

但这些内部分类：

- 不是新协议错误码。
- 不写入 Go enum。
- 不写入 `docs/REDIS_PROTOCOL.md` 的 error_code 集合。
- 不进入新的消息字段。

对外错误文本只能使用固定、无敏感信息的安全文案，例如：

```text
Search analysis failed
No executable search plan
Search plan execution failed
Search response parsing failed
No eligible search results
```

不得包含：

- 完整 URL query。
- HTML。
- response body。
- Cookie。
- Token。
- Authorization。
- Redis 异常原文。
- traceback。
- 原始异常 repr。

发布错误失败时：

- 只记录安全日志。
- 不重新分析。
- 不重新构建。
- 不重新执行计划。
- 不重新写缓存。
- 不通过另一个新队列补偿。

继续保持现有 BRPOP 后处理的交付语义。

## 12. 当前 selectors 上游缺口

当前 `PlanBuilder` 生成：

```text
SearchSelectors("", "", "", "", "")
```

因此当前计划不能仅凭现有字段严格执行。

冻结规则：

- 必填 selectors 为空的计划不能标记为可执行。
- 执行器不得通过启发式解析掩盖上游缺口。
- 在正式实现 TASK-017E 前，必须让 Analyzer/PlanBuilder 能产生符合本契约的 selectors。
- 如果现有 Analyzer 候选模型没有足够信息生成 selectors，必须先修改分析阶段契约。
- 该上游修复应作为独立后续任务，不能暗中混入执行器。

### 12.1 Analyzer → PlanBuilder → SearchPlan 矩阵

| strategy | 当前 Analyzer 是否提供解析证据 | 能否生成 result_item/title/url | 缺失字段 | 最小上游修改文件 |
| --- | --- | --- | --- | --- |
| html_form | 否 | 否 | selectors.result_item、selectors.title、selectors.url | crawler/site/models.py、crawler/site/forms.py、crawler/site/analyzer.py、crawler/search/plan_builder.py |
| json_api | 否 | 否 | selectors.result_item、selectors.title、selectors.url | crawler/site/models.py、crawler/site/signatures.py、crawler/site/analyzer.py、crawler/search/plan_builder.py |
| unknown | 不适用 | 否 | strategy 本身不可执行，且无 selector 证据 | 不适用 |

当前 `SearchCandidate` 只有 `method`、`endpoint`、`keyword_param`、`fixed_params`、`request_encoding`、`source`、`priority`、`scope`、`evidence`、`status`，没有 CSS selector 或 JSON Pointer 字段。

当前 `PlanBuilder` 的 `_SOURCE_STRATEGY` 将 `form` 映射为 `html_form`，将 `trs_signature`、`jpaas_signature` 映射为 `json_api`，但 `SearchSelectors` 使用 SearchPlan 默认空值。

因此 TASK-017E 功能实现被上游 selector 生成能力阻断。

## 13. 非目标

- 不实现 SearchPlan 执行器。
- 不修改 Analyzer、PlanBuilder、PlanCache 或 SearchPlan。
- 不进入 legacy `plugin_search()`。
- 不新增任何 Redis 队列、消息类型或协议字段。
- 不将 SearchPlan 发布到 Redis。
- 不开始 TASK-017F。
## 14. TASK-017E 实施状态与 URLMessage 发布

- 状态：TASK-017E 已实现。
- Python 通过 `protocol.messages.URLMessage.to_dict()` 输出顶层 JSON 并发布到 `crawler:url`。
- Go 当前通过 `PopURL()` + `json.Unmarshal` 宽松解码共同字段 `task_id/url/site/keyword/level/title`。
- `protocol_version/message_id/timestamp/type` 当前被 Go 忽略；缺失旧 `time` 不影响当前 worker。

缓存生命周期：
- 新构建计划先正式执行，`success/no_results` 后才写入缓存。
- 新计划其他执行失败不写缓存。
- 缓存命中计划执行失败时删除对应缓存，本次不重试，下一条独立任务重新分析。
- 删除失败会记录安全 warning，不替换原始 executor 失败，缓存可能保留到 TTL。
- `no_results` 表示结构有效但结果为空，计划保留且零发布。
- `publish_failure` 不使已验证合法计划失效。
- BRPOP 仍为既有 at-most-once 语义。
- 本轮未修改 Go 或消息协议；TASK-017F 已完成 Python/Go 全量离线回归与生产解码契约验证。
- 共享 fixture：`tests/fixtures/url_message_contract.json` 由 Python 正式 `URLMessage.to_dict()` 约束；Go 契约测试通过 go-redis hook 拦截 BRPOP 并注入 fixture，实际调用 `RedisQueue.PopURL()`，经 `pop()` 中的生产 `json.Unmarshal` 解码为生产 `HTMLPayload`。
- `failed`/`no_results` 零发布；`publish_failure` 保留实际 `published_count`；SearchPlan 不进入 `crawler:url`。


## 15. TASK-018B 内部 schema 实施说明

TASK-018B 已将 SearchPlan 内部 schema 提升到 `plan_schema_version=2`，并引入结构化 `request_shape`、新 `pagination`、`adapter/request_format/response_format`。旧 `query_params/request_body_template` 不再属于新 schema。

当前 executor 仅提供单页过渡执行；`max_pages>1` 返回 `plan_not_executable`。多页、TRS、JPAAS 和 Generic JSON 的正式执行由 TASK-018C–G 完成，不在本轮交付。


## 16. TASK-018C HTML Adapter 说明

HTML 计划由 `HTMLSearchAdapter` 执行，覆盖 GET query 与 POST form-urlencoded。HTML 响应解析只使用唯一 `html_response_parser.py`。第一页零结果返回 `no_results`，后续页零结果或零新增 URL 停止；后续页失败时整次执行返回失败且不发布部分结果。结果 URL 必须通过 http/https、userinfo、domain 和 path scope 校验。

Registry 尚未接入 orchestrator；其他 Adapter 未实现。
