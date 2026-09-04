# V1.0/V1.1 联合基线术语表

本文是 DEV-001 的联合解释治理资产，记录 V1.0 主基线与 V1.1 强制附属补丁实际使用的核心术语。本文不取代两份 DOCX，也不能脱离 V1.0/V1.1 单独解释。

## 1. 术语字段

| 字段 | 要求 |
|---|---|
| 规范中文名 | 联合基线使用的正式中文名称 |
| Canonical Name | 正式英文名或 symbol |
| 定义 | 保持基线原始语义 |
| 责任边界 | 组件或角色拥有该概念 |
| 来源 | V1.0/V1.1 精确章节 |
| 旧称或禁用解释 | 防止历史实现重新成为权威 |
| 备注 | 必要的冲突消歧 |

## 2. 术语表

| 规范中文名 | Canonical Name | 定义 | 责任边界 | 来源 | 旧称或禁用解释 | 备注 |
|---|---|---|---|---|---|---|
| V1.0 完整主基线 | V1.0 Main Baseline | 完整产品基线母版，固化后字节不变 | 产品治理与所有下游开发 | V1.0 §1；V1.1 §1.1 | 旧 Markdown PRODUCT_DESIGN_V1.0 不是本概念 | 唯一完整主基线 |
| V1.1 强制附属补丁 | V1.1 Mandatory Patch | 对 V1.0 明确条款的补充或修正，不能脱离 V1.0 使用 | 产品治理与所有下游开发 | V1.1 §1.1、§1.2、§1.5 | 不得视作独立主基线 | 与 V1.0 联合阅读 |
| 联合基线 | Joint Baseline | V1.0 主基线 + V1.1 附属补丁共同构成的有效基线 | 所有 BUILD、Review、测试与发布 | V1.1 §1.2、§15 | 仅读一份文件不能形成完整基线 | 缺一不可 |
| 任务 | CrawlTask | 采集任务生命周期、调度、快照和状态对象 | Go Gateway 与任务状态机 | V1.0 §9、§12.2；V1.1 §1.4 | 旧内存 Task 模型不是正式任务权威 | V1.0 核心实体之一 |
| 站点 | Site | 站点身份、范围、授权依据和策略引用 | Go 管理面 + Python 采集侧使用 | V1.0 §8.1；V1.1 §10 | 旧 site.json 硬编码不是正式 Site 生命周期 | V1.0 单任务绑定单 Site |
| 搜索计划 | SearchPlan | 结构化搜索执行计划，含 request_shape、pagination、selectors | Python Search/Plan 执行面 | V1.0 §8.4；V1.1 §6 | 不允许启发式或旧插件回退 | 有 canonical plan_id |
| 搜索候选 | SearchCandidate | 从受控证据中得到的候选 URL 与来源证据 | Python Analyzer/Probe | V1.0 §8.2、§12.2；V1.1 §7 | 历史全页链接猜测不是候选证据 | 必须可追溯 |
| URL 协调器 | URL Coordinator | `crawler:url` 唯一 Go 消费者与抓取调度协调者 | Go 调度协调 | V1.0 §6.2、§13.1；V1.1 §2.1 | 当前 Go Worker Pool 业务下载主链是待收敛实现 | 目标职责由 V1.1 §5 迁移 |
| 文章身份 | Article | 稳定文章身份，不以 content_hash 区分身份 | MySQL 权威数据 | V1.0 §12.2、§12.3；V1.1 §1.4 | 旧 articles 表含正文混合形态不是最终身份模型 | ArticleVersion 承载正文版本 |
| 正文版本 | ArticleVersion | Article 的不可变正文版本与提取元数据 | MySQL 权威数据 | V1.0 §12.2；V1.1 §4、§6 | 20 类历史快照不包含完整 ArticleVersion 目标 | version_no 单调 |
| 任务文章关联 | TaskArticle | 任务、候选、文章与版本之间的命中结果关联 | MySQL 权威数据 | V1.0 §12.2；V1.1 §4 | 旧 schema 仅含 articles/task_articles 基础 | (task_id, hit_id) 幂等 |
| 抓取产物 | FetchArtifact | 抓取内容/附件的不可变存储元数据 | Python Fetch/Go 调度 | V1.0 §12.2、§12.6；V1.1 §5 | 未写入不可变卷的对象不能称为 FetchArtifact | 使用内容寻址 |
| 审核决定 | ReviewDecision | append-only 的审核决定与证据引用 | Go 审核 API + MySQL | V1.0 §12.2、§17.2；V1.1 §4 | 旧 JSON-only 弱引用不是有效审核模型 | 必须自包含快照或强引用 READY hold |
| 审核保留 | review_hold | 审核证据的长期保留状态与清理例外 | 审核服务、清理服务 | V1.0 §17.2；V1.1 §4 | 30 天原始证据清理不得删除 hold | 跨介质提交状态机 |
| 全局合规熔断 | GlobalBlockEntry | 全局域名/端点合规阻止状态，所有出站检查点生效 | Go/Python 安全执行面 | V1.1 §10 | 历史 URL 黑名单没有统一状态机 | 当前为 22 类实体新增项 |
| Go 外部业务网关 | Go External Business Gateway | 唯一外部业务 API、认证、状态、SSE、调度协调入口 | Go Gateway | V1.0 §6.1；V1.1 §2.1 | Python FastAPI 不是生产外部网关 | /api/v1 由 Go OpenAPI 权威 |
| Python 执行面 | Python Execution Surface | 发现、业务抓取、解析、评分、过滤、去重、附件处理 | Python Worker | V1.0 §6.2；V1.1 §2.1 | Go 下载主链不能替代 Python 业务权威 | 不直接写 MySQL 权威业务表 |
| Playwright Worker | Playwright Worker | 受控 JavaScript 渲染降级执行单元 | Python 隔离 Worker | V1.0 §10.5；V1.1 §8 | 不是默认抓取路径 | 单并发、独立内存 |
| Redis Streams | Redis Streams | 正式任务与事件传递载体 | Go/Python 消息链 | V1.0 §13.1；V1.1 §9 | Redis list 是 CURRENT_CONFLICT | Consumer Group 配合使用 |
| 消费组 | Consumer Group | Streams 中的消费者分组与 ACK 语义 | Redis 消息架构 | V1.0 §13.3；V1.1 §9 | list BRPOP 不构成 consumer group | pending reclaim 受控 |
| 事务性发件箱 | Transactional Outbox | 与 MySQL 业务事务一致的待发布事件机制 | Go 控制面 | V1.0 §13.4；V1.1 §5 | 无 outbox 的双写不是正式机制 | dispatcher 受控 |
| HTTP 幂等 | HTTP Idempotency | 对 mutation HTTP 请求的权威幂等语义 | Go API/MySQL IdempotencyRecord | V1.0 §14.4；V1.1 §1.4 | 不由 Redis 消息幂等键替代 | 创建任务/审核/导出等适用 |
| 消息幂等 | Message Idempotency | 消费者对重复消息的去重语义 | 消费端协议实现 | V1.0 §13.3；V1.1 §1.4 | 不替代 HTTP Idempotency | idempotency_key 只解决消费去重 |
| 逻辑 slot | Logical Slot | Python Worker 加权并发容量，8 slot 不等于 8 进程 | Python Worker 模型 | V1.1 §3 | “8 slot=8 进程”是错误解读 | 受 8C16G 约束 |
| 排空保护 | DRAIN_ONLY | Stream/磁盘容量压力下的只排空不新增消息状态 | Redis/磁盘状态机 | V1.1 §9 | 容量耗尽时仍接受新消息是错误 | 需进入/退出阈值 |
| DuckDB 临时目录 | duckdb_temp | DuckDB 临时文件独立目录和配额 | DuckDB 导出/分析 | V1.0 §12.7；V1.1 §11 | 回落到 /tmp 或项目目录是错误的 | 全局硬上限 20 GiB |
| 导出文件目录 | export_files | 最终导出文件卷 | 导出服务 | V1.0 §17.4；V1.1 §11 | DuckDB 临时文件不能落到 export_files | 原子发布与过期 |
| 就绪状态 | readiness | 服务依赖与迁移、Outbox、Worker、loader 全部就绪的状态 | Go API/Compose | V1.0 §18.7；V1.1 §2.2 | 仅 HTTP 200 不构成 readiness | 未满足依赖不得 ready |
| 发布阻塞 | RELEASE_BLOCKED | 当前产品禁止正式发布的权威状态 | 产品治理 | V1.0 §20.9；V1.1 §18 | 文档固化不解除发布阻塞 | 当前固定状态 |

## 3. 歧义消除

- Go 与 Python 双业务权威：Go 只承担外部网关与权威写入协调；Python 是采集执行面。
- HTTP 幂等与消息幂等：HTTP 幂等由 MySQL IdempotencyRecord 提供；消息幂等只用于消费去重。
- Redis Streams 与 Redis list：Streams 是正式链；list 只属于迁移债务。
- Python Worker 与 Playwright Worker：Playwright Worker 是独立受控 JS 降级单元，不混入普通 Python Worker。
- 实体口径：旧 Markdown 20 类为历史快照；V1.0 DOCX 为 21 类；V1.1 新增 GlobalBlockEntry，当前目标为 22 类。
- React 与 Vue：React + TypeScript strict + Vite 是正式前端目标；Vue 是历史残留，不作为目标方案。

本文不定义完整状态码、错误码或事件字典；此类内容属于后续工作包。
