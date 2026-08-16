# 出站请求安全合同（TASK-022A-R 已冻结）

**状态：** APPROVED / FROZEN FOR IMPLEMENTATION
**批准日期：** 2026-08-14
**版本：** v1.0（已批准，待 TASK-022B–022H 实施）
**关联：** `docs/OUTBOUND_REQUEST_INVENTORY.md`、`docs/SECURITY_THREAT_MODEL.md`、`docs/decisions/ADR-016-outbound-request-security-boundary.md`

本文件是 TASK-022B–022H 的正式安全合同。D-01 至 D-12 已经用户裁决并冻结；本轮没有实现安全 Transport，当前生产路径仍存在审计报告列出的风险，当前版本不可部署。

## 1. 总目标

- 所有正式出站 HTTP/HTTPS 路径共享同一个安全 transport。
- Probe、Adapter、Worker、redirect、proxy、legacy/v1 不得旁路。
- 任何安全拒绝都 fail closed。
- 测试许可不能变成生产开关。
- 不把“部署在内网”当作允许访问私网的理由。

## 2. 已批准决策摘要

### D-01 特殊用途和私网 IP

生产默认拒绝所有非公网可路由地址，包括 loopback、private、link-local、unspecified、multicast、reserved、documentation、benchmark、carrier-grade NAT、IPv4-mapped IPv6 对应禁止地址和云 metadata 地址。IPv4 与 IPv6 必须同时检查。不得依赖字符串前缀或单一 `is_private`。V1 不提供生产私网例外开关；未来内网站点需求必须另立 ADR 和管理员显式策略，不得复用测试开关。

### D-02 域名策略

出站目标必须属于管理员站点配置产生的规范化允许主机集合。默认仅允许精确 hostname；搜索结果、配置 endpoint 和 redirect 目标受同一规则约束。不允许调用方仅凭 JSON API 参数临时授权新域名。子域匹配默认关闭，只有管理员显式开启才允许受控子域；受控子域必须经过 IDNA 规范化、label 边界检查和公共后缀安全检查。禁止 `endswith(domain)` 作为安全判断。IP literal 不能绕过域名白名单。跨主机 redirect 只有目标主机已在同一站点允许集合中才可继续。

### D-03 HTTP 与 HTTPS

仅允许 `http` 和 `https`。HTTPS 为推荐默认；允许管理员配置的公网主机使用 HTTP。HTTP 请求不得携带 Cookie、Authorization、代理凭据或 URL userinfo。允许 HTTP→HTTPS，禁止 HTTPS→HTTP 降级。redirect 后必须重新执行 scheme、host、port、DNS 和 IP 验证。`file/ftp/gopher/data/javascript/ws/wss` 等 scheme 一律拒绝。

### D-04 端口

默认允许 HTTP 80 与 HTTPS 443；省略端口规范化为对应默认端口。非默认端口必须由管理员在站点安全策略中精确列出；即使端口获准，目标解析地址仍必须是允许的公网地址。禁止端口 0、负数、超出 65535、歧义表达和解析失败回退。

### D-05 代理

