import logging

from crawler.site.analyzer import SiteAnalyzer

log = logging.getLogger('crawler.detector')

CMS_SIGNATURES = {
    'trs_json': {'urls': ['/so/s', '/so/ss/query/s'], 'meta': ['siteCode', 'TRS'], 'headers': []},
    'jpaas_jsearch': {'urls': ['jpaas-jsearch', 'search.zj.gov.cn'], 'meta': ['websiteid', 'serviceId'], 'headers': ['JSESSIONID']},
    'html': {'urls': ['/search', '/s'], 'meta': [], 'headers': []},
}


class SiteDetector:
    """Compatibility entry point for the formal TASK-016 analyzer."""

    def __init__(self, downloader=None, analyzer=None):
        self.downloader = downloader
        self.analyzer = analyzer or SiteAnalyzer(downloader=downloader)

    def analyze(self, base_url):
        result = self.analyzer.analyze(base_url)
        scores = {}
        evidence = []
        detected = None
        for candidate in result.candidates:
            scores[candidate.source] = scores.get(candidate.source, 0) + 1
            evidence.extend(candidate.evidence[:2])
        if scores:
            detected = max(scores, key=scores.get)
        return {
            'base_url': base_url,
            'detected': detected,
            'scores': scores,
            'evidence': evidence[:20],
            'candidates': [c.to_dict() for c in result.candidates],
            'diagnostics': [d.to_dict() for d in result.diagnostics],
        }

    def auto_configure(self, base_url):
        a = self.analyze(base_url)
        return {
            'base_url': base_url,
            'detected_cms': a.get('detected', 'html'),
        }
