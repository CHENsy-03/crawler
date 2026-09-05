# 通用型爬虫 V1.0 主基线与 V1.1 补丁

## 1. 当前产品设计基线入口

当前有效产品设计基线由两份独立文档共同组成：

1. V1.0 完整主基线
2. V1.1 独立补丁

| 文档 | 版本 | 仓库路径 | 长度 | SHA-256 |
|---|---|---|---|---|
| 完整主基线 | V1.0 | docs/baselines/通用型爬虫_Python-Go_产品设计与开发基线说明书_V1.0.docx | 499259 | C6033220006A5CF6E880490FD20CEB1138456615FDCD3FDDB7FB5402957E76FA |
| 独立补丁 | V1.1 | docs/baselines/通用型爬虫_Python-Go_产品设计与开发基线补丁_V1.1.docx | 85431 | 2E34CCFCB4DBA06228CBC80A9FDB2A012DF80486897270CF42AD94FA9E580B9C |

校验文件：`docs/baselines/V1.0_V1.1_SHA256SUMS.txt`

## 2. 生效规则

- V1.0 是完整主基线，从固化时点起永久保持原始字节不变。
- V1.1 是独立补丁，不得回写、合并或重新保存进 V1.0。
- V1.1 只覆盖其明确列出的修订点。
- V1.1 与 V1.0 明确冲突时，以 V1.1 为准。
- V1.1 未涉及的内容继续以 V1.0 为准。
- 两份文档必须共同阅读，共同构成当前有效产品设计基线。
- 后续任何调整必须创建 V1.2 或更高版本补丁，不得直接修改已固化文档。

## 3. V1.1 冻结修订主题

V1.1 至少覆盖并冻结以下主题：

- Python Worker 混合执行模型与加权 slot
- Review Hold 结构化引用及跨介质提交状态机
- 旧链高危迁移与单权威切换
- MySQL 窄查询、分页、索引与正文分离
- TRS/JPAAS/Generic JSON/HTML 脱敏 fixture
- Playwright CSP、CORS、iframe 失败语义
- Redis Streams DRAIN_ONLY 容量保护
- GlobalBlockEntry 与 22 类实体模型
- DuckDB 临时空间独立配额和 20 GiB 上限
- 工期重估、DoD CI 门禁、DEV-103/DEV-206 加强审查

## 4. 阅读与校验要求

任何产品 BUILD、代码修改、架构实现或任务拆分开始前，必须：

1. 完整阅读 V1.0 主基线。
2. 完整阅读 V1.1 补丁。
3. 校验两份文档 SHA-256。
4. 按“V1.1 明确修订优先，其余继承 V1.0”解释需求。
5. 在任务报告中记录读取和哈希校验结果。

## 5. 固化边界

- 文档固化不代表产品代码已经完成。
- 当前发布状态保持 RELEASE_BLOCKED。
- 源码审计锚点：97bcf79972f8db293fe8f2bb1e45bb9dfe2129e0。
- 源码审计锚点不是本次基线固化提交；两者必须区分。
- 后续 BUILD 仍须独立只读复核；当前发布状态仍为 RELEASE_BLOCKED。

## 6. DEV-001 联合解释治理资产

- [docs/TERMINOLOGY_V1.0_V1.1.md](TERMINOLOGY_V1.0_V1.1.md)：V1.0/V1.1 规范术语表
- [docs/baselines/V1.0_V1.1_DELTA_MATRIX.md](baselines/V1.0_V1.1_DELTA_MATRIX.md)：V1.1 差异矩阵
- [docs/baselines/V1.0_V1.1_READ_ATTESTATION.md](baselines/V1.0_V1.1_READ_ATTESTATION.md)：阅读与批准证明

上述三项是 DEV-001 治理资产，不取代两份 DOCX；它们只用于帮助一致解释联合基线。

## 7. DEV-002 契约地基资产

- [docs/STATUS_ERROR_EVENT_DICTIONARY_V1.0_V1.1.md](STATUS_ERROR_EVENT_DICTIONARY_V1.0_V1.1.md)：状态/错误/事件字典说明
- [protocol/status_error_event_dictionary.schema.json](../protocol/status_error_event_dictionary.schema.json)
- [tests/fixtures/status_error_event_dictionary_v1.json](../tests/fixtures/status_error_event_dictionary_v1.json)

DEV-002 只冻结契约地基，不表示 API、数据库、Redis Streams 或状态机已实现。

## 8. DEV-004 数据模型资产

- [docs/DATA_MODEL_V1.0_V1.1.md](DATA_MODEL_V1.0_V1.1.md)：当前权威数据模型
- [docs/decisions/ADR-026-opaque-ulid-identifier-contract.md](decisions/ADR-026-opaque-ulid-identifier-contract.md)：21 类 ULID 与 AuditLog 例外标识契约
- [docs/evidence/dev004/DEV004_MYSQL8_VALIDATION.md](evidence/dev004/DEV004_MYSQL8_VALIDATION.md)：DEV-004 B3/B4/B5 真实 MySQL 验证证据
- [migrations/mysql/README.md](../migrations/mysql/README.md)：MySQL migration 执行与版本契约
- [migrations/mysql/0002_v1_0_v1_1_22_entities.sql](../migrations/mysql/0002_v1_0_v1_1_22_entities.sql)
- [migrations/mysql/0002_v1_0_v1_1_22_entities.down.sql](../migrations/mysql/0002_v1_0_v1_1_22_entities.down.sql)

DEV-004 只表示数据模型候选实现，不表示业务 API、Redis Streams、Outbox dispatcher 或状态机已实现。0002 只支持空的 0001 前置状态，非空 legacy 数据与不可变存储迁移仍被阻断。
