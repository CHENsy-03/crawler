# 通用爬虫系统架构

## 1. 架构目标

本平台目标为通用、稳定、可维护、可扩展的信息采集平台，支持具备搜索入口或可配置发现规则的网站，实现信息的自动发现、搜索、下载、解析、评分和存储。

架构设计遵循以下原则：
- Python 负责采集执行面（搜索适配、HTML 解析、评分去重）
- Go 负责平台控制面（API 入口、任务调度、MySQL 持久化）
- Redis 作为跨运行时通信的唯一中间层

## 2. 总体运行流程

采集任务的完整生命周期：

```
用户/API 提交任务 (Go)
  -> Go 创建任务并生成 task_id
  -> crawler:search (Go 生产)
  -> Python 搜索适配器发现 URL
  -> crawler:url (Python 生产)
  -> Go Worker Pool 并发下载
  -> crawler:html (Go 生产)
  -> Python Worker 解析、评分、过滤、去重
  -> crawler:result (Python 生产)
  -> Go 消费结果并写入 MySQL
  -> Go 更新任务状态
```

以上为目标运行流程。TASK-017 已实现 v2 `crawler:search` → Python Search Worker → 正式 `URLMessage` → `crawler:url` → Go Worker Pool 主链；v1 legacy 消息路径仍保留且未修改。

Python CLI 和 FastAPI 当前作为兼容、调试入口保留，不属于目标正式入口。

## 3. Go/Python 职责边界

### Go 负责
1. 正式 CLI 和 API 入口。
2. 任务创建、状态管理和编排。
3. Redis 队列管理。
4. 高并发 HTTP 下载 (Worker Pool + Resty)。
5. 重试、限流、超时和下载错误管理。
6. MySQL 最终结果写入 (GORM)。
7. 运行状态和监控指标汇总。

### Python 负责
1. 搜索源适配和 URL 发现 (TRS、JPAAS、HTML 插件)。
2. HTML 正文解析和 Readability 抽取。
3. PDF 解析、Office 文档解析。
4. 关键词扩展、评分和过滤。
5. URL 与内容去重。
6. DuckDB 本地分析和缓存。
7. Redis Worker 内容处理任务。

### 禁止事项
- Go 不得重复实现 HTML 解析器、评分器、去重器。
- Python 不得管理平台级任务状态或直接写入 MySQL 事务数据。
- 双方不得直接互相导入对方源码。

## 4. 运行时入口

| 运行时 | 入口文件 | 启动方式 | 用途 |
|--------|---------|---------|------|
| Go CLI | go-spider/main.go | go run . --site X --keywords Y | 采集任务 |
| Go API | go-spider/main.go --api | go run . --api 8080 | API 服务 |
| Python CLI | main.py | python main.py --site X --keywords Y | 采集任务 |
| Python API | api/server.py | uvicorn api.server:app --port 8000 | HTTP 调试/解析，不消费 Redis 队列 |
| Python Worker | workers/parser_worker.py | python workers/parser_worker.py | Redis 消费（正式链，crawler:html 单消费者） |
| Python Worker（历史） | parser/redis_worker.py | 已删除 | 历史入口，已于 TASK-019B-4C 退役 |

## 5. Redis 消息协议

### 5.1 当前消息协议

| 队列 | 生产者 | 消费者 | JSON 字段 |
|------|--------|--------|---------|
| crawler:url | Python v2 URLMessage / Go legacy PushURLTask | Go Worker Pool | v2: task_id,url,site,keyword,level,title |
| crawler:html | Go PushHTML | Python BRPop | url, title, html, time |
| crawler:error | Go PushError | - | url, error, time |
| crawler:result | Python LPush | Go PopResult | url, title, score, content |

消息约束：JSON 序列化，字段对应 Go HTMLPayload 与 Python dict，新增字段需两端回归测试。

### 5.2 目标消息协议

| 队列 | 生产者 | 消费者 | 用途 |
|------|--------|--------|------|
| crawler:search | Go | Python | 搜索及 URL 发现 |
| crawler:url | Python | Go | 待下载 URL |
| crawler:html | Go | Python | 待解析内容 |
| crawler:result | Python | Go | 结构化采集结果 |
| crawler:error | Go、Python | Go 监控组件 | 跨阶段错误事件 |

