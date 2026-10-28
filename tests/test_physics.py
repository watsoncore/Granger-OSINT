import math

from grangerpet.physics import CollarPhysics


def test_deliberate_drag_never_counts_as_a_jerk():
    model = CollarPhysics()
    model.grab(100, 100, 0)
    for index in range(1, 120):
        now = index / 60
        assert model.sample(100 + now * 110, 100 - now * 80, now) is None
        pose = model.advance(1 / 60, now)
        assert pose.reaction == "held"
    assert abs(pose.angle) < 2
    assert pose.sag > 2


def test_real_fast_up_and_down_have_distinct_timed_reactions_and_recover():
    for direction, expected in ((-1, "jerk_up"), (1, "jerk_down")):
        model = CollarPhysics()
        model.grab(100, 100, 0)
        # Real Windows motion is a stream of short deltas, not the previous
        # artificial 55px jump in one message. Each delta here is only 8px.
        triggered = []
        for index in range(1, 13):
            reaction = model.sample(100, 100 + direction * 8 * index, index * .008)
            if reaction:
                triggered.append(reaction)
        assert triggered == [expected]
        for index in range(1, 15):
            pose = model.advance(1 / 60, .096 + index / 60)
        assert pose.upset > 0.8
        assert (pose.tuck if direction < 0 else pose.squash) > 0.8
        model.release(0.4)
        for index in range(1, 300):
            pose = model.advance(1 / 60, 0.4 + index / 60)
        assert pose.reaction == "calm"
        assert not model.active
        assert abs(pose.angle) < 0.1


def test_event_noise_or_pauses_do_not_create_spurious_acceleration():
    model = CollarPhysics()
    model.grab(0, 0, 0)
    assert model.sample(0, -5, 0.001) is None
    assert model.sample(0, -300, 0.5) is None
    assert model.sample(0, -301, 0.52) is None
    assert model.pose.reaction == "held"


def test_inertial_response_is_stable_at_different_render_rates():
    angles = []
    for fps in (8, 24, 60, 120):
        model = CollarPhysics()
        model.grab(0, 0, 0)
        model.sample(45, 0, 0.15)
        for index in range(fps):
            pose = model.advance(1 / fps, 0.15 + index / fps)
        assert math.isfinite(pose.angle)
        angles.append(pose.angle)
    assert max(angles) - min(angles) < 0.5


def test_single_coordinate_spike_cannot_trigger_a_directional_reaction():
    model = CollarPhysics()
    model.grab(0, 0, 0)
    assert model.sample(0, -80, .04) is None
    for index in range(1, 15):
        assert model.sample(0, -80, .04 + index * .01) is None
    assert model.pose.reaction == "held"


def test_click_emotion_has_own_lifetime_and_expires_without_a_drag():
    model = CollarPhysics()
    assert model.embarrass(10)
    for index in range(1, 20):
        pose = model.advance(.02, 10 + index * .02)
    assert pose.reaction == "embarrassed" and pose.embarrassed > .8
    for index in range(1, 130):
        pose = model.advance(.02, 10.4 + index * .02)
    assert pose.reaction == "calm" and not model.active
