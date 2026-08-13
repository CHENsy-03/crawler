# 统一 Search Adapter 契约（TASK-018 定义）

状态：accepted，已冻结。协议判别字段已确定为正式 `adapter` 字段，不再使用 `discovery.source` 或运行时猜测分派。

## 1. 范围

TASK-018 定义统一正式执行层，覆盖：

- HTML GET
- HTML POST form
- TRS
- JPAAS
- 通用 JSON GET
- 通用 JSON POST

目标输出统一 `SearchPlanExecutionResult`，由 v2 orchestrator 决定缓存和 `URLMessage` 发布。

## 2. 当前现状审计

| 搜索形态 | 当前发现方式 | 当前请求实现 | 当前解析实现 | 是否进入 SearchPlan v2 | 是否正式执行 | 主要缺口 |
|---|---|---|---|---|---|---|
| HTML GET | forms、common_path、static_script、internal_link | legacy `plugins/html.py` GET | `_extract_results()` + selector evidence | 部分 | 部分 | legacy 与 plan_executor 重复；selector 依赖探测证据 |
| HTML POST form | `forms.py` 生成 `CandidateRequestShape` | probe 可构造 form body；plan_executor 部分支持 | selector evidence | 是 | 部分 | 新 schema 必须改用结构化 `request_shape` |
| TRS | `trs_signature` 静态签名 | legacy `plugins/trs.py` POST form JSON | `parser/api_parser.parse_trs_doc` | 否 | 否 | Candidate 无 request_shape；TRS 是 form POST + JSON 响应 |
| JPAAS | `jpaas_signature` 静态签名 | legacy `plugins/jpaas.py` GET JSON | JPAAS 嵌套 `appSearchResultBeanList` 展开 | 否 | 否 | 缺少 adapter 判别和嵌套规范化 |
| 通用 JSON GET | static_script/common_path 可生成候选 | 无正式执行 | probe JSON selector evidence | 否 | 否 | 当前 source 未映射到 executable adapter |
| 通用 JSON POST | 当前无完整发现证据 | 无正式执行 | 无 | 否 | 否 | 缺少 JSON body 请求形状和 adapter 判别 |

## 3. 当前重复实现

- legacy `plugins/html.py`、`plugins/trs.py`、`plugins/jpaas.py` 各自实现请求构造和结果收集。
- `parser/api_parser.py` 与 `parser/multi_strategy.py` 承担 TRS/JPAAS 文本和日期清洗。
- `crawler/search/plan_executor.py` 已有通用 HTML/JSON 请求构造与 selector 解析。
- `crawler/site/search_probe.py` 已有安全 HTTP 探测和 selector evidence 提取。
- URL 规范化、scope 校验、结果去重在多个层级重复。

## 4. 正式判别决策

### adapter

正式字段 `adapter`，受控枚举：

```text
html
trs
jpaas
generic_json
```

`AdapterRegistry` 只根据已验证的正式 `adapter` 字段选择 Adapter。

禁止：

- 任意自由字符串；
- 根据 endpoint/hostname/selector 形状猜测；
- 以 `discovery.source` 作为正式分派字段；
- 运行时逐个尝试 Adapter。

### discovery.source

`discovery.source` 仅用于：

- 来源追踪；
- 证据审计；
- 日志诊断；
- 测试说明。

不得用于正式 Adapter 分派、请求编码选择、响应解析器选择或绕过 `adapter` 校验。

## 5. 请求与响应格式

受控字段：

```text
request_format
response_format
```

`request_format` 枚举：

```text
none
form_urlencoded
json
```

`response_format` 枚举：

```text
html
json
```

确定性映射：

```text
none
→ 不发送请求 body
→ 不主动发送 body Content-Type

form_urlencoded
→ application/x-www-form-urlencoded

json
→ application/json
```

响应格式用于选择解析器，并对实际响应 Content-Type 做受控兼容验证：

- `response_format=json` 接受 `application/json` 和合法的 `application/*+json`；
- `response_format=html` 接受 `text/html` 和项目明确支持的 XHTML 类型；
- 服务端错误标注 Content-Type 的兼容行为必须显式测试；
- 不得因 Content-Type 不匹配静默切换解析器。

如现有政府站点确实依赖错误 Content-Type，记录为待实现兼容测试，不得在文档中虚构已经支持。

## 6. 结构化请求形状

正式结构字段为 `request_shape`，优先复用或形式化当前 `CandidateRequestShape` 语义：

