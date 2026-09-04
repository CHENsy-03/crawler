# 通用型爬虫测试策略

本文定义完整产品测试目标。最新记录的组件测试基线为：Python 1115 passed、7 skipped；Go 全包 PASS；`go vet` PASS；`go mod verify` PASS。该基线证明底层组件状态，不等于产品 E2E 完成。

## 1. 测试金字塔

| 层级 | 目标 | 工具 |
|---|---|---|
| Unit | 纯函数、解析、状态机、策略 | pytest、Go test |
| Component | 模块间最小组合 | pytest、Go test、contract tests |
| Contract | Python/Go 共享协议 | fixture 双端 contract tests |
| Integration | Redis/MySQL/Worker 组合 | 隔离 Compose E2E |
| Frontend | 页面、交互、无障碍 | Vitest、React Testing Library、Playwright |
| Canary | 真实站点受控验证 | 20 个代表性站点 |
| Security/Performance | SSRF、限流、性能 | 专用 fixture 和基准环境 |
| Release | 发布门禁和回滚 | CI gates、backup restore、migration |

### 1.1 正式测试矩阵

| 类别 | 测试范围 | 工具 | 环境 | 数据来源 | 当前状态 | 通过条件 | 是否阻塞发布 |
|---|---|---|---|---|---|---|---|
| Python | 单元/集成、解析、评分、去重、Worker、OSEC | pytest | 本地/隔离 | fixture | CURRENT_PARTIAL | 全部关键测试 PASS，无未批准 skip | 是 |
| Go | 单元/集成、协议、存储、安全、Worker | go test、go vet、go mod verify | 本地/隔离 | fixture/fake resolver | CURRENT_PARTIAL | 全包 PASS、vet PASS、modules verified | 是 |
| Frontend | 路由、组件、SSE/polling、无障碍 | Vitest、RTL、Playwright | 隔离浏览器 | mock/contract fixture | NOT_STARTED | 关键路径 PASS、WCAG 冒烟 PASS | 是 |
| Contract | API/消息/OpenAPI 契约 | Go/Python contract tests | 本地/隔离 | 共享 fixture | CURRENT_PARTIAL | 双端一致、无漂移 | 是 |
| E2E | Redis/MySQL/Worker/API 组合 | 隔离 Compose | 一次性容器 | 隔离测试数据 | CURRENT_PARTIAL | 端到端链路 PASS，无残留资源 | 是 |
| Canary | 20 个代表性真实站点 | 受控 canary runner | 独立 canary 环境 | 独立授权站点 | NOT_STARTED | 达标并保存每站证据 | 是 |
| Performance | 首屏/API/创建任务/SSE | 独立基准工具 | 性能环境 | 合成数据 | NOT_VERIFIED | 达到 SLA | 是 |
| Security | SSRF/附件/认证/OSEC/fail-closed | 安全 fixture/专项测试 | 隔离 | contract fixtures | CURRENT_PARTIAL | 无 P0/P1，loader fail-closed PASS | 是 |

## 2. Python 测试

- Python unit/integration 默认无网络。
- fixture 覆盖站点发现、TRS/JPAAS/HTML/JSON、正文提取、文档安全、评分、去重、队列协议和 OSEC。
- 运行命令：`python -m pytest tests -q`。
- 禁止 pytest cache 进入仓库；使用环境变量禁用 pyc 写入。

## 3. Go 测试

- Go unit/integration 使用 `go test ./...`，默认无网络。
- 使用 fake resolver、fixture 和隔离 Redis/MySQL 环境。
- `go vet ./...` 和 `go mod verify` 为门禁。
- MySQL v2、Redis protocol、outbound security、result consumer 均有对应测试。

## 4. API Contract

- OpenAPI 是后续外部 API 权威。
- Go/Python 共享 fixture 进行版本化协议测试。
- API contract 测试覆盖 `/api/v1`、错误模型、分页、幂等、SSE、CSRF 和认证。
- API 契约变更必须同步 fixture 和前端 generated types。

## 5. Frontend 测试

- Vitest：纯函数、i18n、Query Key、store/state 逻辑。
- React Testing Library：组件渲染、表单、错误/empty/loading/success 状态。
- Playwright：关键用户路径、SSE/polling 降级、WCAG 冒烟。
- 浏览器矩阵：Chrome/Edge 最近两个稳定版；Firefox 冒烟。

## 6. Redis/MySQL 集成

