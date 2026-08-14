# TASK-019 最终验收

**验收日期：** 2026-08-14
**基线：** `main` @ `3723892e6c0987b3830394ef485258ac6a623901`
**结论：** PASS（实现验收通过，尚未提交，不可部署）

## 1. TASK-019 范围

TASK-019 包含 B1–B8R-B、C1–C2 全部阶段，覆盖 v2 协议、搜索生产链、下载、详情处理、持久化、真实 E2E、文档安全边界与安全门。

## 2. 阶段清单

- TASK-019B-1：ArticleResultV2 双端合同
- TASK-019B-2：SearchHit、多关键词与 URLMessageV2
- TASK-019B-3：Go URL 分流、单次下载与 HTMLMessageV2
- TASK-019B-4：Python 详情提取、重评分与 ArticleResultV2
- TASK-019B-4C：parser/redis_worker.py 退役
- TASK-019B-4D：API 内联 parser 消费者退役
- TASK-019B-5：MySQL migration 与持久化合同
- TASK-019B-6：crawler:result 生产消费者
- TASK-019B-6R：legacy/v2 GORM 表名隔离
- TASK-019B-7：真实 Redis/MySQL 持久化 E2E
- TASK-019B-8：本地 HTTP 全链 E2E
- TASK-019B-8R：PopURLDispatch 显式版本修复
- TASK-019B-8R-B：duplicate/null 四层测试证据
- TASK-019C-1：PDF/Office 现有能力审计
- TASK-019C-2：文档解析最小安全门

## 3. 文件归属

- B1：`protocol/messages.py`、`protocol/__init__.py`、`go-spider/internal/protocol/messages.go`、`go-spider/internal/protocol/article_result_v2_test.go`、`tests/fixtures/article_result_v2_contract.json`、`tests/test_article_result_v2.py`、`docs/decisions/ADR-006-article-result-v2.md`
- B2：`crawler/search/` B2 生产文件、`crawler/search/search_hit_builder.py`、B2 对应测试、`tests/test_search_hit_builder.py`、`tests/test_multi_keyword_pipeline.py`
- B3：`go-spider/internal/client/resty.go`、`resty_v2_test.go`、`go-spider/internal/worker/v2_download_coordinator.go`、`v2_download_coordinator_test.go`、`go-spider/internal/worker/pool.go`、`go-spider/internal/queue/redis.go`
- B4：`crawler/detail/*`、`workers/parser_worker.py`、`parser/html_parser.py`、`tests/test_detail_v2.py`、`docs/decisions/ADR-007-detail-extraction-relevance-v2.md`
- B4C：删除 `parser/redis_worker.py`、`tests/test_parser_worker_retirement.py`
- B4D：`api/server.py`、`tests/test_api_parser_worker_retirement.py`
- B5：`migrations/mysql/0001_articles_task_articles_v2.sql`、`config/schema.sql`、`config/schema.md`、`go-spider/internal/store/article_result_v2.go`、`article_result_v2_persistence.go` 及测试、`docs/MYSQL_PERSISTENCE_V2.md`、`docs/decisions/ADR-008-article-result-v2-persistence.md`
- B6：`go-spider/internal/queue/result_dispatch_v2_test.go`、`go-spider/internal/worker/result_consumer_v2_test.go`、`docs/decisions/ADR-009-article-result-v2-consumer.md`
- B6R：`go-spider/internal/store/mysql.go`、`go-spider/internal/store/table_name_contract_test.go`、`docs/decisions/ADR-010-legacy-gorm-table-names.md`
- B7：`tests/integration/task019b7/compose.yml`、`scripts/task019b7-e2e.ps1`、`go-spider/internal/store/article_result_v2_mysql_e2e_test.go`、`go-spider/internal/worker/result_consumer_v2_mysql_e2e_test.go`、`docs/decisions/ADR-011-task019b7-isolated-e2e.md`
- B8：`tests/integration/task019b8/`、`scripts/task019b8-e2e.ps1`、`go-spider/internal/worker/full_chain_v2_e2e_test.go`、`docs/decisions/ADR-013-local-full-chain-v2-e2e.md`
- B8R：`go-spider/internal/queue/url_dispatch_protocol_version_test.go`、`docs/decisions/ADR-012-url-dispatch-explicit-version.md`
- C1：`tests/test_document_format_contract.py`、`docs/DOCUMENT_FORMAT_SAFETY.md`、`docs/decisions/ADR-014-pdf-office-safe-regression-boundary.md`
- C2：`crawler/parser/document_safety.py`、`tests/test_document_safety.py`、`docs/DOCUMENT_SAFETY_GATE.md`、`docs/decisions/ADR-015-document-parse-safety-gate.md`
- 跨阶段文档：`docs/TASK.md`、`docs/SYSTEM_ARCHITECTURE.md`、`docs/REDIS_PROTOCOL.md`、`docs/E2E_TEST.md`
- 用户文件：用户 DOCX，排除