目标消息公共字段：`protocol_version`、`task_id`、`message_id`、`timestamp`。业务字段由具体消息类型定义。目标协议尚未实施，将由 TASK-004 建立消息模型和双端契约测试。

## 6. 数据存储边界

| 存储 | 写入权 | 用途 |
|------|--------|------|
| MySQL | Go (GORM) | 事务数据 (任务、文章结果) |
| DuckDB | Python (StorageManager) | 本地分析、缓存、日报 |
| Redis | Go + Python | 任务队列、消息协调 |

Python MySQL 写入模块 (storage/mysql_store.py) 暂时保留，后续迁移完成后再下线。

## 7. 项目目录结构

```
workspace/crawler/
- main.py                     Python CLI 入口
- AGENTS.md                   项目开发规则
- docker-compose.yml          监控栈
- api/server.py               FastAPI 服务（仅 HTTP API，不消费 crawler:html）
- config/                     配置 (site/http/score/parser/system/keywords)
- core/                       关键词扩展
- crawler/pipeline.py         采集管线
- crawler/core/downloader.py  统一 HTTP 客户端
- crawler/extractor/          多策略正文提取
- crawler/parser/             文件格式解析 (pdf/office/format)
- crawler/search/             搜索优化 (detector/planner/result)
- dedup/                      去重 (url_hash/bloom)
- docs/                       文档 (TASK.md, SYSTEM_ARCHITECTURE.md)
- extractor/scorer.py         关键词评分
- frontend/                   Vue3 仪表盘
- httpx/                      HTTP 底层 (session/rate_limiter/circuit_breaker)
- monitor/                    监控 (metrics/health/logger/report/trend)
- parser/                     HTML 解析 (html_parser/api_parser/ai_parser)
- plugins/                    搜索插件 (trs/jpaas/html)
- scheduler/                  调度兼容层
- search/                     搜索优化工具
- storage/                    持久化 (manager/mysql_store/exporter)
- tests/                      Python 测试
- utils/                      工具 (RequestContext)
- go-spider/main.go           Go 入口
- go-spider/internal/api/     Gin API
- go-spider/internal/client/  Resty 搜索
- go-spider/internal/config/  配置加载
- go-spider/internal/httpx/   HTTP 基础设施
- go-spider/internal/queue/   Redis 队列
- go-spider/internal/store/   MySQL GORM
- go-spider/internal/worker/  Worker Pool
- output/                     DuckDB + 导出文件
```

## 8. 配置边界

| 文件 | 用途 | 加载方 |
|------|------|--------|
| config/site.json | 站点定义 | Python main.py |
| config/http.json | 速率限制 | Python httpx |
| config/score.json | 评分权重 | Python extractor |
| config/parser.json | 解析参数 | Python parser |
| config/system.json | 系统参数 | Python main.py |
| config/keywords.json | 关键词扩展 | Python search |

Go 与 Python 可以读取同一项目配置目录，但只读取各自职责范围内的配置。共享字段必须具有明确的数据结构和版本约束，不允许双方依赖彼此的配置加载代码。

Go 端负责 API、任务调度、Redis、下载和 MySQL 配置；Python 端负责搜索插件、解析、评分、去重和 DuckDB 配置。

现有配置文件的最终归属将在后续配置契约任务中确定。

## 9. 错误处理与监控

### 9.1 当前实现

- Go 下载失败通过 crawler:error 写入错误消息。
- Go、Python 各自保留现有重试、限流和熔断能力。
- Grafana 配置位于 config/grafana-dashboard.json。

### 9.2 目标要求

- 错误事件统一包含 protocol_version、task_id、stage、url、error_code、retryable 和 timestamp。
- Go 汇总任务状态、错误和平台级监控指标。
- Python 上报搜索、解析、评分和去重阶段指标。
- /metrics 端点及 Grafana 指标必须通过实际运行测试后才能标记为已完成。

## 10. 当前架构与目标架构差异

| 模块 | 当前 | 目标 |
|------|------|------|
| API 服务 | Go Gin + Python FastAPI 重复 | 统一为 Go Gin |
| CLI 入口 | Go + Python 两套 | 统一为 Go |
| MySQL 写入 | Go GORM + Python pymysql | 归 Go 唯一 |
| 搜索执行 | Go + Python 重复 | 归 Python 唯一 |
| HTTP 客户端 | Go Resty + Python httpx | 各归各自运行时 |