Python 与 Go 生产 Transport 必须忽略 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY` 及大小写变体。Python 必须关闭环境代理继承；Go 不得使用 `http.ProxyFromEnvironment`。TASK-022 V1 不支持生产显式代理。未来受管代理必须单独 ADR，验证代理地址、凭据、TLS 和目标策略。不允许环境变量临时绕过安全策略。

### D-06 DNS 与连接固定

每次新 authority 和每次 redirect 都必须解析并验证。所有 A/AAAA 结果必须全部通过；任一结果被拒绝则整体拒绝。单次解析结果最多接受 16 个地址，超出拒绝。禁止只选一个公网 IP 而忽略同域名私网 IP。验证后连接必须固定到该次已验证地址集合中的地址，不允许默认 Transport 再次独立解析 hostname。HTTP Host、TLS ServerName 和证书主机名校验使用规范化 hostname。连接池只能复用相同 authority、相同安全策略下建立的已验证连接；失败重连不得跳出已验证地址集合；新请求或 DNS 缓存失效后重新解析和验证。

### D-07 redirect

最大 redirect 数为 3。每一跳执行完整 URL、域名、端口、DNS、IP、代理和 TLS 策略。只允许目标 host 已在当前站点允许集合中的跨主机 redirect。禁止 HTTPS→HTTP。不向新 authority 转发 Authorization、Cookie、Proxy-Authorization 或其他敏感 header。redirect 循环、缺失 Location、非法 Location、超限均 fail closed。相对 Location 必须先基于当前 URL 规范化再验证。

### D-08 超时与资源预算

已批准 V1 硬上限：

| 类别 | 上限 |
|---|---|
| 规范化 URL 序列化 | 8192 bytes |
| hostname | 253 octets |
| 单个 DNS label | 63 octets |
| DNS 解析 | 5 秒 |
| TCP connect | 5 秒 |
| TLS handshake | 5 秒 |
| response header | 10 秒 |
| 连续读取空闲 | 15 秒 |
| Probe/Search 总时限 | 30 秒 |
| 详情下载总时限 | 60 秒 |
| POST 请求体 | 1 MiB |
| response header | 256 KiB |
| Probe 原始传输/解压后 | 1 MiB |
| Search/Adapter 原始传输/解压后 | 8 MiB |
| HTML 详情原始传输/解压后 | 20 MiB |
| 全局活动出站连接 | 20 |
| 单主机活动连接 | 5 |
| 单主机空闲连接 | 2 |

规则：

- Content-Length 超限在读取正文前拒绝。
- 无 Content-Length、chunked 或错误 Content-Length 仍必须流式计数。
- 原始传输字节和解压后字节分别计数。
- 超限整体拒绝，不得把截断内容交给 Parser。
- 只允许明确支持且可双重计数的 Content-Encoding；未知或多层歧义编码拒绝。
- 禁止无界 `response.content`、`io.ReadAll` 或等价读取。
- 现有并发必须保持有界，不得创建无上限 goroutine、线程或连接。
- 管理员可配置更低值，不能在没有新 ADR 的情况下提高硬上限。

### D-09 安全拒绝与任务闭合

v2 安全拒绝不得伪装成 `ArticleResultV2.extract_failed`、`ArticleResultV2.irrelevant` 或 v1 `ErrorMessage`；不得静默丢弃。采用独立、严格验证的 v2 出站失败事件族，使用现有队列 `crawler:error`，不创建新队列。

事件语义至少包含：

- `protocol_version="2.0"`
- 独立 `type`
- `task_id`
- `message_id`
- `timestamp`
- `stage`
- `category`
- 稳定 `reason_code`
- `retryable`
- 可用时包含 `hit_id`、`plan_id`
- URL 只保存不可逆 hash，不保存完整 URL、query、header、Cookie、正文或目标响应

`category` 至少区分：

- `policy_rejected`
- `transport_failed`
- `resource_rejected`

要求：

- Python 与 Go 使用共享 fixture 和严格解码规则。
- `crawler:error` 必须显式版本分流；v2 事件不得回退 v1。
- 事件支持 TASK-021A 幂等消费和任务状态闭合。
- TASK-022G 负责生产事件；TASK-021A 负责最终消费、幂等状态更新和任务闭合。
- TASK-022 完成但 TASK-021A 尚未完成时，系统仍不可部署。
- TASK-022A-R 只冻结语义，不修改协议代码或创建 fixture。

### D-10 legacy/v1

所有仍可达的 legacy/v1 HTTP 请求必须接入与 v2 相同的安全 Transport，不得保留安全旁路。安全规则优先于旧的不安全可达行为；尽可能保持 v1 消息结构和旧错误合同。v2 安全失败绝不能回退成 v1 ErrorMessage。若某项 v1 兼容行为与安全不变量冲突，必须 fail closed，并在 TASK-022G 测试中记录兼容性变化。

### D-11 本地测试和 loopback

生产默认拒绝 loopback。B8、TASK-022H 等本地测试通过构造函数或接口注入 `resolver`、`address policy`、`dialer`、`Transport`。测试可注入只允许精确 fixture 地址和端口的策略。不得使用生产环境变量、站点配置字段、CLI 开关或隐藏全局变量启用 loopback。测试许可必须明确限定测试进程和精确地址；必须有静态及运行测试证明生产构造入口无法启用测试策略。

### D-12 AI 和第三方服务

TASK-022 期间 AI/第三方外部提取继续默认禁用。不允许使用动态 URL 作为 AI endpoint。若未来启用，必须单独 ADR、固定 endpoint allowlist、独立凭据管理、禁止把原始 HTML/Cookie/Authorization/内部 URL 发送给第三方，并采用独立 Transport 和日志脱敏规则。不得通过通用站点 allowlist 间接授权 AI endpoint。

## 3. 安全不变量

- SEC-URL-001：只接受绝对 HTTP/HTTPS URL。
- SEC-URL-002：URL 在 DNS/连接前完成唯一规范化。
- SEC-URL-003：拒绝 userinfo、控制字符、歧义表达。
- SEC-URL-004：拒绝非 HTTP/HTTPS scheme。
- SEC-URL-005：IDNA、端口、默认端口、尾点域名统一处理。
- SEC-DNS-001：所有 DNS 返回地址经过策略验证。
- SEC-DNS-002：全部地址通过才允许。
- SEC-DNS-003：DNS 校验与实际连接之间无未受控 TOCTOU。
- SEC-DNS-004：CNAME、A/AAAA、IPv4-mapped、rebinding 有离线可测策略。
- SEC-DIAL-001：连接固定到已验证地址。
- SEC-DIAL-002：Host、TLS SNI、证书验证使用规范化域名。
- SEC-DIAL-003：底层不得二次解析未验证 hostname。
- SEC-REDIRECT-001：每跳完整重验。
- SEC-REDIRECT-002：最大 3 跳。
- SEC-REDIRECT-003：禁止 HTTPS→HTTP 降级和未授权跨主机。
- SEC-PROXY-001：忽略环境代理。
- SEC-PROXY-002：V1 无显式代理。
- SEC-TLS-001：证书校验保持启用。
- SEC-TLS-002：不使用 InsecureSkipVerify。
- SEC-TLS-003：SNI/证书按原 hostname，连接使用已验证 IP。
- SEC-LIMIT-001：connect/read/write/pool timeout 显式配置。
- SEC-LIMIT-002：总 deadline 覆盖 DNS、connect、TLS、redirect、body。
- SEC-LIMIT-003：响应体和解压后正文流式预算。
- SEC-LIMIT-004：并发、连接池、请求数有界。
- SEC-POLICY-001：域名、端口、HTTP 策略显式配置。
- SEC-POLICY-002：配置错误时启动失败。
- SEC-LOG-001：日志不记录凭据、Cookie、Authorization、完整 query 或正文。
- SEC-LOG-002：指标标签低基数。
- SEC-LOG-003：安全拒绝生成结构化原因码和事件。
- SEC-LEGACY-001：legacy/v1/v2 无安全绕过。
- SEC-LEGACY-002：安全拒绝不伪造 v1 成功或错误。
- SEC-TEST-001：loopback 许可依赖注入。
- SEC-TEST-002：测试许可无法被生产配置开启。
- SEC-TEST-003：canonical 只作为元数据。
- SEC-TEST-004：PDF/Office 安全门不接生产链。

## 4. TASK-022 阶段映射

| 阶段 | 内容 |
|---|---|
| 022B | URL 规范化、scheme、userinfo、IDNA、端口、IP 分类、DNS 全地址验证、pure function/fake resolver 离线测试 |
| 022C | 连接固定到已验证 IP，保持 Host/SNI/证书验证，底层不二次解析 |
| 022D | 每跳重定向、代理、超时、响应体/解压预算、总 deadline、并发/连接池预算 |
| 022E | 域名/端口/HTTP/管理员显式策略，配置错误启动失败 |
| 022F | 安全日志、脱敏、低基数指标、审计事件 |
| 022G | Probe、四类正式 Adapter（六类搜索形态）、legacy 插件、Python pipeline、Go Worker、休眠客户端统一接入 |
| 022H | 对抗测试、完整回归、Race、隔离 E2E |

## 5. 当前实施状态

- TASK-022C pinned transport foundation = SEALED_LOCAL（R5 PASS，生产接线未开始）
- TASK-022D-1 pure policy contract = SEALED_LOCAL（R2 PASS，纯策略合同未接线）
- TASK-022D-1-R=FAIL，FIX implemented；remaining=0 视为预算耗尽，scheme-relative 双端统一，Location 非字符串/空白 fail closed
- ADR-019-redirect-proxy-resource-budget = accepted（冻结策略与纯合同）
- TASK-022B foundation = SEALED_LOCAL
- TASK-022D-1 已由 R2 审计通过并本地封板
- TASK-022D-2 runtime primitives = IMPLEMENTED_LOCAL（未接线）
- TASK-022D-2-R=FAIL，FIX implemented；Content-Length/clock/Lease/host key 已按合同收紧
- TASK-022D-2-R2=FAIL，FIX2 implemented；空 Content-Length 集合、DNS label hyphen、Lease registry 绑定已收紧
- TASK-022D-2-R3 PASS；D2 实现与 105-case fixture 已本地封板
- D2 实现的是运行时安全原语；实际 Resty/Python HTTP Transport 尚未接线
- TASK-022D-3 isolated secure HTTP executor = IMPLEMENTED_LOCAL（未接线生产）
- D3 实现单跳组合、阶段 timeout/total deadline、raw response header 前置计数、Content-Length 预检、bounded body、逐跳 redirect 重验与共享 limiter 清理
- D3 V1 禁用 keep-alive，实际 idle=0，不启用 HTTP/2 多路复用；不声称实现连接复用
- TASK-022D-3-R=FAIL，FIX implemented：HTTP/1.1 解析与测试合同已收紧
- TASK-022D-3-R2=FAIL，FIX2 implemented：状态行 reason phrase 拒绝 bare LF/CR/NUL/C0/DEL；HEAD/204/304 空正文返回前执行 CL+TE 与 TE coding 前置校验
- TASK-022D-3-R3=FAIL，FIX3 implemented：正文响应错误优先级统一为 response syntax → framing → no-body decision → content encoding → body；CL+TE 无论 Content-Encoding 一律 invalid_transfer_encoding
- TASK-022D-3-R4 PASS；D3 隔离安全 HTTP 执行器与 103-case fixture 已本地封板
- implementation_seal_commit=614cf45af3767d7f8f24c0edc2f8faaf704483b7
- canonical_commit_blob_aggregate=218625b04fcb3c870896030d185f14c0580a0582132ee9915482ba7d654af78d
- historical_r4_worktree_aggregate=1aa1deeecff84e454d2c8987521d603f01b65a571ecf7fdf224650169ab6eb3e
- difference=secure_http_transport_contract.json CRLF→LF Git text normalization only
- canonical_blob_validation=PASS
- production_wiring=ISOLATED_ONLY；existing_client_wiring=NOT_STARTED；deployment=BLOCKED
- ADR-021=accepted；现有 Resty/requests/httpx 尚未切换；Python 真实 TLS E2E 留给 TASK-022H
- TASK-022D-R=FAIL：canonical seal evidence mismatch；TASK-022D-FIX=implemented：canonical blob 已重新验证
- TASK-022D-R2 PASS；D1/D2/D3 组合验收 PASS；canonical blob 为权威 seal 输入
- TASK-022D acceptance=PASS；closure=CLOSED；next_task=TASK-022E_AFTER_USER_APPROVAL
- 当前生产链仍未切换；deployment 继续 BLOCKED
- 进入 TASK-022E 必须满足 12 项进入条件并获得用户批准
- 仅接受严格 HTTP/1.0/1.1 状态行与 CRLF header；bare LF/CR、NUL、obs-fold、非 token 字段名稳定拒绝
- 1xx interim（除 101）与最终响应共享累计 256KiB header 上限；101 返回 `protocol_upgrade_not_allowed`
- Content-Length 与 Transfer-Encoding 同时存在一律 `invalid_transfer_encoding`；TE 仅允许单一 `chunked`
- chunk extension 拒绝（`chunk_extension_not_allowed`）；zero chunk 后仅空 trailer 允许，非空 trailer 返回 `invalid_chunked_trailer`
- raw header 达到 262144 且无完整终止空行返回 `response_headers_too_large`
- D3 共享 fixture：tests/fixtures/secure_http_transport_contract.json（FIX3 后 103 cases：request 18、response 61、redirect 16、resource 8）
- ADR-021-secure-http-transport-composition = accepted
- 现有 Resty/requests/httpx、Adapter、Probe、Worker 均未切换；生产请求不得声称已受 D3 保护
- wire-level header 限制与 per-host idle pool 尚未配置到真实生产连接池
- deadline_capable=True 仅表示 D3 可信适配器契约，不代表任意第三方 reader 可中断
- ADR-020-bounded-io-concurrency-runtime = proposed
- D2 仅实现大小门、有界读取、read-idle/total timeout 与并发限流原语；实际 Transport 组合由 D3 接线
- 60-case 跨语言 fixture 已冻结
- D1 只提供纯策略合同
- 实际运行时执行留给 TASK-022D-2/D3
- production wiring 仍为 NOT_STARTED
- deployment 仍为 BLOCKED
- TASK-022C=R5 PASS，production wiring NOT_STARTED
- implementation_commit=194fba1062b5cffa1c7aa8911a83a3c39136012f
- production integration = NOT_STARTED
- deployment = BLOCKED
- 新安全包目前没有生产调用方。
- URL/DNS 策略基础库封板不等于安全 Transport 已经启用。
- TASK-022C、022D、022E、022F、022G、022H 以及 TASK-021A 未完成前不可部署。
- 当前版本不可部署。

## TASK-022E-B 配置合同状态

- 生产出站安全配置合同、JSON Schema 与共享 fixture 已冻结（生产 loader 未实现）。
- 配置入口固定为 `config/outbound_security.json`（本阶段不创建）；仅 `config_version`/`policies` 顶层字段与 `policy_id`/`allowed_domains`/`allowed_schemes`/`allowed_ports` policy 字段。
- hostname 仅规范化小写 ASCII IDNA A-label，且至少两个 DNS label；单标签 localhost/example 返回 config_invalid_hostname；无 root dot/scheme/userinfo/path/port/通配符/IP literal。
- V1 仅 exact hostname；不使用 `allowed_subdomain_roots`；不修改 OutboundPolicy 模型。
- redirect 使用主 `allowed_domains` 集合，无独立 redirect allowlist；HTTPS→HTTP 始终拒绝。
- `allowed_schemes` 仅 `["https"]` 或 `["http","https"]`；`allowed_ports` 整数 1–65535 且 key 与 schemes 精确一致。
- 稳定 reason code 见 `docs/OUTBOUND_SECURITY_CONFIGURATION.md`；日志不记录原始配置/完整 URL/query/凭据。
- 共享 fixture 104 cases（12 category，16 reason 全部可回放，logging=6）。
- 迁移草案 hostname 清单尚未完成全部站点真实搜索结果/文章 URL/逐跳 redirect hostname 联网验证；后续真实 hostname 审计需另行联网授权并在站点迁移或生产接线封板前完成。
- TASK-022E-B scope=CONTRACT_SCHEMA_SHARED_FIXTURE_ONLY；fix_completed=IMPLEMENTED；fix2=IMPLEMENTED；controlled_rebaseline=WAITING_REVIEW；historical_old96_snapshot=UNAVAILABLE；production_logging_redaction=NOT_IMPLEMENTED；acceptance=WAITING_RE_REVIEW；production_loader=NOT_STARTED；site_migration=NOT_STARTED；production_client_wiring=NOT_STARTED；deployment=BLOCKED。

## TASK-022E-C-A-D / E-B-AMEND-1 决策补充

- 冻结 reason 由 16 增至 18：新增 `config_unreadable`（源存在但不可读/非普通文件/权限/I/O）与 `config_limit_exceeded`（>1,048,576 bytes 或合法 JSON 容器深度>32）。
- 生产路径固定 `config/outbound_security.json`，不允许 env/CLI/site/运行时参数覆盖；测试经内部 from_path 注入；symlink 允许但目标必须为可读普通文件；仅启动时读取一次，不热加载。
- loader 只返回第一个稳定错误；错误对象仅允许 reason/field_path/policy_id/canonical hostname，禁止原始配置/完整 URL/query/凭据。
- 全局验证顺序与混合错误优先级已冻结（详见 OUTBOUND_SECURITY_CONFIGURATION.md 第 8 节）；policies 按文件顺序、site 按 site_id ASCII 升序、site 静态字段顺序 domain→base_url→api_url→page_url。
- domain 为 hostname；base_url/api_url/page_url 为绝对 http/https URL，默认端口 80/443，path/query 不参与 hostname 匹配且不得进入安全日志；先验证全部 outbound_policy_id 引用，再执行静态交叉校验。
- 双端各自独立读取并完整 18-reason 验证；loader 不执行 DNS/redirect，不处理任务级 allowed_domains 交集（交集由后续执行器/接线阶段计算，空交集为运行时拒绝）。
- fixture_case_count=125（原 104 未修改，新增 21）；reason_count=18；amendment=IMPLEMENTED/UNCOMMITTED；production_loader=NOT_STARTED；deployment=BLOCKED。
- fixture 聚合口径：`OSEC-CASE-AGGREGATE-V1`；BASE104_V1=`bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8`；NEW21_V1=`dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850`；ALL125_V1=`75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b`；旧草案值 `2aeca26e…/189612b6…` 标记为 `REJECTED_UNVERSIONED_DRAFT`。
