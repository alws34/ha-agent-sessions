#!/usr/bin/env bash
# Agent Sessions installer. Home Assistant shows you the exact command to run; it looks like:
#   curl -fsSL https://raw.githubusercontent.com/alws34/ha-agent-sessions/<ref>/agent/install.sh \
#     | bash -s -- <ref> <home-assistant-ip> '<ssh public key>'
# It installs the agent to ~/.local/bin/agent-sessions and lets HA's key run only that agent, only from that IP.
# Nothing else is changed. Re-running it is safe (it replaces the previous key line for the same key).
set -euo pipefail

REF=${1:?ref missing}; HA_IP=${2:?Home Assistant IP missing}; KEY=${3:?public key missing}
[[ $REF =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "bad ref" >&2; exit 1; }
[[ $HA_IP =~ ^[0-9A-Fa-f.:/,*]+$ ]] || { echo "bad Home Assistant address: $HA_IP" >&2; exit 1; }
[[ $KEY =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ [A-Za-z0-9@._-]+)?$ ]] || { echo "bad public key" >&2; exit 1; }

say() { printf '\033[1m%s\033[0m\n' "$*"; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v screen >/dev/null || { echo "GNU screen is required (e.g. sudo apt install screen)" >&2; exit 1; }
found=""
for t in claude codex; do
  if command -v "$t" >/dev/null || [ -x "$HOME/.local/bin/$t" ]; then found="$found $t"; fi
done
[ -n "$found" ] || say "Warning: neither claude nor codex found for $(whoami). Install one before starting sessions."

AGENT="$HOME/.local/bin/agent-sessions"
mkdir -p "$HOME/.local/bin"
tmp=$(mktemp)
# AGENT_SESSIONS_URL: install from somewhere else (a fork, or a local file:// copy when testing)
curl -fsSL "${AGENT_SESSIONS_URL:-https://raw.githubusercontent.com/alws34/ha-agent-sessions/$REF/agent/agent-sessions}" -o "$tmp"
head -1 "$tmp" | grep -q python3 || { echo "download failed" >&2; rm -f "$tmp"; exit 1; }
install -m 755 "$tmp" "$AGENT"; rm -f "$tmp"

mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
AK="$HOME/.ssh/authorized_keys"; touch "$AK"; chmod 600 "$AK"
body=$(cut -d' ' -f2 <<<"$KEY")
grep -vF "$body" "$AK" > "$AK.tmp" || true
echo "from=\"$HA_IP\",command=\"$AGENT\",restrict $KEY" >> "$AK.tmp"
mv "$AK.tmp" "$AK"

say "Agent Sessions installed for $(whoami)."
echo "Tools found:${found:- none}"
echo "This server's host key fingerprints (compare with Home Assistant):"
for f in /etc/ssh/ssh_host_ed25519_key.pub /etc/ssh/ssh_host_ecdsa_key.pub /etc/ssh/ssh_host_rsa_key.pub; do
  [ -r "$f" ] && ssh-keygen -lf "$f"
done
echo "Now press Submit in Home Assistant."
