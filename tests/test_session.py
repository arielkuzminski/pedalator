"""The driver session: started and stopped on demand, without restarting the program."""
import asyncio
import socket

import pytest

from pedalator import profiles
from pedalator.session import Runtime, SessionConfig, SessionError
from pedalator.state import history, state

from .conftest import free_port


def run(coro_fn):
    """Run ``coro_fn(runtime)`` on a fresh loop with a fresh runtime."""
    async def main():
        rt = Runtime()
        rt.attach(asyncio.get_running_loop())
        try:
            return await coro_fn(rt)
        finally:
            await rt.stop()
    return asyncio.run(main())


@pytest.fixture(autouse=True)
def user_dir(tmp_path):
    profiles.set_user_dir(tmp_path / "profiles")
    yield
    profiles.set_user_dir(None)


def cfg(**kw):
    kw = {"simulate": True, "game_port": free_port(), "udp_out": f"127.0.0.1:{free_port()}", **kw}
    return SessionConfig(**kw)


def test_a_session_starts_runs_and_stops():
    async def go(rt):
        await rt.start(cfg(target="udp"))
        assert state["session"]["status"] == "running" and state["session"]["profile_id"] == "generic-udp"
        assert state["target"] == "udp"
        await asyncio.sleep(1.3)
        assert state["connected"] and state["power"] > 0 and len(history) >= 1
        await rt.stop()
        assert state["session"]["status"] == "idle" and "profile_id" not in state["session"]
        assert state["connected"] is False and state["power"] == 0 and state["simulate"] is False and not history
    run(go)


def test_a_second_game_can_follow_without_restarting():
    async def go(rt):
        await rt.start(cfg(profile="generic-udp"))
        await rt.stop()
        await rt.start(cfg(profile="omsi"))
        assert state["target"] == "keys" and state["session"]["profile_id"] == "omsi"
    run(go)


def test_starting_twice_is_refused_and_stopping_twice_is_fine():
    async def go(rt):
        await rt.start(cfg(target="udp"))
        with pytest.raises(SessionError, match="already running"):
            await rt.start(cfg(target="udp"))
        await rt.stop()
        await rt.stop()
        assert rt.status == "idle"
    run(go)


def test_a_bad_start_is_an_error_to_show_not_an_exit():
    async def go(rt):
        with pytest.raises(SessionError, match="no profile"):
            await rt.start(cfg(profile="nope"))
        with pytest.raises(SessionError, match="'keys' target"):
            await rt.start(cfg(profile="omsi", target="openmw"))
        with pytest.raises(SessionError, match="HOST:PORT"):
            await rt.start(cfg(target="udp", udp_out="nonsense"))
        with pytest.raises(SessionError, match="'pc' or 'phone'"):
            await rt.start(cfg(trainer="carrier-pigeon"))
        assert rt.status == "idle"                               # a failed start leaves nothing behind
    run(go)


def test_openmw_without_the_mod_says_what_to_do(monkeypatch):
    monkeypatch.setattr("pedalator.paths.find_openmw_state", lambda *a: None)
    async def go(rt):
        with pytest.raises(SessionError, match="pedalator install openmw"):
            await rt.start(cfg(target="openmw"))
    run(go)


def test_the_games_port_is_free_again_after_stopping():
    port = free_port()

    async def go(rt):
        await rt.start(SessionConfig(simulate=True, target="udp", game_port=port, udp_out=f"127.0.0.1:{free_port()}"))
        with pytest.raises(SessionError, match="cannot listen"):             # in use while riding
            await Runtime._start(rt, SessionConfig(simulate=True, game_port=port))
        await rt.stop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("127.0.0.1", port))                                       # free now
    run(go)


def test_the_phone_servers_follow_the_session(tmp_path):
    phone, ca = free_port(), free_port()

    async def go(rt):
        await rt.start(SessionConfig(trainer="phone", click="off", target="udp", game_port=free_port(), ip="127.0.0.1",
                                     data_dir=tmp_path / "d", phone_port=phone, ca_port=ca,
                                     udp_out=f"127.0.0.1:{free_port()}"))
        assert state["trainer_name"] == "(phone)" and state["session"]["trainer"] == "phone"
        with socket.create_connection(("127.0.0.1", ca), timeout=2):
            pass
        await rt.stop()
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", ca), timeout=1)
    run(go)


def test_the_game_is_told_nobody_pedals_when_it_stops(tmp_path):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2)

    async def go(rt):
        await rt.start(SessionConfig(simulate=True, target="udp", game_port=free_port(),
                                     udp_out=f"127.0.0.1:{sock.getsockname()[1]}"))
        await asyncio.sleep(0.3)
        await rt.stop()
    run(go)
    last = b""
    try:
        while True:
            last = sock.recv(2048)
    except OSError:
        pass
    sock.close()
    assert b'"move": 0.0' in last and b'"power": 0' in last


def test_a_part_that_crashes_is_reported_not_silent(monkeypatch):
    async def boom(*a):
        raise RuntimeError("adapter vanished")
    monkeypatch.setattr("pedalator.simulate.simulate", boom)

    async def go(rt):
        await rt.start(cfg(target="udp"))
        for _ in range(40):
            if state["session"]["status"] == "error":
                break
            await asyncio.sleep(0.05)
        assert state["session"]["status"] == "error" and "adapter vanished" in state["session"]["error"]
        await rt.stop()
        assert rt.status == "idle"
    run(go)
