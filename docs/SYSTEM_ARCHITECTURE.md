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

以上为目标运行流程。当前版本尚未实现 `crawler:search`，且 `crawler:url` 仍由 Go 生产并在 Go 内部消费，后续任务将按版本化协议逐步迁移。

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
| Python API | api/server.py | uvicorn api.server:app --port 8000 | 调试/Parser |
| Python Worker | parser/redis_worker.py | python parser/redis_worker.py | Redis 消费 |

## 5. Redis 消息协议

### 5.1 当前消息协议

| 队列 | 生产者 | 消费者 | JSON 字段 |
|------|--------|--------|---------|
| crawler:url | Go PushURLTask | Go (内部) | url, site, keyword, level |
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
- api/server.py               FastAPI 服务
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
- TASK-017（运行时 SearchPlan 生成与正式 Worker 接入）未实施。

### 13.4 TASK-015 契约规则摘要

- 空集合统一为 `{}`/`[]`，协议 JSON 不输出 `null`。
- `level` 默认 0、`max_pages` 默认 1；缺失使用默认值，显式 `null` 拒绝。
- `target_url` 拒绝前后空白、非法端口、缺失 host 和非 http/https scheme。
- v1/v2 使用显式协议版本分派，未知字段和跨版本字段返回明确错误。
- 无版本请求只有合法旧 v1 `site` + 字符串 `keywords` 才固定映射 v1；带 `target_url` 或数组 `keywords` 必须显式声明 v2。
- `plan_id` 使用 SHA-256 canonical JSON；U+2028/U+2029 转义为 `\u2028`/`\u2029`，`<>&` 不转义。
- TASK-016、TASK-017 仍未实施；正式 Worker v2 执行未实现。

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
