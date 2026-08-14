# Document Parse Safety Gate

**状态：** 已实现，未接入生产链

**关联：** TASK-019C-2

## 1. API

```python
safe_parse_document(
    content: bytes,
    content_type: str = "",
    url: str = "",
    policy: DocumentSafetyPolicy = DEFAULT_DOCUMENT_SAFETY_POLICY,
) -> DocumentParseResult
```

- 只接受 `bytes`；str/bytearray/memoryview/None 按 `rejected/invalid_input_type` 拒绝。
- 不读取文件系统、不访问网络、不启动 subprocess、不保存附件。
- 不修改输入 bytes。
- 所有异常收敛为结构化结果。
- 本模块没有任何生产调用方。

## 2. 默认策略

| 项 | 默认值 |
|---|---|
| max_input_bytes | 20 MiB |
| max_pdf_pages | 500 |
| max_archive_members | 2048 |
| max_archive_uncompressed_bytes | 100 MiB |
| max_archive_member_bytes | 50 MiB |
| max_compression_ratio | 100 |
| max_docx_paragraphs | 20000 |
| max_xlsx_sheets | 32 |
| max_xlsx_rows | 100000 |
| max_xlsx_cells | 1000000 |
| max_output_chars | 2000000 |

所有上限均为包含式；超限整体拒绝，不截断。

## 3. 状态与 reason

- `success/ok`
- `empty/empty_input|empty_content`
- `rejected/...`
- `failed/parse_failed`
- `unsupported/unsupported_format`

稳定 reason：`invalid_input_type`、`input_too_large`、`signature_mismatch`、`encrypted_document`、`invalid_archive`、`unsafe_archive_path`、`encrypted_archive_member`、`archive_member_limit`、`archive_member_size_limit`、`archive_uncompressed_limit`、`compression_ratio_limit`、`pdf_page_limit`、`docx_paragraph_limit`、`xlsx_sheet_limit`、`xlsx_row_limit`、`xlsx_cell_limit`、`output_too_large`。

## 4. 稳定预检顺序

1. policy 校验
2. content 类型
3. 空输入
4. 输入字节长度
5. 格式识别
6. 文件签名
7. PDF/Office 结构预检
8. 格式专属数量限制
9. 调用现有提取函数
10. 输出为空判断
11. 输出长度限制
12. 返回 success

## 5. PDF

- 签名：`%PDF-`
- 加密 PDF 拒绝
- 页数超限拒绝
- 文本层为空返回 empty
- 输出超长整体拒绝
- 无 OCR、解密、图片、附件、批注、表单

## 6. Office ZIP

- 只读检查中央目录，不调用 extract/extractall
- 检查成员数、单成员大小、总解压大小、压缩比、加密标志、路径安全
- 拒绝绝对路径、盘符、`..`、反斜杠穿越、NUL、符号链接
- DOCX 必需 `[Content_Types].xml`、`word/document.xml`
- XLSX 必需 `[Content_Types].xml`、`xl/workbook.xml`

## 7. DOCX

- python-docx 只读计数 paragraphs，超限拒绝
- 不新增表格/页眉页脚/图片/文本框解析
- 调用现有 `extract_office_text(content, "docx")`

## 8. XLSX

- openpyxl `read_only=True, data_only=False`
- 计数工作表、行、单元格
- 使用维度信息做保守拒绝，避免遍历超上限空单元格
- 不执行公式，不解析外部链接
- workbook 在 finally 中 close
- 保留现有 0/False 过滤行为
- 调用现有 `extract_office_text(content, "xlsx")`

## 9. 不支持格式

DOC、XLS、PPT、PPTX、DOCM、XLSM、PPTM、RTF、ODT、CSV/JSON/XML/HTML 等返回 `unsupported/unsupported_format`。

## 10. 未来建议映射

- success → 后续相关性状态机
- unsupported → ArticleResultV2.unsupported_format
- empty/rejected/failed → ArticleResultV2.extract_failed

本轮不实现该映射。

## 11. 残余风险

- 没有硬超时
- 没有进程隔离/沙箱
- 预检与提取可能双重解析
- 输出限制发生在旧辅助函数生成文本之后
- 旧辅助函数仍可被直接调用；接生产前必须强制只使用安全入口