# Changelog

本文记录仓库内文档和功能基线的可审计变化。项目尚未形成正式 SemVer release，所有历史提交仍以 Git 为准。

## [Unreleased]

### Governance Task Entry

- 将 AGENTS.md、DEVELOPMENT_RULES.md 和 TASK.md 中旧 TASK 路线明确标记为历史参考。
- 在 TASK.md 建立唯一现行任务入口，区分已集成工作、未提交治理修改和未开始的 OpenAPI BUILD。
- 保留历史执行证据及现有安全、契约和发布约束。
- 本次变更仅涉及治理文档，尚待审查与提交；未实施 OpenAPI 或其他产品功能。

### Governance Validation Policy

- TEST_STRATEGY 增加验证阶段与证据复用边界，保留发布级完整门禁。
- DEVELOPMENT_RULES 增加 GitHub 检查证据用语及判断边界。
- TASK 唯一入口切换到本轮任务，并保留 B4 历史记录及文字勘误。
- 本次仅涉及治理文档，尚待审查与提交；未实施 OpenAPI 或其他产品功能。

### Governance Historical Evidence

- README 完成度百分比改为历史记录说明，不再作为当前完成度。
- TEST_STRATEGY 保留历史测试结果，并注明文档来源及执行证据局限。
- TASK 唯一入口切换到本轮任务，保留 B5 历史记录。
- 未重算完成度、未重跑历史测试、未修改测试门禁。
- 本次变更尚待审查与提交，治理整改尚未完成最终 GitHub 审阅。

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

### Fixed

- 修复 README 的第二权威入口：`docs/PRODUCT_DESIGN_V1.0.md` 改为历史产品设计输入
- 将旧产品设计 Markdown 标记为 `HISTORICAL_REFERENCE` / `SUPERSEDED_AS_PRODUCT_AUTHORITY`
- 将旧 Data Model 标记为 `LEGACY_PARTIAL_REFERENCE`
- 明确 20 类实体为历史快照，当前目标为 V1.1 修订后的 22 类实体
- 澄清 TASK 中旧 `product_design_v1_0` 字段专指历史 Markdown 产品设计状态
- AGENTS 固化当前 scope root 与 repository，并标记旧路径为历史记录
- 未修改冻结 DOCX、产品代码或数据库模型
- 发布仍为 RELEASE_BLOCKED，等待独立只读 R2

### Fixed (B2)

- 修复 `docs/SYSTEM_ARCHITECTURE.md` 中遗留的第二产品权威入口
- 将其产品基线指向统一为 V1.0 完整主基线 DOCX + V1.1 强制附属补丁 DOCX
- 旧 `docs/PRODUCT_DESIGN_V1.0.md` 仅作为历史追溯材料，不再作为冲突裁决权威
- 未修改具体系统架构设计
- 未修改冻结 DOCX 或产品代码
- 发布仍为 RELEASE_BLOCKED，等待独立只读 R3

### Fixed (B3)

- 修复 `docs/E2E_TEST.md` 中旧工作目录操作指令，改为从当前 Git 仓库根目录执行
- 修复 `docs/REDIS_PROTOCOL.md` 中 canonical fixture 旧路径，改为 `tests/fixtures/redis_protocol_v2.json`
- 两处均改为当前仓库根目录相对语义
- 未运行 E2E 或协议测试
- 未修改测试、fixture、Redis 协议或产品代码
- 冻结 DOCX 未变化
- 发布仍为 RELEASE_BLOCKED，等待独立只读 R4

### DEV-001 Added

- 建立 V1.0/V1.1 联合基线术语表：`docs/TERMINOLOGY_V1.0_V1.1.md`
- 建立 V1.0/V1.1 差异矩阵：`docs/baselines/V1.0_V1.1_DELTA_MATRIX.md`
- 建立可复核阅读与批准证明：`docs/baselines/V1.0_V1.1_READ_ATTESTATION.md`
- `PRODUCT_BASELINE_V1.1.md`、`README.md`、`docs/TASK.md` 增加 DEV-001 导航与状态
- 未修改冻结 DOCX
- 未实现产品功能
- 发布仍为 RELEASE_BLOCKED
- DEV-001 等待独立只读 Review

### DEV-002 Added

