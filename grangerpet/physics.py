"""Time-windowed drag measurement and transient emotions in Qt logical pixels."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

# Logical pixels / second, independent of monitor DPR and render frequency.
MOTION_WINDOW_SECONDS = 0.090
STALE_SAMPLE_SECONDS = 0.250
MIN_SAMPLE_SECONDS = 0.003
JERK_SPEED_PX_S = 560.0
JERK_FAST_SPEED_PX_S = 1000.0
JERK_DISTANCE_PX = 22.0
JERK_ACCELERATION_PX_S2 = 1800.0
MIN_DIRECTIONAL_SEGMENTS = 3
REACTION_SECONDS = 0.90
ANGRY_SECONDS = 2.10
EMBARRASSED_SECONDS = 1.55
TRIGGER_COOLDOWN_SECONDS = 0.58


@dataclass
class DragPose:
    angle: float = 0.0
    sag: float = 0.0
    tuck: float = 0.0
    squash: float = 0.0
    stretch: float = 0.0
    upset: float = 0.0
    embarrassed: float = 0.0
    leg_swing: float = 0.0
    held: bool = False
    reaction: str = "calm"


class CollarPhysics:
    """Emotions overlay the existing activity; they never start/cancel a search."""
    def __init__(self, trace=None):
        self.pose = DragPose()
        self.trace = trace
        self._history = deque(maxlen=80)
        self._accelerations = deque(maxlen=40)
        self._last = None
        self._velocity = (0.0, 0.0)
        self._angle_velocity = 0.0
        self._trigger_after = 0.0
        self._upset_until = 0.0
        self._release_time = -10.0
        self._reaction_until = 0.0
        self._embarrassed_until = 0.0
        self._direction_reaction = ""
        self._last_reaction = "calm"
        self.last_measurement = {}
        self.last_transition = {}

    def _record(self, event, now, **values):
        if self.trace:
            self.trace({"event": event, "time_s": now, **values})

    def _state(self, state, now, reason):
        if self.pose.reaction != state:
            old = self.pose.reaction
            self.pose.reaction = state
            self.last_transition = {"from": old, "to": state, "time_s": now, "reason": reason}
            self._record("reaction", now, **self.last_transition)

    def grab(self, x, y, now):
        self.pose.held = True
        self._history.clear()
        self._accelerations.clear()
        self._history.append((float(x), float(y), float(now)))
        self._last = (float(x), float(y), float(now))
        self._velocity = (0.0, 0.0)
        self._trigger_after = now
        self._embarrassed_until = 0.0
        self._state("held", now, "collar_pressed")
        self._record("grab", now, x_px=x, y_px=y)

    @staticmethod
    def _slope(history, axis):
        # Least-squares slope over several real samples suppresses quantization
        # without requiring a physically unrealistic jump in one mouse message.
        mean_t = sum(item[2] for item in history) / len(history)
        mean_v = sum(item[axis] for item in history) / len(history)
        denominator = sum((item[2] - mean_t) ** 2 for item in history)
        return sum((item[2] - mean_t) * (item[axis] - mean_v) for item in history) / denominator if denominator > 1e-10 else 0.0

    def sample(self, x, y, now, source="mouse_event"):
        if not self.pose.held or self._last is None:
            return None
        x, y, now = float(x), float(y), float(now)
        dt = now - self._last[2]
        if dt < MIN_SAMPLE_SECONDS:
            return None
        if dt > STALE_SAMPLE_SECONDS:
            self._history.clear()
            self._accelerations.clear()
            self._velocity = (0.0, 0.0)
        previous_velocity = self._velocity
        self._history.append((x, y, now))
        # An old press sample separated by a pause must not dilute a fresh
        # acceleration burst for the entire window. Retain two points minimum.
        while len(self._history) > 2 and self._history[0][2] < now - MOTION_WINDOW_SECONDS:
            self._history.popleft()
        vx = self._slope(self._history, 0)
        vy = self._slope(self._history, 1)
        ay = (vy - previous_velocity[1]) / max(dt, MIN_SAMPLE_SECONDS)
        self._velocity = (vx, vy)
        self._accelerations.append((now, ay))
        while self._accelerations and self._accelerations[0][0] < now - MOTION_WINDOW_SECONDS:
            self._accelerations.popleft()
        displacement = y - self._history[0][1]
        span = now - self._history[0][2]
        direction = -1 if vy < 0 else 1
        segments = [b[1] - a[1] for a, b in zip(self._history, list(self._history)[1:])]
        moving = [delta for delta in segments if abs(delta) >= 0.35]
        directional = sum(delta * direction > 0 for delta in moving)
        peak_acceleration = max((value * direction for _, value in self._accelerations), default=0.0)
        self.last_measurement = {
            "x_px": x, "y_px": y, "dt_s": dt, "window_s": span,
            "velocity_x_px_s": vx, "velocity_y_px_s": vy,
            "acceleration_y_px_s2": ay, "peak_acceleration_px_s2": peak_acceleration,
            "displacement_y_px": displacement, "samples": len(self._history),
            "direction": "up" if vy < 0 else "down" if vy > 0 else "still",
            "source": source, "held": True,
        }
        self._record("sample", now, **self.last_measurement)
        reaction = None
        consistent = directional >= MIN_DIRECTIONAL_SEGMENTS and directional >= len(moving) * 0.75
        sharp = abs(vy) >= JERK_SPEED_PX_S and (peak_acceleration >= JERK_ACCELERATION_PX_S2 or abs(vy) >= JERK_FAST_SPEED_PX_S)
        if now >= self._trigger_after and span >= 0.024 and consistent and abs(displacement) >= JERK_DISTANCE_PX and sharp:
            reaction = "jerk_up" if vy < 0 else "jerk_down"
            self._direction_reaction = reaction
            self._reaction_until = now + REACTION_SECONDS
            self._upset_until = now + ANGRY_SECONDS
            self._trigger_after = now + TRIGGER_COOLDOWN_SECONDS
            self._embarrassed_until = 0.0
            self._state(reaction, now, "windowed_speed_distance_acceleration")
            self._record("trigger", now, reaction=reaction, duration_s=REACTION_SECONDS, **self.last_measurement)
        self._last = (x, y, now)
        return reaction

    def release(self, now, reason="mouse_released"):
        self.pose.held = False
        self._release_time = now
        self._last = None
        self._history.clear()
        self._velocity = (0.0, 0.0)
        self._record("release", now, reason=reason, reaction=self.pose.reaction)
        if now >= self._upset_until:
            self._state("settling", now, reason)

    def embarrass(self, now):
        if self.pose.held or now < self._upset_until:
            return False
        self._embarrassed_until = now + EMBARRASSED_SECONDS
        self._state("embarrassed", now, "short_click_without_drag")
        self._record("trigger", now, reaction="embarrassed", duration_s=EMBARRASSED_SECONDS)
        return True

    def advance(self, dt, now):
        dt = max(0.0, min(dt, 0.25))
        if now < self._reaction_until:
            self._state(self._direction_reaction, now, "directional_reaction_running")
        elif now < self._upset_until:
            self._state("angry", now, "directional_pose_finished_angry_hold")
        elif self.pose.held:
            self._state("held", now, "reaction_expired_while_held")
        elif now < self._embarrassed_until:
            self._state("embarrassed", now, "soft_click_reaction_running")
        elif now - self._release_time < 0.7:
            self._state("settling", now, "released_stabilizing")
        else:
            self._state("calm", now, "reaction_expired_return_to_activity")
        desired_angle = max(-16.0, min(16.0, -self._velocity[0] * 0.009)) if self.pose.held else 0.0
        steps = max(1, math.ceil(dt * 120))
        step = dt / steps
        for _ in range(steps):
            force = (desired_angle - self.pose.angle) * 56 - self._angle_velocity * 10
            self._angle_velocity += force * step
            self.pose.angle = max(-20.0, min(20.0, self.pose.angle + self._angle_velocity * step))
        up = 1.0 if self.pose.reaction == "jerk_up" else 0.0
        down = 1.0 if self.pose.reaction == "jerk_down" else 0.0
        follow = 1 - math.exp(-dt * 14)
        targets = {
            "tuck": up, "squash": down, "stretch": up,
            "upset": float(now < self._upset_until),
            "embarrassed": float(now < self._embarrassed_until and now >= self._upset_until),
            "sag": 3.5 if self.pose.held else 0.0,
            "leg_swing": max(-1.0, min(1.0, self._velocity[0] / 500)) if self.pose.held else 0.0,
        }
        for name, target in targets.items():
            setattr(self.pose, name, getattr(self.pose, name) + (target - getattr(self.pose, name)) * follow)
        return self.pose

    @property
    def active(self):
        pose = self.pose
        return pose.held or abs(pose.angle) > 0.05 or pose.sag > 0.03 or max(pose.upset, pose.embarrassed, pose.tuck, pose.squash) > 0.01
