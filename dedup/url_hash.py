import hashlib
import logging

log = logging.getLogger('dedup.url_hash')


class UrlHashCache:
    """In-memory URL dedup using MD5 hash set. Lightweight, no disk I/O."""

    def __init__(self):
        self._seen = set()

    def is_duplicate(self, url):
        h = hashlib.md5(url.encode()).hexdigest()
        if h in self._seen:
            return True
        self._seen.add(h)
        return False

    def dedup_list(self, articles):
        result = []
        for a in articles:
            url = a.get('url', '')
            if url and not self.is_duplicate(url):
                result.append(a)
        return result

    def size(self):
        return len(self._seen)

    def clear(self):
        self._seen.clear()
