# ADR-020：Bounded I/O and Concurrency Runtime（TASK-022D-2）

**状态：** accepted
**日期：** 2026-08-15
**关联：** TASK-022D，ADR-016/017/018/019 保持 accepted
**acceptance：** TASK-022D-2-R3 PASS
**implementation_commit：** 55ef24164536946cea3cdecfc37845002ec5f398
**production_wiring：** deferred
**transport_adapter：** deferred to TASK-022D-3
**wire_header_enforcement：** deferred to TASK-022D-3
**per_host_idle_pool：** deferred to TASK-022D-3
**next_task：** TASK-022D-3

## 背景

TASK-022D-1 已封板 transport budget、redirect 逐跳策略和代理禁用合同。TASK-022D-2 在 D1 之上实现运行时基础原语：请求体/响应头/响应体大小门、deadline-aware 有界读取、read-idle 与 total deadline 联合约束，以及全局/单 hostname 活动连接限流。本轮不接入生产 HTTP 链。

## 决策

1. D2 只从 D1 `TransportBudget` 读取固定限制，不复制或重新定义预算常量；未知 profile fail closed，bool 不得冒充整数，调用方不能提高冻结上限。
2. 大小门为包含式：请求体 <= 1048576 bytes、响应头 <= 262144 bytes、probe/search/detail 响应体分别 <= 1048576/8388608/20971520 bytes；超 1 单位即拒绝。
3. Content-Length 仅用于预检；缺失时继续实际流式计数，非法/负数/冲突返回 `invalid_content_length`，Content-Length 小于实际正文时仍由实际计数拒绝。
4. 有界读取每次最多请求 64 KiB，最后使用“剩余允许字节数 + 1”探测；正文等于上限成功，超 1 字节返回 `response_body_too_large`，失败不返回可作完整正文的 partial body。
5. D2 定义 deadline-aware reader 合同：每次 `read(max_bytes, timeout_ms)`；普通阻塞 reader 不通过后台线程包裹伪造超时。实际 socket/HTTP 流适配由 D3 完成。
6. 每次读取前计算 total remaining；remaining=0 返回 `total_timeout_exceeded`；本次 timeout 为 `min(read_idle_timeout, total_remaining)`。
7. 恰好同时到达 idle 与 total deadline 时，两端统一优先返回 `total_timeout_exceeded`；正数 chunk 到达后 read-idle 窗口重新开始，total deadline 不重置；timeout 后不得继续读取。
8. 失败分类固定：`read_idle_timeout`、`total_timeout_exceeded`、`read_failed`、`reader_not_deadline_capable`、`read_no_progress`；错误不包含正文、URL、Cookie、Authorization 或连接地址。
9. 并发限流为 fail-fast：全局 active <= 20，同一规范化 hostname active <= 5；host key 使用小写 ASCII hostname/IP literal 规范化文本，端口不同仍共享同一 host bucket。
10. `release` 幂等，double release 不产生负计数或额外额度；host count 归零后删除 host entry；D3 必须创建并共享一个进程级 limiter 实例。
11. per-host idle connection pool=2 属于 D3 实际连接池配置；D2 不伪装已执行 idle pool 限制。
12. 实际响应流式读取、header/body wire 计数、idle timer、并发限流与生产 Transport 组合由 D3 接线；`crawler:error` 和任务闭合留给 TASK-022G/TASK-021A。

## 影响

- 新增 Python `bounded_io.py`、`concurrency_limiter.py` 与 Go `bounded_io.go`、`concurrency_limiter.go`。
- 新增共享 fixture `tests/fixtures/outbound_runtime_limits_contract.json`（105 cases：size 40、read 26、concurrency 39）。
- 本轮不接入生产 HTTP 请求链；不得声称生产请求已受保护。

## TASK-022D-2-FIX 补充

- Python `deadline_capable=True` 只是 D3 可信适配器的接口契约标记，不能证明任意第三方 reader 可中断；D3 只能传入项目控制的 socket/HTTP 适配器，并把 timeout 落实到底层 socket/read deadline。
- D2 不会为普通阻塞 read 创建后台线程；真正的阻塞中断能力必须在 TASK-022D-3 本地 Transport 测试中验证。
- Content-Length 仅接受 ASCII 十进制、HTTP OWS 与重复相同字段值；float 一律拒绝；Go JSON 解码使用 `json.Number` 保持整数语义。
- clock 采样统一校验为单调不减的非负整数，非法/倒退返回 `invalid_clock`；read 返回后先复核 deadline 再写入 buffer。
- Lease 只能由 `ConcurrencyLimiter.acquire()` 签发；复制、深复制、伪造或跨 Limiter release 均不能改变计数。
- Lease release 只信任 Limiter registry 中的精确对象和 canonical host；Lease 展示属性不是授权数据源。
- 空重复 Content-Length 集合属于非法 header 表示；DNS label 首尾 hyphen 拒绝。
