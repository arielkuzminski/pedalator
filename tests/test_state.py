import time

from pedalator.state import PRESETS, apply_preset, clamp_grade, effective_grade, snapshot, state, throttle_for


def test_game_gradient_is_scaled_by_the_riding_mode():
    apply_preset("easy")
    state["game_grade"] = 10.0
    assert effective_grade() == 4.0                       # easy feels 40 % of the hills
    apply_preset("real")
    assert effective_grade() == 10.0


def test_manual_mode_ignores_the_game():
    state.update(mode="manual", manual_grade=6.0, game_grade=-8.0)
    assert effective_grade() == 6.0


def test_gradient_is_limited():
    assert clamp_grade(40) == 15.0 and clamp_grade(-40) == -15.0
    apply_preset("real")
    state["game_grade"] = 99
    assert effective_grade() == 15.0


def test_throttle_follows_power_gain_and_pmax():
    apply_preset("real")                                   # gain 1, pmax 250
    assert throttle_for(0) == 0 and throttle_for(10) == 0   # below the coasting floor
    assert throttle_for(125) == 0.5 and throttle_for(400) == 1.0
    apply_preset("easy")                                   # gain 2: full throttle from 125 W
    assert throttle_for(125) == 1.0


def test_presets_are_consistent():
    assert set(PRESETS) == {"easy", "medium", "real"}
    gains = [PRESETS[k][0] for k in ("easy", "medium", "real")]
    assert gains == sorted(gains, reverse=True)


def test_snapshot_has_ages_and_no_private_timestamps():
    s = snapshot()
    assert s["age_packet"] is None and "t_packet" not in s
    state["t_packet"] = time.time() - 3
    assert 2.5 < snapshot()["age_packet"] < 4


def test_smoothing_keeps_the_gas_through_a_short_dip_and_lets_go_after_it(monkeypatch):
    from pedalator import state as S
    now = [1000.0]
    monkeypatch.setattr(S.time, "monotonic", lambda: now[0])
    state["smooth"] = True
    assert throttle_for(100) == 0.8                       # pedalling: gain 2 x 100 W / 250
    now[0] += 0.5
    assert throttle_for(0) == 0.8                         # a dip between strokes: the gas stays
    assert throttle_for(10) == 0.8
    now[0] += 0.4
    assert throttle_for(0) == 0                           # 0.9 s without power: you stopped
    assert throttle_for(100) == 0.8                       # and it picks up again at once


def test_without_smoothing_the_gas_follows_every_reading(monkeypatch):
    from pedalator import state as S
    now = [1000.0]
    monkeypatch.setattr(S.time, "monotonic", lambda: now[0])
    state["smooth"] = False
    assert throttle_for(100) == 0.8
    now[0] += 0.1
    assert throttle_for(0) == 0


def test_a_new_ride_forgets_the_gas_of_the_last_one():
    from pedalator import state as S
    state["smooth"] = True
    throttle_for(100)
    S.reset_session()
    assert throttle_for(0) == 0