## 11. 迁移顺序

1. 修复基础契约（TASK-002，已完成）
2. 确定运行时职责边界（TASK-003，已完成）
3. 定义版本化 Redis 消息协议（TASK-004）
4. 建立 Go、Python 双端消息模型和契约测试
5. 新增 crawler:search，调整 crawler:url 的生产消费关系
6. 串联 Go -> Python -> Go 端到端流水线
7. 统一正式 API、CLI 和 MySQL 写入入口
8. 收敛重复搜索、HTTP、API 和存储模块
9. 完善监控、前端展示和端到端验收

## 12. 架构约束

- Python 与 Go 不互相直接调用。
- Redis 是唯一的跨运行时通信通道。
- 搜索能力迭代只在 Python 侧进行。
- HTML 解析、评分、去重只在 Python 侧实现。
- 任务状态、MySQL 事务数据只在 Go 侧管理。
- 目标架构不允许同一业务职责长期存在两份正式实现；迁移期间的兼容模块必须标明状态和计划下线任务。
- 新加模块需先更新本文档，再开始实施。
- go mod tidy 和 task-001-go-deps.patch 在明确归属后处理。

---

## 13. TASK-015 v2 URL + 关键词契约

### 13.1 输入入口

- Go CLI v1：`--site <site_key> --keywords <keyword>`，显式推送 v1 SearchMessage。
- Go CLI v2：`--url <target_url> --keywords <kw1,kw2>`，显式推送 v2 SearchRequested。
- `--url` 与 `--site` 互斥。
- Go API 使用 `protocol_version` 显式分派；缺失版本按旧 v1 兼容入口处理。
- v2 请求携带 `site`、`profile`、`keyword` 等 v1 专属字段返回冲突错误。

### 13.2 运行时模型

- Redis v2 envelope 新增 `SearchRequested`，字段语义在 Go/Python 完全一致。
- 新增可序列化 `SearchPlan` 和 `SearchHit` 模型。
- `plan_id` 由稳定 canonical JSON 的 SHA-256 确定性生成，运行时状态与时间字段不参与计算。
- Go 与 Python 共用 `workspace/crawler/tests/fixtures/redis_protocol_v2.json` 作为 canonical fixture。

### 13.3 范围边界

- TASK-015 只建立输入契约、协议模型和 SearchPlan/SearchHit。
- 不实现 Site Analyzer、表单发现、选择器推断、SearchPlan 缓存或正式 Worker v2 执行。
- TASK-016（网站分析与搜索入口发现）未实施。
- TASK-017A 至 TASK-017D 已实施；TASK-017E 执行契约已冻结；受控探测契约已冻结；功能实现仍被上游 selectors 阻断；TASK-017F 未实施。

### 13.4 TASK-015 契约规则摘要

- 空集合统一为 `{}`/`[]`，协议 JSON 不输出 `null`。
- `level` 默认 0、`max_pages` 默认 1；缺失使用默认值，显式 `null` 拒绝。
- `target_url` 拒绝前后空白、非法端口、缺失 host 和非 http/https scheme。
- v1/v2 使用显式协议版本分派，未知字段和跨版本字段返回明确错误。
- 无版本请求只有合法旧 v1 `site` + 字符串 `keywords` 才固定映射 v1；带 `target_url` 或数组 `keywords` 必须显式声明 v2。
- `plan_id` 使用 SHA-256 canonical JSON；U+2028/U+2029 转义为 `\u2028`/`\u2029`，`<>&` 不转义。
- TASK-016 已实施；TASK-017A 至 TASK-017E 已实施；TASK-017F 已完成 Python/Go 全量离线回归与共享 URLMessage 契约验证。

### 13.5 CLI 与 API 输入保护

- CLI 的 `prepareCLIInput` 在任何 Redis 客户端创建、Ping、Worker 启动和消息推送之前完成全部输入校验。
- API v1 同时出现 `site` 与 `profile` 时返回 400，基于原始 JSON key 判断，null/空值/错误类型不能绕过。
- `keywords` 必须是 JSON 数组；v1 `site/keyword` 必须是非空字符串。
- SearchPlan/SearchHit 整数字段显式 `null` 拒绝；畸形 IPv6 统一返回 `INVALID_TARGET_URL`。

