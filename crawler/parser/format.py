import logging

log = logging.getLogger('crawler.parser.format')

FORMAT_HANDLERS = {
    'application/pdf': 'pdf',
    'application/msword': 'office',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'office',
    'application/vnd.ms-powerpoint': 'office',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'office',
    'application/vnd.ms-excel': 'office',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'office',
    'text/csv': 'csv',
    'application/json': 'json',
    'application/xml': 'xml',
    'text/xml': 'xml',
}


def detect_format(content_type, url=''):
    """Detect file format from Content-Type header or URL extension."""
    if content_type:
        handler = FORMAT_HANDLERS.get(content_type.split(';')[0].strip().lower())
        if handler:
            return handler
    ext = url.rsplit('.', 1)[-1].lower() if '.' in url else ''
    ext_map = {'pdf': 'pdf', 'doc': 'office', 'docx': 'office', 'ppt': 'office',
               'pptx': 'office', 'xls': 'office', 'xlsx': 'office', 'csv': 'csv',
               'json': 'json', 'xml': 'xml'}
    return ext_map.get(ext, 'html')


def parse_content(content, content_type, url=''):
    """Unified content parser: auto-detect format and extract text."""
    fmt = detect_format(content_type, url)
    if fmt == 'pdf':
        from crawler.parser.pdf import extract_pdf_text
        return extract_pdf_text(content)
    elif fmt == 'office':
        from crawler.parser.office import extract_office_text
        return extract_office_text(content, fmt)
    else:
        return content  # HTML, CSV, JSON, XML: return as-is for html_parser
