# Analyzer 受控搜索探测契约

状态：已冻结，作为后续 TASK-017E-R4/R5 的输入契约。

本文件定义 SiteAnalyzer 完成入口页候选发现后，如何在受控、限量、安全边界内观察搜索结果页或 API 响应结构，并形成 selector 证据。

## 1. 架构职责

- SiteAnalyzer 继续负责入口页抓取和候选发现。
- 受控探测是候选发现后的独立 Python 内部阶段。
- 受控探测不属于 SearchPlan 正式执行。
- 受控探测不发布搜索结果 URL。
- 受控探测不进入 legacy `plugin_search()`。
- 受控探测不写入任何 Redis 队列。
- Go 不解析、不执行、不消费探测结果。
- 探测响应体只在当前 Python 进程内短暂存在。
- PlanBuilder 只消费已经形成的 selector 证据。

不新增：

- 跨语言 Probe 消息。
- Redis 探测队列。
- 探测响应缓存。
- 协议字段或错误码。

## 2. 未来模块与入口

冻结未来模块位置：

```text
crawler/site/search_probe.py
```

冻结未来单候选入口：

```python
probe_search_candidate(
    candidate: SearchCandidate,
    keywords: tuple[str, ...],
    *,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
) -> SearchProbeResult
```

- `SearchProbeFetcher` 是可注入的 Python HTTP 抽象。
- `SearchProbePolicy` 明确承载安全边界和请求预算。
- `SearchProbeResult` 是 Python 内部值对象。
- 三者不增加 JSON、Redis 或 Go 序列化类型。
- 测试必须使用 fake，不允许真实网络。
- 本轮只冻结名称、职责和入口，不创建这些类型或文件。

## 3. 未来调用链

```text
严格解码 v2 search_requested
→ 保留已经规范化的 tuple[str, ...] keywords
→ 检查现有 SearchPlanCache
→ 有完整 selectors 且通过执行契约校验的缓存计划：直接使用
→ 缓存缺失或缓存计划不可执行：SiteAnalyzer 发现候选
→ 对符合资格的候选执行受控探测
→ 从探测响应中形成 selector 证据
→ PlanBuilder 构建 SearchPlan
→ 只有完整可执行计划才能写入现有 SearchPlanCache
→ execute_search_plan()
→ 映射并发布现有 URLMessage
```

禁止：

- 在有效缓存命中后重复探测。
- 缓存原始 HTML/JSON 响应。
- 缓存 Cookie、header 或请求 body。
- 缓存失败响应。
- 缓存“无结果”负状态。
- 执行 selector 为空的旧缓存计划。
- 为了兼容旧缓存而启用启发式解析。

旧缓存计划若缺少完整 selectors：

- 必须视为不可执行。
- 不得进入执行器。
- 应走正常重新分析和受控探测路径。
- 不修改现有 Redis key 或缓存协议。

## 4. 候选探测资格

只有同时满足以下条件的候选才可探测：

- 候选来自当前入口页的直接、可追踪证据。
- `strategy` 为 `html_form` 或 `json_api`。
- `method` 为 `GET` 或 `POST`。
- `endpoint` 能确定为合法绝对 HTTP/HTTPS URL。
- 存在唯一、明确的 keyword 注入位置。
- 不需要执行 JavaScript。
- 不需要登录、Cookie、Authorization 或会话状态。
- 不需要 CAPTCHA、浏览器自动化或 WAF 绕过。
- 请求结构能够从入口页静态证据中完整构造。

### html_form

必须具有：

- 真实 form/action/method 证据。
- 唯一的搜索关键词字段。
- 可安全复制的公开固定参数。
- GET query 或 POST form 的确定请求结构。

以下情况不可探测：

- password 或 file input。
- multipart/form-data。
- 登录、上传、删除、修改、支付或管理类 form。
- 依赖 Cookie/session 的 form。
- 依赖 CSRF/token/signature 的 form。
- 无法区分搜索字段与其他文本字段。
- 需要运行 JavaScript 才能生成参数。

### json_api

仅有以下证据不能探测：

- TRS/JPAAS 名称。
- meta 标签。
- script src。
- CMS 文本签名。
- 疑似 API URL。
- 常见字段名。

