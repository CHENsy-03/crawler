# 出站请求清单（TASK-022A 只读审计）

**状态：** TASK-022B / 基础库已实现 / 未接入生产
**日期：** 2026-08-14
**分支：** feat/task-022-outbound-security
**基准 HEAD：** 66ef9a73a9d219529dee12179a100a8f49a6c22f

本文件是本轮真实代码审计的路径清单。它不改变任何生产行为；`docs/OUTBOUND_REQUEST_SECURITY_CONTRACT.md` 已批准并冻结，TASK-022B 基础库已实现但尚未接入生产。

## 1. 审计方法

每一条路径都追踪到：

```text
入口 → 输入来源 → URL 构造 → 客户端/Transport → DNS → 重定向 → 响应处理 → 下游结果
```

分类定义：

- `生产可达`：从当前正式 Go CLI/API、Redis 正式消费者或 Python 正式消费者可实际触达。
- `legacy/v1`：缺版本或 `1.0` 消息路径，保留兼容行为。
- `v2`：显式 `2.0` 消息路径。
- `休眠/无调用方`：当前代码存在网络辅助函数，但没有生产调用方。
- `测试专用`：仅测试或一次性 E2E 使用本地 loopback。
- `内部服务边界`：Redis/MySQL 等平台内部连接，单独记录，不视为普通出站 HTTP。

## 2. 生产出站 HTTP 路径总览

| 编号 | 语言 | 文件/函数 | 生产可达性 | 下游 | 归属 |
|---|---|---|---|---|---|
| P1 | Python | `httpx/fetch.py` `fetch/post_json/get_json`；`httpx/session_pool.py` `get_session_for_domain` | legacy/v1 + Python CLI/兼容入口 | 搜索插件、详情抓取、Python CLI | 022G |
| P2 | Python | `crawler/site/analyzer.py` `SiteAnalyzer._fetch` → `Downloader.fetch_once` | v2 搜索 Worker | 入口页分析与候选发现 | 022B/022C/022D/022G |
| P3 | Python | `crawler/site/search_probe.py` `PinnedProbeFetcher/PinnedPoolTransport` | v2 搜索 Worker（探测与 Adapter 执行共用） | SearchPlan 探测与搜索执行 | 022B/022C/022D/022G |
| P4 | Python | `crawler/search/{html,trs,jpaas,generic_json}_adapter.py` | v2 搜索 Worker | 通过 P3 发请求，自身不直接联网 | 022G |
| P5 | Python | `plugins/trs.py`、`plugins/jpaas.py`、`plugins/html.py` | legacy/v1 搜索 Worker + Python CLI | 通过 P1 发请求 | 022G |
| P6 | Python | `workers/parser_worker.py` | v2/v1 HTML 解析正式消费者 | 只连接 Redis，不发起出站 HTTP | 022G（不涉及） |
| P7 | Python | `crawler/detail_scheduler.py` `_fetch_one_detail` | Python CLI/legacy 详情路径 | 通过 P1 抓详情正文 | 022G |
| P8 | Python | `api/server.py`、`monitor/health.py` | 入站 HTTP 服务 | 不发起出站 HTTP | 022G（不涉及） |
| P9 | Python | `parser/ai_parser.py` `_call_ai_api` | 休眠占位 | 当前无网络实现；配置 `ai_enabled=false` | 022D/022E 决策 |
| G1 | Go | `go-spider/internal/client/resty.go` `RestyFetcher.FetchHTML/Fetch` | 生产 v2 + legacy/v1 下载 | Go Worker Pool / V2DownloadCoordinator | 022B–022G |
| G2 | Go | `go-spider/internal/client/resty.go` `SearchArticles/searchTRS/searchJPAAS` | 当前无生产调用方 | 无 | 022G |
| G3 | Go | `go-spider/internal/httpx/client.go` `Client.Get` | 当前无生产调用方 | 无 | 022G |
| G4 | Go/Python | `go-spider/internal/queue/redis.go`；`workers/*.py` redis client | 内部服务边界 | Redis 队列 | 不属 SSRF 出站 HTTP，单独审计 |
| G5 | Go | `go-spider/internal/store/mysql.go` | 内部服务边界 | MySQL | 不属 SSRF 出站 HTTP，单独审计 |
| G6 | Go | `go-spider/internal/api/*` | 入站 HTTP 服务 | 只推 Redis，不直接出站 | 不涉及 |

