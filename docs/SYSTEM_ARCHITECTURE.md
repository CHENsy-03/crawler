# 通用爬虫系统架构

## 1. 架构目标

本平台目标为通用、稳定、可维护、可扩展的信息采集平台，支持任意政府网站的政策信息自动发现、搜索、下载、解析、评分和存储。

架构设计遵循以下原则：
- Python 负责采集执行面（搜索适配、HTML 解析、评分去重）
- Go 负责平台控制面（API 入口、任务调度、MySQL 持久化）
- Redis 作为跨运行时通信的唯一中间层

## 2. 总体运行流程

采集任务的完整生命周期：

```text
用户/API 提交任务 (Go Gin API)
  -> 任务创建和状态管理 (Go)
  -> 搜索 URL 发现 (Python plugins)
  -> 高并发 HTML 下载 (Go Worker Pool)
  -> HTML 推送到 Redis 队列 (Go PushHTML)
  -> Python Worker 消费 HTML (BRPop)
  -> HTML 解析、评分、去重 (Python)
  -> 结果推送到 Redis (Python LPush)
  -> Go 获取结果 (PopResult)
  -> MySQL 持久化 (Go GORM)
  -> 任务完成
```

Python 同时支持 CLI 模式 (`main.py --site X --keywords Y`) 和 API 模式 (FastAPI)。

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

| 队列 | 生产者 | 消费者 | JSON 字段 |
|------|--------|--------|---------|
| crawler:url | Go PushURLTask | Go (内部) | url, site, keyword, level |
| crawler:html | Go PushHTML | Python BRPop | url, title, html, time |
| crawler:error | Go PushError | - | url, error, time |
| crawler:result | Python LPush | Go PopResult | url, title, score, content |

消息约束：JSON 序列化，字段对应 Go HTMLPayload 与 Python dict，新增字段需两端回归测试。

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

Go 端 config.go 读取同路径 Python 配置 (site.json/http.json/score.json)，无需独立格式。

## 9. 错误处理与监控

- Go Worker Pool 通过 CircuitBreaker 管理失败，失败 URL 进入 crawler:error 队列。
- Python httpx 使用 Retry + RateLimiter + CircuitBreaker。
- 所有错误日志包含 task_id, stage, url, error_code, retryable, timestamp。
- Prometheus /metrics 端点 (Go Gin + Python FastAPI)。
- Grafana 仪表盘配置位于 config/grafana-dashboard.json。

## 10. 当前架构与目标架构差异

| 模块 | 当前 | 目标 |
|------|------|------|
| API 服务 | Go Gin + Python FastAPI 重复 | 统一为 Go Gin |
| CLI 入口 | Go + Python 两套 | 统一为 Go |
| MySQL 写入 | Go GORM + Python pymysql | 归 Go 唯一 |
| 搜索执行 | Go + Python 重复 | 归 Python 唯一 |
| HTTP 客户端 | Go Resty + Python httpx | 各归各自运行时 |

## 11. 迁移顺序

1. 修复基础契约 (已完成 TASK-002)
2. 确定职责边界 (已完成 TASK-003)
3. 统一 HTTP 下载能力
4. 建立标准数据模型
5. 完善 Go 任务 API 和调度
6. 串联端到端采集流水线
7. 收敛冗余模块
8. 完善前端展示
9. 端到端验收

## 12. 架构约束

- Python 与 Go 不互相直接调用。
- Redis 是唯一的跨运行时通信通道。
- 搜索能力迭代只在 Python 侧进行。
- HTML 解析、评分、去重只在 Python 侧实现。
- 任务状态、MySQL 事务数据只在 Go 侧管理。
- 同一功能不允许在两端同时存在两份实现。
- 新加模块需先更新本文档，再开始实施。
- go mod tidy 和 task-001-go-deps.patch 在明确归属后处理。
