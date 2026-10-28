"""Read-only balance for the explicitly configured gateway, without generation.

The vendor field token_balance has no verified denomination documentation.
Its value is displayed verbatim as gateway units, never as model tokens/money.
No response bodies, headers, keys or account data are logged or persisted.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import threading
import time

import httpx

from .agent_evidence import utc_now
from .ai_keys import DEEPSEEK_BASE_URL, resolve_deepseek_key


BALANCE_URL = DEEPSEEK_BASE_URL + '/balance'
UNKNOWN = {'status': 'unknown', 'amount': None, 'unit': None,
           'label': 'Баланс шлюза', 'updated_at': None,
           'message': 'Баланс ещё не запрошен.', 'error': ''}


def balance_error(status=None, *, timeout=False):
    if timeout:
        return 'Шлюз не ответил на запрос баланса вовремя.'
    return {
        401: 'Шлюз отклонил API-ключ. Проверьте ключ в настройках ИИ.',
        402: 'Шлюз требует оплату. Остаток не получен.',
        403: 'Ключу запрещён доступ к балансу шлюза.',
        404: 'Endpoint баланса отсутствует у шлюза.',
        429: 'Шлюз ограничил запросы баланса. Повторите позже.',
    }.get(status, 'Баланс шлюза временно недоступен. Обычный чат работает независимо.')


def fetch_balance(key=None, *, transport=None):
    key = resolve_deepseek_key() if key is None else key
    if not key:
        return {**UNKNOWN, 'status': 'not_configured', 'message': 'Сначала сохраните API-ключ шлюза.'}
    try:
        with httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False,
                          trust_env=False, transport=transport) as client:
            with client.stream('GET', BALANCE_URL, headers={
                    'Authorization': 'Bearer ' + key, 'Accept': 'application/json',
                    'User-Agent': 'Granger-OSINT/3.1'}) as response:
                if response.status_code != 200:
                    return {**UNKNOWN, 'status': 'unavailable', 'error': balance_error(response.status_code),
                            'http_status': response.status_code, 'message': 'Остаток не получен.'}
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65_536:
                        raise ValueError('oversize')
        payload = json.loads(bytes(body))
        if not isinstance(payload, dict) or isinstance(payload.get('token_balance'), bool):
            raise ValueError('shape')
        value = payload.get('token_balance')
        if not isinstance(value, (str, int, float)) or len(str(value)) > 64:
            raise ValueError('amount')
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('1e30') or amount.as_tuple().exponent < -18:
            raise ValueError('amount')
        return {**UNKNOWN, 'status': 'available', 'amount': format(amount, 'f'),
                'unit': 'gateway_units', 'label': 'Единицы шлюза (token_balance)',
                'field': 'token_balance', 'updated_at': utc_now(),
                'message': 'Шлюз вернул остаток token_balance. Его соответствие токенам модели или валюте не документировано.'}
    except httpx.TimeoutException:
        return {**UNKNOWN, 'status': 'unavailable', 'error': balance_error(timeout=True)}
    except (httpx.HTTPError, OSError):
        return {**UNKNOWN, 'status': 'unavailable', 'error': balance_error()}
    except (ValueError, TypeError, InvalidOperation, UnicodeError):
        return {**UNKNOWN, 'status': 'invalid_response',
                'error': 'Шлюз вернул неизвестный формат баланса. Пересчёт не выполнялся.'}


class GatewayBalance:
    """Per-window RAM cache; independent from usage and AI connection state."""
    def __init__(self):
        self.value = dict(UNKNOWN)
        self._identity = None
        self._requested_at = 0.0
        self._lock = threading.Lock()

    def prepare(self, key, *, force=False):
        identity = hashlib.sha256(key.encode('utf-8')).digest() if key else None
        with self._lock:
            if identity != self._identity:
                self.value = dict(UNKNOWN)
                self._identity, self._requested_at = identity, 0
            if self.value['status'] == 'checking' or (not force and time.monotonic() - self._requested_at < 60):
                return False
            # A manual click also has a short cooldown, never one HTTP call per
            # snapshot/stream delta. Failed requests are cached as well.
            if time.monotonic() - self._requested_at < 10:
                return False
            self._requested_at = time.monotonic()
            self.value = {**self.value, 'status': 'checking', 'error': ''}
            return True

    def finish(self, value):
        with self._lock:
            # Preserve the last successful amount/time on transient failures,
            # explicitly mark it stale rather than making it a current balance.
            if value.get('status') != 'available' and self.value.get('updated_at'):
                self.value.update(status=value.get('status', 'unavailable'),
                                  error=value.get('error', ''), message=value.get('message', ''), stale=True)
            else:
                self.value = dict(value)

    def cancel_pending(self):
        with self._lock:
            if self.value.get('status')=='checking':
                self.value.update(status='unknown', error='', message='Запрос баланса отменён.')
                if self.value.get('updated_at'):self.value['stale']=True
            self._requested_at=0

    def snapshot(self):
        with self._lock:
            return dict(self.value)