## 14. TASK-016 网站分析器与 SearchCandidate

- 新增 Python `crawler/site` 包：URL 规范化、请求前安全策略、表单/签名解析、Analyzer 编排和内部模型。
- `SearchCandidate` 与 `SiteAnalysisResult` 是 Python 内部模型，不进入 Go/Python 跨语言协议。
- Analyzer 只生成未经验证的 Candidate；不探测候选、不生成 SearchPlan、不提交 POST。
- 发现阶段真实请求通过 `Downloader.fetch_once`：单次请求、不自动跟随重定向、流式字节限制；重定向由 Analyzer 逐跳重新校验。
- `SiteDetector` 和 `main.py --discover` 已收敛为 Analyzer 的兼容/调试入口。
- 重定向仅允许相同 origin，或同一规范化 host 的 http -> https 升级；https -> http、跨 host、端口变化均拒绝。
- DiscoveryLimits 中的 candidate、script、evidence 预算已集中执行。

## 15. TASK-017E SearchPlan 执行契约

- SearchPlan 由 Python Search Worker 生成或读取缓存，只在同一 Python Worker 进程内交接。
- Python 负责执行；Go 不解析、不执行、不消费 SearchPlan。
- 不新增 SearchPlan Redis 结果消息、计划队列、执行队列或 ACK 队列。
- SearchPlanCache 仅为生成阶段的内部优化缓存，不是结果交付通道。
- 执行器冻结路径：`crawler/search/plan_executor.py`；入口：`execute_search_plan(plan, keywords, *, fetcher, policy)`；TASK-018G 起生产默认经 AdapterRegistry 分派。
- 只执行 `ready/active` 且 `strategy` 为 `html_form/json_api` 的计划。
- 成功候选映射为既有 `URLMessage` 并发布到 `crawler:url`；执行错误复用 `SEARCH_FAILED`。
- 当前 PlanBuilder 已通过 R5 selector evidence 生成可执行 `SearchSelectors`，TASK-017E 执行器与 Worker v2 主链已实现。
- 完整契约：`docs/SEARCH_PLAN_EXECUTION.md`；ADR：`docs/decisions/ADR-003-search-plan-execution.md`。

## 16. TASK-017E-R3 受控搜索探测契约

- 受控探测是候选发现后的独立 Python 内部阶段，不属于 SearchPlan 正式执行。
- 正式模块路径：`crawler/site/search_probe.py`；入口：`probe_search_candidate(candidate, keywords, *, fetcher, policy)`。
- 探测不发布搜索结果 URL，不进入 legacy `plugin_search()`，不写入 Redis，Go 不消费探测结果。
- 探测只用于观察响应结构并形成 selector 证据；响应体只在 Python 进程内短暂存在。
- 请求预算、SSRF/DNS/redirect、Content-Type、selector 门禁和 R4/R5 拆分见 `docs/SEARCH_ANALYSIS_PROBE.md`。
- ADR：`docs/decisions/ADR-004-search-analysis-probe.md`。
- R4/R5 已实现，TASK-017E 已实现。
## 17. TASK-017E-R4 受控探测基础

- 状态：已实现
- 内容：SearchCandidate 请求形状、forms 请求形状映射、SearchProbePolicy、安全请求构造、固定 IP 连接探测、响应门禁
- 文件：crawler/site/models.py、crawler/site/forms.py、crawler/site/search_probe.py、tests/test_search_probe.py
- R5 已实现，TASK-017E 主链已实现。
## 18. TASK-017E-R5 Selector Evidence 提取

- 状态：已实现
- 内容：HTML CSS selector 与 JSON RFC 6901 Pointer 证据提取、同响应重新验证、正式 `probe_search_candidate()`、PlanBuilder 传递
- 文件：crawler/site/selector_evidence.py、crawler/site/search_probe.py、crawler/search/plan_builder.py
- TASK-017E 主执行适配器已实现。
## 19. TASK-017E SearchPlan 执行器与 Worker v2 主链

