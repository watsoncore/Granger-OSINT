"""Small local idle-action scheduler; never performs network or tool operations.

The clock and random source are injectable for deterministic visual/regression
tests. Only interaction with the figure resets its idle clock.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import math
import random
import sys
import time


@dataclass(frozen=True)
class SceneSpec:
    duration: float
    weight: float
    idle: float
    cooldown: float
    work_weight: float = 1.0
    cameo: str = ''


SCENES = {
    'reading':SceneSpec(18,8,35,100,2.5),
    'wand_play':SceneSpec(8,3,45,180,.6),
    'shy':SceneSpec(5.5,3,45,220,.4),
    'annoyed':SceneSpec(4.5,2,45,240,.5),
    'phone_solvnox':SceneSpec(13,.8,360,1200,.7),
    'daydream':SceneSpec(9,.6,480,1500,.3),
    'malfoy':SceneSpec(10,.55,300,1800,.35,'draco'),
    'ron_chat':SceneSpec(8,.8,240,1200,.6,'ron'),
    'ron_note':SceneSpec(9,.8,240,1200,1.2,'ron'),
    'harry':SceneSpec(8,.8,240,1200,1.2,'harry'),
}
ACTIONS = tuple(SCENES)+('cast', 'avada', 'yawn', 'sleep', 'leave', 'away', 'return', 'wake', 'settle')


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
    phase: str = 'active'
    cameo: str = ''
    variant: int = 0


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
        self.last_played = {}
        self.last_cameo = now
        self.born = now
        self.variant = 0

    @property
    def active(self):
        return bool(self.action)

    def start_action(self, name, now=None, *, duration=None, replace=False, variant=None):
        if name not in ACTIONS:
            raise ValueError('Unknown local pet action')
        now = self.clock() if now is None else float(now)
        if self.active and not replace:return self.action
        variants={'reading':3,'shy':3,'annoyed':3,'wand_play':4,'malfoy':2,'harry':2,'ron_chat':2}
        count=variants.get(name,1)
        if variant is not None and (isinstance(variant,bool) or not isinstance(variant,int) or not 0<=variant<count):
            raise ValueError('Invalid local scene variant')
        defaults = {'reading': self.rng.uniform(16, 34), 'cast': 2.5, 'avada': 3.2,
                    'yawn': 2.1, 'sleep': self.rng.uniform(45, 100), 'leave': 2.8,
                    'away': self.rng.uniform(4, 9), 'return': 1.6, 'wake': .65, 'settle': .3}
        defaults.update({name:spec.duration for name,spec in SCENES.items()})
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not .1 <= duration <= 180):
            raise ValueError('Invalid local action duration')
        self.previous, self.action, self.started = self.action, name, now
        self.duration = float(defaults[name] if duration is None else duration)
        self.variant=self.rng.randrange(count) if variant is None else variant
        self.last_played[name]=now
        if name in SCENES and SCENES[name].cameo:self.last_cameo=now
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
            self.start_action('return', now, duration=.45 if immediate else .8,replace=True)
            self._return_from = current
        elif self.action == 'return':
            return  # Do not restart the return on every active-user timer tick.
        elif self.action in ('sleep', 'yawn'):
            self.start_action('wake', now, duration=.25 if immediate else .65,replace=True)
        elif self.action not in ('wake', 'settle'):
            self.start_action('settle', now, duration=.2 if immediate else .3,replace=True)
        if immediate and self.action not in ('return',):
            # User dragging/searching must never wait for a decorative pose.
            self.finish(now)

    def finish(self, now=None):
        now = self.clock() if now is None else float(now)
        self.previous, self.action = self.action, ''
        self.duration = 0
        self.next_due = now + self.rng.uniform(45, 110)

    def update(self, now=None, *, available=True, system_idle=None, context='chat', allow_travel=True, allow_cameo=True):
        now = self.clock() if now is None else float(now)
        # system_idle remains an ignored compatibility argument for old callers.
        # Windows input, typing and scrolling never reset figure-relative idle.
        if not available and self.active:
            # Suppression/mandatory animation may stop a scene, but cannot
            # invent a figure touch or keep postponing an idle deadline.
            last_touch=self.last_activity
            self.notify_activity(now, immediate=True)
            self.last_activity=last_touch
        if self.active and now - self.started >= self.duration:
            current = self.action
            following = {'yawn': 'sleep', 'leave': 'away', 'away': 'return', 'sleep': 'wake'}
            if current in following and available:
                self.start_action(following[current], now,replace=True)
                if self.action == 'return':
                    self._return_from = 1.0
            else:
                self.finish(now)
        if self.active or not available or now < self.next_due:
            return self.pose(now)
        idle = now - self.last_activity
        choices=[];weights=[]
        for name,spec in SCENES.items():
            if name==self.last_action or idle<spec.idle or now-self.last_played.get(name,-float('inf'))<spec.cooldown:continue
            if spec.cameo and (not allow_cameo or now-self.last_cameo<720):continue
            choices.append(name);weights.append(spec.weight*(spec.work_weight if context=='working' else 1))
        if choices:
            self.start_action(self.rng.choices(choices,weights=weights,k=1)[0], now)
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
        if self.action in SCENES:
            strength = min(1.0, elapsed / .65, max(0.0, (self.duration-elapsed) / .6))
        elif self.action == 'settle':
            strength = 1 - smooth
        elif self.action == 'wake':
            strength = 1 - smooth
        fps = 24 if self.action=='reading' else 8 if self.action in ('sleep', 'away') else 12
        phase='enter' if elapsed<.65 else 'exit' if self.duration-elapsed<.6 else 'active'
        cameo=SCENES[self.action].cameo if self.action in SCENES else ''
        return LifePose(self.action, self.previous, progress, elapsed, max(0.0, strength), int(elapsed*fps), travel,phase,cameo,self.variant)
