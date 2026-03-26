"""SafeClaw config template - generates and manages ~/.safeclaw/config.json."""

import json
import os
from copy import deepcopy
from pathlib import Path

DEFAULT_CONFIG: dict = {
    "enabled": True,
    "userId": "",
    "mode": "embedded",
    "embedded": {
        "ontologyDir": "~/.safeclaw/ontologies",
        "auditDir": "~/.safeclaw/audit",
    },
    "remote": {
        "serviceUrl": "http://localhost:8420/api/v1",
        "apiKey": "",
        "timeoutMs": 500,
    },
    "enforcement": {
        "mode": "enforce",
        "blockMessage": "[SafeClaw] Action blocked: {reason}",
        "maxReasonerTimeMs": 200,
    },
    "contextInjection": {
        "enabled": True,
        "includePreferences": True,
        "includePolicies": True,
        "includeSessionFacts": True,
        "includeRecentViolations": True,
        "maxContextChars": 2000,
    },
    "audit": {
        "enabled": True,
        "logLlmIO": True,
        "logAllowedActions": True,
        "logBlockedActions": True,
        "retentionDays": 90,
        "format": "jsonl",
    },
    "roles": {
        "definitions": {
            "researcher": {"enforcement_mode": "enforce", "autonomy_level": "supervised", "policyFile": "researcher.ttl"},
            "developer": {"enforcement_mode": "enforce", "autonomy_level": "moderate", "policyFile": "developer.ttl"},
            "admin": {"enforcement_mode": "warn-only", "autonomy_level": "full", "policyFile": "admin.ttl"},
        },
        "defaultRole": "developer",
    },
    "agents": {
        "delegationPolicy": "configurable",
        "requireTokenAuth": True,
    },
}


def generate_config(
    user_id: str = "",
    mode: str = "embedded",
    service_url: str = "http://localhost:8420/api/v1",
) -> dict:
    """Generate a customized SafeClaw config from defaults."""
    config = deepcopy(DEFAULT_CONFIG)
    config["userId"] = user_id
    config["mode"] = mode
    config["remote"]["serviceUrl"] = service_url
    return config


def write_config(config_path: Path, config: dict) -> None:
    """Write config dict to a JSON file, creating parent dirs if needed.

    Files are created with 0o600 (owner read/write only) and parent
    directories with 0o700 (owner only) since config may contain API keys.
    """
    parent = config_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Ensure parent directories have restrictive permissions
    try:
        os.chmod(str(parent), 0o700)
    except OSError:
        pass
    content = json.dumps(config, indent=2) + "\n"
    fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)


def load_config(config_path: Path) -> dict:
    """Load config from disk, filling in defaults for any missing keys."""
    defaults = deepcopy(DEFAULT_CONFIG)
    if not config_path.exists():
        return defaults
    stored = json.loads(config_path.read_text())
    return _deep_merge(defaults, stored)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning merged result."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
