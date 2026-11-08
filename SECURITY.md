# Security

## Reporting a vulnerability

Please report privately: **Security → Report a vulnerability** on
[github.com/alws34/ha-agent-sessions](https://github.com/alws34/ha-agent-sessions/security). Don't open a public issue.
Only the latest release is supported.

## What Home Assistant can do on your server

Home Assistant gets an SSH key per server. That key can only do what the card does:

| Layer | What it stops |
|---|---|
| `command="…/agent-sessions"` in `authorized_keys` | Whatever the client asks to run, sshd runs the agent instead. No shell, no `scp`/`sftp`. |
| `restrict` | Port, agent and X11 forwarding, and a PTY. |
| `from="<HA address>"` | The key is refused from any other address. |
| Agent: nine verbs | `info`, `list`, `sessions`, `new`, `resume`, `stop`, `trust`, `export`, `import`. Payloads are validated, and nothing goes through a shell unquoted. |
| Agent: flag allowlist | Only the built-in flags, plus exact arguments the server owner lists in `~/.config/agent-sessions/allowed-args`. Prompts, `--settings`, `--mcp-config`, `--append-system-prompt` and Codex `-c` overrides (other than reasoning effort) are refused. |
| Agent: folders | New sessions, resumed sessions and trusted folders must be inside the user's home (symlinks resolved). |
| Agent: stop | Only sessions the card lists. The agent's own `agent-*` screens are closed; in one of your own screens only the Claude Code / Codex process is stopped, so its other windows stay. |
| Agent: moving sessions | `export` reads only `~/.claude/projects/*/<uuid>.jsonl` of a session that isn't running. `import` writes only a new `~/.claude/projects/<folder>/<uuid>.jsonl` (mode 600, never overwriting) for a folder inside home, after checking it is gzip + JSON lines of that session, at most 64 MB unpacked. |
| Integration | The services are admin-only, so other Home Assistant users get *Unauthorized* (and the card hides the buttons). The server's host key is pinned at setup; a changed key is refused. The card only shows this integration's own sensors. |

Home Assistant cannot send a prompt. A session only does work when someone types into it, either over SSH as that
user (`screen -r`) or through the Claude app (`--remote-control`, i.e. whoever has your Claude account).

## What remains

- **The private key is stored unencrypted** in `/config/.storage/core.config_entries`, like every integration's
  credentials. Anyone with your Home Assistant files or an unencrypted backup has it. They can then do what an admin
  can do from the card, but only from Home Assistant's address.
- **Trusting a folder lets the tool load that folder's own configuration.** Claude Code reads project settings
  (`.claude/settings.json`, including hooks) and `.mcp.json`, and Codex reads `.codex/` project config. Starting a
  session in a trusted folder with untrusted content (a cloned repo you haven't read) can run that content's
  commands. Whoever holds the key can mark any folder in your home as trusted. Keep untrusted code out of that user's
  home, or use a dedicated user.
- **Bypass flags.** `--dangerously-skip-permissions` and `--dangerously-bypass-approvals-and-sandbox` let the session
  run any command as that user without asking. Combined with `--remote-control`, your Claude account controls them.
- **Non-admin Home Assistant users can read session titles and folders** in the sensor's attributes (they can't start
  or stop anything). A title can be the start of your first prompt, so don't paste secrets as a session's first message.
- **Moving a session copies its transcript** (your prompts, the tool output, anything secret in it) through Home
  Assistant to the other server. Both servers then hold a copy.
- **No rate limit.** The key can start many sessions (CPU, memory, model usage).
- **`from=` trusts the network.** A device on your LAN that takes over Home Assistant's address still needs the
  private key; `from=` is a second line, not the main one.

## Recommendations

1. Run sessions as a **dedicated, unprivileged user** without sudo, whose home holds only code you trust.
2. Use **encrypted Home Assistant backups**.
3. Give Home Assistant a **fixed address** (DHCP reservation) so `from=` stays meaningful.
4. Don't expose the server's SSH port to the internet.
5. Leave the bypass flags **unticked by default** unless you need them, and add to `allowed-args` only arguments you
   understand.
6. **Revoke** by deleting the `home-assistant-agent-sessions` line from `~/.ssh/authorized_keys`. That takes effect
   immediately, even if Home Assistant is compromised.
