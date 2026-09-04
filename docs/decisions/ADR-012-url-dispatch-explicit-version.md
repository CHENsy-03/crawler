# ADR-012：PopURLDispatch 显式 protocol_version 判定

**状态：** accepted

**日期：** 2026-08-14

**关联：** TASK-019B-8R，ADR-006/009 保持有效

## 问题来源

`PopURLDispatch()` 原先先将 `protocol_version` 反序列化到 `string` 字段，再用空字符串同时表示“字段不存在”和“非法值”。Go 将 JSON `null` 解码到 string 时静默得到零值空字符串，导致显式 `protocol_version=null` 被当作 legacy 消息处理，并触发 HTTP 下载。

## 决策

1. 顶层 JSON 使用 `map[string]json.RawMessage` 解析。
2. `protocol_version` 键不存在时才进入 legacy。
3. 键存在时，值必须是 JSON string，且精确等于 `"1.0"` 或 `"2.0"`。
4. 显式 null、空字符串、空白字符串、数字、boolean、object、array、未知字符串均拒绝。
5. 顶层 null、数组、字符串、非法 JSON 均拒绝。
6. 拒绝后不下载、不发布 HTML、不发布 v1 ErrorMessage，消费者继续运行。
7. `PopResultDispatch` 行为保持不变。

## 真值表

- 字段不存在 → legacy
- `"1.0"` → legacy/v1
- `"2.0"` → 严格 URLMessageV2
- null/空/空白/未知/数字/boolean/object/array → 拒绝
- 顶层非对象或非法 JSON → 拒绝

## 影响

- `protocol_version=null` 不再被吞成 legacy。
- B8 全链 E2E 中非法消息 HTTP 请求数为 0，后续合法 barrier 正常贯通。
- 一次 BRPOP 后完成显式分流，不二次读取队列。