## 3. Python 路径详情

### P1：requests/urllib3 Session 包装（legacy + Python CLI）

- 入口：`main.py` CLI（`--urls`、`--site`、`--discover`、`--with-detail`）、`scheduler/dispatcher.py`、`crawler/pipeline.py`、`crawler/crawl_scheduler.py`、legacy 搜索 Worker `workers/search_worker.py` v1 分支、`plugins/*.py`、`crawler/detail_scheduler.py`。
- 输入来源：CLI 参数、`config/site.json` 的 `base_url/api_url/page_url`、搜索返回的相对/绝对链接、表单 action、静态页面链接。
- URL 构造：配置直用、`plugins/html.py _build_search_url`、`urljoin`、`parse_trs_doc`/`map_jpaas_legacy_article` 拼接。
- 客户端：`requests.Session` + `HTTPAdapter`（urllib3），按 `urlparse(url).netloc` 建域 Session，Session 共享 Cookie。
- 方法：GET（`fetch/get_json`）、POST form（`post_json`）。
- 重定向：默认自动跟随，`requests.DEFAULT_REDIRECT_LIMIT=30`；`fetch_once` 显式 `allow_redirects=False`。
- 代理：`Session.trust_env=True`，默认读取系统/环境代理；未显式禁用。
- TLS：默认证书校验；无自定义 SNI/证书策略；无 IP 固定。
- DNS：系统解析，由 urllib3 在每次新连接时解析；无自定义解析器。
- 连接与 Host/SNI：无法分离；连接地址由 URL hostname 解析，无预检固定。
- 超时：`fetch/post_json/get_json` 默认 15s，requests 将数值超时传给 urllib3 connect/read；没有独立 connect/read/total 分项，也没有严格的墙钟总 deadline。
- 响应限制：`fetch/post_json/get_json` 无响应体上限；`fetch_once` 支持 `max_bytes` 流式上限（Analyzer 传 2 MiB），但自动解压后的实际字节以解码后流计。
- 安全控制：限流、熔断、重试、UA 轮换、Session 池。
- 缺口：私网/IP 策略、代理控制、每跳重定向校验、响应体上限、解压后上限、连接固定、DNS TOCTOU、日志脱敏均缺失。

### P2：SiteAnalyzer 入口抓取（v2）

- 入口：`workers/search_worker.py` v2 分支 → `run_v2_search_pipeline` → `SiteAnalyzer.analyze`。
- 输入来源：Go `SearchRequestedMessage.target_url`（用户/API/CLI 提供）。
- URL 构造：`crawler/site/normalizer.py normalize_target_url`（http/https、无 userinfo、无空白/控制字符、IDNA、端口校验）。
- 客户端：`Downloader.fetch_once` → requests Session，`allow_redirects=False`、`stream=True`。
- 重定向：Analyzer 手工循环，最多 `DiscoveryLimits.max_redirects=5`；每跳执行 `redirect_allowed`（同 origin 或 HTTP→HTTPS 且 80→443）并重新 `security_check`。
- 代理：requests `trust_env=True`，环境代理仍可能生效；Analyzer 不控制。
- DNS：`crawler/site/security.py resolve_host` 先做一次 `socket.getaddrinfo` 全地址校验，随后 requests 仍会再次系统解析；存在 TOCTOU。
- TLS：默认证书校验；连接没有固定到预检 IP。
- 响应：2 MiB 流式上限、Content-Type 白名单（text/html、application/xhtml+xml）、非 2xx/超限拒绝。
- 缺口：预检与实际连接分离、代理、逐跳 DNS/连接固定、日志 URL 脱敏。

### P3：PinnedProbeFetcher / PinnedPoolTransport（v2 搜索探测与执行）

