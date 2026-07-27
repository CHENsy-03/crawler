import time
import logging

log = logging.getLogger('crawler.circuit_breaker')


class CircuitBreaker:
    """熔断机制：连续失败>=3次->冷却60秒->自动恢复"""

    OPEN = 'OPEN'
    HALF_OPEN = 'HALF_OPEN'
    CLOSED = 'CLOSED'

    def __init__(self, failure_threshold=3, recovery_timeout=60, name='default'):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = self.CLOSED
        self.last_failure_time = 0
        self.name = name

    def call(self, func, *args, **kwargs):
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                log.info('[CB:%s] HALF_OPEN', self.name)
                self.state = self.HALF_OPEN
            else:
                raise RuntimeError(f'[CB:{self.name}] OPEN, cooling {self.recovery_timeout}s')
        try:
            result = func(*args, **kwargs)
            if self.state == self.HALF_OPEN:
                log.info('[CB:%s] Recovered', self.name)
                self.state = self.CLOSED
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            log.warning('[CB:%s] Fail %d/%d: %s', self.name,
                        self.failure_count, self.failure_threshold, str(e)[:60])
            if self.failure_count >= self.failure_threshold:
                log.warning('[CB:%s] OPEN', self.name)
                self.state = self.OPEN
            raise

    def reset(self):
        self.failure_count = 0
        self.state = self.CLOSED
