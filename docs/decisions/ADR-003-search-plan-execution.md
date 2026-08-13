# ADR-003：SearchPlan Python 进程内执行契约

**适用范围：** workspace/crawler（信息采集平台）

**状态：** Accepted

**日期：** 2026-08-12

**阻断说明：** TASK-017E implementation blocked until upstream selector generation is compliant.

## 背景

当前 v2 Worker 已能生成或读取 SearchPlan，但 `run_worker()` 只记录日志并继续处理下一条任务。TASK-017E 需要确定 SearchPlan 如何进入 Python 搜索执行链。

当前 `PlanBuilder` 生成的 `SearchSelectors` 全部为空，现有插件以 `site_cfg` 为配置来源，不能直接以 SearchPlan 为唯一配置来源执行。

## 决策

1. SearchPlan 是 Python Search Worker 内部阶段产物，只在同一 Python Worker 进程内交接。
2. Python 负责生成并执行 SearchPlan。
3. Go 不解析、不执行、不消费 SearchPlan。
4. 不新增 SearchPlan Redis 结果消息。
5. 不新增计划队列、执行队列或 ACK 队列。
6. 不复用 `crawler:result` 承载 SearchPlan。
7. SearchPlanCache 仅为内部优化缓存，不是结果交付通道。
8. 执行适配器冻结路径为 `crawler/search/plan_executor.py`。
9. 冻结入口为 `execute_search_plan(plan, keywords, *, fetcher)`。
10. 只有 `ready` 和 `active` 状态可执行。
11. 只支持 `html_form` 和 `json_api` 策略。
12. 只支持 `{keyword}`、`{page}`、`{page_size}` 占位符。
13. GET 使用 query params；POST 按策略使用 form body 或 JSON body。
14. 分页从 1 开始，按 `max_pages` 递增，失败或空页终止。
15. HTML 结果解析使用 CSS selector；JSON 结果解析使用 RFC 6901 JSON Pointer。
16. 候选 URL 必须规范化并满足 scope 约束。
17. 成功候选映射为既有 `URLMessage`，发布到 `crawler:url`。
18. 对外错误统一复用 `SEARCH_FAILED`，不新增跨语言错误码。
19. 禁止启发式解析、猜测字段或回退 legacy plugin。
20. 当前空 selectors 是上游阻断，必须在执行器实现前由独立任务修复。

## 不采用的方案

- SearchPlan 发布到 Redis：违反 Python 进程内执行边界，且 Go 不消费 SearchPlan。
- 回退 legacy `plugin_search()`：仍依赖 `site_cfg`，不是 SearchPlan 唯一配置来源。
- 空 selector 下抓取所有链接：属于启发式解析，可能发布越界 URL。
- 临时新增跨语言错误码：会改变 Python/Go 错误契约。
- 在执行器中重新运行 Analyzer/Builder：职责重复，且无法解决 selector 缺失证据。

## 影响

- 后续 TASK-017E 只能实现执行器与 Worker 内部闭环，不能扩大协议范围。
- 上游必须先让 Analyzer/PlanBuilder 产生符合契约的 `result_item/title/url`。
- 文档必须保持“TASK-017E 尚未实现”的事实，不得宣称已经可执行。