- 入口：`workers/search_worker.py` v2 分支 → `PinnedProbeFetcher`；正式 Adapter 执行复用同一 fetcher。
- 输入来源：`SiteAnalyzer` 生成的 `SearchCandidate.request_shape`、`SearchPlan.endpoint`、keyword。
- URL 构造：`normalize_target_url` + `_build_url`；`_validate_probe_url` 强制 http/https、无 userinfo、非 IP literal、非 localhost、仅 80/443、approved origin 内。
- 客户端：urllib3 自定义 `PinnedPoolManager/PinnedHTTP(S)Connection`，`urlopen(redirect=False)`。
- DNS：`resolve_host` 使用 `socket.getaddrinfo` 获取全部地址；全部地址分类通过后才继续；选择 `ips[0]` 作为连接目标。
- 连接固定：`PinnedHTTPSConnection._new_conn` 连接到已验证 IP，`self.host`/`server_hostname` 仍保留原 hostname；因此当前实现具备“连接 IP 固定 + Host/SNI/证书按 hostname”的基础形态。
- 重定向：手工最多 3 跳，每跳重新 URL 规范化与 approved origin 校验。
- 代理：直接使用 urllib3 `PoolManager`，不读取环境代理。
- TLS：默认证书校验；无自定义 CA 策略；HTTPS 证书按原 hostname 验证。
- 超时：总预算 10s（`total_timeout_seconds`），每跳传入剩余时间；DNS 解析本身没有独立超时。
- 响应：`_read_limited` 流式读取，`decode_content=True`，上限 2 MiB（解压后）；Content-Type 白名单；challenge 页面拒绝。
- 缺口：DNS 超时、IPv6/地址选择策略、CNAME/rebinding 复验策略、跨域 redirect 规则（当前只允许 approved origin）、并发/池资源预算、日志脱敏均未完全覆盖。

### P4：v2 正式 Adapter（四类 adapter / 六类搜索形态）

- 六类搜索形态：HTML GET、HTML POST form、TRS、JPAAS、Generic JSON GET、Generic JSON POST；对应四个受控 `adapter` 名称（html/trs/jpaas/generic_json）。
- 全部通过注入的 `fetcher.fetch` 发请求，自身不创建第二个客户端。
- 结果 URL 校验：`_validate_result_url` 强制 http/https、无 userinfo、同 plan domain、path 前缀允许；结果 URL 不主动抓取。
- 安全属性继承 P3。

### P5：legacy 搜索插件

- `plugins/trs.py`：`dl.post_json(api_url, params, site_cfg)`。
- `plugins/jpaas.py`：`dl.get_json(api_url, params, site_cfg)`。
- `plugins/html.py`：`dl.fetch(url, site_cfg)`（含 `_build_search_url` 手工拼接 query）。
- 无 URL/域名/IP 预检；使用 P1 的 requests Session。
- 输入来源：`config/site.json` 和 legacy Redis v1 `site/keyword`。
- 风险：配置被替换或消息被投毒时可请求任意 host；redirect/代理/响应体限制同 P1。

### P6/P8：解析 Worker、API、健康服务

- `workers/parser_worker.py`：只 BRPOP `crawler:html` 并 LPUSH `crawler:result`，无出站 HTTP。
- `api/server.py`：仅处理入站请求，不消费队列、不发起出站请求。
- `monitor/health.py`：仅启动本地 HTTP server。
- 不构成出站网络路径。

### P9：AI 占位

- `parser/ai_parser.py _call_ai_api` 当前不实现网络调用并返回 `None`；`config/parser.json` 默认 `ai_enabled=false`。
- 若未来启用，将构成新增第三方出站路径，必须先经 022D/022E 决策并接入共享安全 transport。

## 4. Go 路径详情

### G1：RestyFetcher（生产下载）

- 入口：`go-spider/internal/worker/pool.go`（legacy/v1 `Fetch`）与 `v2_download_coordinator.go`（v2 `FetchHTML`）。
- 输入来源：`crawler:url` 消息（v2 `URLMessageV2` 或 legacy `HTMLPayload`）；URL 由搜索适配器、CLI `--url`、API `target_url` 产生。
- URL 校验：
  - v2：`protocol.ValidateTargetURL` 只检查 http/https、host 非空、端口数字范围、无首尾空白；不拒绝 userinfo、IP literal、localhost、私网 IP、非标准端口。
  - legacy/v1：下载前没有 URL 校验。
