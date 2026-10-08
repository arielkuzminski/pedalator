"""Shared test setup: every test starts from a clean shared state."""
import copy
import socket

import pytest

from pedalator import state as S

_DEFAULT = copy.deepcopy(S.state)


@pytest.fixture(autouse=True)
def clean_state():
    S.state.clear()
    S.state.update(copy.deepcopy(_DEFAULT))
    S.history.clear()
    S.log_lines.clear()
    S.stats.update(sum=0.0, n=0, max=0)
    yield


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
