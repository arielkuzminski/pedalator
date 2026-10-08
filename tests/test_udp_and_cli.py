import json
import subprocess
import sys

from pedalator.state import state
from pedalator.targets import udp


def test_udp_packet_describes_the_rider_and_the_buttons():
    state.update(cadence=88.0, speed=24.5, grade=2.0)
    p = json.loads(udp.packet(5, 150, {"LEFT", "B"}))
    assert p["n"] == 5 and p["power"] == 150 and p["turn"] == -1 and p["look"] == 0
    assert p["buttons"] == ["B", "LEFT"] and p["cadence"] == 88.0 and 0 < p["move"] <= 1


def test_cli_help_and_version_work():
    out = subprocess.run([sys.executable, "-m", "pedalator", "--version"], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("pedalator ")
    out = subprocess.run([sys.executable, "-m", "pedalator", "--help"], capture_output=True, text=True)
    assert "--remote" in out.stdout and "--target" in out.stdout


def test_cli_subcommands_are_routed():
    out = subprocess.run([sys.executable, "-m", "pedalator", "install", "openomsi", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "--game-dir" in out.stdout
    out = subprocess.run([sys.executable, "-m", "pedalator", "build-bike", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "--hafencity" in out.stdout