```text
keyword_location
keyword_path
fixed_query_params
form_fields
json_object_template
```

约束：

- `keyword_location`：`query`、`form`、`json`；
- `keyword_path`：统一定义关键词插入位置，使用结构化路径片段，不使用点号拼接模糊字符串；
- `fixed_query_params`：不可变、有序或 canonical 排序的 name/value 集合；
- `form_fields`：不可变 name/value 集合，keyword 字段与固定字段不得重名；
- `json_object_template`：使用结构化 path/value 表达，禁止以自由 JSON 字符串作为正式源。

`keyword_path` 按 `keyword_location` 定义：

| keyword_location | keyword_path 规则 | 示例 |
|---|---|---|
| query | 必须恰好一个非空片段 | `("q",)` |
| form | 必须恰好一个非空片段 | `("searchWord",)` |
| json | 必须包含一个或多个非空片段 | `("request", "keyword")` |

- query：`keyword_path` 是 query 参数名；关键词经标准 URL 编码后写入 query；不得同时出现在 `fixed_query_params`。
- form：`keyword_path` 是 form 字段名；关键词写入 `application/x-www-form-urlencoded` body；不得同时出现在 `form_fields`。
- json：`keyword_path` 逐层定位 JSON object 中的关键词字段；不得与 `json_object_template` 固定 path 重复；不得穿越非 object 节点。
- 路径片段必须是非空字符串，不得包含空片段，不得依赖点号字符串拆分，不得允许隐式数组索引，大小写原样保留。

固定字段边界：

- `fixed_query_params` 只存固定 query 参数；
- `form_fields` 只存固定 form 字段；
- `json_object_template` 只存固定 JSON path/value；
- `keyword_path` 只描述关键词插入位置。

关键词字段不得同时出现在对应固定字段集合中。发现冲突时返回 `plan_invalid`，不得由关键词值覆盖固定值，也不得静默忽略固定值。

TASK-018B 转换规则：

- Candidate keyword 在 query：`candidate.keyword_param` → `request_shape.keyword_path=(keyword_param,)`；
- Candidate keyword 在 form：`candidate.keyword_param` → `request_shape.keyword_path=(keyword_param,)`；
- Candidate keyword 在 JSON：`candidate.request_shape.keyword_path` → SearchPlan `request_shape.keyword_path`。

禁止继续依靠 `query_params` 中的 `{keyword}`、`request_body_template` 中的 `{keyword}`、运行时扫描 placeholder、Adapter 猜测常见字段名或 `discovery.source`。

请求构造器由结构化数据生成 query string、form-urlencoded body 或 JSON body；不得反向解析自由字符串恢复结构。

## 7. 合法字段组合

| adapter | method | request_format | response_format | keyword_location | keyword_path 长度 |
|---|---|---|---|---|---|
| html | GET | none | html | query | 1 |
| html | POST | form_urlencoded | html | form | 1 |
| trs | POST | form_urlencoded | json | form | 1 |
| jpaas | GET | none | json | query | 1 |
| generic_json | GET | none | json | query | 1 |
| generic_json | POST | json | json | json | >=1 |

JPAAS 当前已验证组合以现有正式 plugin 和 fixture 为准：GET、无 body、JSON 响应。如后续发现其他正式请求变体，必须列出受支持组合并要求注册表或 Adapter 严格验证。

不合法组合统一返回 `plan_invalid`，不得 fallback 到其他 Adapter。

## 8. 两层组合架构

```text
AdapterRegistry
→ Adapter
→ RequestBuilder
→ 统一安全 HTTP transport
→ ResponseParser
→ SearchPlanExecutionResult
```

边界：

- Adapter：验证字段组合，协调请求构造与响应解析，返回统一执行结果；
- RequestBuilder：只负责确定性请求构造，不发网络请求，不解析响应；
- ResponseParser：只处理受限响应，不发网络请求，不写缓存，不发布消息；
- Transport：执行现有受限 HTTP 策略，不理解 TRS/JPAAS 业务字段。

## 9. plan_id canonical

以下执行语义必须进入 canonical `plan_id`：

```text
adapter
strategy
http_method
endpoint
request_format
response_format
request_shape
pagination
selectors
scope
其他仍保留的执行语义
```

`keyword_path` 的全部片段都进入 canonical `plan_id`。以下变化必须改变 `plan_id`：

- query 参数名变化；
- form 字段名变化；
- JSON 嵌套路径变化；
- `keyword_location` 变化。

