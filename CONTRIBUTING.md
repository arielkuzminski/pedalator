# Contributing

Thank you for wanting to help! Pedalator is a small, friendly project and every kind of help counts: trying it with your trainer, reporting what works, a new game, a translation, a fix, better docs.

## Report something

- **It worked / it did not work on my setup:** open an issue and tell us the trainer, controller, game, Windows version and (for phone mode) the phone and browser. "Works with X" reports are valuable: they grow the table in the README.
- **A bug:** use the bug template; include the console output and the dashboard's *Event log* ([how](docs/troubleshooting.md#collecting-information-for-a-bug-report)).
- **An idea or a game you would like:** look at the [roadmap](docs/roadmap.md) first, then open an issue.

## Send a change

1. Fork, make a branch.
2. Set up: see [Development](docs/development.md). All three checks must pass:
   ```bash
   python -m ruff check . && python -m pytest -q && node --test
   ```
3. Keep changes focused, add or update tests for logic you touch, update the docs for behaviour you change.
4. Open a pull request and say what you tested **on real hardware** and what you could not.

## Ground rules

- **Be kind.** See the [code of conduct](CODE_OF_CONDUCT.md).
- **Other people's games stay theirs.** Do not add models, textures, scripts or other files from commercial games or add-ons. Build from the user's own copy at install time (as `build-bike` does).
- **No private data**: certificates, tokens, personal paths or addresses.
- **Do not copy code from projects with incompatible licenses** (for example "non-commercial" or GPL code into this MIT project). Describing a protocol you observed is fine; pasting someone's implementation is not.
- Be honest in the docs about what is tested and what is a guess.

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
