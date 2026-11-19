"""Constants and the built-in flag catalog."""
import shlex

DOMAIN = "agent_sessions"
VERSION = "0.2.0"  # must match manifest.json (tests check); also the git tag the installer is fetched from
AGENT_VERSION = "4"  # agent/agent-sessions VERSION this release expects; older agents get a Repairs issue
REPO = "alws34/ha-agent-sessions"
TOOLS = ("claude", "codex")
TOOL_NAMES = {"claude": "Claude Code", "codex": "Codex CLI"}

# Built-in flags per tool. "args" go on the command line; flags with "value" take the value (formatted with "fmt")
# as one more argument. "resume": False means the flag makes no sense when resuming a session; "resume_only": True
# means it only makes sense when resuming.
FLAGS = {
    "claude": [
        {"id": "skip_permissions", "args": ["--dangerously-skip-permissions"]},
        {"id": "remote_control", "args": ["--remote-control"]},
        {"id": "continue", "args": ["--continue"], "resume": False},
        {"id": "fork_session", "args": ["--fork-session"], "resume_only": True},
        {"id": "model", "args": ["--model"], "value": "model"},
        {"id": "effort", "args": ["--effort"], "value": "effort"},
        {"id": "verbose", "args": ["--verbose"]},
    ],
    "codex": [
        {"id": "bypass", "args": ["--dangerously-bypass-approvals-and-sandbox"]},
        {"id": "search", "args": ["--search"]},
        {"id": "model", "args": ["-m"], "value": "model"},
        {"id": "effort", "args": ["-c"], "value": "effort", "fmt": "model_reasoning_effort={}"},
        {"id": "no_alt_screen", "args": ["--no-alt-screen"]},
    ],
}
# What the options form shows is what sessions get. On/off flags are ticked by default when listed here (the form's
# "flags ticked by default"). Flags with a value (model, effort) are not in that list: they are ticked whenever their
# value field in the form is filled in, so a value shown in the form is always sent (an empty model is not sent).
# ENTRY_MINOR_VERSION 3 migrates older entries to this (see async_migrate_entry).
DEFAULT_FLAGS = {"claude": ["skip_permissions", "remote_control"], "codex": ["no_alt_screen"]}
ENTRY_MINOR_VERSION = 3
DEFAULT_VALUES = {"claude": {"model": "opus", "effort": "high"}, "codex": {"model": "", "effort": "medium"}}
EFFORTS = {"claude": ["low", "medium", "high", "xhigh", "max"], "codex": ["none", "minimal", "low", "medium", "high", "xhigh"]}

CONF_HA_ADDRESS = "ha_address"
CONF_PRIVATE_KEY = "private_key"
CONF_HOST_KEY = "host_key"
CONF_TOOLS = "tools"

OPT_FOLDERS = "folders"
OPT_TRUSTED = "trusted_folders"
OPT_TRUST_ANY = "trust_any"
OPT_RECENT = "recent"
OPT_INTERVAL = "scan_interval"
OPT_CONFIRM_STOP = "confirm_stop"
OPT_DEFAULT_TOOL = "default_tool"
OPT_POSITION = "position"


def opt_flags(tool):
    return f"{tool}_flags"


def opt_value(tool, key):
    return f"{tool}_{key}"


def value_flags(tool):
    """Ids of the flags that take a value (model, effort): on by default exactly when their option has a value."""
    return [f["id"] for f in FLAGS[tool] if "value" in f]


def toggle_flags(tool):
    """Ids of the on/off flags: the choices of the options form's "flags ticked by default"."""
    return [f["id"] for f in FLAGS[tool] if "value" not in f]


def opt_custom(tool):
    return f"{tool}_custom_flags"


# SHA-256 of agent/install.sh and agent/agent-sessions at this release's tag (tests check them against the files). The
# install command refuses anything else, so a server only ever runs the agent this release of the integration expects,
# even if the tag on GitHub were moved.
INSTALLER_SHA256 = "397420a7ecfdc8a2455e971a0ab1bdc0bfc6bd65ba697648547f6bc210232999"
AGENT_SHA256 = "6e4e5735596d1955999d39f7f6208bdecd10c2c3a52642976a6ce9485d5dd572"

# Downloads install.sh to a temporary file, checks it, then runs it (a cut-off download or a changed file never runs).
# Plain POSIX sh with everything passed as arguments, so it pastes the same into bash, zsh or fish.
_INSTALL_SH = ('f=$(mktemp) || exit 1; if curl -fsSL "$1" -o "$f" && echo "$2  $f" | sha256sum -c --status; '
               'then bash "$f" "$3" "$4" "$5" "$6"; s=$?; '
               'else echo "agent-sessions: download failed or install.sh does not match this release" >&2; s=1; fi; '
               'rm -f "$f"; exit $s')


def install_command(ha_address, public_key):
    """The one-line installer shown at setup and in the "agent outdated" repair. ha_address is validated at setup."""
    ref = f"v{VERSION}"
    url = f"https://raw.githubusercontent.com/{REPO}/{ref}/agent/install.sh"
    return shlex.join(["sh", "-c", _INSTALL_SH, "sh", url, INSTALLER_SHA256, ref, ha_address, public_key, AGENT_SHA256])