- 客户端：Resty v2.17.2，`resty.New()`；默认 `http.Transport` 使用 `http.ProxyFromEnvironment`、Dialer 30s、TLSHandshake 10s、HTTP/2、KeepAlive 30s、MaxIdleConns 100。
- 方法：GET。
- 重定向：Resty 未设置 `SetRedirectPolicy`，`http.Client` 默认最多 10 跳；`FetchHTML` 读取 `RawResponse.Request.URL` 作为 final URL；无每跳安全校验。
- 代理：默认环境代理生效，未禁用、未审计。
- TLS：默认证书校验；未设置 SNI/证书主机名策略；证书仍按请求 hostname 校验。
- DNS：系统解析；连接地址与 Host/SNI 不能分离；无 IP 分类。
- 超时：`SetTimeout(15s)` 是 `http.Client.Timeout`（含连接、重定向、响应体）；无 connect/header/body 分项。
- 响应限制：`ResponseBodyLimit=0`（无限）；`resp.String()` 一次性读入内存；自动解压无上限。
- 重试：`SetRetryCount(3)`、`SetRetryWaitTime(1s)`。
- 缺口：SSRF/IP/域名策略、代理控制、逐跳重定向、DNS 固定、响应体/解压预算、连接池上限、日志脱敏均缺失。

### G2：SearchArticles / searchTRS / searchJPAAS（休眠）

- 当前 `rg "SearchArticles"` 仅命中定义与测试，无生产调用方。
- 各自 `resty.New().SetTimeout(15s)`；同样使用环境代理、默认重定向、无响应体限制、无 URL/IP/域名策略。
- 标记为休眠 legacy 路径；接入前必须纳入 022G。

### G3：internal/httpx.Client.Get（休眠）

- 当前无生产调用方。
- 使用 Resty，`SetTimeout(15s)`、限流、熔断、重试、dead queue；未设置代理/redirect/body/连接固定。
- 标记为休眠路径；接入前必须纳入 022G。

### G4：Redis 内部边界

- `go-spider/internal/queue/redis.go`：`DialTimeout/ReadTimeout/WriteTimeout=3s`，无 TLS/ACL/密码配置。
- `workers/search_worker.py`、`workers/parser_worker.py`：`redis.Redis(host, port)`，无显式超时/TLS。
- 属于内部服务边界资产，不是外网 SSRF 请求，但在威胁模型中作为内网可达资产记录。

### G5：MySQL 内部边界

- `go-spider/internal/store/mysql.go`：DSN 来自环境变量，GORM AutoMigrate legacy 三表；无显式 TLS/连接池/超时配置。
- 属于内部服务边界资产，单独记录。

### G6：Go API 入站

- `go-spider/internal/api/router.go`：Gin 服务，仅处理 `/task/create`、`/task/status`、`/articles` 等；向 Redis 推消息，不直接发起出站 HTTP。
- 不构成出站网络路径。

## 5. canonical / 文档解析 / 其他边界

- `canonical_url`：`crawler/detail/extraction_v2.py` 只从 `<link rel="canonical">` 规范化并写入结果，不发起请求。
- `crawler/parser/document_safety.py`、`crawler/parser/pdf.py`、`crawler/parser/office.py`：无网络、无 subprocess、无文件写入。
- `storage/manager.py`：DuckDB 本地文件，无网络。
- `frontend/`：无生产后端出站调用，本审计不将其视为正式出站路径。

## 6. 当前安全控制汇总

| 维度 | P1（legacy） | P2（Analyzer） | P3（Probe v2） | G1（Go 下载） |
|---|---|---|---|---|
| URL scheme 白名单 | 无 | http/https | http/https | v2 http/https；legacy 无 |
| userinfo 拒绝 | 无 | 有 | 有 | v2 无；legacy 无 |
| IP literal/localhost 拒绝 | 无 | 部分（`security_check` 检查 IP） | 有 | 无 |
| 私网/特殊 IP 拒绝 | 无 | 有（预检） | 有（全地址） | 无 |
| 连接固定已验证 IP | 无 | 无（TOCTOU） | 有 | 无 |
| 每跳 redirect 校验 | 无（自动 30） | 有（最多 5） | 有（最多 3） | 无（自动 10） |
| 环境代理禁用 | 无（默认启用） | 无（默认启用） | 不读取（直接 PoolManager） | 无（默认启用） |
| TLS 证书校验 | 默认 | 默认 | 默认 | 默认 |
| connect/read/total 分项 | 无 | 无 | 总预算 10s | 无 |
| 响应体上限 | fetch 无 / fetch_once 有 | 有（2 MiB） | 有（2 MiB 解压后） | 无 |
| 解压后上限 | 无 / 流式 | 流式 | 流式 | 无 |
| 日志 URL/query 脱敏 | 无 | 部分（evidence 脱敏） | 无 | 无 |

