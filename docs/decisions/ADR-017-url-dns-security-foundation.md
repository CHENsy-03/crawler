# ADR-017：URL、DNS 与 IP 安全基础库（TASK-022B）

**状态：** proposed
**日期：** 2026-08-14
**关联：** TASK-022B，ADR-016 保持 accepted

## 背景

TASK-022B 需要在 Python 与 Go 建立语义一致、可离线测试的出站请求安全基础库，但本轮不接入现有生产 HTTP 请求链。

## 决策

1. 新增 Python `crawler/security` 与 Go `internal/security` 纯函数基础库。
2. URL 规范化使用固定顺序：类型、空串、UTF-8 字节长度、Unicode 空白/控制/格式字符、反斜杠、URL 解析、absolute/scheme、authority、userinfo、host/IDNA/IP literal、port、path/query 百分号编码、规范化 URL 长度。
3. IDNA 使用 UTS #46 lookup profile，transitional=false、STD3=true；Python 使用 `idna==3.18`（已直接声明），Go 使用 `golang.org/x/net/idna v0.52.0`（已存在本地 module cache，本轮提升为直接依赖）。
4. IP 分类使用两端一致、显式可审计的特殊用途 CIDR 表；IPv4-mapped IPv6 先解包并统一按 `mapped_ipv4` 拒绝。
5. DNS 使用可注入 Resolver；IP literal 不调用 Resolver；全部 A/AAAA 地址去重、稳定排序、全部通过后才允许；超过 16 个拒绝。
6. 策略只支持 exact host allowlist；子域匹配默认关闭，公共后缀数据库和受控子域留给 TASK-022E。
7. 固定连接、Host/SNI/证书处理、重定向/代理/资源预算生产实现分别属于 TASK-022C/022D；生产接线属于 TASK-022G。
8. Python/Go 读取同一份 `tests/fixtures/outbound_request_security_contract.json`，不各自维护第二份期望结果。
9. 本轮不读取 config、不创建 `crawler:error` 事件、不连接真实 DNS/Redis/MySQL，不修改现有 HTTP 客户端。

## 影响

- 新增基础库当前没有生产调用方。
- 生产请求链行为不变。
- 当前检查点不可部署。

## TASK-022B-FIX 补充

- Unicode 数字经 IDNA 映射后整体变成 IPv4/IPv6 literal 时必须拒绝，reason 为 `ambiguous_ip_literal`。
- authority/port 使用严格词法校验：端口仅允许 ASCII `[0-9]+`，禁止 `+`、`-`、空白、Unicode 数字；IPv6 bracket 后缀非法统一 `invalid_port`，缺失右 bracket 为 `invalid_url`。
- Policy 判定分两阶段：URL/scheme/HTTP/host/port/downgrade 为 pre-DNS gate，全部通过后才调用 Resolver。
- Go `OutboundPolicy` 改为不可变内部状态，构造时深拷贝，getter 返回深拷贝，零值 fail closed。
## TASK-022B-FIX2 补充

- 不再因 host 中出现任意 Unicode decimal digit 而预拒绝。
- 仅当整个 host 是“纯 Unicode 数字型主机外观”（只含 Unicode/ASCII Nd 数字与 `.`、U+3002、U+FF0E、U+FF61，可选单个 root dot）时，返回 `ambiguous_ip_literal`。
- IDNA 后整体成为 IPv4/IPv6 literal 或歧义 IPv4 表达时，返回 `ambiguous_ip_literal`。
- 普通 IDN 中包含 Unicode 数字（如 `例１.example`、`１２７.example`、`a１２７.example`、`١٢٧.example`）不构成拒绝理由，继续执行 hostname/label 校验。