# 通用型爬虫 API 文档级契约

本文定义外部 API 的文档级契约，不创建 OpenAPI YAML。后续 Go OpenAPI 是本契约的可执行权威。

公开 API 错误码和 SSE 事件子集以 canonical 字典为权威：

- [docs/STATUS_ERROR_EVENT_DICTIONARY_V1.0_V1.1.md](STATUS_ERROR_EVENT_DICTIONARY_V1.0_V1.1.md)
- [tests/fixtures/status_error_event_dictionary_v1.json](../tests/fixtures/status_error_event_dictionary_v1.json)

本文件不修改端点；完整 SSE/OpenAPI schema 属于 DEV-003。

## 1. 通用约定

- 通用 URL 前缀：`/api/v1`
- 内容类型：`application/json`
- 时间格式：RFC 3339 UTC，展示层本地化
- 分页：`page`、`page_size`，默认 `page=1`、`page_size=20`，上限 100
- 排序：`sort=field`、`order=asc|desc`
- 筛选：稳定字段白名单，禁止把任意用户输入拼入 SQL
- Idempotency Key：按端点矩阵要求用于创建/确认/重试/取消/审核/导出/Token/配置等业务 mutation；login 使用防暴力限流，logout 天然幂等，GET/HEAD 不要求 Idempotency-Key
- Request ID：请求头 `X-Request-Id` 或服务端生成，错误响应回传
- 错误模型：统一 envelope，见第 2 节
- 认证：浏览器会话 Cookie 或 `Authorization: Bearer <api_token>`，二选一，禁止混用
- CSRF：同源浏览器写请求携带 CSRF token；API Token 请求不要求 Cookie CSRF
- 版本：OpenAPI 为权威，版本采用 `/api/v1` 路径和向后兼容废弃策略

## 2. JSON Envelope 与错误模型

成功响应：

```json
{
  "request_id": "req-0001",
  "data": {}
}
```

列表响应：

```json
{
  "request_id": "req-0001",
  "data": {
    "items": [],
    "page": 1,
    "page_size": 20,
    "total": 0
  }
}
```

错误响应：

```json
{
  "request_id": "req-0001",
  "error": {
    "code": "validation_error",
    "message": "字段校验失败",
    "fields": {},
    "retryable": false
  }
}
```

错误信息不得包含内部堆栈、凭据、Token、完整 URL 中的敏感参数或内部 IP。

## 3. 通用状态码

| 状态码 | 含义 |
|---|---|
| 200 | 成功 |
| 201 | 创建成功 |
| 202 | 异步操作已接受 |
| 204 | 无内容成功 |
| 400 | 请求校验失败 |
| 401 | 未认证或 Token 无效 |
| 403 | 无权限或 CSRF 失败 |
| 404 | 资源不存在 |
| 409 | 状态冲突或幂等冲突 |
| 422 | 业务规则校验失败 |
| 429 | 限流或背压 |
| 500 | 内部错误 |
| 503 | readiness 失败或依赖不可用 |

## 4. 认证方式

- Session Cookie：`HttpOnly`、`Secure`、合适 `SameSite`；空闲 30 分钟、绝对 8 小时。
- API Token：只存 hash，支持轮换和吊销；有效期由 token 记录控制。
- Bootstrap：首次初始化使用一次性 bootstrap token，成功后失效。
- 本地 CLI 恢复用于管理员密码/Token 重置，不进外部 API。

## 5. 端点矩阵

除内部探针 `/healthz`、`/readyz` 外，其余端点路径均加 `/api/v1` 前缀。`CURRENT` 表示当前实现状态；除明确 CURRENT_IMPLEMENTED 外均未完成。

