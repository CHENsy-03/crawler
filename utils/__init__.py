import time
import uuid
import logging
from contextlib import contextmanager
import json
import os

log = logging.getLogger('crawler.utils')


class ErrorStats:
    """Error classification counters."""
    def __init__(self):
        self.network = 0
        self.rate_limit = 0
        self.parse = 0
        self.config = 0
        self.unknown = 0

    def record(self, exc):
        msg = str(exc).lower()
        if any(k in msg for k in ('timeout', 'connection', 'dns', 'refused')):
            self.network += 1
        elif any(k in msg for k in ('429', 'rate', 'too many', 'throttl')):
            self.rate_limit += 1
        elif any(k in msg for k in ('parse', 'json', 'syntax', 'decode')):
            self.parse += 1
        elif any(k in msg for k in ('config', 'key', 'missing', 'not found')):
            self.config += 1
        else:
            self.unknown += 1

    def summary(self):
        return 'network=%d rate_limit=%d parse=%d config=%d unknown=%d' % (
            self.network, self.rate_limit, self.parse, self.config, self.unknown)

    @property
    def total(self):
        return self.network + self.rate_limit + self.parse + self.config + self.unknown


class Metrics:
    def __init__(self):
        self.requests = {'total': 0, 'success': 0, 'failed': 0}
        self.articles = {'found': 0, 'scored': 0, 'saved': 0, 'detail_fetched': 0, 'detail_skipped': 0}
        self.error_counts = {'network': 0, 'rate_limit': 0, 'parse': 0, 'config': 0, 'unknown': 0}

    @property
    def success_rate(self):
        if self.requests['total'] == 0: return 1.0
        return self.requests['success'] / self.requests['total']

    @property
    def score_pass_rate(self):
        if self.articles['found'] == 0: return 0.0
        return self.articles['scored'] / self.articles['found']

    @property
    def detail_hit_rate(self):
        total = self.articles['detail_fetched'] + self.articles['detail_skipped']
        if total == 0: return 0.0
        return self.articles['detail_fetched'] / total

    def summary(self, timings=None):
        lines = ['  articles: found=%d scored=%d saved=%d' % (
            self.articles['found'], self.articles['scored'], self.articles['saved'])]
        lines.append('  rates: score_pass=%.0f%% detail_hit=%.0f%%' % (
            self.score_pass_rate * 100, self.detail_hit_rate * 100))
        if self.requests['total'] > 0:
            lines.append('  http: total=%d success=%d failed=%d (success_rate=%.0f%%)' % (
                self.requests['total'], self.requests['success'], self.requests['failed'],
                self.success_rate * 100))
        total_err = sum(self.error_counts.values())
        if total_err > 0:
            err_str = ' '.join('%s=%d' % (k, v) for k, v in self.error_counts.items() if v > 0)
            lines.append('  errors: %s' % err_str)
        return '\n'.join(lines)


class RequestContext:
    """Per-request tracing: ID, timing, error stats."""

    def __init__(self, site_name=''):
        self.request_id = uuid.uuid4().hex[:8]
        self.site_name = site_name
        self.start_time = time.time()
        self.timings = {}
        self.errors = ErrorStats()
        self.metrics = Metrics()

    def elapsed(self):
        return time.time() - self.start_time

    def fmt(self, msg):
        return '[req:%s] %s' % (self.request_id, msg)

    @contextmanager
    def timed(self, label):
        t0 = time.time()
        try:
            yield
        finally:
            self.timings[label] = time.time() - t0
            log.info(self.fmt('%s: %.1fs'), label, self.timings[label])
            if label == 'detail':
                self.metrics.requests['total'] += 1
                self.metrics.requests['success'] += 1  # simplified

    def summary(self):
        lines = [
            self.fmt('===== STATS ====='),
            self.metrics.summary(self.timings),
        ]
        if self.timings:
            timing_str = ' | '.join('%s=%.1fs' % (k, v) for k, v in self.timings.items())
            lines.append(self.fmt('  timing: %s | total=%.1fs' % (timing_str, self.elapsed())))
        if self.errors.total > 0:
            lines.append(self.fmt('  errors: %s' % self.errors.summary()))
        lines.append(self.fmt('===== DONE ====='))
        return '\n'.join(lines)
