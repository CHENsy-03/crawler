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

- 本文件是合同，不是实现。
- 当前生产路径仍存在 `docs/OUTBOUND_REQUEST_INVENTORY.md` 所列风险。
- TASK-022B 尚未开始。
- 当前版本不可部署。
