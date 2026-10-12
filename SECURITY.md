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
| Agent: six verbs | `info`, `list`, `new`, `resume`, `stop`, `trust`. Payloads are validated, and nothing goes through a shell unquoted. |
| Agent: flag allowlist | Only the built-in flags, plus exact arguments the server owner lists in `~/.config/agent-sessions/allowed-args`. Prompts, `--settings`, `--mcp-config`, `--append-system-prompt` and Codex `-c` overrides (other than reasoning effort) are refused. |
| Agent: folders | New sessions and trusted folders must be inside the user's home (symlinks resolved). |
| Agent: stop | Only sessions the card lists (Claude Code / Codex screens and the agent's own `agent-*` screens), never the user's other screens. |
| Integration | The services are admin-only, so other Home Assistant users get *Unauthorized*. The server's host key is pinned at setup; a changed key is refused. |

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
- **Resume uses the folder the session ran in**, which is read from the tool's own records on the server and may be
  outside your home.
- **Non-admin Home Assistant users can read session titles and folders** in the sensor's attributes (they can't start
  or stop anything).
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