## 4. 需求追踪

| 能力 | 结论 |
|---|---|
| Python/Go ArticleResultV2 严格合同 | PASS |
| 三种 v2 消息共享 fixture | PASS |
| 多关键词按序执行 | PASS |
| original_query/query_term 来源保持 | PASS |
| SearchHit 与 hit_id 稳定算法 | PASS |
| 相同 URL 不同 query_term 不同 hit_id | PASS |
| Go crawler:url 显式版本分流 | PASS |
| 缺版本/1.0/2.0/非法版本真值表 | PASS |
| protocol_version=null 不回退 legacy | PASS |
| 相同 task/URL 一次逻辑下载，多 hit 透传 | PASS |
| HTML MIME 边界 | PASS |
| Python crawler:html 唯一消费者 | PASS |
| legacy/v1 与 v2 明确分流 | PASS |
| 未配置站点通用提取 | PASS |
| 完整正文无 3000 字截断 | PASS |
| 标题/日期/canonical 规则 | PASS |
| v2 独立相关性评分 | PASS |
| matched_evidence 稳定顺序 | PASS |
| 合法状态保留 | PASS |
| ArticleResultV2 严格验证后发布 | PASS |
| articles/task_articles migration | PASS |
| 五表名无冲突 | PASS |
| result_hash、replay、conflict rollback | PASS |
| crawler:result 显式分流 | PASS |
| v2 不更新 legacy task/article_count | PASS |
| 真实 Redis/MySQL E2E | PASS |
| 本地 HTTP 全链 E2E | PASS |
| PDF/Office 不进入 v2 生产链 | PASS |
| 文档安全门无生产调用方 | PASS |
| v1 行为保持 | PASS |

## 5. 自动化验证

- Python：`812 passed / 7 skipped / 0 failed`
- Python `pip check`：无 broken requirements
- Go：`go test ./...` 通过
- Go vet：通过
- Race Detector：client/protocol/queue/worker/store 全部通过，无 DATA RACE
- 协议：Python/Go ArticleResultV2 合同测试通过
- 队列：唯一消费者审计通过
- 数据库：五表并存、replay、conflict、空正文语义测试通过
- PDF/Office：C1/C2 合同与安全门测试通过

## 6. E2E

- B7：一次性隔离 Redis/MySQL，migration 两次，五表并存，result consumer 持久化，replay/conflict/全部状态/v1 共存通过；Docker 残留 0
- B8：本地 httptest 全链，多 hit 一次下载，null 请求数 0，duplicate 四层事件与数据库断言，长正文无截断，canonical 不请求，PDF MIME 拒绝通过；Docker 残留 0

## 7. 未完成范围

- 未覆盖 `crawler:search/SearchPlan` 真实服务全链
- 未部署、未合并、未提交、未迁移现有数据库
- TASK-020/TASK-021/TASK-022 尚未开始

## 8. 残余风险

- Redis List BRPOP 无 ACK、重试、死信、背压
- 数据库瞬时失败可能丢消息
- migration 未获准用于现有数据库
- API 仍读取 legacy 表
- PDF/Office 安全门未接生产
- 文档解析无硬超时和进程隔离
- 原始附件默认不保存
- 当前工作区全部未提交
- 当前检查点不可部署

## 9. 状态

- implementation=completed
- acceptance=PASS
- git_state=UNCOMMITTED
- deployment=BLOCKED
- closure=WAITING_USER_APPROVAL

## 10. TASK-022 进入条件

- TASK-019 实现和总验收完成
- 用户明确批准进入 TASK-022
- 当前代码、依赖、出站路径和 legacy 边界重新只读审计
- 完整路线：TASK-019 → TASK-022 → TASK-021A → TASK-020A → TASK-020B