json_api 必须额外存在静态、确定的请求形状证据：

- 真实 API endpoint。
- HTTP method。
- keyword 所在 query 或 JSON body 路径。
- 固定 query params。
- request body object 模板。
- Content-Type。

不得从 `script src` 推断其本身就是搜索 API。

不得执行或反编译 JavaScript 来补齐请求结构。

当前证据不足的 json_api 候选应标记为“不具备探测资格”，不得猜测请求。

## 5. keywords 规则

探测只使用严格消息解码后已有的 `tuple[str, ...]`。

规则：

1. 保持原始规范化顺序。
2. 不新增、不扩展、不排序关键词。
3. 不将关键词永久写入候选或 SearchPlan。
4. 每个候选最多尝试前两个关键词。
5. 第一个关键词产生完整 selector 证据后立即停止。
6. 无结果或证据不充分时才能尝试第二个关键词。
7. 关键词作为逻辑参数交给 HTTP 客户端，只编码一次。
8. 不允许预先 URL encode 后再次编码。
9. 不将关键词写入日志中的完整 URL、query 或 body。

若任务没有关键词，候选不可探测。

## 6. 请求预算与流量限制

默认上限：

- 单次分析最多探测 3 个候选。
- 单个候选最多尝试 2 个关键词。
- 单次分析最多 6 个探测请求。
- 每次探测只请求第一页。
- 并发数：1。
- 自动重试：0。
- 重定向上限：3 跳。
- 单响应解压后最大：2 MiB。
- 单请求总时间上限：10 秒。

要求：

- 候选保持 Analyzer 现有稳定顺序。
- 不因策略类型重新排序。
- 第一个产生完整 selector 证据的候选获胜，随后停止探测。
- 重定向属于同一探测请求，但每一跳都必须重新执行安全校验。
- 既有 rate limiter、熔断器或下载器规则更严格时，以更严格者为准。
- 不得通过重试、换关键词或重定向绕过总预算。
- 不进行分页遍历。
- 不抓取结果详情页。
- 不对结果 URL 发起请求。

若当前 HTTP 抽象无法严格保证这些上限，ADR 必须将其记录为实现阻断，不能弱化契约。

## 7. 请求构造规则

### GET html_form

- endpoint：由真实 form action 解析。
- query params：复制允许的固定参数。
- keyword：写入唯一搜索字段。
- request body：禁止。

### POST html_form

- endpoint：由真实 form action 解析。
- query params：仅使用入口证据明确属于 URL query 的参数。
- form body：固定参数加唯一 keyword 字段。
- Content-Type：`application/x-www-form-urlencoded`。

### json_api

只允许：

- GET + query params。
- POST + JSON object body。

POST JSON body 必须是对象，不接受任意字符串、数组或二进制 body。

禁止：

- PUT/PATCH/DELETE。
- GET body。
- multipart。
- 文件上传。
- 自定义 Cookie。
- Authorization。
- Proxy-Authorization。
- 客户端证书。
- 用户凭据。
- 从 legacy site_cfg 补齐未知参数。

允许的请求 header 限于实现所必需的安全固定集合，例如：

- Accept。
- User-Agent。
- Content-Type。

不得复制入口响应中的：

- Set-Cookie。
- Cookie。
- Authorization。
- Token。
- Referer 中的敏感 query。
- 其他会话 header。

HTTP 客户端不得隐式读取 `.netrc`、浏览器 Cookie 或环境中的认证信息。

## 8. 固定参数与敏感字段

入口页 hidden input 或静态配置只有满足下列条件时才能复制：

- 标量字符串。
- 长度在契约上限内。
- 不含凭据或个人信息。
- 字段名和值均未命中敏感规则。
- 不承担会话、签名或防重放职责。

以下名称或语义命中后，候选不可探测，不得仅删除字段后继续猜测：

```text
password
passwd
secret
token
access_token
refresh_token
authorization
cookie
session
csrf
xsrf
signature
api_key
client_secret
```

字段名检查是安全拒绝规则，不是用于猜测搜索请求的解析启发式。

## 9. SSRF、DNS 和目标边界

