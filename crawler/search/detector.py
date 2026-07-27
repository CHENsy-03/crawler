import re
import logging
from urllib.parse import urljoin

log = logging.getLogger('crawler.detector')

CMS_SIGNATURES = {
    'trs_json': {'urls': ['/so/s', '/so/ss/query/s'], 'meta': ['siteCode', 'TRS'], 'headers': []},
    'jpaas_jsearch': {'urls': ['jpaas-jsearch', 'search.zj.gov.cn'], 'meta': ['websiteid', 'serviceId'], 'headers': ['JSESSIONID']},
    'html': {'urls': ['/search', '/s'], 'meta': [], 'headers': []},
}


class SiteDetector:
    def __init__(self, downloader=None):
        self.downloader = downloader

    def analyze(self, base_url):
        if not self.downloader:
            from crawler.core.downloader import get_downloader
            self.downloader = get_downloader()
        result = {'base_url': base_url, 'detected': None, 'scores': {}, 'evidence': []}
        try:
            resp = self.downloader.fetch(base_url, timeout=10)
            if not resp:
                return result
            html = resp.text
            headers = dict(resp.headers)
        except Exception as e:
            log.warning('fetch: %s', e)
            return result
        for cms, sig in CMS_SIGNATURES.items():
            score = 0
            ev = []
            for u in sig['urls']:
                if u in html:
                    score += 3
                    ev.append('url:' + u)
            for m in sig['meta']:
                if m.lower() in html.lower():
                    score += 2
                    ev.append('meta:' + m)
            for h in sig['headers']:
                if any(h.lower() in k.lower() for k in headers):
                    score += 1
                    ev.append('hdr:' + h)
            if score > 0:
                result['scores'][cms] = score
                result['evidence'].extend(ev)
        if result['scores']:
            best = max(result['scores'], key=result['scores'].get)
            result['detected'] = best
            log.info('Detector: %s -> %s', base_url, best)
        return result

    def auto_configure(self, base_url):
        a = self.analyze(base_url)
        return {
            'base_url': base_url,
            'detected_cms': a.get('detected', 'html'),
        }