- 建立 JSON schema：`protocol/status_error_event_dictionary.schema.json`
- 建立 canonical fixture：`tests/fixtures/status_error_event_dictionary_v1.json`
- 建立 Python/Go 字符串枚举与 contract tests
- 建立状态/错误/事件字典文档：`docs/STATUS_ERROR_EVENT_DICTIONARY_V1.0_V1.1.md`
- 更新 API_CONTRACT、REDIS_PROTOCOL、PRODUCT_BASELINE、README、TASK、CHANGELOG
- 未实现 API、数据库 migration、Redis Streams、状态机或前端功能
- 发布仍为 RELEASE_BLOCKED
- DEV-002 等待独立只读 Review

### DEV-002 Fixed (B2)

- 新增 Audit event：`global_block_legal_request_activated`
- 增强重复检测，防止 status/error/event/alias/decision 重复项被 set/map 折叠
- 真实执行 JSON Schema validation，含正向与负向用例
- 增强 status/error/event metadata 验证
- 未实现 API、数据库、Redis Streams 或业务功能
- 发布仍为 RELEASE_BLOCKED
- DEV-002 等待独立只读 R2

### DEV-002 Fixed (B3)

- 修正 Audit event `global_block_legal_request_activated` 的同步数据流语义
- transport 修正为 in_process；consumer 修正为 go_api；persistence_target=mysql_audit_log
- normative_source 修正为 V1.1 10.3；payload_contract_owner 修正为 DEV-004
- schema 移除 audit_log transport，并增加 Audit 精确约束与五类 family 机械保证
- Python/Go 增加同键异内容的五类重复负向测试
- 未实现 AuditLog、GlobalBlockEntry、migration、Redis Streams 或 Outbox
- 发布仍为 RELEASE_BLOCKED
- DEV-002 等待独立只读 R3

### DEV-002 Fixed (B4)

- 禁止非 AUDIT_EVENT 携带 persistence_target
- Go contract test 增加 persistence_target 正向和负向验证
- transport canonical 拼写收敛为 `SSE`，小写 `sse` 为非法输入
- Python/Go contract negative tests 增强
- 未实现 API、数据库、Redis Streams、AuditLog 或业务功能
- 发布仍为 RELEASE_BLOCKED
- DEV-002 等待独立只读 R4

### DEV-004 Added

- 建立当前权威数据模型：`docs/DATA_MODEL_V1.0_V1.1.md`
- 新增 22 实体 forward migration 与 down migration
- 新增 Go 数据模型元数据与契约测试
- 新增 22 实体 fixture
- 未实现 API、Redis Streams、Outbox dispatcher、GlobalBlockEntry 运行时或 AuditLog 业务代码
- 真实 MySQL 执行未验证
- 发布仍为 RELEASE_BLOCKED
- DEV-004 等待独立只读 Review

### DEV-004 Fixed (B3)

- 新增 ADR-026：21 类非审计实体 canonical ULID 主键契约，AuditLog 作为唯一 AUTO_INCREMENT 例外
- 0002 forward/down 改为 fail-closed：只支持空的 migration 0001 前置状态；拒绝非空 legacy 数据；down 拒绝删除有数据目标表
- 六处 task_id FK 收敛为 CHAR(26) ascii ascii_bin，真实 MySQL 8 创建无 errno 3780
- ReviewDecision 改为 hold_artifact_id/hold_artifact_checksum/evidence_schema_version 强引用，并移除对可清理 ArticleVersion 的强 FK
- GlobalBlockEntry 字段收敛为 match_type/pattern_normalized/reason_code/reason_summary 并增加活动唯一与查询索引
- TaskArticle 增加 persisted_at/relevance_score/review_state 和四种窄列表索引
- Go 正式模型从元数据注册表升级为 22 实体字段模型
- 新增 100k Article/200k TaskArticle 真实 MySQL EXPLAIN 验证证据
- 未实现非空 legacy 内容迁移、不可变存储引用、AuditLog 业务写入、API、Redis Streams 或 Outbox
- legacy_content_migration=BLOCKED_PENDING_IMMUTABLE_STORAGE_CONTRACT
- 发布仍为 RELEASE_BLOCKED
- DEV-004 等待独立只读 R2

### DEV-004 Fixed (B4)

