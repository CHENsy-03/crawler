# ADR-019：Redirect Per-Hop Revalidation, Proxy Disablement and Resource Budget（TASK-022D-1）

**状态：** accepted
**日期：** 2026-08-14
**关联：** TASK-022D，ADR-016/017/018 保持 accepted
**acceptance：** TASK-022D-1-R2 PASS
**implementation_commit：** 228ac0420daaf695f02090661422952b0900d749
**contract_scope：** redirect/proxy/transport-budget pure policy
**production_wiring：** deferred
**runtime_enforcement：** deferred to TASK-022D-2/TASK-022D-3
**next_task：** TASK-022D-2

## 背景

TASK-022B 已提供 URL/DNS/IP/policy 判定，TASK-022C 已提供 PinnedTarget 与数字 IP 连接基础层。TASK-022D-1 需要先把 redirect 逐跳重验、代理禁用和固定资源预算实现为纯决策层，供 TASK-022D-2/022G 接线使用。

## 决策

1. 资源预算使用不可变整数模型：统一 ms 与 bytes；公共预算固定为 DNS/connect/TLS 5000ms、response header 10000ms、read idle 15000ms、request body 1048576 bytes、response headers 262144 bytes、redirects 3、global active 20、per-host active 5、per-host idle 2。
2. 请求类别固定为 probe/search/detail；total deadline 分别为 30000/30000/60000 ms，response body 上限分别为 1048576/8388608/20971520 bytes。
3. 预算限制为包含式；未知 profile、bool 冒充 int、负数、零值非法位置和首次超限单位均稳定拒绝；每跳阶段 timeout 必须受剩余 total deadline 约束。
4. redirect planner 是纯决策层：原始请求 hop=0，第 1–3 次 redirect 允许重验，第 4 次返回 `redirect_limit_exceeded`；Location 缺失、空或语法非法分别返回 `redirect_location_missing`、`redirect_location_invalid`。
5. 相对 Location 先基于当前规范化 URL 解析；每一跳重新执行 URL 规范化、scheme、exact host allowlist、port、DNS 全地址验证、IP 分类、HTTPS→HTTP 降级和 redirect host 检查，并生成全新 PolicyDecision 与 PinnedTarget。
6. 禁止复用上一跳 DNS 结果、IP 地址或 PinnedTarget；任一失败 fail closed，不回退旧 target；不自动执行网络请求，不改变 method/body，不处理 Cookie/Auth，fragment 不进入请求目标，userinfo 继续拒绝。
7. V1 代理固定禁用：安全包不读取环境代理；`None`/空配置允许，任意非空 http/https/socks/PAC 值返回稳定 `proxy_not_allowed`。
8. Python 与 Go 读取同一份 `tests/fixtures/outbound_transport_policy_contract.json`（60 cases：budget 26、redirect 28、proxy 6），不维护第二份预期。

## 影响

- 新增 Python `crawler/security/transport_budget.py`、`redirect_policy.py` 与 Go `transport_budget.go`、`redirect_policy.go`。
- 本轮不实现实际响应读取、流式计数、idle timer、并发限流或生产接线；这些属于 TASK-022D-2/022G。
- 当前版本不可部署。

## TASK-022D-1-FIX 补充

- Location 为 None、精确空字符串或仅 Unicode 空白时返回 `redirect_location_missing`；非字符串、前后空白、Cc/Cf 控制字符或 NUL 返回 `redirect_location_invalid`，且不调用 Resolver。
- scheme-relative `//host/path` 继承当前规范化 URL 的 scheme 解析为绝对 URL，再完整执行 TASK-022B/C 重验；Python 与 Go 结果一致，不允许绕过 host/port/downgrade 策略。
- `remaining_deadline(total, total)=0` 仅表示总预算耗尽；`capped_stage_timeout` 在 remaining=0 时必须返回 `total_timeout_exceeded`，不得返回 0 表示无超时；remaining=1 返回 1ms，stage=remaining 返回 stage。
- 共享 fixture 扩展至 60 case；Python/Go harness 维护已执行 ID 集合并断言与 fixture ID 集合完全相同，未知 action 直接失败；Go 对 JSON bool 输入在 harness 边界明确断言类型拒绝。
- ADR-019 接受的是冻结策略和纯合同；实际响应流式读取、header/body 限制、read-idle timer、并发限流和生产 Transport 组合尚未实现；不得声称资源预算已在生产请求链强制执行。
