# Changelog

本文记录仓库内文档和功能基线的可审计变化。项目尚未形成正式 SemVer release，所有历史提交仍以 Git 为准。

## [Unreleased]

### Added

- 固化 V1.0 完整主基线：`docs/baselines/通用型爬虫_Python-Go_产品设计与开发基线说明书_V1.0.docx`
- 固化 V1.1 独立补丁：`docs/baselines/通用型爬虫_Python-Go_产品设计与开发基线补丁_V1.1.docx`
- 建立 SHA-256 校验文件：`docs/baselines/V1.0_V1.1_SHA256SUMS.txt`
- 建立基线权威入口：`docs/PRODUCT_BASELINE_V1.1.md`

### Changed

- `AGENTS.md` 增加 BUILD 前 V1.0/V1.1 联合阅读和哈希校验门禁
- `README.md` 将当前产品基线入口置于文档入口首位
- `docs/TASK.md` 记录基线状态和只读复核任务

### Clarified

- V1.0 是完整主基线，固化后保持字节不变
- V1.1 是独立补丁，冲突时以 V1.1 明确修订为准，未涉及内容继承 V1.0
- 文档固化不表示产品代码完成
- 未新增产品功能，发布状态仍为 RELEASE_BLOCKED

### Added

- Product Design V1.0 权威文档：`docs/PRODUCT_DESIGN_V1.0.md`
- 六份专题设计文档：`docs/FRONTEND_ARCHITECTURE.md`、`docs/API_CONTRACT.md`、`docs/DATA_MODEL.md`、`docs/DEPLOYMENT_ARCHITECTURE.md`、`docs/SECURITY_ARCHITECTURE.md`、`docs/TEST_STRATEGY.md`
- ADR-023：React、TypeScript 与 Vite 作为 Web 前端基线
- ADR-024：Go 作为唯一外部业务网关
- ADR-025：Redis Streams 与 Transactional Outbox

### Changed

- `docs/SYSTEM_ARCHITECTURE.md` 与冻结决策对齐，区分当前架构和目标 V1 架构
- 建立 `README.md`，记录当前真实状态和文档入口
- `docs/TASK.md` 进入产品设计等待独立 review 状态

### Clarified

- React 替代 Vue 残留作为目标前端
- Go 是唯一外部业务网关
- Python 是发现、业务抓取、解析、评分、过滤、去重和附件处理核心
- 消息架构目标为 Redis Streams 和 Transactional Outbox
- MySQL 是业务权威数据，DuckDB 只用于分析与导出
- OSEC evidence 已 SEALED，但 production loader 仍未开始

### Fixed

- 独立复审发现跨文档冲突并完成第二版候选修复
- 修正 OSEC transport 硬限制与产品调度默认值分层
- PD-075、PD-081 从 IMPLEMENTED 修正为 PARTIAL
- 保守完成度更新为 25.38%，理论上限更新为 25.88%
- DATA_MODEL 从 19 个实体补充为 20 个实体，新增 TaskArticle
- 修正任务终态重试、CrawlTask 阶段和 ExportJob 独立生命周期
- Playwright 隔离 Worker 归入 TARGET_V1 受控 JS 降级能力
- 57 项说明书覆盖映射改为逐条 57 行
- 修正部署启动顺序、资源限制、测试矩阵和 canary 构成
- README Go 命令改为先进入 go-spider 模块
- 产品设计 review 状态为 CHANGES_REQUESTED，未标记为 PASS

### Not Changed

- 无业务代码变化
- 无数据库 migration 变化
- 无 Docker 运行配置变化
- 无前端实现
- 无 production 接入
- deployment 仍为 BLOCKED

本项目仍处于设计基线与部分底层实现阶段，不得依据本文档宣称产品已可发布。
