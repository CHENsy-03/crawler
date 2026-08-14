# Document Format Safety and Regression Boundary

**状态：** 已固化当前能力；未接入生产链

**关联：** TASK-019C-1

## 1. 能力矩阵

| 格式 | MIME/扩展名识别 | 直接辅助函数 | parse_content 统一入口 | v2 生产链 | 当前支持结论 |
|---|---|---|---|---|---|
| PDF | 是 | `extract_pdf_text` 文本层 | 是 | 必须拒绝 | 仅文本层；无 OCR/解密/附件/批注/表单 |
| DOCX | 是 | `extract_office_text` 段落 | 是 | 必须拒绝 | 仅 paragraphs；表格/页眉页脚/图片/文本框/批注/嵌入对象忽略 |
| XLSX | 是 | `extract_office_text(fmt="xlsx")` | 当前无法到达 XLSX 分支 | 必须拒绝 | 直接入口可读；统一入口为当前限制 |
| PPTX | 是 | 无专用分支 | 返回空 | 必须拒绝 | 不支持 |
| DOC | 是 | 无专用分支 | 返回空 | 必须拒绝 | 不支持 |
| XLS | 是 | 无专用分支 | 返回空 | 必须拒绝 | 不支持 |
| PPT | 是 | 无专用分支 | 返回空 | 必须拒绝 | 不支持 |

## 2. 调用链与生产可达性

- `detect_format`、`parse_content` 只有 `crawler/parser/__init__.py` 导出，没有任何生产调用方。
- `extract_pdf_text`、`extract_office_text` 同样没有生产调用方，当前是库级休眠能力。
- legacy Python pipeline 使用 `parser.html_parser`，不调用 `crawler/parser/format.py`。
- v2 Go 下载链只接受 `text/html` 和 `application/xhtml+xml`；PDF/Office MIME 在 `FetchHTML` 阶段即被拒绝。
- Python v2 `parser_worker` 通过正常 `crawler:html` 不可能收到 PDF/Office。
- `unsupported_format` 只是 ArticleResultV2 协议枚举，当前正式链不生成该状态。

## 3. PDF 现有能力

- 使用 PyPDF2 读取现有文本层，页面按顺序以换行拼接。
- 空白页、无文本层、空 bytes、损坏 bytes 均安全返回空字符串。
- 不执行 OCR，不识别扫描图片，不尝试密码破解，不读取附件、批注或表单。
- 输入 bytes 不写日志，不修改输入。

## 4. DOCX 现有能力

- 使用 python-docx 读取 `doc.paragraphs`，按文档顺序输出段落文本。
- 表格、页眉、页脚、图片、文本框、批注、嵌入对象、宏当前均不读取。
- 空文档返回空字符串；损坏 bytes 安全返回空字符串。

## 5. XLSX 直接入口与统一入口

- 直接 `extract_office_text(content, "xlsx")` 使用 openpyxl `read_only` 读取所有工作表、行、单元格。
- 当前实现用 `if c` 过滤单元格，因此 `0`、`False`、`None` 会被丢弃。
- 公式单元格只作为字符串读取，绝不执行公式，不访问外部地址。
- `parse_content` 对 XLSX MIME 或 `.xlsx` URL 会返回 `office`，但 `extract_office_text` 只有 `fmt == "xlsx"` 才进入 XLSX 分支，因此统一入口当前无法到达 XLSX 解析。这是当前限制，本轮不修复。

## 6. DOC/XLS/PPT/PPTX

- `detect_format` 会把对应 MIME/扩展名识别为 `office`。
- `parse_content` 和 `extract_office_text` 均无法解析这些格式，安全返回空字符串。
- 不调用 LibreOffice、Microsoft Office、COM、subprocess、宏或自动转换。

## 7. MIME/扩展名检测行为

- MIME 参数会去除，大小写会规范化。
- MIME 优先于 URL 扩展名。
- `application/octet-stream` + `.pdf` 扩展名会通过扩展名识别为 PDF。
- 大写扩展名可识别。
- 带 query 或 fragment 的 URL 当前不会先剥离，扩展名识别会失败并回退 `html`；这是当前限制。

## 8. 安全边界

- 不保存原始附件，不写附件文件。
- 不执行宏、公式、外部链接或脚本。
- 无 OCR、无解密、无格式转换。
- 无网络请求、无 subprocess、无 Office/COM/LibreOffice。
- 解析异常被捕获并返回空字符串。

## 9. 资源限制缺口

以下限制未接入生产前必须处理：

- PDF 无字节大小上限
- PDF 无页数上限
- PDF 输出文本无长度上限
- DOCX 无压缩包解压后大小限制
- DOCX 无段落数量上限
- XLSX 无工作表/行/单元格数量上限
- XLSX 遍历可能耗时或耗内存
- 无显式解析超时
- 第三方库处理不可信文件仍可能受库漏洞影响
- 无统一预验证安全门
- 无生产级附件隔离或沙箱
- 无原始附件持久化合同
- v2 当前通过 MIME 拒绝避免这些风险进入生产链

## 10. 结论

- 当前小型本地解析能力保留为库级能力。
- 未接入 v2 生产链。
- 未来若接入生产，必须先建立大小、页数、行数、超时和沙箱边界。

## 11. TASK-019C-2 安全门

- 新增 `crawler/parser/document_safety.py`，未接入任何生产模块。
- `safe_parse_document` 在调用旧辅助函数前执行输入大小、格式、签名、ZIP、页数/段落/工作表/行/单元格和输出长度预检。
- 超限整体拒绝，不截断。
- 未来接入生产前必须强制使用安全入口。