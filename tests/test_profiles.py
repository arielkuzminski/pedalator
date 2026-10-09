"""Profiles: the model, validation, storage, import/export, and that remapping really changes what targets do."""
import asyncio
import copy
import json
import sys
import time

import pytest

from pedalator import difficulty, install, keynames, keys, profiles
from pedalator.cli import build_parser, choose_profile
from pedalator.state import state
from pedalator.targets import openmw


@pytest.fixture(autouse=True)
def user_profiles(tmp_path):
    profiles.set_user_dir(tmp_path / "profiles")
    yield tmp_path / "profiles"
    profiles.set_user_dir(None)
    keys.apply_keys({"throttle": "Numpad8", "brake": "Numpad2", "left": "Numpad4", "right": "Numpad6", "use": "KeyE"})


def morrowind() -> dict:
    return profiles.load("morrowind")


# ----------------------------------------------------------------------------------------------- the built-ins
@pytest.mark.parametrize("pid", profiles.builtin_ids())
def test_every_built_in_profile_is_valid(pid):
    p = profiles.load(pid)
    assert p["id"] == pid and p["target"] in profiles.TARGETS
    for slot in profiles.KEY_SLOTS[p["target"]]:
        assert keynames.is_key(p["keys"][slot])


def test_each_target_has_a_default():
    for target, pid in profiles.DEFAULT_ID.items():
        assert profiles.load(pid)["target"] == target


# ----------------------------------------------------------------------------------------------- validation
def bad(**changes):
    data = copy.deepcopy(morrowind())
    data.update(changes)
    return profiles.validate(data)[1]


def test_problems_are_explained_in_plain_words():
    assert any("target" in e for e in bad(target="minecraft"))
    assert any("unknown button" in e and "BANANA" in e for e in bad(bindings={"BANANA": "jump"}))
    assert any("not an action of the openmw target" in e for e in bad(bindings={"A": "steer_left"}))
    assert any("not a known key name" in e for e in bad(keys={"use": "Windows"}))
    assert any("not a key of the openmw target" in e for e in bad(keys={"throttle": "KeyW"}))
    assert any("turn_rate must be a number" in e for e in bad(options={"turn_rate": 99}))
    assert any("run_above" in e for e in bad(options={"run_above": "high"}))
    assert any("options.use_speed_attribute must be true or false" in e for e in bad(options={"use_speed_attribute": 1}))
    assert any("ride.mode" in e for e in bad(ride={"mode": "insane"}))
    assert any("ride.gain" in e for e in bad(ride={"gain": 100}))
    assert any("id must be" in e for e in bad(id="Bad Id!"))
    assert any("newer" in e or "version 9" in e for e in bad(version=9))
    assert profiles.validate([1, 2])[1] == ["a profile must be a JSON object"]


def test_a_hand_written_file_is_filled_in():
    p, errors = profiles.validate({"target": "keys", "name": "My game", "bindings": {"A": "brake", "B": "none"}}, fill_keys=True)
    assert errors == [] and p["id"] == "my-game"
    assert p["keys"] == {"throttle": "Numpad8", "brake": "Numpad2", "left": "Numpad4", "right": "Numpad6"}
    assert p["bindings"] == {"A": "brake"}                      # "none" means unbound


def test_unknown_things_in_a_profile_are_errors_not_silently_dropped():
    assert profiles.validate({"target": "udp", "name": "x", "options": {"turn_rate": 1}})[1]


# ----------------------------------------------------------------------------------------------- storage
def test_save_load_list_delete_roundtrip(user_profiles):
    p = morrowind()
    p.update(id="mine", name="My Morrowind")
    p["bindings"]["B"] = "jump"
    profiles.save_user(p)
    assert profiles.load("mine")["bindings"]["B"] == "jump"
    listing = {e["id"]: e for e in profiles.list_profiles()}
    assert listing["mine"]["user"] and not listing["mine"]["builtin"] and listing["morrowind"]["builtin"]
    assert profiles.delete_user("mine") and not profiles.delete_user("mine")
    assert not profiles.delete_user("morrowind")                # a built-in cannot be deleted
    with pytest.raises(KeyError):
        profiles.load("mine")


def test_your_profile_wins_over_the_built_in_with_the_same_id():
    p = morrowind()
    p["bindings"]["B"] = "jump"
    profiles.save_user(p)
    assert profiles.load("morrowind")["bindings"]["B"] == "jump"
    assert [e for e in profiles.list_profiles() if e["id"] == "morrowind"][0] == {
        "id": "morrowind", "name": "Morrowind (OpenMW)", "target": "openmw", "builtin": True, "user": True}


