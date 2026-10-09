"""The installers and the bike builder, on made-up files (no HafenCity material is used or needed)."""
from pathlib import Path

import pytest

from pedalator import install
from pedalator.bike import UnexpectedBike, build_bike, make_bus, make_script

# A tiny stand-in for the HafenCity bike's files, written for these tests. It only has the shapes the builder relies on.
FAKE_OSC = (
    "{frame}\r\n"
    "'\t################ Zufall A\r\n\t1 (S.L.vmax)\r\n"
    "'\t################ Zufall B\r\n\t0 (S.L.bell)\r\n"
    "'\t################ Bewegung\r\n\t(L.L.Throttle) 100 * (S.L.M_Wheel)\r\n\r\n"
    "{end}"
)
FAKE_BUS = (
    "\t[friendlyname]\r\n\tFahrrad 1\r\n\r\n[type]\r\n2\r\n\r\n[model]\r\nmodel\\model.cfg\r\n\r\n"
    "[sound]\r\nsound\\Sound.cfg\r\n\r\n"
    "[script]\r\n1\r\nscript\\fahrrad.osc\r\n\r\n[constfile]\r\n1\r\nscript\\fahrrad_constfile.txt\r\n\r\n"
    "[varnamelist]\r\n1\r\nscript\\fahrrad_varlist.txt\r\n\r\n"
    "[mass]\r\n0.3\r\n\r\n[momentofintertia]\r\n50\r\n20\r\n50\r\n\r\n[rollwiderstand]\r\n60\r\n\r\n"
    "[inv_min_turnradius]\r\n0.7\r\n\r\n"
    "[newachse]\r\nachse_long\r\n0.8\r\nachse_feder\r\n50\r\nachse_antrieb\r\n1\r\n\r\n"
    "[newachse]\r\nachse_long\r\n-0.3\r\nachse_feder\r\n50\r\nachse_antrieb\r\n1\r\n"
)


@pytest.fixture()
def fake_bike(tmp_path):
    src = tmp_path / "HC_Fahrrad"
    for d in ("model", "sound", "texture"):
        (src / d).mkdir(parents=True)
        (src / d / f"{d}.dat").write_text(d)
    (src / "script").mkdir()
    (src / "script" / "fahrrad.osc").write_bytes(FAKE_OSC.encode("latin-1"))
    (src / "script" / "fahrrad_constfile.txt").write_bytes(b"[const]\r\nvmax_min\r\n15\r\n")
    (src / "script" / "fahrrad_varlist.txt").write_bytes(b"vmax\r\nhelm\r\n")
    (src / "fahrrad_1.bus").write_bytes(FAKE_BUS.encode("latin-1"))
    return src


def test_script_loses_the_ai_blocks_and_gets_the_riders_drive(fake_bike):
    out = make_script(FAKE_OSC.replace("\r\n", "\n"))
    assert "Zufall A" not in out and "Zufall B" in out           # the AI's random top speed and throttle are gone
    assert "P_rider" in out and "k_mass" in out and "(L.L.Throttle) 100 *" not in out
    assert "1 (S.L.engine_on)" in out and out.rstrip().endswith("{end}")


def test_bus_has_light_physics_own_scripts_and_a_rider_camera():
    out = make_bus(FAKE_BUS.replace("\r\n", "\n"), "My Bike")
    assert "My Bike" in out and "Fahrrad 1" not in out
    assert "script\\fahrrad_pedalator.osc" in out and "fahrrad_pedalator_constfile.txt" in out
    assert "[mass]\n0.1" in out and "[rollwiderstand]\n1" in out and "[inv_min_turnradius]\n0.5" in out
    assert out.count("achse_feder\n17") == 2 and "[add_camera_driver]" in out


def test_build_bike_writes_a_complete_vehicle_and_keeps_crlf(fake_bike, tmp_path):
    out = tmp_path / "out"
    bus = build_bike(fake_bike, out)
    root = out / "Vehicles" / "HC_Fahrrad"
    assert bus == root / "fahrrad_pedalator.bus"
    for d in ("model", "sound", "texture"):
        assert (root / d / f"{d}.dat").exists()                   # assets are copied from YOUR folder
    assert b"\r\n" in bus.read_bytes() and b"\n" not in bus.read_bytes().replace(b"\r\n", b"")
    consts = (root / "script" / "fahrrad_pedalator_constfile.txt").read_text()
    assert "vmax_min" in consts and "k_mass" in consts
    assert "Trainer_Power" in (root / "script" / "fahrrad_pedalator_varlist.txt").read_text()


def test_a_different_hafencity_version_is_reported_not_guessed(fake_bike, tmp_path):
    (fake_bike / "fahrrad_1.bus").write_bytes(FAKE_BUS.replace("[mass]\r\n0.3", "[mass]\r\n9").encode("latin-1"))
    with pytest.raises(UnexpectedBike):
        build_bike(fake_bike, tmp_path / "out")


def test_a_wrong_folder_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_bike(tmp_path, tmp_path / "out")


def test_install_openomsi_copies_the_plugin(tmp_path):
    game = tmp_path / "openOMSI"
    (game / "Plugins").mkdir(parents=True)
    assert install.install_openomsi(game) == 0
    assert "omsi.send" in (game / "Plugins" / "pedalator" / "main.lua").read_text()
    assert install.install_openomsi(tmp_path / "nothing") == 2


def test_install_openmw_copies_the_mod_and_edits_the_config_with_a_backup(tmp_path):
    user = tmp_path / "OpenMW"
    user.mkdir()
    cfg = user / "openmw.cfg"
    cfg.write_text('data="C:/Morrowind/Data Files"\ncontent=Morrowind.esm\n')
    assert install.install_openmw(user, None, dry_run=True) == 0
    assert "Pedalator" not in cfg.read_text() and not (user / "mods").exists()      # a dry run changes nothing
    assert install.install_openmw(user, None) == 0
    mod = user / "mods" / "Pedalator"
    assert (mod / "Pedalator.omwscripts").exists() and (mod / "scripts" / "pedalator" / "player.lua").exists()
    assert (mod / "pedalator" / "state.txt").exists()
    text = cfg.read_text()
    assert f'data="{mod.as_posix()}"' in text and "content=Pedalator.omwscripts" in text
    assert list(user.glob("openmw.cfg.bak-pedalator-*"))
    before = cfg.read_text()
    assert install.install_openmw(user, None) == 0 and cfg.read_text() == before     # idempotent
    assert Path(mod / "pedalator" / "state.txt").read_text().startswith("n=")


def test_install_keeps_crlf_line_endings_in_the_file(tmp_path):
    from pedalator import install
    (tmp_path / "openmw.cfg").write_bytes(b"data=\"C:/x\"\r\ncontent=a.esm\r\n")
    assert install.install_openmw(tmp_path, tmp_path / "mod") == 0
    raw = (tmp_path / "openmw.cfg").read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
