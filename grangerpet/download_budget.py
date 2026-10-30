"""Task-scoped decoded HTTP response budget for repository-owned transports."""
from contextvars import ContextVar
import threading

CURRENT = ContextVar('granger_download_budget', default=None)


class DownloadLimit(RuntimeError):
    code = 'download_limit'


class DownloadBudget:
    def __init__(self, limit=20 * 1024 * 1024):
        self.limit, self.used = max(0, int(limit)), 0
        self._lock = threading.RLock()
    def consume(self, count):
        with self._lock:
            self.used += count
            if self.limit and self.used > self.limit:
                raise DownloadLimit('Достигнут бюджет полученных данных источников.')
    def check(self):
        with self._lock:
            if self.limit and self.used >= self.limit:
                raise DownloadLimit('Достигнут бюджет полученных данных источников.')
    def snapshot(self):
        with self._lock:
            return {'used_bytes': self.used, 'limit_bytes': self.limit or None,
                'coverage': 'repository_owned_HTTP_decoded_bodies', 'legacy_CLI_metered': False}


def consume(count):
    budget = CURRENT.get()
    if budget is not None:
        budget.consume(count)


def check():
    budget = CURRENT.get()
    if budget is not None:
        budget.check()