- 0002 up/down 移除 CREATE PROCEDURE/CALL/DELIMITER/GROUP_CONCAT guard，改用会话级 TEMPORARY TABLE
- 空库、结构漂移和非空 legacy 状态返回可识别 guard 错误，不再出现 raw 1146
- down 在目标表非空、legacy 非空、纯 0001、legacy singular 或 partial 状态均 fail closed
- 新增 `migrations/mysql/README.md` migration 执行契约
- 六类 100k/200k EXPLAIN SQL 已固化，Q5 使用规范化 OR/keyset 形式
- 未实现非空 legacy 内容迁移、不可变存储引用、API、Redis Streams 或 Outbox
- legacy_content_migration=BLOCKED_PENDING_IMMUTABLE_STORAGE_CONTRACT
- 发布仍为 RELEASE_BLOCKED
- DEV-004 等待独立只读 R3

### DEV-004 Fixed (B5)

- migration SQL 增加 MySQL 8.0.16+ 版本能力门禁与 certified 8.0.46 执行契约
- up/down 在创建 guard 前自行启用 SESSION STRICT_ALL_TABLES 并验证
- 修正 B4 第四测试数据库历史范围偏差记录：guard_b4 标记 UNAUTHORIZED_AT_EXECUTION，所有者处置为 ACCEPTED_HISTORICAL_SCOPE_DEVIATION_NON_PRECEDENTIAL
- evidence 文件更名为 `DEV004_MYSQL8_VALIDATION.md` 并分节记录 B3/B4/B5
- 非 strict 初始 SESSION 下完成真实 MySQL B5 状态矩阵
- CHECK 约束经真实插入拒绝验证
- 未实现非空 legacy 内容迁移、API、Redis Streams、Outbox 或 production loader
- legacy_content_migration=BLOCKED_PENDING_IMMUTABLE_STORAGE_CONTRACT
- 发布仍为 RELEASE_BLOCKED
- DEV-004 等待独立只读 R4

### DEV-004 Fixed (B6)

- 修复 R4 P1：preflight 版本/strict guard 不再使用 CHECK
- 改为会话级 TEMPORARY TABLE 命名 UNIQUE KEY 重复键碰撞
- MariaDB 通过 VERSION() 和 @@version_comment 双来源显式排除
- 支持谓词固定为 MySQL 8.0、patch>=16
- evidence 新增 B6 分节并注明历史 migration 哈希仅对应当时版本
- 8.0.15 无本地镜像且禁止 pull，标记 MYSQL_8_0_15_RUNTIME_NOT_EXECUTED
- 未实现非空 legacy 内容迁移、API、Redis Streams、Outbox 或 production loader
- legacy_content_migration=BLOCKED_PENDING_IMMUTABLE_STORAGE_CONTRACT
- 发布仍为 RELEASE_BLOCKED
- DEV-004 等待独立只读 R5

### DEV-004 Integrated

- 独立只读 R5 返回 DEV004_REVIEW_R5_PASS_WAITING_COMMIT_AUTHORIZATION
- 候选提交为 e508ab82282be2ccf6b96705b1f1a2b7f74c062d
- GitHub PR #7 使用普通 merge commit 集成
- 集成提交为 c508f5bcb2164d0983222a6ac3150d28a61f594e
- dev_004=IMPLEMENTED_REVIEWED_AND_INTEGRATED
- legacy_content_migration=BLOCKED_PENDING_IMMUTABLE_STORAGE_CONTRACT
- production_loader、deployment 和 release 仍保持阻断或未开始
- DEV-003 是下一项开发任务，DEV-005 仍未开始
- 本次集成只代表 DEV-004 数据模型资产完成，不代表产品功能、部署或发布完成

### DEV-003 Contract Fix (B1)

- canonical ULID 校验增加首字符 `0`—`7` 和 128 bit 溢出拒绝，修复前会接受 `8`/`9` 开头或 26 个 `Z` 的越界表示
- ADR-026 修正 128 bit 结构、时间前缀可见性、ascii_bin 大小写语义与最大值说明
- 新增 canonical error：`task_limit_exceeded` / 422、`event_history_expired` / 410
- 字典 contract_version 更新为 1.1，旧 61 条错误与原有兼容决策保持不变
- Go/Python 枚举与定向测试同步更新
- API_CONTRACT 明确任务硬上限 422 和 SSE Last-Event-ID 过期 410 的恢复语义
- 未实现 OpenAPI/SSE 成品、API handler、业务实现或发布能力
- shared_contract_fix=IMPLEMENTED_WAITING_REVIEW
- DEV-003 OpenAPI BUILD 仍为 NOT_STARTED

### Added

- Product Design V1.0 历史文档记录：`docs/PRODUCT_DESIGN_V1.0.md`，后续已由 DOCX V1.0 主基线与 V1.1 附属补丁取代
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
