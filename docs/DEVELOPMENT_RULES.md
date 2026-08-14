# 开发规则

**状态：** 2026-08-14 由 TASK-022A 补充；原 `docs/DEVELOPMENT_RULES.md` 在仓库中缺失，本文件作为项目长期规则入口。D-01 至 D-12 已于 TASK-022A-R 批准冻结；TASK-022B 已实现基础库但尚未接入安全 Transport，当前版本不可部署。

## 1. 出站请求安全规则

1. 所有正式出站 HTTP/HTTPS 请求必须使用共享安全 transport；不得绕过。
2. 共享 transport 必须执行：URL 规范化、DNS 全地址策略、连接固定、每跳重定向校验、代理策略、TLS/SNI/证书一致性、超时与响应/解压预算。
3. 安全拒绝必须 fail closed，不得伪造成功、`extract_failed` 或 v1 错误结果。
4. 本地测试的 loopback 许可必须通过依赖注入实现，不得使用生产配置开关。
5. 日志不得记录凭据、Cookie、Authorization、完整 query、payload 或 DSN。
6. 新加入的任意出站路径（包括 AI/第三方服务）必须先纳入安全合同，再实施。
7. 本规则实施状态以 `docs/OUTBOUND_REQUEST_SECURITY_CONTRACT.md` 为准；未实施前不得宣称生产级 SSRF 防护。

## 2. 当前唯一任务路线

正式执行路线：

```text
TASK-019
→ TASK-022
→ TASK-021A
→ TASK-020A
→ TASK-020B
```

后续路线：

```text
TASK-020B
→ TASK-021B
```

`TASK-019 → TASK-022 → TASK-020` 仅允许作为父任务级简写，不得替代完整执行门禁。旧路线 `TASK-018 → TASK-022 → TASK-020` 已被替代，不得作为当前路线使用。

## 3. 其他项目规则

- 遵循根级 `AGENTS.md` 与本仓库 `AGENTS.md`。
- 最小修改、文档同步、真实测试、敏感信息保护和 Git 授权边界以其为准。

## 4. TASK-022B 基础库边界

- `crawler/security` 与 `go-spider/internal/security` 是当前唯一允许的出站安全纯函数入口。
- 本轮禁止生产模块 import 基础库；接线属于 TASK-022G。
- 新增出站路径实现前必须复用该基础库，不得自行复制规范化、IP 分类或 DNS 验证逻辑。
## 5. TASK-022B-FIX 记录

- Unicode-to-IP 映射必须拒绝。
- authority/port 使用严格词法校验。
- pre-DNS policy gate 在 host/HTTP/port/downgrade 拒绝时不得调用 Resolver。
- Go `OutboundPolicy` 不可变，构造与 getter 均深拷贝。
## 6. TASK-022B-FIX2 记录

- 纯 Unicode 数字型主机外观拒绝。
- IDNA 后整体成为 IP/歧义 IP 时拒绝。
- 普通 IDN 中包含 Unicode 数字不构成拒绝理由。