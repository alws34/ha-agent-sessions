# Threat model

Agent Sessions lets Home Assistant start, stop, resume and move Claude Code / Codex CLI sessions on servers over SSH.
Starting a session is close to shell access on that server, so the design keeps that power on the server's side:
Home Assistant holds a key that can only run one small agent, and the agent decides what is allowed.

## Assets

| Asset | Where | Why it matters |
|---|---|---|
| HA's SSH private key (one per server) | Config entry in `/config/.storage/core.config_entries` (unencrypted, like every integration's credentials) | Whoever has it can do what an HA admin can do from the card, from HA's address |
| The server account sessions run as | Each server | Sessions run as that user, with its files, tokens and logged-in Claude / OpenAI accounts |
| Session transcripts and titles | `~/.claude/projects`, Codex databases, `~/.cache/agent-sessions/titles.json`; copied through HA when a session moves | Prompts, tool output, anything secret pasted into a session |
| The pinned host key | Config entry | Stops HA talking to an impostor server |
| The release (tag, installer, agent) | GitHub | What every server runs |

## Actors

- **HA admin**: trusted. Can start sessions with any built-in flag, in any folder in the user's home.
- **Non-admin HA user**: can see the card and the sensor's attributes; cannot call the services.
- **LAN attacker**: can reach HA and the servers on the network, but has no key.
- **Attacker with HA's files or an unencrypted backup**: has the private key.
- **Server owner**: trusted on their server; edits `allowed-args`, trusted folders and the authorized_keys line.
- **Untrusted repository content** in the user's home (a cloned repo you haven't read).

## Trust boundaries and controls

1. **HA → server (SSH).** The key line is `from="<HA address>",command="~/.local/bin/agent-sessions",restrict`: no
   shell, no forwarding, no PTY, only from HA's address. HA pins the server's host key at setup and refuses a changed
   one. Passwords are not supported.
2. **Request → agent.** One verb from a fixed list of nine, a base64 JSON payload checked field by field. Arguments
   pass an allowlist (built-in flags with value patterns, plus exact sequences from the owner's `allowed-args`);
   prompts, `--settings`, `--mcp-config`, `--append-system-prompt` and Codex `-c` overrides other than reasoning
   effort are refused. Folders are resolved (symlinks included) and must be inside home. Stop only acts on sessions
   the agent lists. Session ids must be UUIDs.
3. **Agent → shell.** The session command is built with `shlex.join` and run as `screen -dmS <sanitised name> bash
   -lic '<command>'`; tests run hostile names and values through a real `bash -lic` and check they reach the tool
   verbatim. HA's request and a parent Claude Code's session variables are removed from the session's environment.
4. **Server ↔ server (moving a session).** `export` reads only a non-running session's transcript; `import` writes
   only a new transcript (never overwriting, mode 600) for a folder inside home, after checking it is gzip + JSON lines
   of that session, at most 64 MB unpacked.
5. **HA → browser (card).** Every value from the sensor is HTML-escaped; the card only reads this integration's own
   sensors (entity registry platform, not just an attribute) and hides New, Stop and Resume from non-admins (the
   services refuse them anyway).
6. **GitHub → server (install).** The install command checks `install.sh`, and `install.sh` checks the agent, against
   SHA-256 values shipped in the integration release, so a server runs the agent that release expects.

## Threats

| Threat | Mitigation | Residual |
|---|---|---|
| Stolen HA key used from elsewhere | `from=` | An attacker who also takes over HA's address on the LAN |
| HA compromised (or its key stolen and HA's address spoofed) | Agent allowlist, home-only folders, no prompts | Can start sessions with bypass flags and `--remote-control`, mark any home folder trusted (then project config such as hooks or `.mcp.json` in that folder runs), read titles, and copy transcripts between servers |
| Command injection through names, folders, values | Allowlist, value patterns, `shlex.join`, sanitised screen names, JSON/TOML written with escaping and validated | None known |
| Path traversal (resume, import, trust) | `realpath` + inside-home check, UUID session ids, slugged project dirs | Symlink races by the same user (not a boundary) |
| Impostor server | Pinned host key after a fingerprint check at setup | The very first connection is trust on first use |
| Tampered release or moved tag | Checksums pinned in the integration; tag-triggered release with provenance | A compromised HACS install of the integration itself |
| XSS through session titles | Escaping in the card | None known |
| Resource exhaustion (many sessions) | None (admin-only) | No rate limit |
| Secrets in logs | Errors carry the agent's message or the SSH error, never the key; no diagnostics dump | Session titles in sensor attributes |

## Assumptions

- HA admins are trusted; HA is kept updated and its backups are encrypted.
- Sessions run as a dedicated, unprivileged user whose home holds only code you trust.
- The servers' SSH ports are not exposed to the internet.