任何执行语义变化必须生成不同 `plan_id`。

禁止：

- 新增执行字段但不进入 `plan_id`；
- 只靠 `discovery.source` 影响执行却不进入 `plan_id`；
- 对字典顺序或原始 JSON 文本敏感。
- 新 schema 明确排除旧字段 `query_params` 和 `request_body_template`，它们不进入 canonical `plan_id`。
- 新 `pagination` 的全部字段（`enabled/location/value_path/start/step/page_size_path/page_size/max_pages`）都进入 canonical `plan_id`。

canonical 规则要求：

- 稳定字段顺序；
- UTF-8；
- 确定性 JSON；
- 无多余空白；
- 结构化路径稳定；
- 集合排序规则明确。

## 10. 内部 schema 与缓存迁移

外部消息协议不变：

```text
SearchRequestedMessage protocol_version
URLMessage protocol_version
URLMessage schema
crawler:search
crawler:url
Go HTMLPayload
```

SearchPlan 是内部执行协议。TASK-018B 实现时必须采用明确的内部 schema 版本策略：

- 新增或提升 `plan_schema_version`；
- 同步提升 SearchPlan cache envelope schema version。

要求：

- 新 ready plan 必须包含 `adapter/request_format/response_format/request_shape`；
- 旧缓存计划不得由 endpoint、source 或 selector 猜测补全；
- 旧 schema 缓存读取时按受控不兼容处理；
- 旧缓存不得进入 executor；
- 当前任务按 cache miss 路径重新生成计划；
- 重新生成成功后写入新 schema 缓存；
- 不得把旧缓存反序列化失败暴露为新的外部错误码。

如果当前缓存实现对不兼容 schema 使用 `corrupt` 而不是 `miss`，TASK-018B 必须先冻结准确状态语义：允许内部记录 `incompatible/corrupt`，对当前编排流程表现为不可执行缓存，进入安全重建路径。

## 11. request_body_template 迁移

- 新 schema 的 ready plan 以 `request_shape` 为唯一请求结构源；
- `request_body_template` 不得与 `request_shape` 同时成为双重真相；
- legacy v1 保持原样；
- 旧 SearchPlan 缓存安全失效；
- TASK-018B–F 将生产者迁移到 `request_shape`；
- 新 v2 ready plan 不依赖自由字符串 `request_body_template`；
- 删除或废弃旧字段必须在测试证明无生产引用后单独完成。

Adapter 不得在两个 body 字段不一致时任选其一。

## 12. Adapter 分派规则

```text
adapter=html
→ HTMLSearchAdapter

adapter=trs
→ TRSSearchAdapter

adapter=jpaas
→ JPAASSearchAdapter

adapter=generic_json
→ GenericJSONSearchAdapter
```

即使三者都是 `strategy=json_api`、`response_format=json`，也不得合并为依靠运行时响应猜测的单一分派。

内部可复用：

- HTTP transport；
- JSON 解码；
- JSON Pointer；
- 结果规范化；
- 去重；
- 安全限制。

TRS/JPAAS 特有请求与嵌套解析必须保留明确 Adapter 边界。

## 13. 错误语义

继续使用已有对外错误集合：

```text
plan_invalid
plan_not_executable
transport_failure
response_rejected
selector_mismatch
no_results
```

映射：

- 未知 adapter → `plan_invalid`；
- adapter 与 method/format 不一致 → `plan_invalid`；
- request_shape 不完整或冲突 → `plan_invalid`；
- 无法构造正式请求 → `plan_not_executable` 或现有最接近稳定语义，边界在 TASK-018B 实现时明确；
- HTTP 执行失败 → `transport_failure`；
- 响应超限或违反安全策略 → `response_rejected`；
- 预期解析器无法提取结构 → `selector_mismatch`；
- 合法响应、合法解析、结果集合为空 → `no_results`。

不得新增 Adapter 专属对外错误码。

## 14. 安全边界

TASK-018 继承 TASK-016/017 安全约束：

- 仅 http/https；
- 拒绝 localhost、保留地址和非标准端口；
- 限制重定向并逐跳重新验证；
- 限制响应体大小、超时和页数；
- 日志不记录凭据、完整敏感 URL 或响应正文。

留给 TASK-022：

- 连接级 IP 绑定；
- DNS rebinding 完整防护；
- 代理环境绕过防护；
- 生产域名策略；
- 更完整安全可观测性；
- 生产级 SSRF 验收。