- 状态：已实现
- 内容：plan_executor、search_orchestrator、SearchWorker v2 主链、正式 URLMessage 发布
- Python 发布正式 `URLMessage`；Go 当前通过宽松 JSON 解码兼容读取共同字段。
- 本轮未修改 Go 或协议；TASK-017F 已完成共享 fixture 契约验证，Go 测试通过 go-redis hook 注入 BRPOP 并实际调用 `RedisQueue.PopURL()`/`pop()` 生产解码。
- 缓存生命周期：新计划 success/no_results 后写缓存；缓存命中失败删除缓存；publish_failure 不删除合法计划。

## 20. TASK-018G 生产 Registry 与统一 Adapter 集成

- `crawler/search/adapter_composition.py` 提供 `build_default_adapter_registry()`，每次返回新 Registry，注册 HTML、TRS、JPAAS、Generic JSON 四类正式 Adapter。
- `plan_executor.py` 的 `RegistryPlanExecutor` 与 `execute_plan_with_registry()` 只通过注入 Registry 分派；生产默认 executor 使用默认 Registry，无 fallback、无 source/endpoint/strategy 猜测。
- `search_orchestrator.py` 与 `workers/search_worker.py` 的 v2 生产路径已接入默认 Registry，不建立全局可变 singleton，也不在 orchestrator 内直接调用具体 Adapter。
- 正式调用链为：Analyzer/Candidate evidence → PlanBuilder → SearchPlan v2 → cache/orchestrator → PlanExecutor → AdapterRegistry → Adapter → URLMessage publication。
- 真实 Analyzer 只有 HTML GET/POST 可自动生成 ready plan；TRS、JPAAS、Generic JSON GET/POST 仍需显式正式 Candidate/SearchPlan 或后续生产者补齐。
- TASK-018H 最终交付门禁已通过；TASK-022 连接级安全仍不在本轮范围。



## 21. ArticleResult v2 协议合同

TASK-019B-1 冻结 ArticleResult v2 消息族：

- `URLMessageV2`：type=url，队列目标仍为 `crawler:url`
- `HTMLMessageV2`：type=html，队列目标仍为 `crawler:html`
- `ArticleResultV2`：type=article_result，队列目标仍为 `crawler:result`

协议版本显式使用 `2.0`，与 v1 共存；v1 消息、fixture 和运行行为保持不变。本轮只建立协议模型、共享 fixture 和 Go/Python 双端契约测试，未接入 Redis 生产消费，未修改 Worker、Parser、数据库或现有运行逻辑。



## 22. TASK-019B-2：SearchHit → URLMessageV2

Python v2 orchestrator 已按规范化关键词顺序串行执行 SearchPlan，并把每个 SearchResultItem 构造成 SearchHit 与 URLMessageV2，再通过 `RedisURLMessagePublisher` 写入 `crawler:url`。

- 执行器与四类 Adapter 使用单 `query_term`，不再丢弃 `keywords[0]` 之外的关键词。
- `hit_id` 由 `protocol_version/task_id/plan_id/original_query/query_term/url` 的 canonical SHA-256 确定性生成。
- 同一 URL 被不同查询词命中时保留多个逻辑命中记录。
- TRS/JPAAS 日期映射到 `published_at`。
- TASK-019B-3 已接通 Go 下载消费者；当前检查点仍不可部署。


## 23. TASK-019B-4：Python v2 详情提取与 ArticleResultV2 发布

TASK-019B-4 已接通 `crawler:html → Python 单消费者显式分流 → HTMLMessageV2 严格解码 → 正文提取/详情重评分 → ArticleResultV2 → crawler:result`。

