# ADR-016：出站请求安全边界（TASK-022A-R 已接受）

**状态：** accepted
**日期：** 2026-08-14
**关联：** TASK-022A-R，ADR-004/005 保持有效

## 背景

当前生产出站请求分散在 Python requests/urllib3 与 Go Resty 两条链路上。Go 下载链没有私网/IP/域名/重定向/响应体策略，Python legacy 链也没有统一安全 transport。TASK-022A 完成只读路径清单、威胁模型和依赖 API 核实后，用户已批准 D-01 至 D-12。

## 决策

1. 所有正式出站 HTTP/HTTPS 路径共享同一个安全 transport；Probe、Adapter、Worker、redirect、proxy、legacy/v1 不得旁路。
2. 生产默认拒绝非公网可路由地址；V1 不提供私网例外开关。
3. 出站目标必须属于管理员站点配置产生的规范化允许主机集合；默认精确 hostname，子域默认关闭。
4. 仅允许 http/https；允许管理员配置公网主机使用 HTTP；禁止 HTTPS→HTTP 降级。
5. 默认端口 80/443；非默认端口必须管理员精确列出。
6. Python/Go 生产 Transport 忽略环境代理；TASK-022 V1 不支持显式代理。
7. 每次 authority/redirect 解析并验证全部 A/AAAA；最多 16 个；连接固定到已验证地址，Host/SNI/证书使用规范化 hostname。
8. redirect 最多 3 跳，每跳完整重验；不向新 authority 转发敏感 header。
9. 资源预算按 D-08 硬上限执行；超限整体拒绝。
10. v2 安全拒绝采用 `crawler:error` 上的独立 v2 出站失败事件族，不伪装 extract_failed/irrelevant/v1 ErrorMessage；TASK-022G 生产事件，TASK-021A 消费并闭合任务。
11. legacy/v1 必须接入相同安全 Transport，安全规则优先，不保留旁路。
12. 本地测试 loopback 通过 resolver/address policy/dialer/Transport 注入，不得使用生产开关。
13. TASK-022 期间 AI/第三方外部提取保持禁用；未来启用必须单独 ADR 和固定 endpoint allowlist。
14. canonical 只作为元数据，不主动访问；PDF/Office 安全门保持不接生产链。

## 实施状态

- implementation=NOT_STARTED
- TASK-022B=NOT_STARTED
- 当前生产路径仍存在审计报告列出的风险。
- 当前版本不可部署。
- 本 ADR 接受的是合同；后续实现仍需逐阶段验证。
