# ADR-022：Production Outbound Security Configuration Contract（TASK-022E-B）

**状态：** proposed
**日期：** 2026-08-15
**关联：** TASK-022E，ADR-016/017/018/019/020/021 保持 accepted
**decisions：** E-01..E-16 approved
**destructive_change_to_B_model：** NO
**production_wiring：** not_started
**scope：** CONTRACT_SCHEMA_SHARED_FIXTURE_ONLY
**next_task：** TASK-022E-B-R

## 决策

1. 未来生产安全配置使用独立文件 `config/outbound_security.json`；本阶段只冻结路径，不创建生产文件。
2. 使用 policy registry 与站点显式 `outbound_policy_id`；禁止 site 内联安全 override；无默认放行 policy；policy 引用不存在时启动失败。
3. 配置 hostname 只允许规范化小写 ASCII IDNA A-label；loader 不得静默规范化 Unicode 或非 canonical 输入。
4. V1 仅支持 exact hostname，不加入 `allowed_subdomain_roots`，不修改已封板 OutboundPolicy 模型；编译时 `allow_controlled_subdomains=false`。
5. 单个 policy 支持多个 exact hostname。
6. redirect 使用主 `allowed_domains` 集合，不新增独立 redirect allowlist；HTTP→HTTPS 需目标 scheme/host/port 全部被 policy 允许；HTTPS→HTTP 始终拒绝。
7. 每个 policy 显式声明 `allowed_ports`（整数 1–65535，非空/唯一/升序，key 与 `allowed_schemes` 一致）。
8. 配置使用 `allowed_schemes`，仅 `["https"]` 或 `["http","https"]`；编译规则映射到现有 `allowed_http`，不修改现有字段。
9. 仅禁止出站安全字段被环境变量、CLI 或 site 覆盖；基础设施 env（MYSQL_*、Redis 等）不受影响。
10. 拒绝 unknown field、duplicate key/policy/hostname/scheme/port、类型冒充、policy 引用缺失、site 内联 override、非 canonical 顺序、scheme/port key 不一致。
11. 现有 5 站执行一次性显式迁移草案；不从旧 URL 自动生成或扩展 policy，不保留旧回退。
12. 新增配置级共享 fixture；Python/Go 生产 loader 必须真实消费同一配置并各自负责本进程启动验证；E-B 只冻结 fixture。
13. V1 配置与运行时目标均禁止 IP literal；不修改已封板 classify_ip。
14. `config_version` 精确 `"1.0"`；不自动降级；回滚通过 Git。
15. 出站进程启动前完成验证；豁免进程写入 `docs/OUTBOUND_SECURITY_CONFIGURATION.md`。
16. 启动期交叉校验 site.json 静态 URL 与引用 policy；动态运行时 URL 仍需每请求重验。

## 影响

- 新增 `config/outbound_security.schema.json`、`tests/fixtures/outbound_security_config_contract.json` 及 Python/Go 合同 fixture 测试。
- 生产 loader、site.json 迁移与生产客户端接线均未实施。
- 当前版本不可部署；production wiring 仍未开始。
