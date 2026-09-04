# 出站请求威胁模型（TASK-022A 只读审计）

**状态：** TASK-022A-R / APPROVED / FROZEN FOR IMPLEMENTATION
**日期：** 2026-08-14
**关联：** `docs/OUTBOUND_REQUEST_INVENTORY.md`、`docs/OUTBOUND_REQUEST_SECURITY_CONTRACT.md`、`docs/decisions/ADR-016-outbound-request-security-boundary.md`

本文件描述当前生产出站请求面对的威胁、信任边界和风险场景。它不改变任何代码行为。

## 1. 核心结论

“Web V1 部署在公司内网”不等于“爬虫出站请求默认允许访问私网地址”。当前 Go 下载链和 Python legacy 链都没有完整私网/IP/域名策略；即使部署在内网，也必须把 SSRF 视为真实风险。

## 2. 资产

| 编号 | 资产 | 说明 |
|---|---|---|
| A1 | 公司内网与宿主机网络 | 爬虫 Worker 所在网络可访问的内部服务 |
| A2 | loopback 服务 | 127.0.0.1/::1 上的本机服务 |
| A3 | Redis/MySQL 等内部服务 | 平台自身依赖，也属于被 SSRF 探测的目标 |
| A4 | 云主机 metadata 地址 | 169.254.169.254、fe80::/10 等元数据端点 |
| A5 | 管理员会话与 JSON API token | Go API 当前无鉴权，后续 TASK-020 引入会话/token |
| A6 | 代理凭据 | 若环境代理被读取并带凭据，可能泄露给恶意代理 |
| A7 | 搜索关键词与 URL query | 用户输入和搜索词可能进入日志、错误、证据 |
| A8 | 下载正文与日志 | 响应正文、HTML、URL、query 可能被记录 |
| A9 | Worker 可用性与系统资源 | 慢响应、超大响应、连接池耗尽影响可用性 |

## 3. 攻击者

| 编号 | 攻击者 | 能力 |
|---|---|---|
| AT1 | 持有 JSON API token 的恶意/失陷调用方 | 提交任意 target_url；未来 API token 一旦启用即可触发出站 |
| AT2 | 被攻击者控制的搜索结果或网页 | 控制搜索结果 URL、Location、canonical 或页面内容 |
| AT3 | 恶意站点配置 | 替换 `config/site.json` 或配置加载来源 |
| AT4 | DNS 污染/DNS Rebinding | 控制解析结果或在两次解析之间切换 IP |
| AT5 | 恶意重定向目标 | 返回 Location 指向内网/metadata/降级 scheme |
| AT6 | 被污染的系统代理环境变量 | 通过 HTTP_PROXY/HTTPS_PROXY 把流量导向代理 |
| AT7 | 返回超大或压缩炸弹响应的服务器 | 消耗内存/CPU/带宽 |
| AT8 | 利用 legacy/v1 消息生产者的攻击者 | 绕过 v2 安全规则投递旧格式 URL |

## 4. 信任边界

- 边界 1：外部站点与爬虫 Worker 之间。最需要防护。
- 边界 2：Redis 消息生产者与消费者之间。任何能向 `crawler:url` 投递消息的进程都可触发出站请求。
- 边界 3：配置文件与生产进程之间。配置中的 endpoint 会被直接请求。
- 边界 4：系统 DNS/代理环境与进程之间。解析和代理结果默认被信任。
- 边界 5：Go API 入站与内部队列之间。当前无认证，但出站 URL 来自用户参数。

## 5. 攻击场景与当前状态

### SSRF 到 loopback/private/link-local/metadata

- 当前状态：Go `RestyFetcher.FetchHTML/Fetch` 无 IP 分类；Python legacy `requests` 链无 IP 分类；Python v2 Analyzer 有预检但连接会二次解析；Python v2 Probe 有全地址分类并固定连接。
- 场景：向 `crawler:url` 投递 `http://127.0.0.1:3306/` 或 `http://169.254.169.254/latest/meta-data/`，Go 下载链可触达。
- 影响：内网侦察、metadata 泄露、内部服务滥用。

### IPv4/IPv6/IPv4-mapped、特殊表达

- 当前状态：Python `classify_ip` 对 IPv4-mapped IPv6 做归一化；Go 无分类。URL 规范化尚未统一处理十进制/八进制/十六进制 IP、IPv6 简写、尾点域名。
- 场景：`http://2130706433/`、`http://0x7f000001/`、`http://[::ffff:127.0.0.1]/` 可能在部分解析器中到达本机。
- 影响：绕过基于文本的域名/IP 黑名单。

### IDNA、Unicode、尾点域名

- 当前状态：Python `normalize_target_url` 使用 `idna.encode`；Go `ValidateTargetURL` 不执行 IDNA 规范化。
- 场景：Unicode 同形域名或带尾点域名绕过按字符串匹配的策略。
- 影响：域名策略/白名单失效。

### URL userinfo、反斜杠、空白、控制字符

- 当前状态：Python v2 规范化拒绝 userinfo/空白/控制字符；Go v2 只拒绝首尾空白，legacy 无校验。
- 场景：`https://attacker@127.0.0.1/` 在 Go 下载链中可携带 userinfo 并被请求。
- 影响：授权混淆、日志泄露。

### 非 HTTP/HTTPS scheme