def test_ids_cannot_escape_the_folder():
    for bad_id in ("../secrets", "a/b", "", "A", "x" * 60):
        with pytest.raises(KeyError):
            profiles.load(bad_id)
        assert not profiles.delete_user(bad_id)


def test_export_then_import_gives_the_same_profile(user_profiles):
    text = profiles.export_text(morrowind())
    p, errors = profiles.import_text(text, new_id="copy")
    assert errors == [] and p["id"] == "copy"
    assert {**profiles.load("copy"), "id": "morrowind"} == morrowind()
    again, errors = profiles.import_text(text, new_id="copy")
    assert again is None and "already exists" in errors[0]
    assert profiles.import_text(text, new_id="copy", overwrite=True)[1] == []


def test_import_reports_bad_files_without_saving(user_profiles):
    assert "not valid JSON" in profiles.import_text("{nope")[1][0]
    p, errors = profiles.import_text(json.dumps({"target": "openmw", "name": "x", "bindings": {"A": "fly"}}))
    assert p is None and errors and not list(user_profiles.glob("*.json")) if user_profiles.exists() else True


# ----------------------------------------------------------------------------------------------- running
def test_the_default_applies_when_nothing_is_active_or_the_target_differs():
    assert profiles.current("openmw")["id"] == "morrowind"
    profiles.apply(profiles.load("omsi"))
    assert profiles.current("keys")["id"] == "omsi" and profiles.current("openmw")["id"] == "morrowind"


def test_applying_a_profile_sets_the_keys_with_their_scan_codes():
    profiles.apply(profiles.load("generic-wasd"))
    assert keys.BINDINGS["throttle"] == (0x11, False)
    p = copy.deepcopy(profiles.load("omsi"))
    p["keys"]["left"] = "ArrowLeft"
    profiles.apply(p)
    assert keys.BINDINGS["left"] == (0x4B, True)                # arrows are "extended" keys


def test_ride_settings_apply_when_they_change_but_not_on_every_edit():
    p = morrowind()
    p["ride"] = {"mode": "real", "pmax": 300}
    profiles.apply(p)
    assert state["preset"] == "real" and state["pmax"] == 300
    state["difficulty"] = 0.55                                    # the rider changed it with the Click
    edited = copy.deepcopy(p)
    edited["bindings"]["B"] = "jump"                             # an edit of something else
    profiles.apply(edited)
    assert state["difficulty"] == 0.55
    edited = copy.deepcopy(edited)
    edited["ride"] = {"mode": "easy", "gain": 3.0}
    profiles.apply(edited)
    assert state["gain"] == 3.0 and state["preset"] == "custom"


def test_remapping_changes_what_the_openmw_target_sends():
    def fields(line):
        return dict(x.split("=") for x in line.strip().split(";"))
    assert fields(openmw.state_line(1, 0, {"Y"}))["draw"] == "1"
    p = morrowind()
    p["bindings"] = {"Y": "attack", "B": "none"}
    profiles.apply(profiles.validate(p)[0])
    f = fields(openmw.state_line(1, 0, {"Y"}))
    assert f["atk"] == "1" and f["draw"] == "0"
    assert fields(openmw.state_line(1, 0, {"B"}))["atk"] == "0"


def test_remapping_changes_which_keys_the_keys_target_holds():
    profiles.apply(profiles.load("omsi"))
    assert keys.wanted_slots({"LEFT"}) == {"left"} and keys.wanted_slots({"Z"}) == {"left"}
    assert keys.wanted_slots({"B"}) == {"brake"} and keys.wanted_slots({"Y"}) == set()
    p = profiles.load("omsi")
    p["bindings"] = {"Y": "steer_right"}
    profiles.apply(p)
    assert keys.wanted_slots({"Y"}) == {"right"} and keys.wanted_slots({"LEFT"}) == set()


def test_the_difficulty_buttons_follow_the_profile():
    p = morrowind()
    p["bindings"] = {"UP": "difficulty_up"}
    profiles.apply(profiles.validate(p)[0])
    state.update(target="openmw", difficulty=0.4, raw=["PLUS"], t_buttons=time.time())

    async def scenario():
        task = asyncio.create_task(difficulty.difficulty_loop())
        await asyncio.sleep(0.2)
        assert state["difficulty"] == 0.4                       # + is not bound any more
        state.update(raw=["UP"], t_buttons=time.time())
        await asyncio.sleep(0.2)
        assert state["difficulty"] == 0.5
        task.cancel()

    asyncio.run(scenario())


def test_the_openmw_mod_is_tuned_from_the_profile_options():
    p = morrowind()
    p["options"].update(turn_rate=3.0, use_speed_attribute=True)
    profiles.apply(profiles.validate(p)[0])
    assert openmw.config_line() == "turn_rate=3.0;pitch_rate=1.2;run_above=0.55;speed_attr=1;speed_boost=60\n"


