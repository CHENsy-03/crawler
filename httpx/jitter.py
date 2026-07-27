import random
import time


def jitter_sleep(base_delay=1.5, jitter=0.8):
    """随机延迟：sleep = base_delay + random(0, jitter)"""
    delay = max(0.0, base_delay + random.uniform(0, jitter))
    if delay > 0:
        time.sleep(delay)
    return delay


def get_jitter_value(base_delay=1.5, jitter=0.8):
    """返回延迟值但不sleep，供调用方自行决定何时sleep"""
    return max(0.0, base_delay + random.uniform(0, jitter))
