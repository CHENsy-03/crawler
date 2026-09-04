# 通用型爬虫

面向内部单机部署的政务/公开网站信息采集平台，以 Web 管理面板为主入口，以 CLI 与 API 作为工程和运维接口。

## 产品基线（当前权威）

当前有效产品基线由 V1.0 完整主基线与 V1.1 独立补丁共同构成，权威入口为：

- [docs/PRODUCT_BASELINE_V1.1.md](docs/PRODUCT_BASELINE_V1.1.md)
- [V1.0 主基线](docs/baselines/通用型爬虫_Python-Go_产品设计与开发基线说明书_V1.0.docx)
- [V1.1 补丁](docs/baselines/通用型爬虫_Python-Go_产品设计与开发基线补丁_V1.1.docx)
- [SHA-256 校验文件](docs/baselines/V1.0_V1.1_SHA256SUMS.txt)

V1.0/V1.1 固化不表示产品代码已完成，当前发布状态仍为 RELEASE_BLOCKED。

## 当前开发阶段

当前处于产品设计基线刚建立、完整产品尚未实现的阶段。以下状态为当前事实：

- OSEC Evidence/Manifest/S1/Seal Record 已 SEALED
- production_loader=NOT_STARTED
- deployment=BLOCKED
- 保守产品化完成度=25.38%
- NOT_VERIFIABLE 理论上限=25.88%

当前不得视为可正式发布版本。

## 当前真实可用入口

- Python CLI：`python main.py --site <site> --keywords <keyword>`
- Go CLI/基础 API：先进入 `go-spider` Go 模块，再运行 `go run .`
- Python Parser Worker：`python workers/parser_worker.py`
- Python Search Worker：`python workers/search_worker.py`
- 底层采集能力：TRS/JPAAS/HTML/JSON API 搜索适配、正文提取、评分、去重、出站安全基础库

当前尚不可用：

- React Web 管理面板
- 完整管理员认证与 Session
- `/api/v1`
- SSE 任务事件
- Redis Streams/Transactional Outbox
- production loader
- 正式 Docker Compose 产品部署

## 目标技术架构

- Web：React + TypeScript strict + Vite + Ant Design
- 外部网关：Go 唯一外部业务网关
- 采集核心：Python 负责发现、业务抓取、解析、评分、过滤、去重和附件处理
- 队列：Redis Streams + Consumer Groups
- 权威数据：MySQL
- 分析导出：DuckDB
- 入口与 TLS：Nginx
- 原始证据：不可变文件卷

目标架构是设计约束，不代表当前代码已按该架构完成。

## 当前主要冲突

- `frontend/index.html` 是 Vue 3 CDN 页面，分类为 CURRENT_CONFLICT，后续由 React Web 替换
- `api/server.py` FastAPI 是调试/受控接口，不作为生产外部网关
- Go 当前 Worker Pool 承担业务下载主链，属于待收敛实现
- Redis 当前使用 list，与目标 Redis Streams 冲突
- Python 历史 MySQL 写入模块与 MySQL 权威写入路径冲突
- 当前 Compose 不是完整产品拓扑

## 文档导航

- [docs/PRODUCT_BASELINE_V1.1.md](docs/PRODUCT_BASELINE_V1.1.md)：V1.0/V1.1 当前产品基线权威入口
- [docs/PRODUCT_DESIGN_V1.0.md](docs/PRODUCT_DESIGN_V1.0.md)：完整产品设计权威入口
- [docs/FRONTEND_ARCHITECTURE.md](docs/FRONTEND_ARCHITECTURE.md)：Web 前端目标架构
- [docs/API_CONTRACT.md](docs/API_CONTRACT.md)：API、OpenAPI 与 SSE 文档契约
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md)：20 类核心实体、MySQL、Redis Streams、DuckDB 与文件存储
- [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)：目标单机部署拓扑
- [docs/SECURITY_ARCHITECTURE.md](docs/SECURITY_ARCHITECTURE.md)：安全架构与 OSEC 边界
- [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md)：测试策略与发布门禁
- [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md)：系统架构现状与目标
- [docs/TASK.md](docs/TASK.md)：任务状态
- [docs/CHANGELOG.md](docs/CHANGELOG.md)：变更记录
- [docs/decisions/ADR-023-react-typescript-vite-frontend.md](docs/decisions/ADR-023-react-typescript-vite-frontend.md)
- [docs/decisions/ADR-024-go-unique-external-gateway.md](docs/decisions/ADR-024-go-unique-external-gateway.md)
- [docs/decisions/ADR-025-redis-streams-transactional-outbox.md](docs/decisions/ADR-025-redis-streams-transactional-outbox.md)

## 仓库目录导航

```text
api/                Python 调试 HTTP API
config/             配置与 schema
crawler/            Python 采集、搜索、解析、安全实现
docs/               产品、架构、任务、ADR 文档
frontend/           Vue 残留页面（CURRENT_CONFLICT）
go-spider/          Go CLI/API/Worker/Store 实现
migrations/         MySQL migration
tests/              Python 测试与 fixtures
workers/            Python Worker
```

## 开发与测试命令

所有命令应使用仓库相对路径，不要依赖本机绝对路径。

PowerShell：

```powershell
Set-Location .\go-spider
go run .
go test ./...
go vet ./...
go mod verify
Set-Location ..
```

Bash：

```bash
cd go-spider
go run .
go test ./...
go vet ./...
go mod verify
cd ..
```

Python 与文档检查：

```text
python -m pytest tests -q
git diff --check
```

仓库根目录没有 `go.mod`，不要从根目录执行 `go run ./go-spider`、`go test ./go-spider/...` 或 `go vet ./go-spider/...`。

仓库规范默认禁止访问真实外部网站、Redis、MySQL 的网络测试；相关 E2E 使用隔离 Compose 环境和 fixture。

## 安全与合法采集边界

- 不绕过登录、验证码、WAF 或访问控制
- 不从事未授权采集
- 遵守 robots、站点条款、访问频率与授权边界
- SSRF/DNS/IP/redirect/HTTP 限制由安全架构统一约束

## 不可正式发布说明

本项目尚未达到内部试用或正式发布条件。文档完成不等于功能完成，OSEC 证据 SEALED 不等于 production loader 已接入，测试通过不等于完整产品 E2E 完成。
