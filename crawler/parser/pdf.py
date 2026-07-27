import logging

log = logging.getLogger('crawler.parser.pdf')


def extract_pdf_text(content):
    """Extract text from PDF bytes. Returns empty string on failure."""
    try:
        from io import BytesIO
        from PyPDF2 import PdfReader
        reader = PdfReader(BytesIO(content))
        return '\n'.join(page.extract_text() or '' for page in reader.pages)
    except ImportError:
        log.warning('PyPDF2 not installed. Run: pip install PyPDF2')
    except Exception as e:
        log.warning('PDF extract error: %s', e)
    return ''
