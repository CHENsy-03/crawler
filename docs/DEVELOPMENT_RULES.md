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
## 7. TASK-022C Pinned Transport 边界

- 生产出站连接只允许使用 PinnedTarget 中已验证的数字 IP。
- HTTPS ServerName 必须使用规范化 hostname，不得使用连接 IP。
- 禁止通过公开 API/config/env/CLI/API 参数启用 loopback 测试许可。
- 新 Pinned Transport 未接入生产前，不得替换现有 HTTP 客户端。
## 8. TASK-022C-FIX 记录

- 测试专用 loopback/private 构造器必须只存在于 `tests/` 或 `*_test.go`。
- `crawler/` 与 Go 非测试生产 `.go` 不得包含测试构造器。
- 禁止以“下划线开头”作为测试旁路安全边界。
## 9. TASK-022C-FIX2 记录

- Python `PinnedTarget` 不得公开可伪造字段构造器；只有正式 builder 能签发。
- `connect_pinned` 必须在创建 socket 前验证来源与结构；未签发对象返回 `invalid_pinned_target`。
- 测试 loopback 只能通过测试侧路由转发，不能进入生产 target 地址集合。

## 10. 封板哈希规则（TASK-022D-FIX）

- 未提交阶段：工作区 hash 只能作为临时诊断证据；若启用 text filter/core.autocrlf，工作区字节 hash 不得直接作为最终 seal hash。
- 暂存阶段：应从 Git index 中的 blob 计算候选 seal hash；staged diff 通过后，index blob 是即将提交内容的权威输入。
- 提交后：必须从 implementation commit tree/blob 重新计算最终 aggregate；commit blob aggregate 是恢复、审计、封板的唯一权威值。
- 文本过滤：必须记录 working-tree encoding/line-ending 与 blob encoding/line-ending；CRLF/LF 差异不得伪装成内容一致，也不得因此强制仓库存储 CRLF；可通过规范化比较证明语义差异仅为行尾。
- 文档 seal 提交修改状态文档后：验证实现时必须读取 implementation commit，不得用当前 HEAD 工作区的状态文档重新计算旧实现 aggregate。

## 11. TASK-022E-B 出站安全配置规则

- 生产安全配置入口固定为 `config/outbound_security.json`；本阶段只冻结路径，不创建生产文件。
- 配置 hostname 只允许规范化小写 ASCII IDNA A-label，且必须至少两个 DNS label；单标签 localhost/example 返回 config_invalid_hostname；禁止 root dot、scheme、userinfo、path/query/fragment、port、通配符与 IP literal。
- V1 仅 exact hostname，不使用 `allowed_subdomain_roots`，不修改已封板 OutboundPolicy 模型。
- redirect 使用主 `allowed_domains` 集合，不新增独立 redirect allowlist。
- 仅禁止出站安全字段被环境变量、CLI 或 site 覆盖；基础设施 env（MYSQL_*、Redis 等）不受影响。
- 配置级共享 fixture 必须被 Python/Go 生产 loader 真实消费；E-B 只冻结 fixture，生产 loader 留给 E-C。
