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
http_method
endpoint
request_format
response_format
request_shape
pagination
selectors
scope
其他现有执行字段
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