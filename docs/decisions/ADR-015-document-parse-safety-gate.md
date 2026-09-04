# ADR-015：文档解析安全门

**状态：** accepted

**日期：** 2026-08-14

**关联：** TASK-019C-2，ADR-014 保持有效

## 背景

现有 PDF/DOCX/XLSX 辅助函数没有资源限制，直接调用时可能处理不可信输入。需要在不修改旧辅助函数的前提下，新增独立安全入口。

## 决策

1. 新增 `crawler/parser/document_safety.py`，提供唯一入口 `safe_parse_document`。
2. 不修改旧 `extract_pdf_text`、`extract_office_text`、`detect_format` 或 `parse_content`。
3. 不接 Redis、Worker、API、数据库或下载链。
4. 超限整体拒绝，不截断输出。
5. 不实现线程硬超时；超时与进程隔离后置。
6. 不宣称可处理任意不可信附件。
7. 预检与提取可能产生双重解析，接受为当前保守成本，记录为优化点。
8. 未来接线前必须强制只使用安全入口，并完成硬超时/进程隔离决策。

## 影响

- 新增结构化 `DocumentSafetyPolicy` 与 `DocumentParseResult`。
- 新增离线测试，覆盖拒绝路径不调用旧提取器。
- 生产模块不 import 安全门。