- `crawler:html` 仍只有一个 Python BRPOP 消费者；缺版本与 `protocol_version=1.0` 走原 legacy/v1 路径，`2.0` 走独立 v2 路径。
- v2 严格解码失败、显式 null、非字符串版本、未知版本、非对象 JSON 均拒绝，不回退 v1，不伪造 v1 ErrorMessage。
- v2 站点配置按 `final_url.hostname` 精确匹配 `config/site.json`；未命中时使用通用提取，不报 unknown site。
- 正文提取策略按实际成功结果记录：`site_selector/cms_rule/ai/density/fallback/none`；v2 不应用 3000/10000 字截断。
- 标题顺序：站点/CMS规则 → h1 → og:title → html title → 消息标题回退；发布日期详情页优先，消息 `published_at` 规范化回退；canonical 只读取 `<link rel="canonical">` 的合法绝对 URL。
- summary 优先使用纯文本化 snippet，否则取正文前 500 字符；content 来源摘要不重复计分。
- 详情评分使用 `config/score.json` 的 `title_weight/body_weight/url_weight/threshold`；URL 候选为 canonical_url 非空时优先。
- accepted 必须由详情页标题或正文的 original evidence 达到阈值；搜索标题、search snippet、expanded 或 URL 单独命中最高为 review_required。
- ArticleResultV2 发布到 `crawler:result`，accepted/review_required/irrelevant/extract_failed 均保留。
- B3 Windows Race Detector 已正式通过，本机已记录环境、命令与 exit code=0 结果；B4 未修改 Go 代码，也未重复执行 Race Detector。
- 当前检查点不可部署；Go 持久化消费者与数据库合同等待 TASK-019B-5。
- TASK-019B-4C 已退役并删除 `parser/redis_worker.py`；正式链唯一 Python 消费者为 `workers/parser_worker.py`。

- TASK-019B-4D 已退役 `api/server.py` 内联 Redis Parser；`api/server.py` 仅承担 HTTP API，不消费 `crawler:html`。

## 24. TASK-019B-5：ArticleResultV2 MySQL 持久化合同

- 旧 `article/task/crawl_log` 表保留，继续服务 legacy/v1。
- 新增 v2 表 `articles/task_articles` 及迁移合同，但未自动迁移、未接入生产消费者。
- `ArticleV2` 保存 URL 身份与正文版本；`TaskArticleV2` 保存任务命中结果与全部状态。
- `MySQLStore.PersistArticleResultV2` 是单事务入口，支持幂等重放与 `ErrArticleResultConflict`。
- 当前正式链仍为 `crawler:result → 旧 ResultMessage v1 消费者 → 旧 article`。
- ArticleResultV2 仍发布到 `crawler:result`，但 Go v2 生产消费者尚未接入。

## 25. TASK-019B-6：crawler:result 显式版本分流

- `crawler:result` 正式链使用单次 `PopResultDispatch()`。
- 缺失版本与 `1.0` 继续走旧 ResultMessage v1 消费、旧 `article` 表和旧任务统计。
- `2.0` 严格解码为 ArticleResultV2 并调用 `PersistArticleResultV2` 写入 `articles/task_articles`。
- v2 不更新旧 task 状态、不修改 article_count、不经过旧 URL 去重。
- `PopResultMessage/PopResult` 保留兼容但不再作为生产入口。
- 未新增第二个 `crawler:result` 消费者；迁移未自动执行。

## 26. TASK-019B-6R：Legacy GORM 表名固化

- 旧 GORM 模型显式映射 singular 表：`Article → article`、`Task → task`、`CrawlLog → crawl_log`。
- v2 模型保持：`ArticleV2 → articles`、`TaskArticleV2 → task_articles`。
- 不启用全局 SingularTable；AutoMigrate 仍只管理三个 legacy 模型。
- 五个表名无冲突；config/schema.sql、Python MySQL 和 Go GORM 表名一致。
- B5 migration 仍独立显式执行，未自动接入。

## 27. TASK-019B-7：一次性隔离 E2E 已验证

- 使用唯一 Compose project 和 loopback 随机端口验证真实 MySQL/Redis。
- Legacy AutoMigrate 只创建 singular 表；B5 migration 显式执行两次成功。
- 五表并存，正式结果消费者到 MySQL 的真实路径通过。
- replay、conflict rollback、五种状态、legacy/v1 共存和非法版本隔离均通过。
- 精确项目容器/网络/卷残留为 0；migration 仍不属于自动启动流程。

## 28. TASK-019B-8/8R：本地全链 v2 E2E

- 本地 httptest + 隔离 Redis/MySQL 贯通 URLMessageV2 到 MySQL 持久化。
- `PopURLDispatch` 使用显式 protocol_version 键存在性判定，null/非字符串不再回退 legacy。
- 多 hit 共用一次下载；accepted/review_required/irrelevant/extract_failed 真实贯通。
- PDF MIME 被下载边界拒绝；非法消息请求数为 0。
- migration 独立执行，未自动接入生产启动。

