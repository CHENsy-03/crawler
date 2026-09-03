# 通用型爬虫安全架构

本文定义产品安全目标、信任边界、控制矩阵和 OSEC runtime 边界。OSEC Evidence/Manifest/S1/Seal Record 已 SEALED，但 production loader 为 NOT_STARTED，deployment 为 BLOCKED。

## 1. 资产与威胁矩阵

| 资产 | 主要威胁 | 控制 |
|---|---|---|
| 管理员账号与 Session | 凭证猜测、Session 窃取 | 单管理员 bootstrap、密码 hash、30 分钟空闲/8 小时绝对过期、HttpOnly/Secure/SameSite |
| API Token | Token 泄露、越权使用 | 只存 hash、轮换、吊销、scope 限制 |
| 浏览器会话 | CSRF | CSRF token、SameSite Cookie、同源写校验 |
| 出站 HTTP | SSRF、恶意 DNS/IP、redirect 逃逸 | URL/DNS/IP 策略、pinned transport、逐跳 redirect 校验、fail-closed |
| 采集内容 | 恶意附件、超限响应 | 类型/魔数/大小/内容检查、有界 I/O、文档安全门 |
| 原始证据 | 篡改、覆盖 | 内容寻址只读文件卷、content_hash、审计日志 |
| 配置与 secrets | 泄露、错误放行 | sealed security 优先级、Docker secrets、无默认放行 policy |
| 日志/审计 | 敏感信息泄露、不可审计 | 脱敏、低基数 metrics、audit log append-only |
| 生产安全配置加载 | 未加载或错误降级 | production loader、启动前全量验证、fail-closed |

## 2. 信任边界

- 外部不可信网络：公网/外部站点。
- edge/DMZ：nginx，唯一对外暴露和 TLS 终止边界，不得直接视为信任区。
- app：web、go-api、python worker 的受控内部网络。
- data：mysql、redis、raw_evidence 等数据面，只允许 app 受控访问。
- observability：prometheus/grafana 指标面。
- Web/Go API 不是“只接收已认证请求”的绝对边界：bootstrap、`/healthz`、`/readyz` 是认证规则例外；健康探针只用于容器编排和受控运维。
- 低信任内容：外部站点响应、附件、JavaScript 渲染内容。
- 采集 Worker 必须把外部响应视为不可信数据。
- MySQL/Redis 只允许 app 网络访问。

## 3. 认证与 Session

- 首次管理员初始化使用一次性 bootstrap token，成功后失效。
- Session 空闲 30 分钟过期、绝对 8 小时过期。
- Session token 只存 hash；Cookie 使用 HttpOnly、Secure 和合适 SameSite。
- 密码和恢复密钥不得写入日志。
- 登录必须启用防暴力控制：速率限制、失败审计和受控冷却。
- bootstrap、health/readiness 是认证规则例外，但必须按例外最小化设计。

## 4. API Token

- API Token 只存 hash，创建响应只返回一次明文。
- 支持轮换、吊销和过期。
- Token 调用外部 API 不依赖 Cookie CSRF。
- API Token scope 模型需要在 Go OpenAPI 中显式定义；scope 未定义前不得授予宽泛 Token。

## 5. CSRF、CSP 与 TLS

- 同源浏览器写操作要求 CSRF token。
- 默认启用 CSP 和必要安全响应头。
- 生产入口使用 TLS，nginx 终止。
- API 错误不得暴露内部堆栈、凭据、Cookie 或内部地址。

## 6. 出站安全

- SSRF 防护覆盖协议、DNS 解析、IP 网段和 redirect 链。
- URL 规范化保守执行；禁止 IP literal 生产出站。
- SEALED transport 硬上限：
  - DNS/connect/TLS timeout=5 秒
  - response header timeout=10 秒、read idle timeout=15 秒
  - probe/search total=30 秒、detail total=60 秒
  - request body=1MiB、response headers=256KiB
  - probe response body=1MiB、search response body=8MiB、detail response body=20MiB
  - redirects 最多 3 跳
  - transport global_active=20、per_host_active=5、per_host_idle=2
- TARGET_V1 产品调度默认值：global active tasks HTTP budget=16、单域默认=2、允许配置上限=4；该层尚未完整接入。
- 瞬时错误最多重试 3 次，指数退避并带 jitter。

## 7. 附件与文件安全

- 仅允许白名单内 PDF/DOCX 附件解析。
- 校验 MIME/魔数、大小、重定向、恶意内容和存储路径。
- 文档解析在隔离 Worker/安全进程中执行，禁止执行宏和外部关系加载。
- 原始附件写入只读卷，不允许覆盖。

## 8. 审计日志

- 记录关键管理操作、配置变更、导出、Token 操作、审核决定和安全事件。
- AuditLog append-only。
- 安全证据永久保留。
- 日志和错误不包含 secret、Token、密码、完整 URL 中的敏感参数或内部 IP。

## 9. OSEC 证据链与 runtime 边界

- 已 SEALED：OSEC Manifest V2、S1 evidence seal commit、Seal Record V2。
- NOT_STARTED：production loader、site migration、production client wiring、production logging redaction。
- runtime fail-closed 接入仍是发布门禁，不属于已完成。
- 前端安全状态页面只读，不展示敏感值。

## 10. 安全验收条件

- P0/P1 安全问题 = 0。
- SSRF/redirect/DNS 绕过测试全部通过。
- production loader 未验证时服务不得标记 ready。
- secrets 不出现在镜像、Compose、日志或错误中。
- 原始证据不被审核或规范化流程覆盖修改。
- 发布物包含 SBOM。
- production loader 与生产接线未完成时，SSRF 基础库通过不能解除部署阻塞。

## 11. 发布安全门禁

- production loader 已接入并完成 fail-closed 验证。
- 无 P0/P1 安全问题和未批准越权/SSRF 失败。
- CSRF、CSP、TLS、secrets 和审计日志满足验收。
- 20 站 canary 与安全测试未发现绕过访问控制。
- 任一发布安全门禁失败时 deployment 继续 BLOCKED。
