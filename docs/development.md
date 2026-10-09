# Development

## Setup

```bash
git clone https://github.com/arielkuzminski/pedalator
cd pedalator
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run the checks

```bash
python -m ruff check .            # lint
python -m pytest -q               # Python tests (servers, state, targets, installers, bike builder)
node --test  # JavaScript tests (Click decoders, request queue)
```

These three run in CI (`.github/workflows/ci.yml`) on every push and pull request. No test needs a trainer, a phone or a game: the servers are started on free ports, the bike builder works on a small made-up fixture, and the installers on temporary folders.

Try the whole thing without hardware: `python -m pedalator --simulate`.

## Code layout

See the module table in [Architecture](architecture.md). Rules of thumb:

- Shared state lives in `pedalator/state.py` and nowhere else.
- Anything that talks to hardware or a game is **small and replaceable**; the logic that decides *what to send* is pure functions where possible (`targets/openmw.state_line`, `ftms.parse_bike_data`) so it can be tested.
- The web pages are plain HTML/JS. The Click decoders sit between `// <decoders>` and `// </decoders>` in `phone.html` so the JS tests can load them without a browser.
- Both pages translate through `t('English text', args…)` and a `PL` dictionary at the top of their script. Add a language by adding another dictionary.
- Never put private data in the repository: certificates, tokens, paths of one machine, files of other people's games. `.gitignore` guards the usual suspects; `git ls-files` should show only our own work.

## Adding a game

Decide how the game can be reached (see the [roadmap](roadmap.md#what-makes-a-game-easy-to-connect)).

1. **A mod or plugin for the game** — it should
   - read what Pedalator sends (JSON over UDP for the `udp` target; a state file for games without sockets) and make the player move;
   - report the slope under the player as `grade=<percent>;speed=<km/h>` to UDP `127.0.0.1:27100` — or print it to a log that Pedalator can follow.
2. **A target in `pedalator/targets/`** only if the generic `udp` target does not fit (the OpenMW target exists because OpenMW's Lua has no sockets). A target is a module with async functions that read `state` and talk to the game; start them in `cli.bridge()`.
3. **An installer** in `pedalator/install.py` if the mod must be copied or enabled somewhere, with a dry run and a backup of anything it edits.
4. **Tests** for the pure parts, and a page in `docs/games/`.
5. Add the game to the README table and move it from 💡 to ✅ in the roadmap.

## Releasing

1. Update `pedalator/__init__.py` and `pyproject.toml` versions, `CHANGELOG.md`.
2. `python -m pytest`, `node --test`, `python tools/make_demo.py` if the dashboard changed.
3. Tag `vX.Y.Z` and create a GitHub release with the changelog entry.

## Regenerating the demo

`python tools/make_demo.py` starts a simulated rider on spare ports, takes screenshots of the dashboard with headless Chrome/Edge and writes `docs/img/dashboard.gif` and `dashboard.png` (needs `pip install pillow`).
