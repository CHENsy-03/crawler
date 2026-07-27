from collections import deque


class TaskQueue:
    def __init__(self):
        self._queue = deque()

    def push(self, task):
        task.setdefault('retry_count', 0)
        self._queue.append(task)

    def pop(self):
        return self._queue.popleft() if self._queue else None

    def size(self):
        return len(self._queue)

    def empty(self):
        return len(self._queue) == 0