## 7. 文档一致性处理记录

- `docs/DEVELOPMENT_RULES.md` 原文件缺失，已在 TASK-022A 补建，并在 TASK-022A-R 记录 D-01 至 D-12 冻结状态。
- `docs/UNIFIED_SEARCH_ADAPTER.md` 的历史路线 `TASK-018 → TASK-022 → TASK-020` 已在 TASK-022A-R 标记为历史旧路线/SUPERSEDED，并指向当前唯一完整路线 `TASK-019 → TASK-022 → TASK-021A → TASK-020A → TASK-020B`。
- `docs/TASK_019_ACCEPTANCE.md` 的 `TASK-022A=NOT_STARTED` 已保留为 E-3 封板时快照，并增加后续状态说明。

## 8. TASK-022B 基础库（未接线）

- 新增 `crawler/security` 与 `go-spider/internal/security` 纯函数基础库。
- 实现 URL 规范化、显式 IP 分类表、可注入 Resolver 全地址验证、exact host/scheme/port/redirect 策略判定。
- Python/Go 读取同一份 `tests/fixtures/outbound_request_security_contract.json`（164 cases）。
- 当前没有生产调用方；现有 HTTP 客户端、Adapter、Worker、queue、protocol 均未 import 新包。
- 固定连接、重定向/代理/资源预算、生产接线分别属于 TASK-022C/022D/022G。
## 9. TASK-022C Pinned Transport（未接线）

- `PinnedTarget` 绑定已验证地址、端口、Host header 与 server_name；TCP 只连接数字 IP。
- Host header 使用规范化 hostname；HTTPS ServerName 与证书校验使用原 hostname。
- 本地 loopback 测试通过测试内部构造注入；生产公开 API 无测试开关。
- 当前没有生产调用方；代理、redirect、资源预算与生产接线分别属于 TASK-022D/022G。
## 10. TASK-022D-1 纯决策层（未接线）

- Python/Go 新增固定预算模型：整数 ms/bytes，probe/search/detail 三类 total deadline 与 response body 上限；未知 profile、bool/负值/超限稳定拒绝。
- redirect planner 每跳重新规范化并执行完整 policy/DNS/IP/pin 重验，禁止 HTTPS→HTTP，最多 3 跳，不自动跟随网络请求。
- proxy 合同拒绝任意非空代理配置，安全包不读取环境代理。
- 共享 fixture：tests/fixtures/outbound_transport_policy_contract.json（44 cases：budget 21、redirect 17、proxy 6）。
- 当前没有生产调用方；实际响应读取、流式计数、idle timer、并发限流与生产接线属于 TASK-022D-2/022G。
## 11. TASK-022D-2 运行时基础原语（未接线）

- 大小门、有界读取、read-idle/total timeout、全局/单 hostname 并发限流仅作为未接线安全基础库。
- 实际 socket/HTTP Transport 适配、wire-level header 计数、idle pool 与生产组合属于 TASK-022D-3。
- 共享 fixture：tests/fixtures/outbound_runtime_limits_contract.json（105 cases：size 40、read 26、concurrency 39）。
## 12. TASK-022D-3 隔离安全 HTTP 执行器（未接线生产）

- Python 新增 `crawler/security/http_transport.py`、`http_executor.py`；Go 新增 `go-spider/internal/security/http_transport.go`、`http_executor.go`。
- 执行器实现单跳完整调用顺序、阶段 timeout 与 total deadline 联合、raw response header 前置计数、Content-Length 预检、bounded body、逐跳 redirect 重验和共享 limiter Lease 清理。
- V1 只实现 HTTP/1.1，固定 `Connection: close`，实际 idle=0；不启用 HTTP/2 多路复用，不声称实现连接复用。
- 共享 fixture：tests/fixtures/secure_http_transport_contract.json（FIX 后 84 cases：request 18、response 42、redirect 16、resource 8）。
- FIX 后响应解析仅接受 HTTP/1.0/1.1 严格 CRLF header、1xx interim 累计上限、101/CL+TE/非单一 chunked/extension/非空 trailer 均 fail closed。
- 当前没有生产调用方；Resty、requests/httpx、Adapter、Probe、Worker、queue、protocol、store 均未切换；生产接线属于 TASK-022G。
