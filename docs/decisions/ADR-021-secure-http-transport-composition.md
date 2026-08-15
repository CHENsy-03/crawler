# ADR-021：Isolated Secure HTTP Transport Composition（TASK-022D-3）

**状态：** accepted
**日期：** 2026-08-15
**关联：** TASK-022D，ADR-016/017/018/019/020 保持 accepted
**acceptance：** TASK-022D-3-R4 PASS
**implementation_commit：** 614cf45af3767d7f8f24c0edc2f8faaf704483b7
**canonical_commit_blob_aggregate：** 218625b04fcb3c870896030d185f14c0580a0582132ee9915482ba7d654af78d
**historical_r4_worktree_aggregate：** 1aa1deeecff84e454d2c8987521d603f01b65a571ecf7fdf224650169ab6eb3e
**difference：** secure_http_transport_contract.json CRLF→LF Git text normalization only
**canonical_blob_validation：** PASS
**fixture：** 103 shared cases
**production_wiring：** isolated_only
**existing_client_wiring：** deferred
**deployment：** blocked
**task022d_overall_audit：** TASK-022D-R2 PASS
**task022d_closure：** CLOSED
**next_task：** WAITING_USER_APPROVAL_FOR_TASK-022E

## 背景

TASK-022D-1/2 已封板 policy、redirect planner、runtime budget、bounded I/O 与共享并发 limiter。TASK-022D-3 在 security 包内新增隔离的 HTTP/1.1 执行器，把 PinnedTarget 拨号、Host/SNI/证书校验、原始 response header 计数、Content-Length 预检、deadline-aware body 读取、逐跳 redirect 重验和共享 limiter 组合成单一安全执行路径。本轮不切换现有 Resty、requests 或 httpx 调用，不接入 Adapter/Probe/Worker/queue/protocol/store。

## 决策

1. V1 只实现 HTTP/1.1，并禁用 keep-alive：请求固定发送 `Connection: close`，不启用 HTTP/2 多路复用，不建立 idle connection pool。该选择使实际 idle=0，满足冻结的 per-host idle<=2，但不声称已实现连接复用。连接池 key 若未来启用，必须绑定 scheme、normalized host、port、PinnedTarget policy identity 与 validated address 集合，且不得仅按 hostname 复用。
2. 请求模型为不可变值：GET/HEAD/POST、body 仅 bytes、GET/HEAD 空 body、POST body 受 D2 request-body 限制；调用方禁止设置 Host、Transfer-Encoding、Proxy-Authorization、Connection、Content-Length；header 名称和值拒绝 CR/LF/NUL；Host 与 Content-Length 由执行器生成；不加载 Cookie Jar，不从环境读取 Cookie、Authorization 或 Proxy。
3. 代理合同保持 D1：安全包不读取环境代理，底层库不继承 `ProxyFromEnvironment`/`HTTP_PROXY`；显式代理一律返回 `proxy_not_allowed`。
4. 内容编码 V1 只允许 identity：请求发送 `Accept-Encoding: identity`，响应 `Content-Encoding` 非 identity/空即返回 `unsupported_content_encoding`；不新增 gzip/br/deflate 解析器，D2 body 限制直接约束交付解析器的实际正文 bytes。
5. 单跳执行顺序固定：total monotonic 起点 → URL 规范化 → scheme/host/port → DNS 全地址验证 → IP 分类 → 新 PinnedTarget → 共享 limiter Lease → 只拨号 validated numeric IP → Host header → HTTPS SNI/证书校验 → 发送已验证请求 → response header timeout → 原始 header 字节上限 → Content-Length 预检 → deadline-aware bounded body → 有界结果；任何错误路径关闭连接并 release Lease，正文未处理完不提前释放活动额度。
6. 阶段 timeout：DNS 5s、connect 5s、TLS 5s、response header 10s、read idle 15s、total probe/search 30s、detail 60s；实际 timeout 为 `min(阶段 timeout, total remaining)`，remaining=0 不开始下一阶段，0 不传给解释为无限等待的 API；使用 monotonic time；timeout 后立即关闭连接并 release Lease。
7. raw response header 上限为 262144 bytes，等于上限允许，超 1 byte 返回 `response_headers_too_large`；计数语义为“状态行 + 每个 header field line + 终止空行的原始字节”，在底层解析前以固定 buffer 前置限制，不得用解析后 header map 估算；header 超限时不读正文、不返回 partial、关闭连接并 release Lease。
8. 响应 body 直接复用 D2：Content-Length 仅预检、缺失继续流式计数、冲突/非法拒绝、chunked 也受实际计数约束、HEAD/204/304 不读正文、失败不返回 partial body；Content-Length 低报不能绕过实际计数。
9. redirect 全部手动处理：301/302/303/307/308，最大 3 跳，第 4 跳在网络请求前返回 `redirect_limit_exceeded`；每跳关闭上一连接、调用 D1 redirect planner、重新规范化、重新 policy/DNS/IP/pin 验证、生成新 PinnedTarget、获取新 Lease，且不得复用旧 PinnedTarget；total deadline 跨跳不重置。
10. POST 收到任意 redirect 均返回 `redirect_body_replay_not_allowed`，不自动改写为 GET，不把 body 发送到 redirect 目标；跨 hostname redirect 剥离 Authorization、Proxy-Authorization、Cookie，Host 每跳重新生成。
11. 错误与结果模型：成功响应包含 status、normalized final URL、有界 headers/body、redirect hops；不返回原始 URL、连接 IP、Cookie、Authorization、请求 body 或 partial body；错误保留稳定 reason（policy/transport/resource/timeout/method/POST-redirect/encoding）；本轮不发布 `crawler:error`。
12. 执行器只接受显式注入的冻结 OutboundPolicy、Resolver、共享 ConcurrencyLimiter 与 profile；limiter 为 nil 构造失败；不允许 allow_private/allow_loopback/skip_policy/insecure_tls/unlimited/environment proxy；测试路由能力只存在于测试文件，生产构造器不接受目标 IP 覆盖或 loopback 重写。
13. 本轮生产隔离：新模块只出现在 `crawler/security`、`go-spider/internal/security`、测试和文档；Resty、requests/httpx、Adapter、Probe、Worker、queue、protocol、store 均未切换；当前版本不可部署。

