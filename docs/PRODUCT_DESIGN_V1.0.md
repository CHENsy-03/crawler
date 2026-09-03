# 通用型爬虫产品设计说明书 V1.0

## 1. 文档控制与阅读说明

| 项目 | 内容 |
|---|---|
| 文档版本 | V1.0 |
| 文档状态 | IMPLEMENTED_WAITING_REVIEW |
| 产品阶段 | 设计基线，尚未完成产品实现 |
| 基线 Git commit | 524fe5ea1f116fa1f496be8ec8056ef8b67db8fc |
| 冻结需求 | PD-001—PD-103 |
| 编制日期 | 2026-09-03 |

### 1.1 权威范围

本文是完整产品设计的权威入口，定义当前实现、目标 V1、目标 V1.1 和延期内容。专题文档承载可独立维护的技术契约，主文档不复制其全文。

### 1.2 非权威历史输入

- tracked V1.3/V2.0 DOCX：历史产品方案输入，不覆盖冻结 PD。
- `frontend/index.html` Vue 页面：历史残留，CURRENT_CONFLICT。
- `api/server.py` FastAPI：调试/受控接口，不是生产外部网关。
- local-artifacts：仓库外历史参考。

### 1.3 文档引用

- [docs/FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md)
- [docs/API_CONTRACT.md](API_CONTRACT.md)
- [docs/DATA_MODEL.md](DATA_MODEL.md)
- [docs/DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)
- [docs/SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md)
- [docs/TEST_STRATEGY.md](TEST_STRATEGY.md)
- [docs/SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- [docs/TASK.md](TASK.md)

### 1.4 状态标识

- CURRENT_IMPLEMENTED：当前代码和测试已证明实现
- CURRENT_PARTIAL：存在部分实现
- CURRENT_CONFLICT：当前实现与冻结目标冲突
- TARGET_V1：V1 正式目标
- TARGET_V1_1：V1.1 目标
- DEFERRED：明确延期
- NOT_VERIFIED：需要生产、性能或外部环境验证

### 1.5 编号规则

产品决策使用 PD-001 至 PD-103；模块完成度使用 R2 机器校验后的唯一主模块；缺陷使用 P0—P3。

## 2. 产品背景、目标与非目标

### 2.1 产品定位

通用型政务/公开网站采集平台，面向内部单机部署，通过 Web 管理面板进行任务创建、进度跟踪、结果审核和导出。

“任意网站，只要能搜索，尽可能自动采集”是受控含义：只采集授权范围内、可公开访问且符合站点规则的内容，不保证也不实现绕过登录、验证码、WAF 或访问控制。

### 2.2 产品目标

- Web 管理面板为主要入口。
- CLI/API 为工程、运维与集成接口。
- V1 支持内部单管理员单机使用。
- 系统提供发现、抓取、解析、评分、过滤、去重、存储、审核、导出完整闭环。
- 原始证据、规范化结果和人工审核结论分层保存。

### 2.3 非目标

- V1 不做多租户和复杂 RBAC。
- V1 不做复杂定时调度产品。
- 不绕过登录、验证码、WAF 或访问控制。
- 不从事未授权采集。
- V1.1 之前不做多站点/多主题自动发现的产品化能力。

## 3. 用户、角色、场景与范围

### 3.1 角色

| 角色 | 职责 | V1 归属 |
|---|---|---|
| 系统管理员 | 初始化、账号、系统与安全状态 | 单管理员合并承担 |
| 任务操作人员 | 创建任务、确认范围、取消、查看进度 | 同一管理员 |
| 结果审核人员 | 审核结果、复核证据 | 同一管理员 |
| 工程/运维人员 | CLI、日志、备份、恢复、健康检查 | CLI/API/受控入口 |
| 外部 API 集成方 | 通过 API Token 调用受控能力 | API Token |

### 3.2 场景

- 初始化：首次启动完成管理员 bootstrap。
- 创建任务：选择站点、输入关键词、查看范围建议。
- 确认范围：确认搜索范围和限制后执行。
- 查看进度：通过任务详情和 SSE 实时查看阶段进度。
- 审核结果：查看完整正文、证据和评分，作出审核决定。
- 导出：异步导出 CSV/XLSX/JSON。
- 插件/站点配置：注册、启停和审计插件与站点能力。
- 故障恢复：Worker lost、队列异常、服务重启和 checkpoint 恢复。
- 安全状态查看：只读查看 OSEC、production loader 和安全事件状态。

## 4. 产品功能架构与版本范围

### 4.1 V1 范围

- 单站点 Web V1：React 管理面板、认证、任务创建/确认/进度/结果/审核/导出。
- 单机内网 Docker Compose 部署。
- 立即执行任务，不做复杂定时调度。
- Go 唯一外部网关；Python 采集核心；Redis Streams + outbox；MySQL 权威。
- 原始证据不可变文件卷；DuckDB 分析与导出。

### 4.2 V1.1 范围

- 多站点/多主题自动发现产品化。
- 更完整的站点能力和插件生态。
- 企业级扩展项仅在 V1.1 或后续阶段进入。

### 4.3 DEFERRED 范围

- 多租户和复杂 RBAC：无 V1 需求，延期原因是为控制单机内部产品边界。
- 复杂定时调度：V1 仅立即任务，延期原因是产品闭环不需要。
- 浏览器 JS 渲染：只作为受控降级能力进入 V1，不作为默认抓取路径。
- Playwright 隔离 Worker：在 V1 中作为受控降级能力，不作为主链默认。

### 4.4 七大 Web 模块

1. 初始化与登录
2. Dashboard
3. 创建任务
4. 任务列表/详情/进度
5. 结果列表/详情/审核/导出
6. 站点与插件配置
7. 系统/日志/只读安全状态

### 4.5 功能依赖

- 认证/API 依赖 Go 网关和 OpenAPI。
- 任务功能依赖状态机、Redis Streams 和 Worker。
- 审核和结果依赖 MySQL 权威写入与原始证据卷。
- 导出依赖异步任务和 DuckDB/查询服务。
- 安全状态页面依赖 OSEC 只读状态接口。

### 4.6 验收边界

- Web V1 验收不包含多站点自动发现、复杂 RBAC 和复杂定时调度。
- 组件测试通过不等于完整产品 E2E 完成。
- OSEC evidence SEALED 不等于 production loader 完成。

## 5. 系统架构与职责

### 5.1 组件

| 组件 | 职责 |
|---|---|
| Nginx | 同源入口和 TLS 终止 |
| React Web | 管理面板 |
| Go Gateway | 外部 API、认证、状态、SSE、调度协调 |
| Python Worker | 发现、业务抓取、解析、评分、过滤、去重、附件处理 |
| Redis Streams | 任务与事件传递 |
| MySQL | 业务权威数据 |
| DuckDB | 分析与导出 |
| 原始文件持久卷 | 不可变原始证据与附件 |
| Prometheus/Grafana 或等价监控 | 指标与看板 |
| OSEC 外部证据 | Manifest/S1/Seal Record |

### 5.2 冻结职责

- Go：唯一外部网关、认证、API、状态、SSE、调度协调、MySQL 权威写入协调。
- Python：发现、业务抓取、解析、评分、过滤、去重、附件处理。
- Redis Streams：任务与事件传递。
- MySQL：业务权威数据。
- DuckDB：分析与导出。
- 文件卷：不可变原始证据与附件。
- Nginx：同源入口和 TLS 终止。

### 5.3 当前冲突

| 冲突 | 当前证据 | 目标 |
|---|---|---|
| Vue 残留 | `frontend/index.html` | React Web |
| Python FastAPI 外露 | `api/server.py` | 内部受控，不做生产外部入口 |
| Redis list | Go/Python queue 实现 | Redis Streams |
| Go 业务抓取主链 | Go Worker Pool 下载主链 | Python 业务抓取，Go 调度协调 |
| Python MySQL 写入 | 历史 storage/mysql_store.py | Go 权威写入协调 |
| 不完整 Compose | `docker-compose.yml` | 完整九服务产品拓扑 |

### 5.4 端到端目标数据流

```text
Web/API -> Go Gateway -> MySQL task -> Outbox -> Redis Streams
-> Python Search Worker -> crawler:url
-> Python/受控 Fetch Worker -> crawler:html
-> Python Parser/Scorer/Dedup -> crawler:result
-> Go Result Consumer -> MySQL -> 文件卷/DuckDB/Export
```

当前实现与目标数据流存在差异：Go Worker 仍承担下载主链，Redis 仍为 list，outbox 未实现。
## 6. Web 信息架构与详细交互

七大模块的完整页面、组件、状态和权限矩阵见 `docs/FRONTEND_ARCHITECTURE.md`。以下为产品层要求。

| 模块 | 用户目标 | 关键页面 | 核心操作 | API | 当前状态 |
|---|---|---|---|---|---|
| 初始化与登录 | 初始化管理员、登录/登出 | bootstrap、login | 初始化、登录、登出 | `/bootstrap`、`/auth/*` | NOT_STARTED |
| Dashboard | 掌握任务、队列、存储和安全状态 | 总览 | 跳转详情、刷新 | `/system/health`、`/tasks` | NOT_STARTED |
| 创建任务 | 创建任务并确认范围 | 任务表单、范围建议 | 创建、建议、确认 | `/tasks`、`scope-suggestion`、`confirm` | NOT_STARTED |
| 任务列表/详情/进度 | 查看生命周期和阶段 | 任务列表、详情 | 取消、重试、SSE | `/tasks/*`、`/events` | NOT_STARTED |
| 结果列表/详情/审核/导出 | 审核结果、导出 | 结果列表、正文详情 | 审核、异步导出 | `/results/*`、`/export-jobs` | NOT_STARTED |
| 站点与插件配置 | 管理站点/插件 | 站点、插件 | 启停、版本、审计 | `/sites/*`、`/plugins/*` | NOT_STARTED |
| 系统/日志/只读安全状态 | 查看系统与安全状态 | 系统页 | 只读检索 | `/system/*` | NOT_STARTED |

### 6.1 交互要求

- 每个视图必须有 empty、loading、error、success 状态。
- 危险操作必须二次确认。
- 列表服务端分页、筛选、排序。
- 时间以 UTC 存储，展示本地化。
- 页面遵循 WCAG 2.2 AA，Chrome/Edge 最近两个稳定版，Firefox 冒烟。
- 目标技术：React + TypeScript strict + Vite + Ant Design + TanStack Query + OpenAPI types + 薄 Axios。

### 6.2 当前状态

当前 `web/` 不存在，Vue 页面 CURRENT_CONFLICT；上述全部页面 NOT_STARTED。

## 7. 任务生命周期与端到端流程

### 7.1 生命周期状态

`DRAFT → PENDING_CONFIRMATION → QUEUED → RUNNING → SUCCEEDED/PARTIAL_SUCCEEDED/FAILED/CANCELLED/TIMED_OUT`

辅助状态：

- RETRY_WAIT：等待受控重试
- RECOVERING：Worker lost 或服务重启后恢复
- CANCELLING：取消请求已接受，正在停止

终态：SUCCEEDED、PARTIAL_SUCCEEDED、FAILED、CANCELLED、TIMED_OUT。

### 7.2 执行阶段

执行阶段独立于生命周期状态：

`DISCOVERY → FETCH → PARSE → SCORE → FILTER → DEDUP → PERSIST → EXPORT`

同一生命周期状态可包含多个执行阶段；阶段写入 TaskStage。

### 7.3 合法转换

- DRAFT → PENDING_CONFIRMATION → QUEUED。
- QUEUED → RUNNING。
- RUNNING → RETRY_WAIT → QUEUED/RECOVERING。
- RUNNING → RECOVERING → RUNNING。
- RUNNING/QUEUED → CANCELLING → CANCELLED。
- RUNNING → SUCCEEDED/PARTIAL_SUCCEEDED/FAILED/TIMED_OUT。

### 7.4 非法转换

- 终态不得转换为非终态。
- DRAFT 不得直接进入 RUNNING。
- CANCELLED 不得被迟到事件覆盖。
- 缺失 attempt/heartbeat 不得标记 SUCCEEDED。

### 7.5 可靠性

- 事件和状态更新幂等，重复消息不重复计数。
- Worker 心跳默认 30 秒，约 2 分钟无心跳判定 lost。
- checkpoint 记录阶段状态，支持受控恢复。
- 取消和超时使用显式状态转换。
- 局部失败进入 PARTIAL_SUCCEEDED 或按策略重试。
- 用户可见状态由 TaskEvent 和任务状态机产生，禁止页面自行推断。

## 8. 站点发现、插件与关键词扩展

### 8.1 发现能力

| 能力 | 当前状态 | 目标 |
|---|---|---|
| TRS 搜索 | CURRENT_IMPLEMENTED | V1 |
| JPAAS 搜索 | CURRENT_IMPLEMENTED | V1 |
| HTML 搜索 | CURRENT_IMPLEMENTED | V1 |
| 公共 JSON API | CURRENT_IMPLEMENTED | V1 |
| 搜索入口探测 | CURRENT_IMPLEMENTED | V1 受控 |
| siteCode | CURRENT_IMPLEMENTED | V1 |
| 多证据置信度 | CURRENT_PARTIAL | V1 |
| 多站点/多主题自动发现 | NOT_STARTED | TARGET_V1_1 |

### 8.2 插件体系

- 插件必须注册、版本化、可禁用、可审计。
- 插件配置不内联出站安全 override。
- 四川 HTML 插件历史问题作为案例记录，不作为目标硬编码。
- V1 插件边界：TRS/JPAAS/HTML/JSON API；V1.1 再扩展自动发现。

### 8.3 关键词与分页

- 关键词缺失时支持受控关键词扩展、降级和自动切换。
- 分页必须有最大页数、重复页和循环检测。
- URL 规范化保守执行。

## 9. 抓取、JS 降级、附件与解析

### 9.1 抓取职责

- Python 是业务抓取权威。
- Go 只负责调度协调，不成为业务抓取实现权威。
- 受控 JavaScript 渲染仅在需要时进入隔离 Playwright Python Worker。
- 默认 HTTP 限制：连接 10 秒、读取 30 秒、最多 5 次重定向、正文 20MB、附件 50MB。
- SSRF 防护覆盖协议、DNS、IP、redirect；遵守 robots、站点条款和访问频率。

### 9.2 附件与解析

- PDF/DOCX 附件仅白名单内解析。
- 校验 MIME/魔数、大小、重定向、恶意内容和存储安全。
- 解析分层：结构化规则、正文算法和站点插件。
- 原始附件保存到只读卷。
- 不绕过登录、验证码、WAF 或访问控制。

## 10. 评分、过滤、去重与版本

### 10.1 评分

- 相关性评分和内容质量评分分离。
- 阈值可配置；上线前至少使用 200 条人工标注样本校准。
- 评分输出可解释证据。

### 10.2 去重与版本

- URL/内容/业务键组合去重。
- 保留正文版本关系。
- 原始证据不可变；规范化结果与人工审核结论分层保存。
- 误判通过审核决定和版本记录修正，不覆盖原始证据。
## 11. 数据模型、存储和消息队列

完整实体、字段、索引和保留期见 `docs/DATA_MODEL.md`。核心实体：

Admin、Session、APIToken、CrawlTask、TaskAttempt、TaskStage、TaskEvent、SearchCandidate、FetchArtifact、Article、ArticleVersion、ReviewDecision、ExportJob、Site、Plugin、OutboxEvent、AuditLog、DeadLetter、Checkpoint。

### 11.1 数据权威

- MySQL 是业务权威。
- Python 通过版本化事件交付结果，不直接写权威业务表。
- Go 消费事件并执行权威写入。
- Transactional Outbox 保证业务事务与消息发布一致。
- Redis Streams 使用 consumer groups、at-least-once、幂等键和 pending reclaim。
- 失败进入 dead-letter，支持受控重放。
- DuckDB 只做分析与导出。
- 原始文件使用内容寻址或不可变路径。

### 11.2 保留期

| 数据 | 保留 |
|---|---|
| 结构化结果 | 180 天 |
| 原始内容/附件 | 30 天 |
| 普通日志 | 90 天 |
| 诊断材料 | 30 天 |
| 安全证据 | 永久 |

## 12. API、OpenAPI 与 SSE

完整端点和对象见 `docs/API_CONTRACT.md`。

### 12.1 API

- 外部 API 统一 `/api/v1`。
- Go OpenAPI 是外部 API 权威来源。
- 覆盖 bootstrap、登录/登出、Session、API Token、任务、任务确认/取消/重试、任务事件 SSE、结果、审核、导出、站点、插件、系统健康、日志和只读安全状态。
- API 必须定义向后兼容和废弃策略。

### 12.2 SSE

- 使用 event_id 和 Last-Event-ID 恢复。
- 15 秒 heartbeat。
- 支持重连、事件保留和断档处理。
- 降级 polling 默认 5 秒。

## 13. 认证、安全与 OSEC 边界

完整控制见 `docs/SECURITY_ARCHITECTURE.md`。

### 13.1 认证

- 单管理员一次性 bootstrap，并提供本地 CLI 恢复。
- Session 空闲 30 分钟、绝对 8 小时。
- Cookie 使用 HttpOnly、Secure 和合适 SameSite。
- API Token 与浏览器会话分离，Token 只存 hash，支持轮换和吊销。
- 同源浏览器写操作启用 CSRF。

### 13.2 边界

- 启用 TLS、CSP 和安全响应头。
- secrets 通过 Docker secrets 或等价机制提供。
- 管理、配置、导出和安全事件进入审计日志。
- 前端安全状态页面只读，不展示敏感值。

### 13.3 OSEC

- OSEC Manifest/S1/Seal Record 已 SEALED。
- production loader 仍为 NOT_STARTED。
- fail-closed 生产接入仍是发布门禁。
- 不把 evidence SEALED 写成 runtime 已完成。

## 14. 错误、重试、可靠性与恢复

### 14.1 错误模型

- 统一错误模型包含 code、message、fields、retryable、request_id。
- 用户错误信息安全，不暴露内部堆栈、凭据或敏感地址。

### 14.2 重试与幂等

- retryable 与 non-retryable 显式区分。
- 瞬时错误最多重试 3 次，指数退避并带 jitter。
- 消费者按幂等键处理重复。
- outbox 失败进入受控重试或 dead-letter。

### 14.3 恢复

- Worker 心跳默认 30 秒，约 2 分钟无心跳判定 lost。
- checkpoint 支持阶段恢复。
- 服务重启、Redis/MySQL 不可用时不得破坏终态。
- 取消、超时和局部失败使用显式状态转换。

## 15. 运维、配置、监控、保留和备份

### 15.1 配置

- 配置优先级：sealed security > server > site > task。
- feature flag 必须可审计。

### 15.2 监控

- liveness/readiness、指标、日志、trace。
- 监控 queue lag、Worker 健康、站点错误率、磁盘/内存/CPU 压力。
- 压力触发背压和拒绝策略。

### 15.3 备份

- 每日加密备份。
- 保留 7 个日备份和 4 个周备份。
- RPO ≤ 24 小时，RTO ≤ 4 小时。
- 清理任务与保留期一致；定期执行恢复演练。
## 16. 部署、性能、浏览器与无障碍

### 16.1 部署

- V1 为单机 Docker Compose。
- 服务：nginx、web、go-api、python-worker、python-playwright-worker、redis、mysql、prometheus、grafana。
- DuckDB 嵌入分析/导出服务；原始证据卷和数据卷分离。
- secrets 使用 Docker secrets 或等价机制。
- 控制网络分区、端口暴露和 TLS；MySQL/Redis/管理监控不暴露公网。
- 详情见 `docs/DEPLOYMENT_ARCHITECTURE.md`。

### 16.2 性能

- 内网首屏 ≤ 2.5 秒。
- 普通 API P95 ≤ 500ms。
- 创建任务 ≤ 1 秒。
- SSE 事件延迟 ≤ 3 秒。
- 列表服务端分页。

### 16.3 浏览器与无障碍

- Chrome/Edge 最近两个稳定版为正式支持。
- Firefox 执行冒烟测试。
- 关键界面以 WCAG 2.2 AA 为目标。

## 17. 测试、CI、验收与发布

完整矩阵见 `docs/TEST_STRATEGY.md`。

### 17.1 测试层级

- Python unit/integration、Go unit/integration。
- fixture 与 contract 测试。
- Frontend：Vitest、React Testing Library、Playwright。
- 真实站点 canary 至少 20 个代表性站点。
- SSRF/安全/性能/备份恢复/migration 回滚测试。

### 17.2 CI 与发布

- CI 执行代码、测试、依赖、安全和构建门禁。
- 生成 SBOM；采用 SemVer 和不可变构建产物。
- 分阶段发布。

### 17.3 质量门槛

- 发现成功率 ≥ 95%
- 提取成功率 ≥ 90%
- 重复率 < 1%
- 不可恢复失败率 < 2%
- P0/P1 安全问题 = 0
- 至少 2 周观察期

## 18. 路线图、工期、风险与合规

### 18.1 当前完成度

- 保守产品化完成度：26.21%
- NOT_VERIFIABLE 理论上限：26.71%
- 当前 P0=0

### 18.2 缺陷与技术债务

| 级别 | 说明 | 发布影响 |
|---|---|---|
| P0 | 当前无可触发数据/证据破坏或严重安全暴露 | 不阻塞当前开发 |

P1：

- P1-01：无 React Web、OpenAPI、认证、SSE 和 `/api/v1` 产品闭环。
- P1-02：Go/Python 职责未收敛，外部入口和业务抓取主链与冻结架构冲突。
- P1-03：Redis Streams、Transactional Outbox、dead-letter 和幂等迁移未完成。
- P1-04：production loader 与 fail-closed runtime 接入未开始，deployment BLOCKED。

P2：

- P2-01：`frontend/index.html` Vue 残留与 FastAPI 调试入口需要收敛。
- P2-02：Redis list 与 Python/Go 双写路径需要迁移。
- P2-03：Compose 仍非完整产品拓扑，缺少备份、保留期和完整可观测性。

P3：

- P3-01：Python/Go 测试、fixture 和文档覆盖可继续扩展。
- P3-02：canary 站点、性能基准、无障碍和监控指标需在实施阶段补充。

### 18.3 工期

- 单主工程师净人日：内部可演示 90-110；试用加 55-70；RC 加 45-60；正式发布加 30-40，另加两周观察期。
- 小团队净日历：内部可演示 8-10 周；试用加 5-6 周；RC 加 4-5 周；正式发布加 3-4 周，另加两周观察期。
- 风险缓冲：20%—25%。

### 18.4 关键路径

产品设计 review → Go API/OpenAPI/认证/SSE → React Web V1 → Python/Redis/MySQL 集成 → canary/安全门 → 部署/发布门禁 → RC → 观察期。

### 18.5 可并行路径

Python 采集缺口、数据/队列、生产安全 loader、测试/fixture、备份和可观测性可与前端/Go 并行。

### 18.6 合规

- 遵守 robots、站点条款、访问频率和合法授权边界。
- 不绕过访问控制。
- 原始证据与审核数据安全保存，控制隐私泄露和导出范围。
## 19. 术语、需求追踪和当前差距附录

### 19.1 术语表

| 术语 | 含义 |
|---|---|
| Go Gateway | 唯一外部业务网关 |
| Python Crawler | 发现/业务抓取/解析/评分/过滤/去重/附件处理核心 |
| Outbox | 与业务事务一致的待发布事件表 |
| Dead Letter | 超过重试上限的事件 |
| Checkpoint | 任务阶段可恢复状态 |
| ArticleKey | URL 身份与内容版本的确定性键 |
| OSEC Evidence | 已封存的安全证据链 |

### 19.2 57 项说明书覆盖映射

| 原说明书要求 1-57 | 本文章节/专题 |
|---|---|
| 1-2 文档控制与版本 | §1 |
| 3-4 产品背景/目标非目标 | §2 |
| 5-6 用户角色/场景/范围 | §3 |
| 7-9 产品范围/功能架构/系统架构/职责 | §4、§5 |
| 10-12 Web 信息架构/七大模块/页面交互 | §6、FRONTEND_ARCHITECTURE |
| 13-15 任务生命周期/采集流程/站点发现 | §7、§8 |
| 16-17 插件/关键词扩展 | §8 |
| 18-20 抓取/JS/附件/解析 | §9 |
| 21-22 评分过滤/去重版本 | §10 |
| 23-27 数据模型/MySQL/Redis/原始存储 | §11、DATA_MODEL |
| 28-30 API/OpenAPI/SSE | §12、API_CONTRACT |
| 31-35 认证/Token/安全/SSRF/审计/配置 | §13、SECURITY_ARCHITECTURE |
| 36-40 错误/重试/outbox/checkpoint/并发 | §14、§15 |
| 41-43 可观测/保留/备份 | §15 |
| 44-46 Compose/环境/性能/兼容无障碍 | §16、DEPLOYMENT_ARCHITECTURE |
| 47-49 测试/CI/验收/质量指标 | §17、TEST_STRATEGY |
| 50-52 风险/合规/版本路线 | §18 |
| 53-57 项目计划/术语/追踪/差距 | §18、§19 |

### 19.3 八模块完成度

| 模块 | PD 数 | 完成度 | 加权 |
|---|---:|---:|---:|
| PRODUCT_UX | 4 | 0.00% | 0.00% |
| PYTHON_CRAWLER | 21 | 69.05% | 13.81% |
| GO_CONTROL_API | 19 | 23.68% | 3.55% |
| DATA_QUEUE | 13 | 23.08% | 3.46% |
| WEB_FRONTEND | 21 | 2.38% | 0.36% |
| SECURITY | 11 | 36.36% | 2.91% |
| TEST_QUALITY | 4 | 12.50% | 0.88% |
| OPS_RELEASE | 10 | 25.00% | 1.25% |

### 19.4 PD 统计

IMPLEMENTED=18、PARTIAL=23、NOT_STARTED=54、CONFLICT=7、OBSOLETE=0、NOT_VERIFIABLE=1；合计 103。

### 19.5 当前实现与目标状态矩阵

| 领域 | 当前状态 | 目标阶段 |
|---|---|---|
| Python 底层采集能力 | CURRENT_IMPLEMENTED/PARTIAL | V1 |
| Go 基础 API/Worker | CURRENT_PARTIAL | Go Gateway |
| Redis 队列 | CURRENT_CONFLICT | V1 Redis Streams |
| Web | CURRENT_CONFLICT/Vue | V1 React |
| MySQL/DuckDB | CURRENT_CONFLICT/PARTIAL | V1 权威边界 |
| OSEC Evidence | SEALED | 永久证据 |
| Production Loader | NOT_STARTED | 发布门禁 |
| Deployment | BLOCKED | V1 |

### 19.6 PD-001—PD-103 追踪矩阵

状态列取值：IMPLEMENTED、PARTIAL、NOT_STARTED、CONFLICT、OBSOLETE、NOT_VERIFIABLE。模块列为 R2 唯一主模块。
| PD | 需求摘要 | 状态 | 模块 | 目标阶段 | 章节 | 证据/缺口 |
|---|---|---|---|---|---|---|
| 001 | Web管理面板为主入口 | NOT_STARTED | PRODUCT_UX | V1 | §6 | 无 web/，Vue 为 CURRENT_CONFLICT |
| 002 | CLI/API为工程接口 | PARTIAL | GO_CONTROL_API | V1 | §12 | Go API/FastAPI 调试存在，无统一 /api/v1 |
| 003 | V1单管理员 | NOT_STARTED | GO_CONTROL_API | V1 | §13 | 无认证/Session 实现 |
| 004 | 无多租户/复杂RBAC | IMPLEMENTED | GO_CONTROL_API | V1 | §3 | 当前无多租户与 RBAC 模型 |
| 005 | 内部单机部署 | NOT_STARTED | OPS_RELEASE | V1 | §16 | 无完整产品部署 |
| 006 | 单主机Docker Compose | PARTIAL | OPS_RELEASE | V1 | §16 | docker-compose.yml 不完整 |
| 007 | 核心服务拓扑 | PARTIAL | OPS_RELEASE | V1 | §16 | 存在基础 Compose，目标九服务缺失 |
| 008 | 仅立即任务 | NOT_STARTED | PRODUCT_UX | V1 | §4 | 任务产品流程未实现 |
| 009 | 任务范围建议 | NOT_STARTED | PRODUCT_UX | V1 | §6 | 无 Web 范围建议流程 |
| 010 | 中文+i18n | NOT_STARTED | PRODUCT_UX | V1 | §6 | 无前端 i18n 工程 |
| 011 | React前端 | CONFLICT | WEB_FRONTEND | V1 | §6 | frontend/index.html 为 Vue 3 |
| 012 | TypeScript strict | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 013 | Vite | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 014 | Ant Design | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 015 | TanStack Query/本地状态 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 016 | OpenAPI生成types+Axios | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无 OpenAPI/前端 client |
| 017 | 桌面端优先 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 018 | 初始化/登录独立模块 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 019 | Dashboard | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 020 | 创建任务模块 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 021 | 任务列表/详情/进度 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 022 | 结果列表/详情/审核/导出 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 023 | 站点/插件配置模块 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 024 | 系统/日志/安全状态模块 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 025 | 浅色蓝灰视觉 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 026 | 完整内容审核 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无审核页面 |
| 027 | 原始内容不可覆盖 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无审核页面/数据层约束待固化 |
| 028 | CSV/XLSX/JSON异步导出 | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无导出任务产品闭环 |
| 029 | WCAG 2.2 AA | NOT_STARTED | WEB_FRONTEND | V1 | §6 | 无前端工程 |
| 030 | Chrome/Edge+FF冒烟 | NOT_STARTED | WEB_FRONTEND | V1 | §16 | 无前端工程 |
| 031 | Go唯一外部网关 | CONFLICT | GO_CONTROL_API | V1 | §5 | FastAPI/Go 双入口存在 |
| 032 | Go认证/API/状态/SSE/调度 | PARTIAL | GO_CONTROL_API | V1 | §5 | Go 基础调度/API 存在，认证/SSE 缺 |
| 033 | Python采集核心 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §5 | crawler/search、parser、extractor、detail |
| 034 | Redis Streams | CONFLICT | DATA_QUEUE | V1 | §11 | 当前 queue 使用 list |
| 035 | 内部仅健康检查 | IMPLEMENTED | GO_CONTROL_API | V1 | §5 | monitor/health.py 等存在 |
| 036 | Transactional Outbox | NOT_STARTED | DATA_QUEUE | V1 | §11 | 无 outbox 实现 |
| 037 | at-least-once/幂等 | PARTIAL | DATA_QUEUE | V1 | §11 | v2 消息有幂等合同，队列/消费未完整 |
| 038 | Worker心跳30秒/2分钟lost | NOT_STARTED | GO_CONTROL_API | V1 | §7 | 无完整 heartbeat/lost 状态机 |
| 039 | checkpoint/受控恢复 | NOT_STARTED | GO_CONTROL_API | V1 | §7 | 无完整 checkpoint 恢复 |
| 040 | 完整任务状态机 | NOT_STARTED | GO_CONTROL_API | V1 | §7 | 无完整状态机 |
| 041 | MySQL权威 | CONFLICT | DATA_QUEUE | V1 | §11 | Python/Go 历史写入路径并存 |
| 042 | DuckDB分析 | PARTIAL | DATA_QUEUE | V1 | §11 | storage/duckdb_store.py 存在，边界未固化 |
| 043 | 原始页/附件持久卷 | NOT_STARTED | DATA_QUEUE | V1 | §11 | 无不可变文件卷设计实现 |
| 044 | 存储职责分离 | CONFLICT | DATA_QUEUE | V1 | §11 | 历史存储边界与冻结职责冲突 |
| 045 | Nginx同源/TLS | NOT_STARTED | OPS_RELEASE | V1 | §16 | 无产品 nginx 拓扑 |
| 046 | 会话30分/8小时 | NOT_STARTED | GO_CONTROL_API | V1 | §13 | 无 Session 实现 |
| 047 | Cookie HttpOnly/Secure/SameSite | NOT_STARTED | SECURITY | V1 | §13 | 无认证 Cookie 实现 |
| 048 | Bootstrap/CLI恢复 | NOT_STARTED | GO_CONTROL_API | V1 | §13 | 无 bootstrap 流程 |
| 049 | API Token hash/轮换/吊销 | NOT_STARTED | GO_CONTROL_API | V1 | §13 | 无 API Token 实现 |
| 050 | CSRF | NOT_STARTED | SECURITY | V1 | §13 | 无 CSRF 实现 |
| 051 | 外部API /api/v1 | CONFLICT | GO_CONTROL_API | V1 | §12 | Go/FastAPI 路径无 /api/v1 契约 |
| 052 | Go OpenAPI权威 | NOT_STARTED | GO_CONTROL_API | V1 | §12 | 无 OpenAPI |
| 053 | SSE event_id/恢复/15秒/5秒polling | NOT_STARTED | GO_CONTROL_API | V1 | §12 | 无 SSE |
| 054 | API兼容/废弃策略 | NOT_STARTED | GO_CONTROL_API | V1 | §12 | 无版本化 API 文档基线 |
| 055 | 版本化JSON envelope | IMPLEMENTED | GO_CONTROL_API | V1 | §11 | protocol/messages、fixtures contract |
| 056 | 前端错误信息安全 | PARTIAL | WEB_FRONTEND | V1 | §13 | 后端有错误脱敏基础，前端无实现 |
| 057 | 静态HTML站点 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §8 | crawler/search/html_adapter.py、plugins/html.py |
| 058 | TRS搜索 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §8 | trs_adapter.py、trs_response_parser.py |
| 059 | JPAAS搜索 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §8 | jpaas_adapter.py、jpaas_parser.py |
| 060 | 公开JSON API | IMPLEMENTED | PYTHON_CRAWLER | V1 | §8 | generic_json_adapter.py |
| 061 | JS渲染受控降级 | NOT_STARTED | PYTHON_CRAWLER | V1 | §9 | 无 Playwright 生产路径 |
| 062 | Playwright隔离Worker | NOT_STARTED | PYTHON_CRAWLER | V1 | §9 | 无隔离 JS Worker |
| 063 | 不绕过登录/验证码/WAF | IMPLEMENTED | SECURITY | V1 | §9 | site/security.py、登录 fixture 拒绝路径 |
| 064 | 白名单PDF/DOCX附件 | PARTIAL | PYTHON_CRAWLER | V1 | §9 | parser 安全门存在，白名单附件链路不完整 |
| 065 | 附件安全检查 | PARTIAL | SECURITY | V1 | §9 | 文档安全门存在，存储/重定向完整检查缺 |
| 066 | 多站点自动发现V1.1 | NOT_STARTED | PYTHON_CRAWLER | V1.1 | §8 | 无 V1.1 实现 |
| 067 | 关键词扩展/降级 | PARTIAL | PYTHON_CRAWLER | V1 | §8 | core/query_expander.py 存在，自动切换不完整 |
| 068 | 多证据置信度 | PARTIAL | PYTHON_CRAWLER | V1 | §8 | 发现证据基础存在，置信度产品化不完整 |
| 069 | 分层正文提取 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §9 | multi_strategy、extractor、detail 分层存在 |
| 070 | 保守URL规范化 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §9 | crawler/site/normalizer.py、security url_normalizer |
| 071 | 分页限制/重复/循环 | PARTIAL | PYTHON_CRAWLER | V1 | §8 | SearchPlan 有 max_pages，循环产品门缺 |
| 072 | 熔断/冷却/恢复 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §9 | httpx circuit breaker、jitter 等存在 |
| 073 | 条件请求/内容hash | PARTIAL | PYTHON_CRAWLER | V1 | §9 | content_hash 协议存在，条件请求未完整接入 |
| 074 | SSRF防护 | IMPLEMENTED | SECURITY | V1 | §9 | crawler/security、go internal/security |
| 075 | 默认HTTP限制 | IMPLEMENTED | SECURITY | V1 | §9 | transport_budget、bounded_io、contract tests |
| 076 | robots/条款/授权 | NOT_STARTED | SECURITY | V1 | §9 | 无产品化 robots/条款策略 |
| 077 | 插件注册/版本/禁用/审计 | PARTIAL | PYTHON_CRAWLER | V1 | §8 | adapter registry 存在，管理/审计不完整 |
| 078 | sealed security配置优先级 | PARTIAL | SECURITY | V1 | §15 | ADR-022/schema 冻结，runtime loader 未开始 |
| 079 | 可审计feature flag | NOT_STARTED | GO_CONTROL_API | V1 | §15 | 无 feature flag 服务 |
| 080 | 队列/资源背压 | PARTIAL | DATA_QUEUE | V1 | §15 | concurrency/bounded runtime 存在，任务级背压缺 |
| 081 | HTTP并发16/2/4 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §9 | concurrency_limiter/config 合同存在 |
| 082 | 任务默认限制 | PARTIAL | GO_CONTROL_API | V1 | §7 | 部分 config 限制，产品任务限制缺 |
| 083 | 重试3次/指数/jitter | IMPLEMENTED | PYTHON_CRAWLER | V1 | §14 | retry/jitter 合同存在 |
| 084 | UTC存储/本地展示 | PARTIAL | DATA_QUEUE | V1 | §12 | 协议 UTC 存在，展示层未实现 |
| 085 | 相关性与质量评分分离 | IMPLEMENTED | PYTHON_CRAWLER | V1 | §10 | relevance_v2/scorer 分离存在 |
| 086 | 200条人工标注校准 | NOT_STARTED | TEST_QUALITY | V1 | §10 | 无标注集/校准门禁 |
| 087 | URL/内容/业务键去重+版本 | PARTIAL | PYTHON_CRAWLER | V1 | §10 | dedup 基础存在，业务键/版本未完整 |
| 088 | 原始证据/审核分层 | PARTIAL | DATA_QUEUE | V1 | §10 | v2 分层模型存在，文件卷/审核层不完整 |
| 089 | dead-letter/受控重放 | NOT_STARTED | DATA_QUEUE | V1 | §11 | 无 DLQ 实现 |
| 090 | 数据保留期 | NOT_STARTED | DATA_QUEUE | V1 | §11 | 无清理任务/保留执行 |
| 091 | 管理/安全审计日志 | NOT_STARTED | SECURITY | V1 | §13 | 无 AuditLog 产品实现 |
| 092 | 内置监控 | PARTIAL | OPS_RELEASE | V1 | §15 | monitor/config 基础存在，完整指标缺 |
| 093 | Vitest/RTL/Playwright | NOT_STARTED | TEST_QUALITY | V1 | §17 | 无前端工程/测试 |
| 094 | fixture+20站canary | PARTIAL | TEST_QUALITY | V1 | §17 | fixture/E2E 基础存在，20 站 canary 缺 |
| 095 | secrets/Docker secrets | CONFLICT | SECURITY | V1 | §16 | docker-compose 存在明文配置风险 |
| 096 | 版本化可回滚migration | PARTIAL | DATA_QUEUE | V1 | §17 | migrations/0001 存在，回滚/CI 缺 |
| 097 | liveness/readiness | IMPLEMENTED | OPS_RELEASE | V1 | §15 | monitor/health.py 等存在，产品 readiness 待接 |
| 098 | 每日加密备份/RPO/RTO | NOT_STARTED | OPS_RELEASE | V1 | §15 | 无备份实施 |
| 099 | 性能SLA | NOT_VERIFIABLE | OPS_RELEASE | V1 | §16 | 需部署/基准环境，无完整证明 |
| 100 | CSP/安全头/SBOM | NOT_STARTED | SECURITY | V1 | §13 | 无前端/发布物安全头与 SBOM |
| 101 | 分阶段质量门槛 | NOT_STARTED | TEST_QUALITY | V1 | §17 | 无发布阶段质量门 |
| 102 | SemVer/不可变产物/CI | NOT_STARTED | OPS_RELEASE | V1 | §17 | 无 CI/发布流水线 |
| 103 | 文档齐全/两周观察 | NOT_STARTED | OPS_RELEASE | V1 | §17 | 设计文档建立中，发布文档/观察未开始 |

### 19.7 当前差距与任务建议

- PRODUCT_UX/WEB_FRONTEND：产品设计 review 后建立 OpenAPI、React Web 与交互验收。
- GO_CONTROL_API：补全 Go 网关、认证、Session、Token、状态机、SSE 和 `/api/v1`。
- DATA_QUEUE：迁移 Redis Streams、outbox、dead-letter、保留期和权威写入边界。
- PYTHON_CRAWLER：收敛业务抓取权威，补齐 JS/Playwright、附件和 canary 能力。
- SECURITY：接入 production loader、CSRF/CSP/secrets/audit 与 fail-closed。
- TEST_QUALITY/OPS_RELEASE：建立 frontend/contract/canary/performance、CI、备份和发布门禁。

### 19.8 文档到实现追踪

| 后续能力 | 入口文档 | 当前状态 |
|---|---|---|
| Web | FRONTEND_ARCHITECTURE | NOT_STARTED |
| API/SSE | API_CONTRACT | NOT_STARTED |
| 数据/队列 | DATA_MODEL | CONFLICT/PARTIAL |
| 安全 | SECURITY_ARCHITECTURE | Evidence SEALED，loader NOT_STARTED |
| 测试 | TEST_STRATEGY | PARTIAL |
| 部署 | DEPLOYMENT_ARCHITECTURE | BLOCKED |
