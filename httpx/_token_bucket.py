import time


class RateLimiter:
    """令牌桶算法限流器"""

    def __init__(self, rate=5, per=1):
        self.rate = float(rate)
        self.per = float(per)
        self.allowance = self.rate
        self.last_check = time.time()

    def acquire(self, block=True):
        now = time.time()
        elapsed = now - self.last_check
        self.last_check = now
        self.allowance += elapsed * (self.rate / self.per)
        if self.allowance > self.rate:
            self.allowance = self.rate
        if self.allowance < 1:
            if block:
                sleep_time = (1 - self.allowance) * (self.per / self.rate)
                time.sleep(sleep_time)
                self.allowance = 0
            return False
        self.allowance -= 1
        return True

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        pass
