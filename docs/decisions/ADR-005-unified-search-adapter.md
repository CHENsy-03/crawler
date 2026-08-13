# ADR-005：统一 Search Adapter

**状态：** accepted

**日期：** 2026-08-13

**关联：** TASK-018，TASK-017 已完成

## 背景

TASK-017 已实现 SearchPlan v2 分析、探测、构建、执行、缓存和 Worker 发布闭环，但正式执行能力只覆盖通用 HTML/JSON selector 路径。TRS、JPAAS、HTML POST form 和通用 JSON POST 仍分散在 legacy plugin 与 parser 中，无法统一进入 v2 orchestrator。

`SearchPlan` 现有 `strategy` 和 `discovery.source` 不足以无歧义选择正式 Adapter，且无法表达 TRS form POST + JSON 响应的组合。

## 决策

采用方案 B：新增正式 `adapter` 字段，并新增受控字段 `request_format`、`response_format` 与结构化 `request_shape`。

- `adapter` 枚举：`html`、`trs`、`jpaas`、`generic_json`。
- `request_format` 枚举：`none`、`form_urlencoded`、`json`。
- `response_format` 枚举：`html`、`json`。
- `request_shape` 使用结构化语义：`keyword_location`、`keyword_path`、`fixed_query_params`、`form_fields`、`json_object_template`。

`AdapterRegistry` 只根据已验证的正式 `adapter` 字段选择 Adapter。

## 契约澄清

原文早期草稿把 `keyword_path` 限定为仅 JSON body 使用，无法表达 query/form 的关键词参数名。现澄清为：

- `keyword_path` 是所有 `keyword_location` 的结构化关键词插入位置；
- query/form 使用恰好一个非空片段表示参数名；
- json 使用一个或多个非空片段表示嵌套路径；
- 路径片段不得为空、不得依赖点号拆分、不得隐式数组索引、大小写原样保留；
- 关键词字段不得与对应固定字段集合冲突。

这是补齐表达能力，不改变 Adapter 架构、正式 `adapter` 枚举或 method/format 组合决策。
## 拒绝方案

- 拒绝方案 A：让 `discovery.source` 同时承担来源证据与执行分派。`discovery.source` 保留为来源追踪、证据审计、日志诊断和测试说明，不进入执行协议。
- 拒绝方案 C：根据 endpoint、hostname、selector 形状或运行时响应猜测 Adapter。禁止自动推断和逐个尝试。
- 拒绝自由 Content-Type 字符串：使用受控 `request_format`/`response_format` 枚举，由请求构造器确定性映射 MIME。
- 拒绝自由字符串 `request_body_template` 作为新 ready plan 的唯一请求 body 契约：新 schema 以结构化 `request_shape` 为唯一请求结构源。

## 两层组合结构

正式采用：

```text
AdapterRegistry
→ Adapter
→ RequestBuilder
→ 统一安全 HTTP transport
→ ResponseParser
→ SearchPlanExecutionResult
```

边界：

- Adapter 验证字段组合、协调请求构造与响应解析、返回统一执行结果；
- RequestBuilder 只负责确定性请求构造；
- ResponseParser 只处理受限响应；
- Transport 不理解 TRS/JPAAS 业务字段。

## plan_id 变化

以下执行语义进入 canonical `plan_id`：

```text
adapter
http_method
endpoint
request_format
response_format
request_shape
pagination
selectors
scope
其他现有执行字段
```

执行语义变化会生成不同 `plan_id`，这是预期行为。

## 旧缓存失效策略

- 旧 schema 缓存按受控不兼容处理；
- 旧缓存不得进入 executor；
- 当前任务按 cache miss 路径重新生成；
- 重新生成成功后写入新 schema 缓存；
- 不把旧缓存反序列化失败暴露为新的外部错误码。

## 外部协议不变

以下外部消息协议保持不变：

```text
SearchRequestedMessage protocol_version
URLMessage protocol_version
URLMessage schema
crawler:search
crawler:url
Go HTMLPayload
```

## 错误语义

继续使用已有错误集合：

```text
plan_invalid
plan_not_executable
transport_failure
response_rejected
selector_mismatch
no_results
```

不新增 Adapter 专属对外错误码。

## 安全边界

继承 TASK-016/017 安全约束；不把 TASK-022 生产级 SSRF 伪装为已完成。

## legacy v1 边界

TASK-018 保持 legacy v1 不变；迁移完成前双路径并存。

## 后续关系

正式冻结：

```text
TASK-018：统一正式执行 Adapter
→ TASK-022：生产级 SSRF 与连接级安全
→ TASK-020：未知站点 MVP 验收
```

版本、tag、release 策略推迟到 TASK-020 MVP 验收通过后定义。