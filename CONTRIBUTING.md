# Contributing

Issues and pull requests are welcome.

## Workflow

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
   Anything that widens what Home Assistant's key can do on a server (a new verb, flag or folder
   rule) needs a note on why it is safe; see [SECURITY.md](SECURITY.md) and
   [docs/threat-model.md](docs/threat-model.md).
2. One branch per change, pull request against `main`. Keep PRs focused; CI (HACS validation,
   hassfest, ruff, tests, CodeQL) must pass before merge.
3. Releases are tagged `vX.Y.Z` from `main` by the maintainer; the tag must equal the version in
   `manifest.json` and `const.py`.

## Local checks

```bash
uv venv .venv --python 3.14 && uv pip install -p .venv -r requirements_test.txt
.venv/bin/ruff check custom_components tests
.venv/bin/pytest -q --cov=custom_components
```

Test requirements are pinned exactly in `requirements_test.txt`. `pytest-homeassistant-custom-component` fixes the
Home Assistant version under test, so when it is bumped, set in the same commit:

- `home-assistant-frontend` to what that Home Assistant release pins (`homeassistant/components/frontend/manifest.json`
  at that tag of home-assistant/core);
- `asyncssh` to the version that release ships (`requirements_all.txt`), never below `manifest.json`'s lower bound.

Dependabot only proposes `pytest-homeassistant-custom-component` and `ruff`; `nodejs-wheel-binaries` (Node for the
card's tests) is bumped by hand as well.

The card's tests run the real `agent-sessions-card.js` under Node (`tests/card_harness.js`); the
Node binary comes from the `nodejs-wheel-binaries` test requirement, so no system Node is needed.
Tests never contact a real server, Claude or OpenAI (one optional test reads `claude --help` when
Claude Code is installed).

## Changing the server agent or the installer

`const.AGENT_SHA256` and `const.INSTALLER_SHA256` pin `agent/agent-sessions` and
`agent/install.sh`: the install command Home Assistant shows refuses anything else. After editing
either file, update the value (the failing test prints it). Bump `AGENT_VERSION` (both in
`const.py` and the agent's `VERSION`) when the integration needs the new agent; servers then get
a Repairs issue with the install command.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Sign-off

No CLA and no DCO sign-off required. By contributing you agree your work is released under the
project's [MIT license](LICENSE).

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