所有候选 endpoint 和每一跳 redirect 都必须执行安全校验。

拒绝：

- 非 HTTP/HTTPS scheme。
- 含 username/password 的 URL。
- IP literal endpoint。
- localhost。
- 回环地址。
- 私网地址。
- 链路本地地址。
- 组播地址。
- 保留地址。
- 未指定地址。
- 云元数据地址。
- 非 80/443 端口。
- HTTPS 降级到 HTTP。
- DNS 解析失败。
- 任一解析结果不是公网地址。

允许的探测 origin 只能来自：

1. 入口页最终 URL 的 origin。
2. 入口 HTML 中直接出现的真实 form action origin。
3. 入口 HTML 静态配置中直接出现且证据完整的真实 API origin。

不得通过以下来源扩大 origin 集合：

- 重定向返回的陌生 origin。
- 响应正文中的任意链接。
- 字符串拼接猜测。
- CMS 默认域名。
- legacy site_cfg。
- 脚本执行结果。

重定向目标必须：

- 重新执行 scheme、端口、DNS 和 IP 校验。
- 仍处于最初批准的 origin 集合。
- 不得因 30x 自动携带敏感 header。
- 不得接受 redirect 动态扩大目标范围。

如果现有下载器存在 DNS 重绑定或校验与连接之间的安全缺口，必须在能力矩阵中明确记录，作为后续实现前置项。不得在本轮修复该缺口。

## 10. 响应接收规则

仅接受：

- HTTP 2xx。
- html_form：`text/html` 或 `application/xhtml+xml`。
- json_api：`application/json` 或 `application/*+json`。

拒绝：

- 4xx/5xx。
- Content-Type 与策略不符。
- 超过大小上限。
- 解压异常。
- 乱码或不可解析内容。
- 登录页。
- 验证码页。
- WAF 挑战页。
- 下载文件。
- 流式无限响应。

规则：

- 不通过内容猜测绕过错误 Content-Type。
- 不把登录页或 CAPTCHA 当成搜索结果页。
- 不从错误页生成 selector。
- 不跟随页面内 meta refresh。
- 不执行 JavaScript。
- 不加载页面引用的图片、CSS、字体或其他资源。
- 忽略且不保存响应中的 `Set-Cookie`。
- 达到字节上限立即终止接收。
- 原始响应只允许在内存中存活到结构分析结束。

## 11. selector 证据形成门禁

受控探测只提供原始结构观察机会，不能降低 TASK-017E-R1 的 selector 要求。

### HTML

完整证据必须证明：

- `result_item` 能定位重复结果容器。
- `title` 相对单个容器定位规范化标题文本。
- `url` 相对单个容器定位具有 href 的链接元素。
- 至少两个结构一致的结果项支持该映射。
- 生成后的 selectors 在同一响应上重新应用并验证通过。

不得使用：

- 全页 `a[href]`。
- nth-child/nth-of-type 位置猜测。
- 按中文文字猜测。
- 随机或明显动态 class。
- 仅凭单个孤立链接声称结果容器成立。

如果只有 0 或 1 个结果项，证据不足，不生成可执行 selectors。

### JSON

完整证据必须证明：

- `result_item` 是从响应根对象出发的 RFC 6901 JSON Pointer。
- `result_item` 实际指向数组。
- `title` 和 `url` 是相对单个数组元素的 RFC 6901 JSON Pointer。
- 至少两个结构一致的数组元素具有相同 title/url 映射。
- title 和 url 最终解析为字符串。
- `~` 和 `/` 按 RFC 6901 正确转义。

禁止：

- JSONPath。
- 通配符。
- 递归下降。
- 过滤表达式。
- 猜测 items/data/list/results。
- 仅凭字段名选取 title/url。
- 在多个可行数组之间任意选择。

存在多个同等可能的数组、标题字段或 URL 字段时，必须返回“证据不充分”。

本轮只冻结判定条件，不实现推断算法。

## 12. 探测结果和候选关联

未来 `SearchProbeResult` 至少要能表达：

- 是否发起请求。
- 安全拒绝原因分类。
- 是否获得合格响应。
- 是否有结果。
- 是否形成完整 selector 证据。
- 对应候选身份。
- 产生证据的 keyword 位置。
- 结构证据来源。