def test_the_config_file_is_written_on_change(tmp_path):
    f = tmp_path / "config.txt"

    async def scenario():
        task = asyncio.create_task(openmw.config_loop(f))
        await asyncio.sleep(0.3)
        assert f.read_text() == openmw.config_line()
        p = morrowind()
        p["options"]["pitch_rate"] = 2.5
        profiles.apply(profiles.validate(p)[0])
        await asyncio.sleep(0.9)
        assert "pitch_rate=2.5" in f.read_text()
        task.cancel()

    asyncio.run(scenario())


# ----------------------------------------------------------------------------------------------- key names
def test_key_names_map_to_real_scan_codes():
    assert keynames.scan("KeyW") == (0x11, False) and keynames.scan("Numpad8") == (0x48, False)
    assert keynames.scan("ArrowUp") == (0x48, True)             # the same code as Numpad8, told apart by "extended"
    assert all(0 < scan < 0x80 for scan, _ in keynames.KEYS.values())
    assert keynames.label("KeyW") == "W" and keynames.label("Numpad8") == "Numpad 8" and keynames.label("ArrowLeft") == "←"
    assert not keynames.is_key("MetaLeft") and not keynames.is_key("AltLeft") and not keynames.is_key(None)


# ----------------------------------------------------------------------------------------------- command line
def parse(*argv):
    return build_parser().parse_args(argv)


def test_the_profile_is_chosen_from_the_target_and_the_options():
    assert choose_profile(parse("--target", "openmw"))["id"] == "morrowind"
    assert choose_profile(parse())["id"] == "omsi"
    assert choose_profile(parse("--keyset", "wasd"))["id"] == "generic-wasd"
    assert choose_profile(parse("--profile", "generic-wasd"))["id"] == "generic-wasd"
    assert choose_profile(parse("--target", "udp"))["id"] == "generic-udp"


def test_a_profile_alone_brings_its_own_target():
    assert choose_profile(parse("--profile", "morrowind"))["target"] == "openmw"


def test_a_profile_for_another_target_or_an_unknown_one_stops_the_start():
    with pytest.raises(SystemExit, match="openmw"):
        choose_profile(parse("--profile", "morrowind", "--target", "keys"))
    with pytest.raises(SystemExit, match="no profile"):
        choose_profile(parse("--profile", "nope"))


def test_a_profile_file_can_be_used_directly(tmp_path):
    f = tmp_path / "friend.json"
    f.write_text(json.dumps({"target": "keys", "name": "Friend", "keys": {"throttle": "KeyI"}}))
    p = choose_profile(parse("--profile", str(f)))
    assert p["name"] == "Friend" and p["keys"]["throttle"] == "KeyI" and p["keys"]["left"] == "Numpad4"


def test_profile_commands(tmp_path, capsys):
    data = str(tmp_path / "data")

    def run(*a):
        code = install.main(["profile", "--data-dir", data, *a])
        return code, capsys.readouterr().out

    code, out = run("list")
    assert code == 0 and "morrowind" in out and "built-in" in out
    out_file = tmp_path / "out.json"
    assert run("export", "morrowind", "--out", str(out_file))[0] == 0
    assert run("import", str(out_file), "--id", "copy")[0] == 0
    assert "yours" in run("list")[1]
    code, out = run("import", str(out_file), "--id", "copy")
    assert code == 2 and "already exists" in out
    assert run("import", str(out_file), "--id", "copy", "--overwrite")[0] == 0
    assert run("show", "copy")[1].startswith("{")
    assert run("delete", "copy")[0] == 0 and run("delete", "copy")[0] == 2
    assert run("show", "ghost")[0] == 2
    out_file.write_text('{"target": "openmw", "name": "x", "bindings": {"Q": "jump"}}')
    code, out = run("import", str(out_file))
    assert code == 2 and "unknown button" in out


@pytest.mark.skipif(sys.platform != "win32", reason="key output is Windows-only")
def test_extended_keys_are_sent_with_the_extended_flag(monkeypatch):
    sent = []

    class FakeUser32:
        @staticmethod
        def SendInput(n, ptr, size):
            import ctypes
            sent.append(ctypes.cast(ptr, ctypes.POINTER(keys._IN)).contents.ki.dwFlags)

    monkeypatch.setattr(keys.ctypes, "windll", type("W", (), {"user32": FakeUser32}), raising=False)
    keys.BINDINGS["left"] = keynames.scan("ArrowLeft")
    keys.key("left", True)
    keys.key("left", False)
    assert sent == [0x0008 | 0x0001, 0x0008 | 0x0001 | 0x0002]
