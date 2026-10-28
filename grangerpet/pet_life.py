"""Small local idle-action scheduler; never performs network or tool operations.

The clock and random source are injectable for deterministic visual/regression
tests. Application activity takes priority over every autonomous action.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import math
import random
import sys
import time


ACTIONS = ('reading', 'cast', 'avada', 'yawn', 'sleep', 'leave', 'away', 'return', 'wake', 'settle')


def windows_idle_seconds():
    """Only elapsed Windows input inactivity; no keys, window names or content."""
    if sys.platform != 'win32':
        return None
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
    try:
        user, kernel = ctypes.WinDLL('user32'), ctypes.WinDLL('kernel32')
        info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
        if not user.GetLastInputInfo(ctypes.byref(info)):
            return None
        kernel.GetTickCount64.restype = ctypes.c_ulonglong
        return ((kernel.GetTickCount64() & 0xffffffff) - info.dwTime) % (2**32) / 1000.0
    except (OSError, AttributeError):
        return None


@dataclass(frozen=True)
class LifePose:
    action: str
    previous: str
    progress: float
    elapsed: float
    strength: float
    frame: int
    travel: float


class PetLifeController:
    """Natural local actions with bounded durations and interruptible transitions."""
    def __init__(self, *, clock=None, rng=None):
        self.clock, self.rng = clock or time.monotonic, rng or random.Random()
        now = self.clock()
        self.action, self.previous = '', ''
        self.started = self.last_activity = now
        self.duration = 0.0
        self.next_due = now + self.rng.uniform(45, 95)
        self.last_action = ''
        self.last_avada = -float('inf')
        self._return_from = 1.0
        self._last_system_idle = None

    @property
    def active(self):
        return bool(self.action)

    def start_action(self, name, now=None, *, duration=None):
        if name not in ACTIONS:
            raise ValueError('Unknown local pet action')
        now = self.clock() if now is None else float(now)
        defaults = {'reading': self.rng.uniform(16, 34), 'cast': 2.5, 'avada': 3.2,
                    'yawn': 2.1, 'sleep': self.rng.uniform(45, 100), 'leave': 2.8,
                    'away': self.rng.uniform(4, 9), 'return': 1.6, 'wake': .65, 'settle': .3}
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not .1 <= duration <= 180):
            raise ValueError('Invalid local action duration')
        self.previous, self.action, self.started = self.action, name, now
        self.duration = float(defaults[name] if duration is None else duration)
        if name == 'avada':
            self.last_avada = now
        if name not in ('away', 'return', 'wake', 'settle'):
            self.last_action = name
        return name

    def notify_activity(self, now=None, *, immediate=False):
        now = self.clock() if now is None else float(now)
        self.last_activity = now
        self.next_due = max(self.next_due, now + self.rng.uniform(40, 90))
        if not self.active:
            return
        if self.action in ('leave', 'away'):
            current = self.pose(now).travel
            self.start_action('return', now, duration=.45 if immediate else .8)
            self._return_from = current
        elif self.action == 'return':
            return  # Do not restart the return on every active-user timer tick.
        elif self.action in ('sleep', 'yawn'):
            self.start_action('wake', now, duration=.25 if immediate else .65)
        elif self.action not in ('wake', 'settle'):
            self.start_action('settle', now, duration=.2 if immediate else .3)
        if immediate and self.action not in ('return',):
            # User dragging/searching must never wait for a decorative pose.
            self.finish(now)

    def finish(self, now=None):
        now = self.clock() if now is None else float(now)
        self.previous, self.action = self.action, ''
        self.duration = 0
        self.next_due = now + self.rng.uniform(45, 110)

    def update(self, now=None, *, available=True, system_idle=None):
        now = self.clock() if now is None else float(now)
        if system_idle is not None:
            if self._last_system_idle is not None and system_idle + .25 < self._last_system_idle:
                self.notify_activity(now)
            self._last_system_idle = max(0.0, system_idle)
        if not available:
            self.notify_activity(now, immediate=True)
        if self.active and now - self.started >= self.duration:
            current = self.action
            following = {'yawn': 'sleep', 'leave': 'away', 'away': 'return', 'sleep': 'wake'}
            if current in following and available:
                self.start_action(following[current], now)
                if self.action == 'return':
                    self._return_from = 1.0
            else:
                self.finish(now)
        if self.active or not available or now < self.next_due:
            return self.pose(now)
        idle = now - self.last_activity
        if system_idle is not None:
            idle = min(idle, system_idle)
        choices = ['reading'] if idle >= 35 else []
        if idle >= 45:
            choices += ['cast']
        if idle >= 180:
            choices += ['leave']
        if idle >= 240:
            choices += ['yawn', 'yawn']
        if idle >= 60 and now - self.last_avada >= 1800 and self.rng.random() < .035:
            choices = ['avada']
        if choices:
            alternate = [name for name in choices if name != self.last_action]
            self.start_action(self.rng.choice(alternate or choices), now)
        else:
            self.next_due = now + self.rng.uniform(15, 35)
        return self.pose(now)

    def pose(self, now=None):
        now = self.clock() if now is None else float(now)
        elapsed = max(0.0, now - self.started)
        progress = min(1.0, elapsed / self.duration) if self.duration else 0.0
        smooth = progress * progress * (3 - 2 * progress)
        travel = smooth if self.action == 'leave' else 1.0 if self.action == 'away' else self._return_from * (1 - smooth) if self.action == 'return' else 0.0
        strength = 1.0
        if self.action == 'reading':
            strength = min(1.0, elapsed / .65, max(0.0, (self.duration-elapsed) / .6))
        elif self.action == 'settle':
            strength = 1 - smooth
        elif self.action == 'wake':
            strength = 1 - smooth
        fps = 8 if self.action in ('sleep', 'away') else 12
        return LifePose(self.action, self.previous, progress, elapsed, max(0.0, strength), int(elapsed*fps), travel)
