# ADR-007：详情提取与详情后相关性 v2

**状态：** accepted

**日期：** 2026-08-13

**关联：** TASK-019B-4，TASK-019B-1 已完成

## 背景

TASK-019B-1 已冻结 `ArticleResultV2` 协议，但 Python 详情处理仍没有独立的 v2 链。TASK-019B-4 需要接通 `HTMLMessageV2 → 正文提取 → 详情后重评分 → ArticleResultV2 → crawler:result`，同时保持 legacy/v1 Parser 行为不变。

## 决策

1. `crawler:html` 保持唯一 Python BRPOP 消费者；缺版本与 `1.0` 走原 `_process_message()`，`2.0` 走独立 `_process_v2_message()`。
2. v2 使用 B1 `HTMLMessageV2` 严格解码；显式 null、非字符串版本、未知版本、未知字段、非法 URL/MIME、非对象 JSON 均拒绝，不回退 v1。
3. v2 站点配置按 `final_url.hostname` 规范化后精确匹配 `config/site.json`；未命中使用通用提取，不报 unknown site。
4. 新增 `crawler/detail/extraction_v2.py`，输出 `DetailExtractionResult`，包含 `title/title_source/publish_date/canonical_url/content/extraction_method`。
5. 正文提取按实际成功策略记录：`site_selector → cms_rule → ai（仅显式启用）→ density → fallback → none`；v2 不应用 3000/10000 字截断。
6. 标题顺序为站点/CMS规则、h1、og:title、html title、消息标题回退；发布日期详情页优先，消息 `published_at` 规范化回退；canonical 只读取 `<link rel="canonical">` 的合法绝对 URL。
7. summary 优先使用纯文本化 snippet，最多 500 Unicode 字符；snippet 为空时使用正文前 500 字符，content 来源摘要不重复计分。
8. 新增 `crawler/detail/relevance_v2.py` 纯函数评分器，读取 `title_weight/body_weight/url_weight/threshold`，证据按 original/expanded 与 title/summary/content/url 顺序稳定输出。
9. accepted 必须由详情页标题或详情正文的 original evidence 达到阈值；搜索标题、search snippet、expanded 词或 URL 单独命中最高为 review_required。
10. `extract_failed/review_required/irrelevant/accepted` 均生成并发布 ArticleResultV2；`unsupported_format` 保留给后续 PDF/Office 安全回归。
11. 发布前调用 B1 `ArticleResultV2` 严格验证；发布目标固定为 `crawler:result`。
12. 本轮不写 MySQL/DuckDB/文件，不保存原始 HTML；原始 HTML 仅存在于消息与进程内存。
13. B3 Windows Race Detector 已正式通过；B4 不修改 Go 代码，也不重复执行 Race Detector。
14. 当前检查点不可部署；Go 持久化消费者与数据库合同等待 TASK-019B-5。

## 不采用的方案

- 在 v2 中继续使用旧 `score_article()`：无法区分 original/expanded、详情标题来源和 summary 重复计分。
- 无条件以 HTML `<title>` 覆盖文章 `<h1>`：会丢失详情页结构化标题。
- 对 v2 正文继续使用 legacy `max_detail_chars=3000`：不符合完整正文输出要求。
- 未命中站点配置时报 unknown site 并停止：会阻断未配置站点的通用处理。
- 在 B4 接入数据库或任务结束合同：超出本轮范围。

## 影响

- Python v2 详情链可发布严格校验的 ArticleResultV2 到 `crawler:result`。
- legacy/v1 Parser、3000 字截断和 v1 ErrorMessage 行为保持不变。
- 后续 TASK-019B-5 只负责固化 MySQL 增量迁移与 Go 持久化合同。

## TASK-019B-4C 退役记录

- `parser/redis_worker.py` 为历史入口，已于 TASK-019B-4C 退役并删除。
- 退役原因：避免与 `workers/parser_worker.py` 竞争 `crawler:html`，旧入口不支持 v2 严格分流且直接写本地 JSON。
- 唯一正式 Python 消费者为 `workers/parser_worker.py`；legacy/v1 与 v2 行为保持不变。

## TASK-019B-4D 退役记录

- `api/server.py` 内联 Redis Parser 已于 TASK-019B-4D 退役。
- 已移除 `startup_parser_worker()`、`PARSER_WORKER_ENABLED`、`_run_parser_worker()`、后台线程和 `crawler:html` BRPOP。
- `api/server.py` 只承担 HTTP API；`/parse` 保持同步 HTTP 解析，不消费 Redis 队列。
- 全仓唯一正式 `crawler:html` Python 消费者为 `workers/parser_worker.py`。