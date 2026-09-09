# 通用型爬虫 API 文档级契约

本文是人类可读导航，不构成第二权威。机器可执行权威为：

- OpenAPI：`go-spider/openapi/v1/openapi.yaml`
- SSE schema：`go-spider/openapi/v1/sse/*.schema.json`
- 43-operation 契约矩阵：`tests/fixtures/openapi_v1_contract.json`
- canonical 错误/状态/事件：DEV-002 字典资产

## 通用约定

- URL 前缀：`/api/v1`
- OpenAPI 3.1.0，本地 `$ref`，无远程引用
- 外部资源 ID 使用 canonical ULID（ADR-026）
- 时间使用 RFC 3339 UTC
- JSON envelope 与响应边界以 OpenAPI 为准
- 认证：Session Cookie、CSRF header 或 Bearer API Token
- Cookie 与 Bearer 不得混用；OpenAPI security 数组不自动实现该互斥
- JSON 成功响应的 `data` 必须解析为具体 DTO schema，不使用开放 object 作为最终契约
- Results 支持 `page` 与 `cursor` 互斥模式；排序白名单和唯一尾键按 OpenAPI 扩展与 contract test 表达
- 每个 operation 的错误响应按契约矩阵裁剪，不再复制统一错误模板
- Last-Event-ID 只属于 streamTaskEvents
- createResultReview 成功状态为 200
- TaskLimits 候选上限为 10000
- export_finished 中 download_url 与 error_code 不得同时出现；字段值为 null 仍表示字段存在
- updateSite/updatePlugin 为 Session-only；Bearer Token scope 仅在批准接口使用
- bootstrapSystem 校验 bootstrap_token，失败使用 unauthorized/401

## SSE

外部事件只有六类：

- task_status_changed
- stage_progress
- worker_lost
- result_persisted
- task_error
- export_finished

SSE `id:` 为 TaskEvent ULID，`event:` 为 canonical token，`data:` 为 JSON payload。
payload 由对应 JSON Schema 验证。Last-Event-ID 早于保留窗口时，在建立流前返回
JSON 410/`event_history_expired`。

## 当前状态

- `/api/v1` OpenAPI：契约已建立，API handler 未实现
- SSE 服务运行：未实现
- polling fallback：未实现
- 发布状态：RELEASE_BLOCKED