| 端点 | Method | Auth | Request/Response 要点 | 关键状态码 | Idempotency | Pagination | Errors | CURRENT |
|---|---|---|---|---|---|---|---|---|
| `/bootstrap` | POST | 无 | body: username,password,bootstrap_token | 200/409 | Idempotency-Key | N/A | invalid_token, already_initialized | NOT_STARTED |
| `/auth/login` | POST | 无 | body: username,password | 200/401 | 否，但防暴力限流 | N/A | invalid_credentials | NOT_STARTED |
| `/auth/logout` | POST | Session | 登出并失效 Session | 204 | 幂等 | N/A | unauthorized | NOT_STARTED |
| `/auth/session` | GET | Session | 返回当前管理员和会话过期 | 200/401 | 幂等 | N/A | unauthorized, session_expired | NOT_STARTED |
| `/auth/tokens` | GET | Session | 返回 token 元数据，不含 secret | 200 | 幂等 | 是 | unauthorized | NOT_STARTED |
| `/auth/tokens` | POST | Session | 创建 API Token，secret 只在创建响应出现一次 | 201 | Idempotency-Key | N/A | token_limit_exceeded | NOT_STARTED |
| `/auth/tokens/{tokenId}` | DELETE | Session | 吊销 Token | 204 | 幂等 | N/A | not_found | NOT_STARTED |
| `/tasks` | GET | Session/Token | 任务列表按 status/created_at 筛选 | 200 | 幂等 | 是 | validation_error | NOT_STARTED |
| `/tasks` | POST | Session/Token | 创建 DRAFT；body: site_code,keywords,mode,limits | 201 | Idempotency-Key | N/A | site_not_found, limits_invalid | NOT_STARTED |
| `/tasks/{taskId}/scope-suggestion` | POST | Session/Token | 创建任务返回范围建议，不开始执行 | 200 | Idempotency-Key | N/A | task_not_found, state_conflict | NOT_STARTED |
| `/tasks/{taskId}/confirm` | POST | Session/Token | 确认范围并进入 QUEUED | 200 | Idempotency-Key | N/A | state_conflict, over_limit | NOT_STARTED |
| `/tasks/{taskId}` | GET | Session/Token | 返回任务状态、阶段、进度和 checkpoint | 200 | 幂等 | N/A | not_found | NOT_STARTED |
| `/tasks/{taskId}/cancel` | POST | Session/Token | 请求取消，进入 CANCELLING | 202 | Idempotency-Key | N/A | state_conflict, already_terminal | NOT_STARTED |
| `/tasks/{taskId}/retry` | POST | Session/Token | 保留原任务终态，创建新 CrawlTask；响应返回 new_task_id 和 source_task_id | 201 | Idempotency-Key | N/A | not_retryable, state_conflict | NOT_STARTED |
| `/tasks/{taskId}/events` | GET SSE | Session/Token | task event 流；Last-Event-ID 恢复 | 200 | N/A | event_id 游标 | unauthorized | NOT_STARTED |
| `/results` | GET | Session/Token | 结果列表含任务、站点、审核状态 | 200 | 幂等 | 是 | validation_error | NOT_STARTED |
| `/results/{articleId}` | GET | Session/Token | 返回规范化正文、证据、审核状态 | 200 | 幂等 | N/A | not_found | NOT_STARTED |
| `/results/{articleId}/review` | PUT | Session | 审核决定 approved/rejected/needs_review | 200 | Idempotency-Key | N/A | state_conflict, evidence_missing | NOT_STARTED |
| `/export-jobs` | POST | Session/Token | 异步导出 CSV/XLSX/JSON | 202 | Idempotency-Key | N/A | export_not_supported, no_results | NOT_STARTED |
| `/export-jobs` | GET | Session/Token | 导出任务列表 | 200 | 幂等 | 是 | validation_error | NOT_STARTED |
| `/export-jobs/{jobId}/download` | GET | Session/Token | 下载完成后文件 | 200/202/404 | 幂等 | N/A | not_ready, not_found | NOT_STARTED |
| `/sites` | GET | Session/Token | 站点及能力列表 | 200 | 幂等 | 是 | validation_error | NOT_STARTED |
| `/sites` | POST | Session | 创建/更新站点配置 | 201 | Idempotency-Key | N/A | site_code_conflict | NOT_STARTED |
| `/sites/{siteCode}` | PUT | Session | 更新站点能力/策略引用 | 200 | Idempotency-Key | N/A | not_found, policy_missing | NOT_STARTED |
| `/sites/{siteCode}` | DELETE | Session | 禁用站点而非删除证据 | 204 | 幂等 | N/A | in_use | NOT_STARTED |
| `/plugins` | GET | Session/Token | 插件注册列表 | 200 | 幂等 | 是 | validation_error | NOT_STARTED |
| `/plugins/{pluginId}` | PUT | Session | 启停/禁用插件版本 | 200 | Idempotency-Key | N/A | not_found, version_conflict | NOT_STARTED |
| `/healthz` | GET | 无 | 内部容器探针 liveness，不属于外部业务 OpenAPI | 200 | 不适用 | N/A | N/A | NOT_STARTED |
| `/readyz` | GET | 无 | 内部容器探针 readiness，依赖未就绪返回 503 | 200/503 | 不适用 | N/A | dependency_not_ready | NOT_STARTED |
| `/system/logs` | GET | Session | 日志检索，敏感字段脱敏 | 200 | 幂等 | 是 | validation_error | NOT_STARTED |
| `/system/security/status` | GET | Session | 只读安全状态 | 200 | 幂等 | 是 | unauthorized | NOT_STARTED |

