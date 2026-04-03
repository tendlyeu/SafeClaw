"""Policy checker - evaluates proposed actions against policy ontology."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from safeclaw.constants import PATH_PARAM_KEYS
from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SC, SP

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy

logger = logging.getLogger("safeclaw.policy")


@dataclass
class PolicyCheckResult:
    violated: bool
    policy_uri: str = ""
    policy_type: str = ""
    reason: str = ""
    all_violations: list[dict] = field(default_factory=list)


class PolicyChecker:
    """Checks actions against policy prohibitions and obligations."""

    @staticmethod
    def _extract_resource_path(params: dict) -> str:
        """Extract resource path from params, checking common key variants."""
        for key in PATH_PARAM_KEYS:
            val = params.get(key, "")
            if val and isinstance(val, str):
                return val
        return ""

    _PROTOCOL_SCHEME_MAP: dict[str, set[str] | None] = {
        "rest": {"https", "http"},
        "grpc": {"https", "http"},
        "websocket": {"wss", "ws"},
        "full": None,
    }

    # Action classes that trigger NemoClaw network checks
    _NETWORK_ACTION_CLASSES = {"WebFetch", "WebSearch"}

    # Action classes that trigger NemoClaw filesystem checks
    _FILE_WRITE_ACTION_CLASSES = {
        "FileWrite",
        "FileDelete",
        "FileCreate",
        "WriteFile",
        "EditFile",
        "DeleteFile",
    }
    _FILE_READ_ACTION_CLASSES = {"FileRead", "ReadFile"}
    _FILE_ACTION_CLASSES = _FILE_WRITE_ACTION_CLASSES | _FILE_READ_ACTION_CLASSES

    # Patterns in exec commands that indicate network activity
    _NETWORK_COMMAND_RE = re.compile(r"\b(?:curl|wget|fetch|http)\b", re.IGNORECASE)

    # URL extraction regex for shell commands (http, https, ws, wss)
    _URL_RE = re.compile(r"(?:https?|wss?)://[^\s\"'<>]+")

    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        hierarchy: ClassHierarchy | None = None,
        nemoclaw_enabled: bool = False,
    ):
        self.kg = knowledge_graph
        self._hierarchy = hierarchy
        self._nemoclaw_enabled = nemoclaw_enabled
        self._forbidden_paths: list[tuple[str, str, str]] = []
        self._forbidden_commands: list[tuple[str, str, str]] = []
        self._class_prohibitions: list[tuple[str, str, str]] = []
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Load forbidden patterns from the knowledge graph."""
        # Path constraints
        path_results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?policy ?pattern ?reason WHERE {{
                ?policy a sp:Prohibition ;
                        sp:forbiddenPathPattern ?pattern ;
                        sp:reason ?reason .
            }}
        """)
        self._forbidden_paths = [
            (str(r["policy"]), str(r["pattern"]).strip("/"), str(r["reason"])) for r in path_results
        ]

        # Command constraints
        cmd_results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?policy ?pattern ?reason WHERE {{
                ?policy a sp:Prohibition ;
                        sp:forbiddenCommandPattern ?pattern ;
                        sp:reason ?reason .
            }}
        """)
        self._forbidden_commands = [
            (str(r["policy"]), str(r["pattern"]), str(r["reason"])) for r in cmd_results
        ]

        # Class-level prohibitions (sp:appliesTo)
        class_results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            PREFIX sc: <{SC}>
            SELECT ?policy ?target ?reason WHERE {{
                ?policy a sp:Prohibition ;
                        sp:appliesTo ?target ;
                        sp:reason ?reason .
            }}
        """)
        for r in class_results:
            target_uri = str(r["target"])
            # Extract local name from URI
            target_class = target_uri.rsplit("#", 1)[-1] if "#" in target_uri else target_uri
            self._class_prohibitions.append((str(r["policy"]), target_class, str(r["reason"])))

    def _safe_match(self, pattern: str, text: str) -> bool:
        """Safely match a regex pattern, catching malformed patterns."""
        try:
            return bool(re.search(pattern, text))
        except re.error:
            logger.warning(f"Invalid regex pattern in policy: {pattern!r}")
            return False

    def check(self, action: ClassifiedAction) -> PolicyCheckResult:
        """Check if action violates any policies."""
        all_violations: list[dict] = []

        # Check path constraints
        file_path = self._extract_resource_path(action.params)
        if file_path:
            normalized_path = file_path.strip("/")
            for policy_uri, pattern, reason in self._forbidden_paths:
                if self._safe_match(pattern, normalized_path):
                    all_violations.append(
                        {
                            "policy_uri": policy_uri,
                            "policy_type": "Prohibition",
                            "reason": reason,
                        }
                    )

        # Check command constraints
        command = action.params.get("command", "")
        if command:
            for policy_uri, pattern, reason in self._forbidden_commands:
                if self._safe_match(pattern, command):
                    all_violations.append(
                        {
                            "policy_uri": policy_uri,
                            "policy_type": "Prohibition",
                            "reason": reason,
                        }
                    )

        # Check class-level prohibitions (hierarchy-aware)
        if self._class_prohibitions:
            action_classes = (
                self._hierarchy.get_superclasses(action.ontology_class)
                if self._hierarchy
                else {action.ontology_class}
            )
            for policy_uri, target_class, reason in self._class_prohibitions:
                if target_class in action_classes:
                    all_violations.append(
                        {
                            "policy_uri": policy_uri,
                            "policy_type": "Prohibition",
                            "reason": reason,
                        }
                    )

        # NemoClaw checks (allowlist semantics, gated on nemoclaw_enabled)
        if self._nemoclaw_enabled:
            nemo_net = self._check_nemo_network_rules(action)
            if nemo_net:
                all_violations.append(nemo_net)

            nemo_fs = self._check_nemo_filesystem_rules(action)
            if nemo_fs:
                all_violations.append(nemo_fs)

        if all_violations:
            first = all_violations[0]
            return PolicyCheckResult(
                violated=True,
                policy_uri=first["policy_uri"],
                policy_type=first["policy_type"],
                reason=first["reason"],
                all_violations=all_violations,
            )

        return PolicyCheckResult(violated=False)

    # ------------------------------------------------------------------
    # NemoClaw network allowlist check
    # ------------------------------------------------------------------

    def _is_network_action(self, action: ClassifiedAction) -> bool:
        """Return True if this action involves network access."""
        if action.ontology_class in self._NETWORK_ACTION_CLASSES:
            return True
        if action.ontology_class in ("ExecuteCommand", "NetworkRequest"):
            command = action.params.get("command", "")
            if self._NETWORK_COMMAND_RE.search(command):
                return True
        return False

    def _extract_url(self, action: ClassifiedAction) -> str | None:
        """Extract a URL from the action parameters."""
        # Direct URL params (WebFetch, WebSearch)
        for key in ("url", "endpoint"):
            val = action.params.get(key, "")
            if val and isinstance(val, str):
                return val

        # Extract from command string
        command = action.params.get("command", "")
        if command:
            match = self._URL_RE.search(command)
            if match:
                return match.group(0)

        return None

    @staticmethod
    def _host_matches(rule_host: str, target_host: str) -> bool:
        """Check if target_host matches rule_host (supports wildcard suffix)."""
        if rule_host.startswith("*."):
            # Wildcard: *.github.com matches foo.github.com and github.com
            suffix = rule_host[1:]  # .github.com
            return target_host.endswith(suffix) or target_host == rule_host[2:]
        return rule_host == target_host

    def _check_nemo_network_rules(self, action: ClassifiedAction) -> dict | None:
        """Check network action against NemoClaw allowlist rules.

        Returns a violation dict if the action is blocked, or None if allowed.
        Allowlist semantics: no rules = skip, no match = block.
        """
        if not self._is_network_action(action):
            return None

        url = self._extract_url(action)
        if not url:
            # Fail-closed: if network rules exist but URL can't be extracted, block
            has_rules = bool(
                self.kg.query(f"""
                PREFIX sp: <{SP}>
                SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule }} LIMIT 1
            """)
            )
            if has_rules:
                return {
                    "policy_uri": "nemoclaw:network-allowlist",
                    "policy_type": "NemoNetworkRule",
                    "reason": (
                        "Network activity detected but URL could not be extracted "
                        "for allowlist verification"
                    ),
                }
            return None

        # Query all NemoClaw network rules (including optional binary restrictions)
        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule ?host ?port ?protocol ?binary ?enforcement WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
                OPTIONAL {{ ?rule sp:allowsPort ?port }}
                OPTIONAL {{ ?rule sp:allowsProtocol ?protocol }}
                OPTIONAL {{ ?rule sp:binaryRestriction ?binary }}
                OPTIONAL {{ ?rule sp:enforcement ?enforcement }}
            }}
        """)

        # No NemoClaw network rules in graph = not running with NemoClaw, skip
        if not results:
            return None

        # Parse the target URL
        parsed = urlparse(url)
        target_host = parsed.hostname or ""
        target_port = parsed.port
        target_scheme = parsed.scheme or ""

        # Default ports when not explicit in URL
        if target_port is None:
            if target_scheme in ("https", "wss"):
                target_port = 443
            elif target_scheme in ("http", "ws"):
                target_port = 80

        # Group rows by rule URI so we can collect all binary restrictions
        rule_rows: dict[str, dict] = {}
        for row in results:
            uri = str(row["rule"])
            if uri not in rule_rows:
                enforcement = row.get("enforcement")
                enforcement_str = str(enforcement) if enforcement else "enforce"
                rule_rows[uri] = {
                    "host": row["host"],
                    "port": row.get("port"),
                    "protocol": row.get("protocol"),
                    "binaries": set(),
                    "enforcement": enforcement_str,
                }
            binary = row.get("binary")
            if binary is not None:
                rule_rows[uri]["binaries"].add(str(binary))

        command = action.params.get("command", "")

        # Filter out disabled rules before matching
        active_rules = {
            uri: info
            for uri, info in rule_rows.items()
            if info["enforcement"] != "disabled"
        }

        # If no active (non-disabled) rules remain, skip the check
        if not active_rules:
            return None

        for info in active_rules.values():
            rule_host = str(info["host"])
            if not self._host_matches(rule_host, target_host):
                continue

            rule_port = info["port"]
            if rule_port is not None:
                try:
                    if int(rule_port) != target_port:
                        continue
                except (ValueError, TypeError):
                    continue

            rule_protocol = info["protocol"]
            if rule_protocol is not None and str(rule_protocol):
                if not self._protocol_matches(str(rule_protocol), target_scheme):
                    continue

            binaries = info["binaries"]
            if binaries:
                if not self._binary_matches(action, binaries, command):
                    continue

            return None

        port_str = f":{target_port}" if target_port else ""
        return {
            "policy_uri": "nemoclaw:network-allowlist",
            "policy_type": "NemoNetworkRule",
            "reason": (f"Not in NemoClaw network allowlist: {target_host}{port_str}"),
        }

    @classmethod
    def _protocol_matches(cls, rule_protocol: str, target_scheme: str) -> bool:
        """Check if a rule protocol matches the URL scheme.

        NemoClaw uses protocol names like ``rest``, ``grpc``, ``websocket``
        which do not correspond directly to URL schemes. This method maps
        known protocol names to their valid scheme sets. Unknown protocols
        fall back to exact string comparison (e.g. ``https`` == ``https``).
        """
        allowed = cls._PROTOCOL_SCHEME_MAP.get(rule_protocol)
        if allowed is None and rule_protocol in cls._PROTOCOL_SCHEME_MAP:
            return True
        if allowed is not None:
            return target_scheme in allowed
        return rule_protocol == target_scheme

    @staticmethod
    def _binary_matches(
        action: ClassifiedAction,
        binaries: set[str],
        command: str,
    ) -> bool:
        """Check if the action context matches any binary restriction.

        For ``ExecuteCommand`` actions the command string is checked for
        references to the restricted binaries. For other action types
        (e.g. ``WebFetch``) binary checking is skipped since we cannot
        determine the calling binary — the rule still matches.
        """
        if action.ontology_class not in ("ExecuteCommand", "NetworkRequest"):
            return True
        if not command:
            return False
        for bp in binaries:
            # Full path: match with word boundary to avoid /usr/bin/git matching
            # /usr/bin/github-cli
            if re.search(rf"(?:^|\s){re.escape(bp)}(?:\s|$)", command):
                return True
            binary_name = bp.rsplit("/", 1)[-1]
            if binary_name and re.search(rf"\b{re.escape(binary_name)}\b", command):
                return True
        return False

    # ------------------------------------------------------------------
    # NemoClaw filesystem policy check
    # ------------------------------------------------------------------

    def _is_file_action(self, action: ClassifiedAction) -> bool:
        """Return True if this action involves filesystem access."""
        return action.ontology_class in self._FILE_ACTION_CLASSES

    def _is_write_action(self, action: ClassifiedAction) -> bool:
        """Return True if this is a write/delete/create action (not read-only)."""
        return action.ontology_class in self._FILE_WRITE_ACTION_CLASSES

    def _check_nemo_filesystem_rules(self, action: ClassifiedAction) -> dict | None:
        """Check file action against NemoClaw filesystem rules.

        Returns a violation dict if the action is blocked, or None if allowed.
        Prefix matching: most specific (longest) rule path wins.
        """
        if not self._is_file_action(action):
            return None

        target_path = os.path.normpath(self._extract_resource_path(action.params))
        if not target_path:
            return None

        # Query all NemoClaw filesystem rules
        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)

        # No NemoClaw filesystem rules in graph = skip
        if not results:
            return None

        # Find the most specific (longest prefix) matching rule
        best_match: tuple[str, str] | None = None  # (path, mode)
        best_len = -1

        for row in results:
            rule_path = str(row["path"])
            rule_mode = str(row["mode"])

            # Prefix matching (like Landlock): rule path must be a prefix of target
            if target_path == rule_path or target_path.startswith(
                rule_path if rule_path.endswith("/") else rule_path + "/"
            ):
                if len(rule_path) > best_len:
                    best_len = len(rule_path)
                    best_match = (rule_path, rule_mode)

        if best_match is None:
            # No rule covers this path — outside sandbox
            return {
                "policy_uri": "nemoclaw:filesystem-policy",
                "policy_type": "NemoFilesystemRule",
                "reason": (f"Path {target_path} is outside NemoClaw sandbox filesystem policy"),
            }

        _rule_path, mode = best_match
        is_write = self._is_write_action(action)

        if mode == "denied":
            return {
                "policy_uri": "nemoclaw:filesystem-policy",
                "policy_type": "NemoFilesystemRule",
                "reason": f"NemoClaw filesystem policy: {_rule_path} is denied",
            }

        if mode == "read-only" and is_write:
            return {
                "policy_uri": "nemoclaw:filesystem-policy",
                "policy_type": "NemoFilesystemRule",
                "reason": f"NemoClaw filesystem policy: {_rule_path} is read-only",
            }

        # read-write allows all, read-only allows reads
        return None
