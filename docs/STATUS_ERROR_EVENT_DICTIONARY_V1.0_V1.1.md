# V1.0/V1.1 状态、错误与事件字典

## 1. 权威关系与适用范围

本文件是 DEV-002 的说明性契约文档。唯一机器可读词汇集合是：

- `protocol/status_error_event_dictionary.schema.json`
- `tests/fixtures/status_error_event_dictionary_v1.json`

Go/Python 枚举与 canonical fixture 精确一致；本文件只提供来源导航和说明，不构成另一套词汇表。

## 2. 文件路径

| 资产 | 路径 |
|---|---|
| JSON Schema | protocol/status_error_event_dictionary.schema.json |
| canonical fixture | tests/fixtures/status_error_event_dictionary_v1.json |
| Python enums | protocol/status_error_event.py |
| Go enums | go-spider/internal/protocol/status_error_event.go |
| Python contract test | tests/test_status_error_event_dictionary.py |
| Go contract test | go-spider/internal/protocol/status_error_event_test.go |

## 3. 状态、错误、事件边界

- 状态是实体生命周期值，必须以 domain 限定。
- 错误是失败原因，使用 canonical lower_snake_code 和 legacy alias 兼容处置。
- 事件是已发生事实或消息类型，按 family/version 限定。
- 心跳不是事件类型；错误码不是任务状态；事件类型不混入状态 domain。

## 4. 机械统计

状态共 101 项，分布于 24 个 domain：

| domain | 数量 |
|---|---:|
| crawl_task | 12 |
| task_attempt | 5 |
| task_stage_name | 7 |
| task_stage | 4 |
| site | 7 |
| search_plan | 4 |
| search_candidate | 5 |
| fetch_artifact | 3 |
| artifact_hold | 4 |
| article_version | 2 |
| task_article | 5 |
| review_decision | 3 |
| export_job | 5 |
| outbox_event | 4 |
| dead_letter | 4 |
| checkpoint | 3 |
| admin | 3 |
| session | 4 |
| api_token | 3 |
| global_block_entry | 3 |
| capacity | 4 |
| stream_work_class | 4 |
| readiness | 2 |
| release | 1 |

错误共 63 项：

- NEVER：46
- ALWAYS：8
- CONDITIONAL：9
- 无公开 HTTP 映射的内部错误：4

事件共 22 项：

- TASK_EVENT：7
- STREAM_MESSAGE：6
- AUDIT_EVENT：1
- CONTROL_EVENT：4
- OPERATIONAL_EVENT：4

legacy alias 共 16 项，兼容决策共 6 项。

字典 contract_version：`1.1`。新增兼容决策 `DEV003_CONTRACT_FIX_001`，保留 DEV-002 原有五项决策不变。

## 4.1 场景专用错误

- `task_limit_exceeded`：HTTP 422，namespace=api，retryability=NEVER，client_exposable=true，用于 V1.0 §7.4 关键词、搜索页、候选量或策略硬上限。
- `event_history_expired`：HTTP 410，namespace=api，retryability=NEVER，client_exposable=true，用于 Last-Event-ID 早于 SSE 保留窗口。
- `validation_error` 继续表示请求结构、字段类型等 400 校验错误。
- `over_limit` 429 保留给既有限流/背压语义；新 `/api/v1` 任务硬上限不再继续用 `over_limit` 代替。
- `export_expired` 410 继续只用于导出文件过期，不复用到 SSE。
- NEVER 表示不应自动原样重试同一失败请求或同一过期游标；修改任务参数后提交或获取任务快照后以新游标恢复不被禁止。

ADR-026 已记录 `DEV003_CONTRACT_FIX_001` 修订：ULID 首字符 0—7、128 bit 最大值、ascii_bin 大小写语义和格式 pattern。

## 5. 覆盖证明

- V1.0 附录 C.7 的 19 项稳定错误码全部存在，missing=0。
- V1.1 附录 B.2 的 14 项稳定错误码全部存在，missing=0。
- V1.0 附录 C.1-C.6 的 CrawlTask、TaskStage、Site、Article result、Review、ExportJob 状态全部存在。
- V1.1 附录 B.1 的 Artifact hold、Disk/Stream、GlobalBlockEntry、Stream work class 状态全部存在。
- Audit event `global_block_legal_request_activated` 记录 LEGAL_REQUEST 类型 GlobalBlockEntry 生效操作，来源 V1.1 §10.3。
- 该事件由已批准的 Go 业务路径 `go_api` 在同一进程内同步处理：producer=go_api、consumer=go_api。
- transport=in_process，表示不经过 Redis Stream、Consumer Group、Outbox 或网络消息传输。
- persistence_target=mysql_audit_log，表示 GlobalBlockEntry mutation 与 AuditLog 追加在同一 MySQL 权威事务中完成。
- 不存在独立部署的 `audit_service`；AuditLog 是 MySQL 持久化实体，不是消息 transport。
- payload/data contract 属于 DEV-004；DEV-005 不负责该事件的 Stream/Outbox payload。
- persistence_target 只允许用于 AUDIT_EVENT；非 Audit Event 出现该字段即为契约错误。
- `SSE` 是区分大小写的唯一 canonical transport token；小写 `sse` 不是 canonical、不是 alias、不是合法输入。
- Redis transport 固定为 `redis_stream`；Audit 同步路径固定为 `in_process`；`mysql_audit_log` 是 persistence target，不是 transport。
- Go/Python 双侧 contract test 均验证上述 persistence_target 与 transport 约束。

## 6. 当前代码冲突与 legacy alias

- 旧大写协议错误码如 `INVALID_TARGET_URL` 等只作为 legacy alias，不冒充新公开 API 权威错误码。
- `SEARCH_FAILED` 映射到 canonical `search_failed`。
- ArticleResultV2 和 SearchPlan 保留当前 lower-case wire value。
- 无法在 DEV-002 消除的旧值语义冲突记录在 `compatibility_decisions`，由对应 DEV 工作包处理。

## 7. casing 与 wire value

- canonical symbol 使用 UPPER_SNAKE。
- canonical error code 使用 lower_snake_case。
- event type 使用 lower_snake_case。
- 需要保持现有序列化的 wire value 与 canonical symbol 分离记录。

## 8. 后续边界

- DEV-003：冻结外部 OpenAPI/SSE payload schema。
- DEV-004：数据模型和 migration。
- DEV-005：Redis Stream payload、consumer group、outbox 协议。
- DEV-204：任务状态机转换 guard 和业务实现。

本字典只冻结名称、值、职责和兼容身份，不实现上述运行逻辑。

## 9. 兼容与废弃规则

- canonical fixture 是版本化单一权威。
- 新增值必须更新 schema、fixture、Go、Python 和测试。
- 废弃值必须在 legacy_aliases 中记录兼容处置。
- 不允许静默改写现有消息序列化结果。

## 10. 状态

当前状态：共享契约修复候选 `IMPLEMENTED_WAITING_REVIEW`；DEV-003 OpenAPI/SSE 成品仍未实施。
