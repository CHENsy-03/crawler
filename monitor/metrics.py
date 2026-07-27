import threading


class MetricsCollector:
    """Prometheus-style metrics collector with counter/gauge/histogram."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters = {}
        self._gauges = {}
        self._histograms = {}

    def inc(self, name, value=1, labels=None):
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def set(self, name, value, labels=None):
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name, value, labels=None):
        key = self._key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)

    def _key(self, name, labels):
        if labels:
            return name + '{' + ','.join(f'{k}={v}' for k, v in sorted(labels.items())) + '}'
        return name

    def dump_prometheus(self):
        lines = []
        with self._lock:
            for key, val in self._counters.items():
                base = key.split('{')[0]
                lines.append(f'# TYPE {base} counter')
                lines.append(f'{key} {val}')
            for key, val in self._gauges.items():
                base = key.split('{')[0]
                lines.append(f'# TYPE {base} gauge')
                lines.append(f'{key} {val}')
        return '\n'.join(lines) + '\n'

    def snapshot(self):
        with self._lock:
            return {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histogram_sizes': {k: len(v) for k, v in self._histograms.items()},
            }


_collector = MetricsCollector()


def get_collector():
    return _collector
