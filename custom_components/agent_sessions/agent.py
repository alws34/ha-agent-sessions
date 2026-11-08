"""SSH client for the agent on a server (agent/agent-sessions)."""
import asyncio
import base64
import json

import asyncssh

HOST_KEY_ALGS = ["ssh-ed25519", "ecdsa-sha2-nistp256", "rsa-sha2-512", "rsa-sha2-256"]
RETRY_SAFE = frozenset({"info", "list", "sessions", "export"})  # read-only verbs
TIMEOUT = {"export": 180, "import": 180}  # seconds; moving a large transcript takes a while


class AgentError(Exception):
    """The agent refused a request or could not be reached."""


class AuthFailed(AgentError):
    """The server rejected Home Assistant's key (installer not run, or key line removed)."""


def public_key(private_key):
    """The OpenSSH public key line for a stored private key (for the install command)."""
    key = asyncssh.import_private_key(private_key)
    return key.export_public_key().decode().strip()  # keeps the "home-assistant-agent-sessions" comment


def new_key():
    """A fresh ed25519 key pair: (OpenSSH private key, public key line)."""
    key = asyncssh.generate_private_key("ssh-ed25519", comment="home-assistant-agent-sessions")
    return key.export_private_key().decode(), key.export_public_key().decode().strip()


class Agent:
    """One persistent SSH connection per server; every call is one exec of the forced-command agent."""

    def __init__(self, host, port, username, private_key, host_key=None):
        self._host, self._port, self._user = host, port, username
        self._key = asyncssh.import_private_key(private_key)
        self._host_key = host_key  # pinned after the first connection; None only during setup
        self._conn = None
        self._lock = asyncio.Lock()
        self.server_key = None  # what the server presented, for the setup flow to pin

    async def _connect(self):
        async with self._lock:
            if self._conn is not None:
                return self._conn
            known = ([asyncssh.import_public_key(self._host_key)], [], []) if self._host_key else None
            try:
                conn = await asyncssh.connect(
                    self._host, port=self._port, username=self._user, client_keys=[self._key],
                    known_hosts=known, agent_path=None, config=[], connect_timeout=10, keepalive_interval=30,
                    preferred_auth="publickey",
                    # ed25519 first so the fingerprint shown at setup is the one users are told to check
                    server_host_key_algs=HOST_KEY_ALGS)
            except asyncssh.PermissionDenied as err:
                raise AuthFailed(str(err)) from err
            except (OSError, asyncssh.Error) as err:
                raise AgentError(f"cannot connect to {self._host}: {err}") from err
            self.server_key = conn.get_server_host_key()
            self._conn = conn
            return conn

    async def call(self, verb, payload=None, stdin=None):
        """Run one agent verb. stdin carries bulk data (import); everything else goes in the command line."""
        cmd = verb + (" " + base64.b64encode(json.dumps(payload).encode()).decode() if payload else "")
        for attempt in (1, 2):
            conn = await self._connect()
            try:
                res = await conn.run(cmd, input=stdin, check=False, timeout=TIMEOUT.get(verb, 60))
                break
            except (TimeoutError, OSError, asyncssh.Error) as err:
                await self.close()
                # The kept-open connection may have died (server reboot): retry once on a new one. Verbs that start
                # or change something only when the command surely never ran, or a slow reply would start it twice.
                if attempt == 2 or (verb not in RETRY_SAFE and not isinstance(err, asyncssh.ChannelOpenError)):
                    raise AgentError(f"{self._host}: {err or type(err).__name__}") from err
        out = (res.stdout or "").strip().splitlines()
        try:
            data = json.loads(out[-1])
        except (IndexError, ValueError):
            raise AgentError(f"agent did not answer ({str(res.stderr or '').strip()[:200] or 'no output'})") from None
        if not isinstance(data, dict):
            raise AgentError("agent sent an invalid reply")
        if "error" in data:
            raise AgentError(str(data["error"]))
        return data

    async def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
