import logging

log = logging.getLogger('crawler.parser.office')


def extract_office_text(content, fmt='office'):
    """Extract text from Office documents (docx, pptx, xlsx)."""
    try:
        from io import BytesIO
        if fmt in ('docx', 'office'):
            try:
                from docx import Document
                doc = Document(BytesIO(content))
                return '\n'.join(p.text for p in doc.paragraphs)
            except Exception:
                pass
        if fmt in ('xlsx',):
            try:
                from openpyxl import load_workbook
                wb = load_workbook(BytesIO(content), read_only=True)
                texts = []
                for ws in wb.worksheets:
                    for row in ws.iter_rows(values_only=True):
                        texts.append(' '.join(str(c) for c in row if c))
                return '\n'.join(texts)
            except Exception:
                pass
        log.warning('Office extract: format=%s not fully supported', fmt)
    except ImportError:
        log.warning('python-docx/openpyxl not installed. Run: pip install python-docx openpyxl')
    except Exception as e:
        log.warning('Office extract error: %s', e)
    return ''