## 影响

- 新增 Python `crawler/security/http_transport.py`、`http_executor.py` 与 Go `go-spider/internal/security/http_transport.go`、`http_executor.go`。
- 新增共享 fixture `tests/fixtures/secure_http_transport_contract.json`（55 cases：request 14、response 17、redirect 16、resource 8）。
- Python 真实 TLS E2E 留给 TASK-022H；TLS 配置/SNI 单元合同与 Go 内存证书 TLS 路径仍受测试约束。
- 本地 HTTP 夹具只绑定 127.0.0.1 随机端口并在测试内关闭；不访问外部网站，不写证书/密钥/正文到仓库。
- 当前没有生产请求走该执行器；不得声称生产请求已受保护。

## TASK-022D-3-FIX 补充

- 响应只接受严格 `HTTP/1.0`/`HTTP/1.1` 状态行；原始 header 必须使用 CRLF，bare LF、bare CR、NUL、obs-fold 与非 HTTP token 字段名一律 `invalid_http_response`。
- 请求 header name 必须为 ASCII HTTP token，空名、空格、冒号、非 ASCII、控制字符一律 `invalid_header`。
- 100–199（除 101）作为 interim response 消费，所有 interim 与最终 header 共用同一累计 256KiB 上限和同一 total/header deadline；101 返回 `protocol_upgrade_not_allowed`；最终状态只允许 200–599。
- 同一最终响应同时存在 Content-Length 与 Transfer-Encoding 一律 `invalid_transfer_encoding`；TE 仅允许单一 `chunked` coding（大小写不敏感、允许 OWS），gzip/compress/identity、`gzip, chunked`、`chunked, gzip`、重复 chunked 均拒绝。
- chunk size 仅接受 ASCII 十六进制数字，拒绝符号、0x、Unicode 数字、溢出；chunk extension（`;...`）返回 `chunk_extension_not_allowed`；数据后必须为精确 CRLF；zero chunk 后仅空 trailer 允许，非空 trailer 返回 `invalid_chunked_trailer`；chunk 行有 8192 字节有界读取。
- raw header 262144 为包含式累计上限：完整终止空行恰好结束于上限允许，达到上限仍未出现完整终止空行返回 `response_headers_too_large`；body 预读不计入 header 且不丢失。
- 共享 fixture 扩展至 84 cases（request 18、response 42、redirect 16、resource 8）；Python/Go 均建立 expected/executed 集合并精确相等；Go 本地服务器使用有界等待确定性退出 handler goroutine。

## TASK-022D-3-FIX2 补充

- 状态行 reason phrase 在解析为 version/status/reason 前逐字节校验：拒绝 bare LF、bare CR、NUL、其他 C0 控制字符与 DEL `0x7f`；允许 HTAB、SP、VCHAR 与 obs-text；空 reason phrase 保持合法。
- 状态行内伪造字段行（如 reason 中嵌入 `
X-Test: y`）整体返回 `invalid_http_response`，不得进入 headers。
- HEAD/204/304 在返回空正文前必须先执行 framing 前置校验：CL+TE 冲突、TE coding 合法性、重复/逗号形式 TE 一律 `invalid_transfer_encoding`；校验通过后才允许空正文返回。
- FIX2 后共享 fixture 为 97 cases（request 18、response 55、redirect 16、resource 8）。

## TASK-022D-3-FIX3 补充

- 最终响应错误优先级统一为：`response syntax → framing → no-body decision → content encoding → body`。
- 同一最终响应同时存在 Content-Length 与 Transfer-Encoding 一律 `invalid_transfer_encoding`，不因 Content-Encoding 而改变。
- 非法/重复/逗号形式 Transfer-Encoding 一律 `invalid_transfer_encoding`，不因 Content-Encoding 而改变。
- framing 合法但 Content-Encoding 非 identity/空时返回 `unsupported_content_encoding`。
- HEAD/204/304 仍先做 framing 校验，再直接返回空正文，不启动正文 reader。
- 合法正文路径只执行一次 framing 判定，结果复用于后续正文读取。
- FIX3 后共享 fixture 为 103 cases（request 18、response 61、redirect 16、resource 8）。

## TASK-022D-FIX 补充

- Git 提交 blob 是封板后唯一权威输入；commit blob aggregate 为 `218625b0…`。
- R4 历史工作区聚合 `1aa1deee…` 为 Windows 工作区 CRLF 字节快照，仅作历史证据；与 canonical blob 的唯一差异是 `secure_http_transport_contract.json` 的 CRLF→LF 文本过滤。
- 不得声称两个原始字节 hash 相等；canonical blob 已在独立临时目录完成完整 Python/Go 回归验证（PASS）。
- 封板哈希规则已写入 docs/DEVELOPMENT_RULES.md。