- 当前状态：Python v2 限制 http/https；Go v2 `ValidateTargetURL` 限制 http/https；Go legacy 无限制；Resty/requests 通常只支持 http/https，但消息可能产生错误行为。
- 影响：低；但仍应在统一入口拒绝。

### 异常端口与默认端口混淆

- 当前状态：Python v2 Probe 只允许 80/443；Analyzer 允许任意合法端口；Go 下载链允许任意端口。
- 场景：`https://legit.example:8443/` 连接内网非标准端口。
- 影响：端口扫描、服务探测。

### DNS 多 A/AAAA、CNAME、DNS Rebinding

- 当前状态：Python Probe 检查全部解析地址并固定到已验证 IP；Python Analyzer 预检后二次解析（TOCTOU）；Go 无解析前校验。
- 场景：第一次解析为公网 IP，随后解析切换为 127.0.0.1；或 A/AAAA 中只有一个是内网地址。
- 影响：绕过 IP 策略；连接固定后仍有首次解析、重试、连接池复用等重解析风险。

### DNS 校验与实际连接之间的 TOCTOU

- 当前状态：`SiteAnalyzer` 先 `security_check`，再由 requests 重新解析；Go 完全无预检。
- 影响：校验结果与连接目标不一致。

### 重定向到禁止地址

- 当前状态：Python Analyzer/Probe 有逐跳校验；Go Resty 自动跟随最多 10 跳且无每跳校验；Python legacy requests 自动跟随最多 30 跳。
- 场景：公网 URL 302 到 `http://127.0.0.1/` 或 `http://169.254.169.254/`。
- 影响：SSRF 在重定向阶段发生。

### HTTPS 降级到 HTTP

- 当前状态：Python Analyzer 只允许 HTTP→HTTPS 升级；Python Probe 要求同 approved origin（不含降级）；Go/Resty 默认允许跨 scheme 重定向。
- 场景：`https://site` 302 到 `http://site` 或攻击者域。
- 影响：明文传输、凭据/正文泄露。

### 环境代理绕过目标校验

- 当前状态：Go Resty 默认 `http.ProxyFromEnvironment`；Python requests `trust_env=True`；Python Probe 不读取环境代理。
- 场景：HTTP_PROXY 指向攻击者代理，目标校验无法控制代理实际连接地址。
- 影响：SSRF 防护失效、代理凭据泄露。

### Host header/SNI/证书校验错配

- 当前状态：Python Probe 固定连接 IP 时保留原 hostname 作为 Host/SNI/证书验证，形态正确；Go/Python legacy 无法分离连接地址与 Host/SNI。
- 场景：恶意 IP 直接作为 hostname 或连接地址与 SNI 不一致。
- 影响：证书校验与目标身份错配。

### 自动解压导致资源耗尽

- 当前状态：Go `resp.String()` 自动解压且无上限；Python legacy 自动解压无上限；Python Probe/`fetch_once` 在解码流上限制字节。
- 场景：返回 1 MiB gzip 解压为 1 GiB。
- 影响：内存耗尽、Worker 崩溃。

### 无响应、慢响应、连接池耗尽

- 当前状态：Go 15s client timeout；Python legacy 15s/10s 超时；Python Probe 总预算 10s。无每 host 连接上限、无并发预算、无背压。
- 场景：大量慢连接占满连接池或 goroutine。
- 影响：平台不可用。

### 完整 URL、query、header、Cookie、正文进入日志

- 当前状态：Go/Python 多处日志记录 `url`，`query` 未统一脱敏；Session 共享 Cookie；Resty 默认日志可能记录请求。
- 场景：URL 含 token/密码或正文敏感数据被写入日志/错误/死信。
- 影响：敏感信息泄露。

### legacy/v1、调试入口绕过共享安全层

- 当前状态：v2 `ValidateTargetURL` 与 Python Probe 有部分校验，但 legacy/v1 下载和 Python legacy 插件仍可被直接投递；`SearchArticles`、`internal/httpx.Client` 等休眠入口若被唤醒可绕过。
- 场景：攻击者向 `crawler:url` 投递无版本 legacy 消息，绕过 v2 校验。
- 影响：共享安全层不共享。

### 本地 E2E 依赖 loopback 与生产默认拒绝 loopback 的冲突

- 当前状态：B7/B8/022H 测试使用 127.0.0.1；生产默认拒绝 loopback 后，测试必须通过测试专用依赖注入获得许可。
- 风险：如果实现为“全局允许 loopback”开关，生产配置可能误开启。
- 要求：测试许可必须是测试代码注入，不能是生产配置开关。

## 6. 日志与指标敏感面

- 禁止记录：Authorization、Cookie、代理凭据、完整 query、完整 payload、密码/DSN。
- 允许记录：hostname（经归一化/低基数）、阶段、错误类型、状态码、reason。
- 当前状态：不满足；`log.Printf("fetch html %s ...", url)` 等记录完整 URL。

## 7. 阶段映射

- 022B：URL 规范化、IP 分类、DNS 多地址验证。
- 022C：连接固定、Host/SNI/证书一致性。
- 022D：重定向、代理、超时、响应体/解压预算。
- 022E：域名/端口/HTTP 管理策略。
- 022F：日志脱敏、低基数指标、安全事件。
- 022G：Probe、Adapter、legacy pipeline、Go Worker 统一接入。
- 022H：对抗测试、完整回归、Race、隔离 E2E。

D-01 至 D-12 已批准并冻结，具体选项与精确预算见安全合同。
