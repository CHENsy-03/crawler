import hashlib
import random


class UAPool:
    """UA绑定Session机制：每个域名绑定固定UA，不每次随机"""

    UA_LIST = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Edg/131.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.1 Safari/605.1.15',
    ]

    def __init__(self):
        self._domain_ua = {}

    def get_for_domain(self, domain):
        if domain not in self._domain_ua:
            idx = int(hashlib.md5(domain.encode()).hexdigest(), 16) % len(self.UA_LIST)
            self._domain_ua[domain] = self.UA_LIST[idx]
        return self._domain_ua[domain]

    def get_random(self):
        return random.choice(self.UA_LIST)