要求：

- selector 证据必须与产生它的同一个候选绑定。
- 不得把候选 A 的 endpoint、候选 B 的 body 和候选 C 的 selector 合并。
- 不得将不同关键词响应中的冲突结构拼接。
- 探测结果只在当前 Python 调用链内交接。
- 不增加 JSON 序列化。
- 不写 Redis。
- 不创建 Go 类型。
- 不进入 URLMessage。
- 不发布从探测响应中观察到的结果 URL。

## 13. 失败处理

候选级失败默认采用 fail-closed：

```text
不具备资格：跳过，不发请求
安全校验失败：拒绝，不发请求
请求失败：终止当前候选，尝试下一个合格候选
响应拒绝：终止当前候选
无结果：按预算尝试下一个关键词
证据不充分：按预算尝试下一个关键词或候选
完整证据：立即停止探测并交给 PlanBuilder
```

全部候选探测结束仍没有完整 selector 证据时：

- 不得生成 ready/active 的空 selector 计划。
- 不得进入 `execute_search_plan()`。
- 不得回退 legacy plugin。
- 不得发布部分 URL。
- 不得创建新错误码。

对外继续复用：

```text
error_code = SEARCH_FAILED
error_message = No executable search plan
```

探测编排出现非预期内部异常时，可使用既有安全文案：

```text
Search analysis failed
```

不得在错误消息或日志中包含：

- 完整 URL query。
- request body。
- response body。
- HTML。
- JSON 原文。
- Cookie。
- Token。
- Authorization。
- 原始异常 repr。
- traceback。

## 14. 日志、指标和数据保留

允许记录的安全元数据：

- task/message 关联标识。
- 候选序号。
- strategy。
- method。
- 规范化 hostname。
- 结果分类。
- HTTP 状态类别。
- 响应字节数。
- 耗时。
- 是否形成 selector 证据。

禁止记录：

- 完整请求 URL。
- query 参数值。
- form/JSON body。
- 关键词原文。
- 响应正文。
- 响应 header 原文。
- Cookie 或认证数据。
- selector 对应的原始敏感内容。

不得新增：

- Redis 日志队列。
- 探测响应缓存。
- 本地响应文件。
- HTML/JSON 调试转储。
- 数据库表。
- 协议字段。

测试 fixture 必须是手工最小化、无敏感信息的静态内容，不得直接保存真实网站完整响应。

## 15. 现有能力审计矩阵

| 能力 | 当前实现位置 | 当前是否满足 | 契约要求 | 最小后续修改范围 | 是否阻断实现 |
| --- | --- | --- | --- | --- | --- |
| 可注入 fetcher | crawler/site/analyzer.py 的 fetcher/downloader 参数 | 部分 | SearchProbeFetcher | crawler/site/search_probe.py | 是 |
| GET 无 body | httpx/fetch.py `fetch()` | 是 | 强制 | 可复用 | 否 |
| POST form | httpx/fetch.py `post_json()` | 否 | html_form | 需返回原始响应的新抽象 | 是 |
| POST JSON object | 当前不存在 | 否 | json_api | httpx/fetch.py 或 search_probe fetcher | 是 |
| 禁止凭据继承 | requests.Session 未显式禁用 .netrc/凭据继承 | 否 | 强制 | httpx/session_pool.py 或 search_probe fetcher | 是 |
| redirect 逐跳校验 | SiteAnalyzer + normalizer.redirect_allowed | 否 | 强制 | search_probe 专用逐跳实现 | 是 |
| DNS/IP 安全校验 | crawler/site/security.py | 部分 | 强制 | search_probe 调用链 | 是 |
| 响应大小上限 | httpx/fetch.py `fetch_once()` | 是 | 2 MiB | 复用 fetch_once 或专用实现 | 否 |
| 请求总超时 | httpx/fetch.py timeout | 部分 | 10 秒 | search_probe policy | 是 |
| 禁止自动重试 | session_pool Retry + `_retry` | 否 | 强制 | search_probe 专用无重试路径 | 是 |
| Content-Type 校验 | analyzer.py 入口页检查 | 否 | 按策略 | search_probe 响应门禁 | 是 |
| 原始响应不落盘 | 当前无写盘 | 是 | 强制 | 保持内存处理 | 否 |
| 候选请求形状证据 | models.py、forms.py、signatures.py | 部分 | 完整请求形状 | crawler/site/models.py、forms.py、signatures.py | 是 |
| HTML 结果结构证据 | 当前不存在 | 否 | 完整 CSS selectors | search_probe + selector 提取 | 是 |
| JSON 响应结构证据 | 当前不存在 | 否 | RFC 6901 pointers | search_probe + selector 提取 | 是 |