TASK-018 不得削弱当前安全边界，也不得宣称已完成 TASK-022。

## 15. 复用与迁移策略

- 直接复用：`parser/api_parser.parse_trs_doc`、JPAAS 嵌套展开逻辑、`crawler/site/search_probe.py` 安全 transport、`plan_executor` 的规范化/去重。
- 提取为无状态解析函数：TRS doc 归一化、JPAAS 嵌套展开、HTML 结果提取。
- 由 Adapter 包装：现有 plugin 请求构造和响应解析。
- 最终废弃：与 plan_executor 重复的 legacy plugin 请求路径。
- legacy v1 保持不变。
- 迁移期间双路径并存，TASK-018 不直接删除 legacy v1。
- 删除旧路径放在 TASK-018H 或后续独立收敛任务。

## 16. 任务拆分

| 子任务 | 目标 | 是否修改产品代码 | 依赖 |
|---|---|---|---|
| TASK-018A | 本轮文档与协议决策冻结 | 否 | 用户决策已确认 |
| TASK-018B | SearchPlan 内部 schema 演进、adapter/request_format/response_format/request_shape、canonical plan_id、cache schema 不兼容处理、Adapter 接口/Registry/统一结果模型 | 是 | 018A |
| TASK-018C | HTML GET/POST，RequestBuilder + HTML parser | 是 | 018B |
| TASK-018D | TRS Adapter，复用现有 TRS 无状态逻辑 | 是 | 018B |
| TASK-018E | JPAAS Adapter，复用现有嵌套展开逻辑 | 是 | 018B |
| TASK-018F | Generic JSON GET/POST，JSON Pointer 与结构化 JSON body | 是 | 018B |
| TASK-018G | PlanExecutor/orchestrator 集成，缓存与发布边界不回归 | 是 | 018C-F |
| TASK-018H | 完整 Python/Go/跨语言门禁 | 否（测试/文档） | 018G |

TASK-018B 不得顺手实现完整 HTML/TRS/JPAAS/Generic JSON Adapter。

## 17. 测试矩阵

全部离线，使用 fake transport、mock、fixture、临时目录、内存对象。

覆盖：

- HTML GET 成功/零结果/selector mismatch；
- HTML POST form 成功/非法模板；
- TRS 成功/错误响应/嵌套字段；
- JPAAS 成功/错误响应/嵌套字段；
- Generic JSON GET/POST；
- 嵌套 JSON path；
- 分页边界；
- 响应体过大；
- 超时；
- 重定向拒绝；
- 跨 origin 结果；
- 重复结果；
- 部分解析成功；
- 未知 adapter；
- 不合法 adapter/method/format 组合；
- 请求构造确定性；
- 错误码稳定性；
- 旧 schema 缓存不兼容处理；
- 缓存生命周期不回归；
- failed/no_results/publish_failure 发布边界不回归；
- Python URLMessage → Go PopURL 契约不回归；
- legacy v1 不回归。

## 18. 总验收条件

1. 六类搜索形态均通过正式 Adapter 执行；
2. Adapter 选择只依据正式 `adapter` 字段；
3. 不依赖测试专用分派字段；
4. 不复制一套新的 TRS/JPAAS 业务逻辑；
5. 所有结果统一规范化；
6. 错误与 `no_results` 清晰区分；
7. 请求形状和分页有严格上限；
8. 无真实外部访问；
9. TASK-017 缓存与发布语义不回归；
10. Python/Go URLMessage 契约不回归；
11. legacy v1 保持；
12. BRPOP at-most-once 语义不变；
13. TASK-022 风险边界准确记录；
14. Python 完整回归不低于当前基线；
15. Go 完整回归和 `go vet` 通过；
16. 文档与实际测试一致。

## 19. 后续顺序与版本策略

正式冻结：

```text
TASK-018：统一正式执行 Adapter
→ TASK-022：生产级 SSRF 与连接级安全
→ TASK-020：未知站点 MVP 验收
```

版本、tag、release 策略推迟到 TASK-020 MVP 验收通过后定义。


## 20. 请求单一真相与分页契约

### 20.1 请求参数唯一真相

新 SearchPlan schema 冻结为：

- `request_shape` 是所有固定请求参数和关键词位置的唯一正式来源；
- `pagination` 是所有动态分页参数的唯一正式来源。

新 schema 不再使用顶层 `query_params`：

- 不接受；
- 不序列化；
- 不进入 canonical `plan_id`；
- 不供 Adapter 或 RequestBuilder 读取。

