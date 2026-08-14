# ADR-018：Pinned Address Transport（TASK-022C）

**状态：** proposed
**日期：** 2026-08-14
**关联：** TASK-022C，ADR-016/017 保持 accepted

## 背景

TASK-022B 已建立 URL 规范化、DNS 全地址验证和策略判定。TASK-022C 需要把已验证地址集合转换为不可变 PinnedTarget，并建立数字 IP 连接、Host header 和 TLS SNI/证书校验基础层，但不接入生产 HTTP 客户端。

## 决策

1. 新增 Python `PinnedTarget` 与 Go `PinnedTarget`，只保存规范化 host、有效端口、Host header、server_name、已验证地址和策略身份；不保存原始 URL、userinfo、fragment、Cookie 或 header。
2. 地址集合必须来自已允许的 PolicyDecision，重新执行策略与地址不变量检查；空、超过 16 个、非 global、伪造 allowed 均拒绝。
3. TCP 连接只使用 validated_addresses 中的数字 IP 与 PinnedTarget.port，不把 hostname 传给系统 resolver。
4. HTTP Host header 使用规范化 hostname 和有效端口；调用方只能提供空值或完全一致值，否则 `host_header_mismatch`。
5. HTTPS ServerName 固定为 normalized_host；TLS 使用系统根或显式测试 Root CA，`InsecureSkipVerify=false`、证书链与 hostname/IP SAN 正常校验。
6. 每个 PinnedTarget 绑定单一 authority；scheme、host、port 任一不匹配都在连接前拒绝，不发起 socket。
7. 本地 loopback 连接只通过测试代码内部构造 `_pinned_target_for_test` / `newPinnedTargetForTest` 实现，生产公开 API 不提供 allow_loopback/test_mode/skip_policy/insecure 参数。
8. Python 使用 Fake SSLContext 验证 server_hostname 与安全上下文；真实 TLS 证书 E2E 由 Go 本地测试完成，Python 真实 TLS E2E 留给 TASK-022H。
9. 不实现 DNS cache、代理、redirect、body 读取、连接池或生产接线；这些属于 TASK-022D/G。

## 影响

- 新增 Python `crawler/security/pinned_connection.py`、`tls_policy.py` 与 Go `pinned_target.go`、`pinned_dialer.go`、`pinned_transport.go`。
- 当前没有生产调用方。
- 当前检查点不可部署。

## TASK-022C-FIX 补充

- Python `_pinned_target_for_test` 已从生产 `pinned_connection.py` 删除，只存在于 `tests/test_pinned_connection.py`。
- Go `newPinnedTargetForTest` 已从生产 `pinned_target.go` 删除，只存在于 `pinned_test_helpers_test.go` 等 `*_test.go` 文件。
- 生产代码不再包含任何 loopback/private 测试构造器；正式 `NewPinnedTarget`/`build_pinned_target` 继续拒绝非 global 地址。
## TASK-022C-FIX2 补充

- Python `PinnedTarget` 关闭普通字段构造，仅 `build_pinned_target` 可签发。
- `connect_pinned` 在 socket 前验证来源标记与结构不变量；未签发对象返回 `invalid_pinned_target`。
- 测试本地 listener 使用正式 builder 签发 global target，并在测试代码内部把实际连接路由到 127.0.0.1 随机端口。
## TASK-022C-FIX3 补充

- 删除模块级 `_SOURCE_TOKEN`，不再使用 object identity 作为签发证明。
- 签发密钥在模块初始化工厂闭包内由 `secrets.token_bytes(32)` 生成一次，不写入模块属性、实例、配置、日志或文档。
- 正式 `build_pinned_target` 对固定字段顺序 canonical JSON array 计算 HMAC-SHA-256，结果保存为 `PinnedTarget._integrity_tag`（repr=False、compare=False）。
- canonical payload 固定包含 `crawler.pinned-target.v1`、scheme、normalized_host、port、authority、host_header、server_name、validated_addresses 有序列表、is_ip_literal、policy_identity。
- `connect_pinned` 在 socket 前重新计算 HMAC 并使用 `hmac.compare_digest` 验证，再执行既有类型、地址、global、authority、host_header、server_name 结构复核。
- 复制完全相同、不可变的已签发 capability 不扩大权限；修改任何签名内容都会使 HMAC 失效并返回 `invalid_pinned_target`。

## TASK-022C-FIX4 补充

- `connect_pinned`、`connect_with_authority`、`prepare_request_host_header`、`validate_request_authority` 均使用 `type(target) is PinnedTarget` 精确类型判定，拒绝子类、duck-typed 和 `__class__` 伪装对象。
- `_ensure_signed_target` 从精确类型对象一次性捕获全部安全字段到内部不可变快照；HMAC、结构/global 复核与 dial/fallback 全部只使用该快照。
- 原始 target 在快照捕获后不再被读取，消除验证与拨号之间的动态 property TOCTOU。
