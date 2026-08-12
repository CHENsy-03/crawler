# ADR-004：Analyzer 受控搜索探测契约

**适用范围：** workspace/crawler（信息采集平台）

**状态：** Accepted

**日期：** 2026-08-12

**阻断说明：** TASK-017E remains blocked until TASK-017E-R4 and TASK-017E-R5 are implemented.

## 背景

TASK-017E-R2 确认当前 Analyzer 输入只有入口页表单和 CMS/script 签名，没有搜索结果 DOM 或 JSON 响应 schema，无法生成符合 TASK-017E-R1 契约的 selectors。

TASK-017E-R3 需要冻结受控探测契约，使后续任务能够在安全、限量、可注入 HTTP 的边界内观察响应结构。

## 决策

1. 受控探测是候选发现后的独立 Python 内部阶段，不属于 SearchPlan 正式执行。
2. 受控探测不发布搜索结果 URL，不进入 legacy `plugin_search()`，不写入 Redis。
3. Go 不解析、不执行、不消费探测结果。
4. 正式模块路径冻结为 `crawler/site/search_probe.py`。
5. 正式入口冻结为 `probe_search_candidate(candidate, keywords, *, fetcher, policy) -> SearchProbeResult`。
6. 只有具备完整静态请求形状证据的候选可探测。
7. 探测只使用严格解码后的 `tuple[str, ...]`，不扩展、不重排关键词。
8. 请求预算为：最多 3 个候选、每候选 2 个关键词、单次分析 6 个请求、第一页、并发 1、重试 0、重定向 3 跳、2 MiB、10 秒。
9. GET 只允许 query params；POST 只允许 form-urlencoded 或 JSON object body。
10. 禁止复制 Cookie、Authorization、Token、CSRF、签名、session、api_key 等敏感字段。
11. 所有 endpoint 和每一跳 redirect 必须执行 DNS/IP/端口/SSRF 校验。
12. 响应只接受对应策略的 2xx Content-Type，达到上限立即终止。
13. HTML selector 证据必须由至少两个结构一致的结果项验证，禁止全页 `a[href]` 和位置猜测。
14. JSON selector 证据必须使用 RFC 6901 JSON Pointer，禁止 JSONPath、通配符和字段名猜测。
15. selector 证据必须与产生它的同一个候选绑定，禁止跨候选拼接。
16. 探测响应只在内存中短暂存在，不缓存、不落盘、不写 Redis。
17. 探测失败默认 fail-closed，对外错误复用 `SEARCH_FAILED` 和 `No executable search plan`。
18. 当前 HTML/JSON 输入缺口必须由 R4/R5 补齐，不得在执行器中猜测。
19. 当前 HTTP 安全能力缺口必须先由 R4 修复。
20. TASK-017E 仍处于 blocked，直到 R5 能生成符合 R1 契约的 selectors。

## 不采用的方案

- 在 SiteAnalyzer 内隐式发送不限量请求。
- 直接把探测并入 `plan_executor.py`。
- 让 PlanBuilder 自己访问网络。
- 把探测响应写入 Redis。
- 缓存完整 HTML/JSON。
- 执行 JavaScript。
- 使用浏览器自动化绕过动态页面。
- 携带 Cookie、Authorization 或 CSRF token。
- 从 CMS 名称猜测 API request body。
- 空 selector 时抓取所有链接。
- 通过 legacy plugin 补齐 selector。
- 新增跨语言 Probe 消息或错误码。

## 影响

- 后续 R4 必须先实现安全 HTTP 基础、候选请求形状和完整 fake 测试。
- 后续 R5 才能基于受控探测响应生成 selectors。
- TASK-017E 执行器只有在 R5 产出符合 R1 契约的 selectors 后才能实现。
- 文档不得宣称 R4、R5 或 TASK-017E 已实现。
