#!/usr/bin/env bash
# Agent Sessions installer. Home Assistant shows you the exact command to run. It downloads this script from the
# release tag, checks it against the SHA-256 that release of the integration expects, and runs it as
#   bash install.sh <ref> <home-assistant-ip> '<ssh public key>' [<agent sha256>]
# It installs the agent to ~/.local/bin/agent-sessions (checked against <agent sha256> when given) and lets HA's key
# run only that agent, only from that IP. Nothing else is changed. Re-running it is safe (it replaces the previous key
# line for the same key).
set -euo pipefail
umask 077  # everything this script creates (authorized_keys rewrite included) is private to the user

# Everything runs from main, called on the last line, so a download cut short never runs half a script.
main() {
  local REF=${1:?ref missing} HA_IP=${2:?Home Assistant IP missing} KEY=${3:?public key missing} SHA=${4:-}
  [[ $REF =~ ^[A-Za-z0-9._/-]+$ ]] || fail "bad ref"
  # addresses/networks only; no "*" (that would accept the key from any address)
  [[ $HA_IP =~ ^[0-9A-Fa-f.:/,]+$ ]] || fail "bad Home Assistant address: $HA_IP"
  [[ $KEY =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ [A-Za-z0-9@._-]+)?$ ]] || fail "bad public key"
  [[ -z $SHA || $SHA =~ ^[0-9a-f]{64}$ ]] || fail "bad agent checksum"

  command -v python3 >/dev/null || fail "python3 is required"
  command -v screen >/dev/null || fail "GNU screen is required (e.g. sudo apt install screen)"
  local found="" t
  for t in claude codex; do
    if command -v "$t" >/dev/null || [ -x "$HOME/.local/bin/$t" ]; then found="$found $t"; fi
  done
  [ -n "$found" ] || say "Warning: neither claude nor codex found for $(whoami). Install one before starting sessions."

  local AGENT="$HOME/.local/bin/agent-sessions"
  # it goes into authorized_keys as command="...", which sshd runs through the user's shell
  [[ $AGENT =~ ^[A-Za-z0-9._/@+-]+$ ]] || fail "unsupported home folder path: $HOME"
  mkdir -p "$HOME/.local/bin"
  local tmp
  tmp=$(mktemp)
  # AGENT_SESSIONS_URL: install from somewhere else (a fork, or a local file:// copy when testing)
  curl -fsSL "${AGENT_SESSIONS_URL:-https://raw.githubusercontent.com/alws34/ha-agent-sessions/$REF/agent/agent-sessions}" \
    -o "$tmp" || { rm -f "$tmp"; fail "download failed"; }
  head -1 "$tmp" | grep -q python3 || { rm -f "$tmp"; fail "download failed"; }
  if [ -n "$SHA" ]; then
    command -v sha256sum >/dev/null || { rm -f "$tmp"; fail "sha256sum is required"; }
    echo "$SHA  $tmp" | sha256sum -c --status \
      || { rm -f "$tmp"; fail "the downloaded agent does not match this release (checksum mismatch)"; }
  fi
  install -m 755 "$tmp" "$AGENT"
  rm -f "$tmp"

  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  local AK="$HOME/.ssh/authorized_keys" body
  touch "$AK"
  chmod 600 "$AK"
  body=$(cut -d' ' -f2 <<<"$KEY")
  grep -vF "$body" "$AK" > "$AK.tmp" || true
  echo "from=\"$HA_IP\",command=\"$AGENT\",restrict $KEY" >> "$AK.tmp"
  chmod 600 "$AK.tmp"  # sshd (StrictModes) ignores a group/world-writable authorized_keys
  mv "$AK.tmp" "$AK"

  say "Agent Sessions installed for $(whoami)."
  echo "Tools found:${found:- none}"
  echo "This server's host key fingerprints (compare with Home Assistant):"
  local f
  for f in /etc/ssh/ssh_host_ed25519_key.pub /etc/ssh/ssh_host_ecdsa_key.pub /etc/ssh/ssh_host_rsa_key.pub; do
    if [ -r "$f" ]; then ssh-keygen -lf "$f"; fi
  done
  echo "Now press Submit in Home Assistant."
}

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { echo "$*" >&2; exit 1; }

main "$@"
