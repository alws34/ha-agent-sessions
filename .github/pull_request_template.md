## What and why

<!-- One focused change. Link the issue it fixes, if any. -->

## Checklist

- [ ] `pytest` and `ruff check custom_components tests` pass locally
- [ ] Tests cover the change (flags: the end-to-end cases in `tests/test_flags.py`)
- [ ] If `agent/agent-sessions` or `agent/install.sh` changed: `AGENT_SHA256` / `INSTALLER_SHA256` in `const.py` updated
      (the tests print the new value), and `AGENT_VERSION` bumped if the protocol changed
- [ ] If it changes what Home Assistant's key can do on a server: `SECURITY.md` and `docs/threat-model.md` updated
- [ ] README updated for user-visible changes
