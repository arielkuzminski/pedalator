"""The new-game wizard: files out, a profile that works, and clear refusals."""
import json

import pytest

from pedalator import install, keys, newgame, profiles


@pytest.fixture(autouse=True)
def restore():
    yield
    profiles.set_user_dir(None)
    keys.apply_keys({"throttle": "Numpad8", "brake": "Numpad2", "left": "Numpad4", "right": "Numpad6", "use": "KeyE"})


def run(tmp_path, *argv):
    return install.main(["new-game", "--data-dir", str(tmp_path / "data"), *argv])


def test_keys_game_gets_a_working_profile_and_a_readme(tmp_path, capsys):
    out = tmp_path / "out"
    assert run(tmp_path, "--name", "Cool Bikes", "--how", "keys", "--key", "throttle=ArrowUp", "--out", str(out)) == 0
    p = json.loads((out / "cool-bikes.json").read_text(encoding="utf-8"))
    assert p["target"] == "keys" and p["keys"]["throttle"] == "ArrowUp" and p["keys"]["left"] == "KeyA"
    assert not (out / "listen.py").exists()
    assert "pedalator --profile cool-bikes --target keys" in (out / "README.md").read_text(encoding="utf-8")
    # the profile was saved for the user and passes the same checks as any other
    profiles.set_user_dir(tmp_path / "data" / "profiles")
    assert profiles.validate(profiles.load("cool-bikes"))[1] == []


def test_udp_game_gets_a_listener_and_a_lua_sketch(tmp_path):
    out = tmp_path / "udp"
    assert run(tmp_path, "--name", "Space Cycle", "--how", "udp", "--slope", "--out", str(out)) == 0
    assert (out / "listen.py").read_text(encoding="utf-8").startswith('"""Shows what Pedalator sends')
    lua = (out / "mod_sketch.lua").read_text(encoding="utf-8")
    assert "report_slope" in lua and "27100" in lua and "Space Cycle" in lua
    compile((out / "listen.py").read_text(encoding="utf-8"), "listen.py", "exec")
    no_slope = tmp_path / "udp2"
    assert run(tmp_path, "--name", "Flat Land", "--how", "udp", "--no-slope", "--out", str(no_slope)) == 0
    assert "report_slope" not in (no_slope / "mod_sketch.lua").read_text(encoding="utf-8")


def test_bad_input_is_refused_before_anything_is_written(tmp_path, capsys):
    out = tmp_path / "nope"
    assert run(tmp_path, "--name", "X", "--how", "keys", "--key", "throttle=Windows", "--out", str(out)) == 2
    assert run(tmp_path, "--name", "X", "--how", "keys", "--key", "jump=Space", "--out", str(out)) == 2
    assert not out.exists() and "not a known key name" in capsys.readouterr().out


def test_an_existing_profile_is_not_replaced_without_asking(tmp_path, capsys):
    assert run(tmp_path, "--name", "OMSI", "--how", "keys", "--out", str(tmp_path / "a")) == 2      # a built-in id
    assert "already exists" in capsys.readouterr().out
    assert run(tmp_path, "--name", "Mine", "--how", "keys", "--out", str(tmp_path / "b")) == 0
    assert run(tmp_path, "--name", "Mine", "--how", "keys", "--out", str(tmp_path / "b")) == 2
    assert run(tmp_path, "--name", "Mine", "--how", "keys", "--out", str(tmp_path / "b"), "--overwrite") == 0


def test_the_questions_can_be_answered_at_the_keyboard(tmp_path, monkeypatch):
    answers = iter(["Typed Game", "keys", "", "", "ArrowLeft", "", ])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert run(tmp_path, "--out", str(tmp_path / "typed")) == 0
    p = json.loads((tmp_path / "typed" / "typed-game.json").read_text(encoding="utf-8"))
    assert p["keys"] == {"throttle": "KeyW", "brake": "KeyS", "left": "ArrowLeft", "right": "KeyD"}


def test_udp_listener_template_really_receives_a_packet(tmp_path):
    """The generated listener must parse exactly what the udp target sends."""
    from pedalator.state import state
    from pedalator.targets import udp
    state.update(cadence=80.0, speed=20.0, grade=0.0)
    p = json.loads(udp.packet(1, 150, {"LEFT"}))
    assert {"move", "power", "turn", "buttons"} <= set(p)
    assert newgame.LISTENER.count("p['move']") == 1