不得把“可由未来实现补齐”写成“当前已满足”。

## 16. HTML/JSON 上游最小修改矩阵

| strategy | 当前已有证据 | 为构造探测请求还缺什么 | 为生成 selectors 还缺什么 | 最小后续修改文件 |
| --- | --- | --- | --- | --- |
| html_form | method、endpoint、keyword_param、fixed_params、request_encoding | POST form body 模板和 URL/body 参数归属 | 搜索结果 DOM | crawler/site/models.py、forms.py、analyzer.py、search_probe.py、plan_builder.py |
| json_api | CMS 签名、script src、疑似 endpoint、keyword_param | 真实 method、keyword 路径、固定参数、body 模板、Content-Type | JSON 响应 schema/结果数组 | crawler/site/models.py、signatures.py、analyzer.py、search_probe.py、plan_builder.py |

特别确认：

- html_form 当前拥有唯一 keyword 字段，但 POST 请求体模板尚未模型化。
- POST form 的固定参数当前可构造，但需要敏感字段和会话字段安全门禁。
- json_api 当前只有 CMS 签名，没有请求模板。
- `SearchCandidate` 需要增加“请求形状证据”和“selector 证据”两类字段。
- `SiteAnalyzer`、新 `search_probe.py`、`PlanBuilder` 各自有最小修改范围。
- 现有 downloader/httpx 层必须先补齐逐跳 SSRF、凭据隔离、无重试和 JSON POST 能力。

## 17. 后续任务拆分

原则上拆为：

```text
TASK-017E-R4：受控探测 HTTP 安全基础与候选请求形状
TASK-017E-R5：HTML/JSON selector 证据提取与 PlanBuilder 传递
TASK-017E：plan_executor.py 正式执行适配器
TASK-017F：后续集成与跨语言验证
```

顺序约束：

- 如果现有 HTTP 层缺少逐跳 SSRF、大小上限或凭据隔离，R4 必须先修安全基础。
- 如果 json_api 没有请求形状证据，R4 必须先补分析模型，R5 不得猜测。
- R4 未通过完整 fake 测试前不得开始 R5。
- R5 未生成符合 R1 契约的 selectors 前不得开始 TASK-017E。
- 本轮不得实施 R4/R5。

## 18. 非目标

- 不实现 `search_probe.py`。
- 不实现 selector 推断。
- 不实现 `plan_executor.py`。
- 不修改 Python/Go 功能代码。
- 不访问真实网站。
- 不发送 DNS/HTTP 请求。
- 不开始 TASK-017E-R4、R5、TASK-017E 或 TASK-017F。
## 19. TASK-017E-R4 实施状态

- 状态：已实现受控探测安全基础与候选请求形状。
- 未实现：HTML/JSON selector 推断、PlanBuilder selector 传递、SearchPlan 执行、Worker 集成。
- R4 不创建 `probe_search_candidate()` 完整入口，该入口归 R5 使用；R4 提供 `build_probe_request()`、`SearchProbePolicy`、`PinnedProbeFetcher` 等基础能力。
- TASK-017E 仍被 R5 selector 证据提取阻断。
## 20. TASK-017E-R5 实施状态

- 状态：已实现 HTML/JSON selector evidence 提取与验证。
- 已实现正式入口 `probe_search_candidate()`。
- 已实现 PlanBuilder 将已验证 evidence 映射为 `SearchSelectors` 和 `ready` SearchPlan。
- 未实现：SearchPlan 执行、Worker 集成、缓存写入、URLMessage 发布。
- TASK-017E 主执行适配器尚未实现。
