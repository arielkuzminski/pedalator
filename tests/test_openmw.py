import asyncio
import time
from pathlib import Path

from pedalator.install import update_openmw_cfg
from pedalator.paths import cfg_values, find_openmw_state
from pedalator.state import apply_preset, state
from pedalator.targets import openmw


def fields(line: str) -> dict:
    return dict(p.split("=") for p in line.strip().split(";"))


def test_state_line_for_each_click_button():
    apply_preset("real")
    base = fields(openmw.state_line(1, 125, set()))
    assert base["move"] == "0.500" and base["turn"] == "0" and base["power"] == "125"
    assert fields(openmw.state_line(2, 0, {"LEFT"}))["turn"] == "-1"
    assert fields(openmw.state_line(2, 0, {"RIGHT"}))["turn"] == "1"
    assert fields(openmw.state_line(2, 0, {"UP"}))["look"] == "-1"
    assert fields(openmw.state_line(2, 0, {"DOWN"}))["look"] == "1"
    f = fields(openmw.state_line(2, 0, {"B", "A", "Y"}))
    assert (f["atk"], f["jump"], f["draw"]) == ("1", "1", "1")
    assert openmw.state_line(7, 0, {"PLUS", "MINUS"}).endswith("power=0\n")      # unmapped buttons do nothing


def test_state_line_counter_and_coasting():
    apply_preset("real")
    assert fields(openmw.state_line(41, 10, set()))["move"] == "0.000"            # below the floor
    assert fields(openmw.state_line(41, 999, set()))["move"] == "1.000"
    assert fields(openmw.state_line(41, 0, set()))["n"] == "41"


def test_parse_grades_reads_only_the_mods_lines():
    log = (b"[10:00:01.000 I] L@0x1[scripts/pedalator/player.lua]:\tPEDALATOR grade=2.50\n"
           b"[10:00:01.100 I] something else grade=9\n"
           b"[10:00:01.250 I] L@0x1[scripts/pedalator/player.lua]:\tPEDALATOR grade=-30.00\n")
    assert openmw.parse_grades(log) == [2.5, -15.0]


def test_log_tail_follows_new_lines_and_restarts(tmp_path):
    log = tmp_path / "openmw.log"
    log.write_bytes(b"PEDALATOR grade=9.00\n")                                    # old: before the bridge started

    async def scenario():
        task = asyncio.create_task(openmw.log_tail(log))
        await asyncio.sleep(0.5)
        assert state["game_grade"] == 0.0                                         # the old line is ignored
        with open(log, "ab") as f:
            f.write(b"PEDALATOR grade=3.25\nPEDALATOR grade=4.50\n")
        await asyncio.sleep(0.6)
        assert state["game_grade"] == 4.5 and state["t_udp"] > 0
        log.write_bytes(b"PEDALATOR grade=7.00\n")                                # the game restarted: a shorter log
        await asyncio.sleep(0.6)
        assert state["game_grade"] == 7.0
        task.cancel()

    asyncio.run(scenario())


def test_state_loop_rewrites_the_file_in_place(tmp_path):
    f = tmp_path / "state.txt"
    f.write_text("")
    state.update(simulate=True, power=150, raw=["B"], t_buttons=time.time())

    async def scenario():
        task = asyncio.create_task(openmw.state_loop(f))
        await asyncio.sleep(0.3)
        task.cancel()

    asyncio.run(scenario())
    got = fields(f.read_text())
    assert got["power"] == "150" and got["atk"] == "1" and int(got["n"]) >= 2


def test_cfg_helpers_and_mod_discovery(tmp_path):
    mod = tmp_path / "mods" / "Pedalator"
    (mod / "pedalator").mkdir(parents=True)
    (mod / "pedalator" / "state.txt").write_text("n=0\n")
    user = tmp_path / "user"
    user.mkdir()
    (user / "openmw.cfg").write_text(
        f'data="C:/Games/Morrowind/Data Files"\ndata="{mod.as_posix()}"\ncontent=Morrowind.esm\n')
    assert cfg_values(user / "openmw.cfg", "content") == ["Morrowind.esm"]
    assert find_openmw_state(user) == Path(mod / "pedalator" / "state.txt")
    assert find_openmw_state(tmp_path) is None


def test_update_cfg_is_idempotent_keeps_crlf_and_drops_the_old_mod():
    original = ('data="R:/Morrowind/Data Files"\r\ndata="R:/Mods/TrainerBike"\r\n'
                'content=Morrowind.esm\r\ncontent=TrainerBike.omwscripts\r\n')
    new, changes = update_openmw_cfg(original, Path("R:/mods/Pedalator"))
    assert "TrainerBike" not in new and "\n" not in new.replace("\r\n", "")
    assert 'data="R:/mods/Pedalator"' in new and "content=Pedalator.omwscripts" in new
    assert len(changes) == 4
    again, changes2 = update_openmw_cfg(new, Path("R:/mods/Pedalator"))
    assert again == new and changes2 == []
