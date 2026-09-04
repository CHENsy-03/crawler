# ADR-014：PDF/Office 安全回归边界

**状态：** accepted

**日期：** 2026-08-14

**关联：** TASK-019C-1

## 背景

仓库存在 PDF、DOCX、XLSX 的小型本地解析辅助函数，但没有生产调用方。需要固化当前能力与失败边界，避免把“格式识别”误当成“格式支持”，并明确 v2 生产链对 PDF/Office 的 MIME 拒绝边界。

## 决策

1. 保留现有小型本地解析能力，不新增复杂解析。
2. 不把 PDF/Office 接入 v2 下载、解析或持久化链。
3. 不引入 OCR、PDF 解密、Office/LibreOffice、COM、subprocess、宏或格式转换。
4. 不保存原始附件，不建立附件持久化合同。
5. 不把 `detect_format` 的识别结果等同于解析支持。
6. `unsupported_format` 仅保留为协议状态，本轮不接生产生成。
7. 资源安全门（大小、页数、行数、超时、沙箱）后置到独立任务。
8. 新增 `tests/test_document_format_contract.py` 固化当前行为，包括当前限制。

## 影响

- PDF 文本层、DOCX 段落、XLSX 直接辅助函数均有离线回归测试。
- XLSX 统一入口无法到达 XLSX 分支、URL query/fragment 扩展名识别失败等限制被明确记录。
- v2 Go 下载链仍拒绝 PDF/Office MIME。