新 schema 不再使用 `request_body_template`：

- 不接受；
- 不序列化；
- 不进入 canonical `plan_id`；
- 不供新执行路径读取；
- form 和 JSON body 只能由结构化 `request_shape` 生成。

禁止过渡性双重读取：

- 优先 `request_shape`、缺少时读取 `query_params`；
- 优先 `request_shape`、失败时解析 `request_body_template`；
- 比较两个来源后任选其一；
- 运行时扫描 `{keyword}`、`{page}`、`{page_size}`。

旧 schema 缓存必须整体失效并重建。

### 20.2 endpoint query

新 ready plan 的正式 `endpoint` 必须是：

```text
scheme + authority + path
```

不得把固定 query 参数隐藏在 endpoint 中。

Candidate endpoint 如果带 query：

- PlanBuilder 必须确定性解析；
- 合并到 `request_shape.fixed_query_params`；
- 保存无 query、无 fragment 的 endpoint。

规则：

- 固定 query 参数名不得重复；
- 不得与 `keyword_path` 冲突；
- 不得与 `pagination` 路径冲突；
- fragment 拒绝；
- 非法 percent encoding 拒绝；
- 冲突返回既有 `plan_invalid`/构建拒绝语义。

不得让 RequestBuilder 同时从 endpoint query 和 `request_shape` 取固定参数。

### 20.3 strategy 角色

- `adapter` 是 AdapterRegistry 唯一分派字段；
- `strategy` 是兼容性分类字段；
- `strategy` 不参与 AdapterRegistry 分派；
- `strategy` 不决定请求编码；
- `strategy` 不决定响应解析器。

新 ready/active plan 必须满足：

| adapter | strategy |
|---|---|
| html | html_form |
| trs | json_api |
| jpaas | json_api |
| generic_json | json_api |

不一致返回 `plan_invalid`。

`strategy` 暂时保留在 schema 与 canonical `plan_id` 中，直到独立任务证明所有生产引用均可移除。不得用 `strategy` 回退选择 Adapter。

### 20.4 结构化分页

新 schema 中的 `SearchPagination` 冻结为：

```text
enabled
location
value_path
start
step
page_size_path
page_size
max_pages
```

字段语义：

- `enabled`：是否启用分页参数注入；
- `location`：`none`、`query`、`form`、`json`；
- `value_path`：当前页码、页索引或 offset 的结构化路径；
- `start`：第一次请求的分页值，整数且 `>= 0`；
- `step`：后续每次请求的增量，整数且 `>= 1`；
- `page_size_path`：可选的 page-size 结构化路径；
- `page_size`：与 `page_size_path` 对应的正整数；无路径时必须为 `null`；
- `max_pages`：最多请求页数，正整数，并受全局策略上限约束。

第 `i` 次请求使用零基索引：

```text
pagination_value = start + i * step
```

可以表达：

```text
1, 2, 3...       → start=1, step=1
0, 1, 2...       → start=0, step=1
0, 10, 20...     → start=0, step=10
```

TASK-018 不支持 cursor token 分页；如以后需要，必须提升内部 schema 版本。

### 20.5 禁用分页

`enabled=false` 时：

```text
location=none
value_path=()
start=0
step=0
page_size_path=()
page_size=null
max_pages=1
```

不得发送任何分页参数。

### 20.6 启用分页

`enabled=true` 时：

```text
location 为 query/form/json 之一
value_path 非空
start >= 0
step >= 1
max_pages >= 1
```

即使 `max_pages=1`，也允许注入第一页参数，因为 TRS/JPAAS 可能要求显式发送第一页。

### 20.7 分页路径规则

- query/form：`value_path` 恰好一个非空片段；`page_size_path` 为空或恰好一个非空片段；
- json：`value_path` 一个或多个非空片段；`page_size_path` 为空或一个或多个非空片段；
- 所有路径不得包含空片段；
- 不得隐式拆分点号字符串；
- 不得包含数组索引；
- 大小写原样保留。

### 20.8 page size

- `page_size_path` 为空 → `page_size` 必须为 `null` → 不注入 page-size 参数；
- `page_size_path` 非空 → `page_size` 必须为正整数 → 每次请求注入相同 page-size。

不得使用 `{page_size}` 占位符。

### 20.9 分页位置合法矩阵

| 请求组合 | pagination.location |
|---|---|
| GET + request_format=none | none 或 query |
| POST + form_urlencoded | none、query 或 form |
| POST + json | none、query 或 json |