当前存在 `api/server.py` FastAPI `/parse` 调试接口和 Go 基础 API，但均不是冻结的 `/api/v1` 外部契约。

内部探针 `/healthz`、`/readyz` 不属于外部业务 OpenAPI，不通过 Nginx 向普通用户暴露，只用于容器编排和受控运维。

## 6. SSE 契约

路径：`GET /api/v1/tasks/{taskId}/events`。

- 事件头 `id` 为 event_id，单调递增。
- 客户端用 `Last-Event-ID` 恢复断档。
- 服务端每 15 秒发送 heartbeat。
- 客户端 45 秒无事件时重连。
- 服务端只保留最近 N 条任务事件；断档超过保留窗口时返回 410 或要求 polling。
- SSE 不可用时前端按 5 秒 polling fallback。

事件类型：

| event | 字段要点 |
|---|---|
| task_status_changed | task_id, from_status, to_status, stage |
| stage_progress | task_id, stage, current, total, percent |
| worker_lost | task_id, attempt_id, heartbeat_expired_at |
| result_persisted | task_id, article_id, article_key |
| task_error | task_id, error_code, retryable, request_id |
| export_finished | job_id, download_url |
## 7. 关键请求/响应对象

### Task

```json
{
  "task_id": "string",
  "status": "DRAFT",
  "stage": "DISCOVERY",
  "site_code": "string",
  "keywords": ["string"],
  "created_at": "2026-09-03T00:00:00Z",
  "updated_at": "2026-09-03T00:00:00Z"
}
```

### ArticleResult

```json
{
  "article_id": "string",
  "article_key": "string",
  "identity_url_hash": "string",
  "task_id": "string",
  "title": "string",
  "content_hash": "string",
  "review_status": "PENDING"
}
```

### ExportJob

```json
{
  "job_id": "string",
  "format": "CSV",
  "status": "PENDING",
  "download_url": null,
  "created_at": "2026-09-03T00:00:00Z"
}
```

## 8. 筛选、分页与幂等

- 列表查询使用白名单 filter：`status`、`site_code`、`created_from`、`created_to`、`review_status`、`format`。
- 排序字段白名单：`created_at`、`updated_at`、`score`、`status`。
- 创建任务、确认任务、重试任务、取消任务、审核、创建导出、创建 Token 和配置变更等业务 mutation 按端点矩阵要求支持 Idempotency-Key；重复请求返回原结果或 409。
- login 不使用 Idempotency-Key，使用防暴力限流；logout 天然幂等，不要求 Idempotency-Key；GET/HEAD 不要求 Idempotency-Key。
- 任务状态冲突返回 409，禁止静默覆盖终态。
- 导出下载完成后文件在保留期内可重复下载，不重复计算导出任务。

重试不会把 FAILED、PARTIAL_SUCCEEDED 等终态改回 QUEUED/RUNNING；重试通过创建新 CrawlTask 实现，新任务记录 retry_of_task_id，从 DRAFT 或 PENDING_CONFIRMATION 进入流程。

## 9. API 版本与废弃策略

- 当前正式目标为 `/api/v1`。
- 兼容窗口：同一版本内不得破坏字段语义。
- 废弃流程：OpenAPI 标记 deprecated → 维护迁移期 → 新版本发布 → 旧版本按声明周期下线。
- 版本变更必须更新 OpenAPI、文档、前端生成 types 和 contract tests。

## 10. 当前状态

| 能力 | 当前状态 |
|---|---|
| `/api/v1` | NOT_STARTED |
| Go OpenAPI | NOT_STARTED |
| 认证/Session/API Token | NOT_STARTED |
| SSE | NOT_STARTED |
| 5 秒 polling | NOT_STARTED |
| 任务/结果/导出 API | NOT_STARTED |
| 只读安全状态 API | NOT_STARTED |
| Python FastAPI 调试入口 | CURRENT_PARTIAL，不作为生产入口 |

## 11. 验收指标

- 普通 API P95 ≤ 500ms。
- 创建任务请求 P95 ≤ 1 秒。
- SSE 事件延迟 ≤ 3 秒。
- 所有列表接口服务端分页。
- 错误响应不泄露内部堆栈、Token、Cookie 或内部 IP。
