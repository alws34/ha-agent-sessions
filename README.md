# Agent Sessions for Home Assistant

Start, stop and resume **Claude Code** and **Codex CLI** sessions on your servers from Home Assistant.

- One integration entry per server; add as many servers as you like.
- Sessions run in GNU `screen` on the server, so they keep running when you close the dashboard, and you can attach to
  them over SSH (`screen -r`) or continue them in the Claude app (`--remote-control`).
- A bundled dashboard card: one slide per server, running sessions with **Stop**, recent sessions with **Resume**, and
  **New session** with a checklist of command-line flags (defaults per server).
- Home Assistant reaches each server over SSH with its own key, which can **only** run the Agent Sessions agent.

## Requirements

On each server:

- Linux with `python3` (3.9+), GNU `screen` and an SSH server.
- `claude` (Claude Code) and/or `codex` (Codex CLI), installed and logged in for the user that will run the sessions.

In Home Assistant: 2026.9 or newer, and [HACS](https://hacs.xyz).

## Install

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/alws34/ha-agent-sessions` as an **Integration**.
2. Install **Agent Sessions** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Agent Sessions.**

## Add a server

1. **Server details.** Name, host, SSH port and the user the sessions run as. The last field, *Home Assistant address
   as seen by the server*, is detected for you; the server only accepts Home Assistant's key from that address.
2. **Authorize Home Assistant.** Home Assistant creates an SSH key for this server and shows a command filled in with
   your host, user and address, for example:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/alws34/ha-agent-sessions/v0.1.4/agent/install.sh \
     | bash -s -- v0.1.4 10.0.0.2 'ssh-ed25519 AAAAC3Nza… home-assistant-agent-sessions'
   ```

   Run it on the server as that user. It installs the agent to `~/.local/bin/agent-sessions` and adds one line to
   `~/.ssh/authorized_keys`:

   ```
   from="10.0.0.2",command="/home/dev/.local/bin/agent-sessions",restrict ssh-ed25519 AAAAC3Nza… home-assistant-agent-sessions
   ```

   Nothing else is changed. [Read the script](agent/install.sh) first if you like.
3. **Confirm the server's identity.** Home Assistant connects and shows the server's host key fingerprint. It should
   match the `ED25519` line the installer printed. From then on Home Assistant refuses to connect if the key changes.

Repeat for each server.

## The card

The card is loaded automatically; add it from the card picker (**Agent Sessions**) or in YAML:

```yaml
type: custom:agent-sessions-card
# optional:
recent: 3                      # recent sessions shown before "Show more" (default 3)
entities:                      # default: every Agent Sessions server
  - sensor.workstation_sessions
```

- **‹ ›**, the server chips, or a swipe switch servers.
- **■ Stop** asks first (can be turned off per server), then closes the session's screen.
- **▶ Resume** starts the session again in a new screen, in the folder it ran in, with that server's default flags.
  Sessions that are already open (in a screen, a terminal or the desktop app) are not offered, and the agent refuses
  to resume them twice.
- **+ New session** opens the checklist: tool (if the server has both), folder (favorites or any path), optional
  name, and the flags. The bottom of the dialog shows the exact command.

## Options (per server)

**Settings → Devices & services → Agent Sessions → Configure**:

| Option | What it does |
|---|---|
| Default tool | Claude Code or Codex CLI, when the server has both |
| Flags ticked by default | Per tool: which built-in flags start ticked in **New session** and are used for **Resume** |
| Default model / effort | Per tool: values for the model and effort flags |
| Custom flags | Per tool, one per line (e.g. `--chrome`). Start a line with `*` to tick it by default. The server must allow each one too (see [Security](#security)) |
| Favorite folders | Offered in **New session** |
| Trusted folders | One per line, subfolders included. The tools won't ask "Do you trust this folder?" there. Written on the server when you save |
| Also trust any other folder I start a session in | Marks each new session's folder as trusted |
| Recent sessions to show | How many past sessions the server reports |
| Check the server for changes every | Poll interval (seconds) |
| Ask before stopping a session | Inline confirmation on **Stop** |

Built-in flags: Claude Code `--dangerously-skip-permissions`, `--remote-control`, `--continue`, `--model`, `--effort`,
`--verbose`; Codex CLI `--dangerously-bypass-approvals-and-sandbox`, `--search`, `-m`, reasoning effort
(`-c model_reasoning_effort=…`), `--no-alt-screen`.

## Entities and services

Each server has one sensor, `sensor.<server>_sessions`: the state is the number of running sessions, and the
attributes carry the running and recent sessions (not recorded in history). Services, for automations and scripts:

These services are admin-only: other Home Assistant users get *Unauthorized*.

- `agent_sessions.new_session`: `config_entry_id`, `tool` (`claude`/`codex`), `folder`, `args` (list), `name`
- `agent_sessions.resume_session`: `config_entry_id`, `tool`, `session_id`, `args`
- `agent_sessions.stop_session`: `config_entry_id`, `session` (the screen ID, `pid.name`)

## How it works

Every *n* seconds Home Assistant runs `agent-sessions list` over a kept-open SSH connection. The agent reads local
state only: `screen -ls`, Claude Code's `~/.claude/sessions/*.json` and transcripts in `~/.claude/projects/`, and
Codex's `~/.codex/state_*.sqlite`. **It does not contact Anthropic or OpenAI and uses none of your usage.**

New sessions run as `screen -dmS agent-<tool>-<name> bash -lic '<tool> <flags>'`, so they get your normal login
environment. When the tool exits, its screen closes.

## Security

Short version (details, what remains and recommendations in [SECURITY.md](SECURITY.md)):

- **Home Assistant's key can only run the agent**: `command=` forces it, `restrict` disables shells and forwarding,
  and `from=` accepts the key only from Home Assistant's address.
- **The server decides what is allowed, not Home Assistant.** The agent accepts six verbs and only the built-in flags
  (model and effort values are checked). A prompt, `--settings`, `--mcp-config` or a Codex `-c` override could run
  commands, so they are refused. To allow more, list exact arguments in `~/.config/agent-sessions/allowed-args` on the
  server, one `<tool> <argument>` per line (e.g. `claude --chrome`).
- **Folders must be inside the user's home**, and **Stop only closes sessions the card lists**.
- **Only Home Assistant admins** can call the services, and **the server's host key is pinned** at setup.
- **The private key is stored unencrypted** in Home Assistant's `.storage`, so use encrypted backups.
- Sessions started with the bypass flags can run any command as that user. Consider a dedicated, unprivileged user.
- Passwords are not supported on purpose.

Found a problem? Report it privately; see [SECURITY.md](SECURITY.md).

## Remove a server

Delete the entry in Home Assistant, then on the server remove the `home-assistant-agent-sessions` line from
`~/.ssh/authorized_keys` and `rm ~/.local/bin/agent-sessions`.

## Limitations

- Codex CLI status (working/idle) and titles come from Codex's internal SQLite database. If a Codex update changes
  it, Codex sessions still start and stop but may show without a title or status.
- Resume uses the server's default flags; pick different flags with **New session** + `--continue`.

## Development

```bash
uv venv .venv && uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest -q && .venv/bin/ruff check custom_components tests
```

`AGENT_SESSIONS_URL=file:///path/to/agent/agent-sessions bash agent/install.sh …` installs a local agent copy.

## License

MIT