禁止：

- GET 使用 form/json 分页；
- form POST 使用 json 分页；
- JSON POST 使用 form 分页。

不合法组合返回 `plan_invalid`。

已知 Adapter 推荐位置：

- HTML GET → query；
- HTML POST → query 或 form，以正式计划为准；
- TRS POST → form；
- JPAAS GET → query；
- Generic GET → query；
- Generic POST → query 或 json。

不得由 Adapter 根据参数名称猜测位置。

### 20.10 路径冲突

以下路径必须互不冲突：

```text
request_shape.keyword_path
pagination.value_path
pagination.page_size_path
固定字段路径
```

- query/form：同名字段出现于两个来源即冲突；
- json：完全相同路径、祖先路径、后代路径、穿越已经固定为非 object 的节点均为冲突；
- 任何冲突返回 `plan_invalid`；
- 不得覆盖、合并或静默忽略。

### 20.11 RequestBuilder 顺序

```text
1. 从无 query 的 endpoint 开始
2. 复制 request_shape 中对应的固定字段
3. 注入 keyword
4. 注入 pagination value
5. 注入可选 page_size
6. 进行最终冲突验证
7. 使用标准编码生成 query/form/JSON
```

不得依赖 dict 插入顺序、自由模板替换、字符串拼接 query 或运行时字段名猜测。

编码要求：

- query/form 使用标准百分号编码；
- 空格语义由标准 `application/x-www-form-urlencoded` 规则确定；
- JSON 使用确定性序列化；
- JSON 禁止 NaN/Infinity；
- 不得记录完整敏感请求 body。

### 20.12 旧 schema 与缓存

保持已接受决策：

- 旧 SearchPlan schema 不迁移；
- 旧 `query_params`/`request_body_template` 不转换；
- 旧缓存不进入 executor；
- 当前任务按 cache miss 路径安全重建。

TASK-018B 应：

- 新增/提升 `plan_schema_version`；
- 提升 cache envelope schema version；
- 保持 `CACHE_KEY_PREFIX` 和 target fingerprint 算法不变；
- 保持 TTL 不变。

缓存读取状态允许新增内部 `incompatible`，但：

- 不得新增外部错误码；
- 不得把 `incompatible` 报成任务失败；
- 不得发布 URLMessage；
- 不得进入 executor；
- 应进入安全重建路径。

生成新计划并成功执行后，原 key 可被新 schema 缓存覆盖。


## 21. TASK-018B 实施记录

- `plan_schema_version=2`，cache envelope schema version 为 2。
- `CACHE_KEY_PREFIX`、target fingerprint 算法和 TTL 保持不变。
- 新 schema 不接受、不序列化、不读取 `query_params`/`request_body_template`。
- `request_shape` 是固定请求参数和关键词位置的唯一来源；`pagination` 是动态分页唯一来源。
- `plan_id` canonical 包含 `plan_schema_version/strategy/adapter/endpoint/http_method/request_format/response_format/request_shape/pagination/selectors/scope`。
- 旧 schema 缓存读取返回内部 `incompatible`，不进入 executor，按 cache miss 重建。
- `execution_models.py` 是统一执行结果唯一模型；`plan_executor.py` 仅 re-export。
- `adapter.py` 定义 SearchAdapter Protocol；`adapter_registry.py` 实现精确分派，无 fallback，无具体 Adapter 注册。
- `request_builder.py` 是纯函数式无网络请求构造器。
- executor 目前只执行 `max_pages=1` 的过渡路径；多页计划返回 `plan_not_executable`。
- TASK-018C–G 尚未完成；不得声称多页执行或具体 Adapter 已交付。


## 22. TASK-018C 实施记录

- `HTMLSearchAdapter` 已实现并位于 `crawler/search/html_adapter.py`。
- 支持 GET + `request_format=none` 与 POST + `request_format=form_urlencoded`。
- 唯一 HTML parser 位于 `crawler/search/html_response_parser.py`，`plan_executor.py` 不再包含第二套 HTML 解析实现。
- 多页执行按 `max_pages` 逐页调用 RequestBuilder；第一页零结果返回 `no_results`，后续页空/重复停止。
- 后续页 transport/response/selector 失败返回 fail-closed，`items=()`。
- 结果 URL 安全校验包括相对解析、http/https、userinfo、domain 与 allowed path prefix。
- Registry 未接入 orchestrator，未注册 TRS/JPAAS/Generic JSON Adapter。
