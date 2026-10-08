import asyncio
import time

from pedalator.difficulty import apply_step, difficulty_loop, stepped
from pedalator.state import apply_preset, current_notice, snapshot, state
from pedalator.targets import openmw


def test_steps_are_a_tenth_and_stay_between_zero_and_one():
    assert stepped(0.4, 1) == 0.5 and stepped(0.4, -1) == 0.3
    assert stepped(1.0, 1) == 1.0 and stepped(0.0, -1) == 0.0
    v = 0.0
    for _ in range(10):
        v = stepped(v, 1)
    assert v == 1.0                                         # ten presses, no float drift


def test_a_step_changes_the_mode_to_custom_and_tells_the_rider():
    apply_preset("easy")                                    # 40 %
    apply_step(1)
    assert state["difficulty"] == 0.5 and state["preset"] == "custom"
    assert current_notice() == "difficulty:50"
    assert snapshot()["notice"] == "difficulty:50"
    assert "t_notice" not in snapshot()


def test_at_the_limit_the_rider_is_still_told():
    state["difficulty"] = 1.0
    apply_step(1)
    assert state["difficulty"] == 1.0 and current_notice() == "difficulty:100"


def test_a_notice_fades_after_a_few_seconds():
    apply_step(1)
    state["t_notice"] = time.time() - 4
    assert current_notice() == "" and snapshot()["notice"] == ""


def test_the_loop_steps_once_per_press_then_repeats_while_held():
    apply_preset("real")                                    # 100 %
    state["difficulty"] = 0.5

    async def scenario():
        task = asyncio.create_task(difficulty_loop())
        state.update(raw=["MINUS"], t_buttons=time.time())
        await asyncio.sleep(0.3)
        assert state["difficulty"] == 0.4                   # one press = one step
        for _ in range(8):                                  # the phone page repeats the state while a button is held
            state["t_buttons"] = time.time()
            await asyncio.sleep(0.2)
        held = state["difficulty"]
        assert held <= 0.2                                  # holding repeats (0.5 s, then every 0.25 s)
        state.update(raw=[], t_buttons=time.time())
        await asyncio.sleep(0.2)
        state.update(raw=["PLUS"], t_buttons=time.time())    # a new press steps again
        await asyncio.sleep(0.3)
        assert state["difficulty"] == round(held + 0.1, 2)
        task.cancel()

    asyncio.run(scenario())


def test_stale_buttons_do_nothing():
    state.update(difficulty=0.5, raw=["PLUS"], t_buttons=time.time() - 5)

    async def scenario():
        task = asyncio.create_task(difficulty_loop())
        await asyncio.sleep(0.3)
        task.cancel()

    asyncio.run(scenario())
    assert state["difficulty"] == 0.5


def test_the_openmw_state_line_carries_the_difficulty_in_percent():
    state["difficulty"] = 0.7
    line = openmw.state_line(1, 0, set())
    assert line.strip().endswith("diff=70")