## 29. TASK-019C-1：PDF/Office 安全回归边界

- PDF/DOCX/XLSX 解析函数当前为库级休眠能力，无生产调用方。
- v2 下载链通过 MIME 拒绝 PDF/Office，不进入 Python 详情处理或持久化。
- 新增离线能力矩阵、安全副作用测试与资源风险记录。
- 不新增 OCR、解密、复杂解析、Office/COM、subprocess 或附件保存。

## 30. TASK-019C-2：文档解析安全门

- `safe_parse_document` 作为独立安全入口，当前无生产调用方。
- 在调用旧 PDF/DOCX/XLSX 辅助函数前执行资源预检，超限整体拒绝。
- 不接 Worker/Redis/API/数据库，不保存附件。
- 未来接入生产前必须强制只使用安全入口。

## 31. 出站请求安全边界（TASK-022A-R 合同已冻结）

`docs/OUTBOUND_REQUEST_SECURITY_CONTRACT.md` 与 ADR-016 已于 TASK-022A-R 批准冻结（D-01 至 D-12），但生产代码尚未统一接入安全 transport，当前版本不可部署。

已知出站面：

- Python legacy `requests` 链：CLI、legacy 搜索插件、详情抓取、v1 搜索 Worker。
- Python v2 Analyzer 入口抓取：预检 IP 后仍由 requests 二次解析，存在 TOCTOU。
- Python v2 PinnedProbeFetcher：全地址 IP 分类并固定连接，是当前安全形态最完整的一条路径。
- Go RestyFetcher：v2/legacy 下载，默认环境代理、默认自动重定向、无 IP/DNS/域名/响应体策略。
- Go `SearchArticles` 与 `internal/httpx.Client`：当前无生产调用方，属于休眠路径，不得绕过后续统一 transport。
- Redis/MySQL 属于内部服务边界，不作为普通出站 HTTP 处理，但属于 SSRF 威胁模型资产。

实施原则：

- 所有正式出站路径共享安全 transport，不允许 Probe、Adapter、Worker、redirect、proxy、legacy/v1 旁路。
- 连接固定到已验证 IP，Host/SNI/证书使用原 hostname。
- 安全拒绝 fail closed；不得伪造 v1 成功或 `extract_failed`。
- 测试 loopback 许可通过依赖注入实现，不得变成生产开关。
- 未完成 022B–022H 前，不得宣称生产级 SSRF 防护。

## 32. 出站安全基础库（TASK-022B）

- Python 新增 `crawler/security`：`url_normalizer`、`ip_policy`、`dns_policy`、`outbound_policy`、`models`。
- Go 新增 `go-spider/internal/security`：`url_normalizer.go`、`ip_policy.go`、`dns_policy.go`、`outbound_policy.go`、`models.go`。
- Python/Go 读取同一份 `tests/fixtures/outbound_request_security_contract.json`（164 cases），不维护第二份期望结果。
- IDNA 使用 UTS #46 lookup profile；Python `idna==3.18` 已直接声明，Go `golang.org/x/net/idna v0.52.0` 已提升为直接依赖。
- 本轮基础库不接入现有 HTTP 客户端、Adapter、Worker、queue 或 protocol；生产请求链行为不变。
- 固定连接属于 TASK-022C，生产接线属于 TASK-022G；当前版本不可部署。
## 33. Pinned Address Transport（TASK-022C）

- Python 新增 `crawler/security/pinned_connection.py` 与 `tls_policy.py`。
- Go 新增 `go-spider/internal/security/pinned_target.go`、`pinned_dialer.go`、`pinned_transport.go`。
- `PinnedTarget` 保存规范化 host、有效端口、Host header、server_name、已验证地址与策略身份；不保存原始 URL、userinfo、fragment、Cookie 或 header。
- TCP 只连接已验证数字 IP；HTTPS 使用原规范化 hostname 作为 ServerName 并正常验证证书链与 hostname/IP SAN。
- 本地 loopback 测试通过测试内部构造方式注入；生产公开 API 无 allow_loopback/test_mode/skip_policy/insecure。
- 当前没有生产调用方；生产接线属于 TASK-022G。