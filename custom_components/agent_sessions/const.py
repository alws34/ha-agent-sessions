"""Constants and the built-in flag catalog."""
DOMAIN = "agent_sessions"
VERSION = "0.1.4"  # must match manifest.json (tests check); also the git tag the installer is fetched from
REPO = "alws34/ha-agent-sessions"
TOOLS = ("claude", "codex")
TOOL_NAMES = {"claude": "Claude Code", "codex": "Codex CLI"}

# Built-in flags per tool. "args" go on the command line; flags with "value" take the value (formatted with "fmt")
# as one more argument. "resume": False means the flag makes no sense when resuming a session.
FLAGS = {
    "claude": [
        {"id": "skip_permissions", "args": ["--dangerously-skip-permissions"]},
        {"id": "remote_control", "args": ["--remote-control"]},
        {"id": "continue", "args": ["--continue"], "resume": False},
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
DEFAULT_FLAGS = {"claude": ["skip_permissions", "remote_control"], "codex": ["no_alt_screen"]}
DEFAULT_VALUES = {"claude": {"model": "opus", "effort": "high"}, "codex": {"model": "", "effort": "medium"}}
EFFORTS = {"claude": ["low", "medium", "high", "xhigh", "max"], "codex": ["minimal", "low", "medium", "high"]}

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


def opt_flags(tool):
    return f"{tool}_flags"


def opt_value(tool, key):
    return f"{tool}_{key}"


def opt_custom(tool):
    return f"{tool}_custom_flags"