- 使用一次性隔离 Compose project、随机端口和随机密码。
- 测试结束必须清理容器、网络和卷残留。
- 覆盖 consumer group、pending reclaim、outbox dispatcher、dead-letter、幂等入库。
- MySQL migration 测试包含正向执行和回滚。
- 状态机测试必须断言 FAILED/PARTIAL_SUCCEEDED 等终态不返回非终态。
- 重试测试必须断言创建新 CrawlTask 且记录 retry_of_task_id，原任务终态不变。
- CrawlTask 阶段测试不得包含 EXPORT；导出由独立 ExportJob 生命周期覆盖。

## 7. Fixture 管理

- fixture 是 contract/security 测试的冻结输入。
- fixture 变更必须显式记录，不静默修改。
- site discovery fixture 区分真实站点的静态样本，不依赖实时网络。
- 安全 fixture 用于 SSRF、redirect、URL/DNS/IP、HTTP framing、文档格式和 config contract。

## 8. 20 站 Canary

- 上线前至少覆盖 20 个代表性站点。
- 构成：TRS=5、JPAAS=5、静态 HTML=5、公开 JSON API=3、附件站点=2，合计 20。
- canary 使用独立配置、独立任务范围、显式 policy 和受控频率。
- 不绕过登录、验证码、WAF 或访问控制。
- 每站必须保存结果与失败证据。
- 失败重试不得掩盖首轮失败结果。
- 任何越权或 SSRF 安全失败立即阻塞发布。
- 不在文档或配置中填写未经确认的真实站点名称。

## 9. Security 测试

- SSRF、DNS/IP、redirect、proxy、bounded I/O、HTTP limits。
- SEALED transport 硬限制：5 秒 timeout、redirects 最多 3 跳、transport global_active=20、per_host_active=5、per_host_idle=2、request body=1MiB、response headers=256KiB、probe/search/detail response body=1/8/20MiB。
- TARGET_V1 产品调度默认值为 HTTP budget=16、单域默认=2、允许配置上限=4；该层为 TARGET/PARTIAL，不冒充 transport 硬限制。
- 附件类型/魔数/大小/恶意内容。
- 认证、Session、Token、CSRF、CSP、错误脱敏。
- OSEC loader 未接入前，安全测试不能证明 production fail-closed 完成。

## 10. Performance 测试

- 内网首屏 ≤ 2.5 秒。
- 普通 API P95 ≤ 500ms。
- 创建任务 ≤ 1 秒。
- SSE 事件延迟 ≤ 3 秒。
- 性能测试需要独立基准环境，当前为 NOT_VERIFIED。

## 11. Migration、备份与失败注入

- migration 必须有版本和回滚。
- 每日备份恢复演练达到 RPO ≤ 24 小时、RTO ≤ 4 小时。
- 故障注入覆盖 Redis/MySQL 不可用、Worker lost、进程重启、取消、超时和局部失败。

## 12. 发布质量门槛

- 发现成功率 ≥ 95%
- 提取成功率 ≥ 90%
- 重复率 < 1%
- 不可恢复失败率 < 2%
- P0/P1 安全问题 = 0
- 至少 2 周观察期

### 12.1 发布阻塞条件

- 任一 P0/P1 安全问题
- production loader 未接入或 fail-closed 未验证
- Python/Go/Contract/E2E 关键门失败
- 20 站 canary 未达门槛或存在越权/SSRF 安全失败
- migration 正向或回滚失败
- backup restore 未达到 RPO/RTO
- 性能 SLA 未验证
- dirty 生成物或 OpenAPI generated types 漂移
- 存在无批准的 skip/flaky
- deployment 仍为 BLOCKED

## 13. Flaky/Skip 策略

- skip 必须包含原因、责任人、关联任务和到期日期。
- 临时 skip 最长 14 天，到期未关闭必须重新 review。
- flaky 可隔离，但必须保留原始失败证据。
- 不得通过删除测试、删除断言或永久 skip 获得绿色 CI。
- 删除测试仅允许在对应功能正式废弃、有替代覆盖并经独立 review 后执行。

## 14. 数据隔离

- 单元/契约测试禁止访问真实外网、生产 Redis/MySQL。
- E2E 使用一次性环境，测试数据不进入生产。
- 真实站点 canary 与业务数据物理隔离。

## 15. 当前与目标区分

| 测试能力 | 当前状态 | 目标 |
|---|---|---|
| Python/Go 组件测试 | 当前基线 PASS | 保持并扩展 |
| Redis/MySQL 隔离 E2E | 部分存在 | Streams/outbox 覆盖 |
| API contract | 版本化消息 contract 存在 | `/api/v1`/OpenAPI contract |
| Frontend | NOT_STARTED | Vitest/RTL/Playwright |
| 20 站 canary | NOT_STARTED | 上线门禁 |
| Performance | NOT_VERIFIED | 独立基准 |
| Backup restore | NOT_STARTED | 发布门禁 |

当前组件测试通过不等于完整产品已可发布。
