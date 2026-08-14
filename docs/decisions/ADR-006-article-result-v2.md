# ADR-006：ArticleResult v2 协议合同

**状态：** accepted

**日期：** 2026-08-13

**关联：** TASK-019B-1，TASK-018 已完成

## 背景

TASK-018 已交付统一 Search Adapter 执行链，但搜索命中和后续文章处理仍缺少版本化、严格校验的 v2 传输契约。现有 v1 `URLMessage/HTMLMessage/ResultMessage` 使用 `site/keyword`，无法承载 `hit_id/plan_id/original_query/query_term` 等结构化上下文，也不能表达多关键词命中来源。

## 决策

1. 新增 `protocol_version=2.0` 的 ArticleResult v2 消息族：
   - `URLMessageV2`，`type=url`
   - `HTMLMessageV2`，`type=html`
   - `ArticleResultV2`，`type=article_result`
2. 公共信封统一为 `protocol_version、task_id、message_id、timestamp、type`。
3. 按 `protocol_version + type` 显式分流，禁止根据字段猜测版本。
4. 保留 v1 消息、fixture 和运行行为完全不变。
5. 本轮只固化协议模型、共享 fixture 和双端契约测试，不接入 Redis 生产消费，不修改 Parser/Worker/数据库。
6. `matched_evidence` 必须为数组，空集合输出 `[]`，不得输出 `null`。
7. `ArticleResultV2.status` 冻结为 `accepted/review_required/irrelevant/extract_failed/unsupported_format`。
8. `ArticleResultV2.extraction_method` 冻结为 `site_selector/cms_rule/ai/density/fallback/pdf/docx/xlsx/none`。
9. `score` 必须是非负整数，JSON boolean 不算整数。
10. 正文非空时，`content_hash` 必须是正文 UTF-8 字节的 SHA-256 小写十六进制；正文为空时哈希必须为空。
11. `canonical_url` 可为空；非空时必须是绝对 HTTP/HTTPS URL。
12. 显式 `null`、未知字段、非法 URL、非法状态、非法哈希、非法 score 和非法 evidence 在 Go/Python 两端一致拒绝。
13. 新模型不定义数据库持久化字段；`HTMLMessageV2.html` 只作为队列传输内容。

## 共享证据

- 共享 fixture：`tests/fixtures/article_result_v2_contract.json`
- Python 契约测试：`tests/test_article_result_v2.py`
- Go 契约测试：`go-spider/internal/protocol/article_result_v2_test.go`

## 不采用的方案

- 修改 v1 消息以承载 v2 字段：会破坏既有运行契约。
- 复用 v1 `ResultMessage` 并在运行时猜测版本：违反显式版本分流。
- 将 `HTMLMessageV2.html` 定义为数据库持久化字段：队列传输与存储职责应分离。
- 在 TASK-019B-1 接入生产队列：超出本轮合同固化范围。

## 影响

- 后续 TASK-019B-2 可在不修改 v1 的前提下接通 `SearchHit → URLMessageV2`。
- 后续 HTML/Article 队列生产消费仍须等待对应实施任务。
- v1 协议继续保持不变。
