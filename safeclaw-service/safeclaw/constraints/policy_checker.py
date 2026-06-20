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
from safeclaw.engine.roles import _glob_match

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

    # NemoClaw v0.0.65 protocol enum is exactly ``rest`` | ``websocket``.
    # ``access: full`` is a *separate* endpoint field (not a protocol) handled
    # via the ``networkAccessMode`` rule property, so it is intentionally not
    # in this map. Unknown protocol names fall back to exact scheme comparison.
    _PROTOCOL_SCHEME_MAP: dict[str, set[str]] = {
        "rest": {"https", "http"},
        "websocket": {"wss", "ws"},
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
        self._forbidden_paths: list[tuple[str, re.Pattern, str]] = []
        self._forbidden_commands: list[tuple[str, re.Pattern, str]] = []
        self._class_prohibitions: list[tuple[str, str, str]] = []
        self._nemo_net_rules: list[dict] = []
        self._nemo_fs_rules: list[dict] = []
        self._load_patterns()

    @staticmethod
    def _compile_pattern(pattern: str) -> re.Pattern:
        """Compile a regex pattern, falling back to escaped literal on error."""
        try:
            return re.compile(pattern)
        except re.error:
            logger.warning("Invalid regex in policy, treating as literal: %r", pattern)
            return re.compile(re.escape(pattern))

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
            (
                str(r["policy"]),
                self._compile_pattern(str(r["pattern"]).strip("/")),
                str(r["reason"]),
            )
            for r in path_results
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
            (
                str(r["policy"]),
                self._compile_pattern(str(r["pattern"])),
                str(r["reason"]),
            )
            for r in cmd_results
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
        self._class_prohibitions = []
        for r in class_results:
            target_uri = str(r["target"])
            # Extract local name from URI
            target_class = target_uri.rsplit("#", 1)[-1] if "#" in target_uri else target_uri
            self._class_prohibitions.append((str(r["policy"]), target_class, str(r["reason"])))

        # Pre-load NemoClaw rules so SPARQL is not re-executed per request
        self._load_nemo_network_rules()
        self._load_nemo_filesystem_rules()

    @staticmethod
    def _safe_match(pattern: re.Pattern, text: str) -> bool:
        """Match a pre-compiled regex pattern against text."""
        return bool(pattern.search(text))

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
    # NemoClaw rule caching
    # ------------------------------------------------------------------

    def _load_nemo_network_rules(self) -> None:
        """Pre-load NemoClaw network rules from the knowledge graph."""
        if not self._nemoclaw_enabled:
            self._nemo_net_rules = []
            return

        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule ?host ?port ?protocol ?binary ?enforcement ?accessMode
                   ?allowMethod ?allowPath
            WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
                OPTIONAL {{ ?rule sp:allowsPort ?port }}
                OPTIONAL {{ ?rule sp:allowsProtocol ?protocol }}
                OPTIONAL {{ ?rule sp:binaryRestriction ?binary }}
                OPTIONAL {{ ?rule sp:enforcement ?enforcement }}
                OPTIONAL {{ ?rule sp:networkAccessMode ?accessMode }}
                OPTIONAL {{
                    ?rule sp:allowsRule ?allowNode .
                    ?allowNode sp:allowsPathGlob ?allowPath .
                    OPTIONAL {{ ?allowNode sp:allowsMethod ?allowMethod }}
                }}
            }}
        """)
        self._nemo_net_rules = list(results)

    def _load_nemo_filesystem_rules(self) -> None:
        """Pre-load NemoClaw filesystem rules from the knowledge graph."""
        if not self._nemoclaw_enabled:
            self._nemo_fs_rules = []
            return

        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        self._nemo_fs_rules = list(results)

    # ------------------------------------------------------------------
    # NemoClaw network allowlist check
    # ------------------------------------------------------------------

    def _is_network_action(self, action: ClassifiedAction) -> bool:
        """Return True if this action involves network access.

        For exec/network commands we treat the action as network access when it
        either invokes a known HTTP client (curl/wget/...) OR embeds a URL — so a
        command reaching a non-allowlisted host via an arbitrary binary (e.g.
        ``python client.py https://evil.com``) cannot bypass the egress allowlist.
        """
        if action.ontology_class in self._NETWORK_ACTION_CLASSES:
            return True
        if action.ontology_class in ("ExecuteCommand", "NetworkRequest"):
            command = action.params.get("command", "")
            if self._NETWORK_COMMAND_RE.search(command) or self._URL_RE.search(command):
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
        Uses cached rules from _load_nemo_network_rules().
        """
        if not self._is_network_action(action):
            return None

        url = self._extract_url(action)
        if not url:
            # Fail-closed: if network rules exist but URL can't be extracted
            if self._nemo_net_rules:
                return {
                    "policy_uri": "nemoclaw:network-allowlist",
                    "policy_type": "NemoNetworkRule",
                    "reason": (
                        "Network activity detected but URL could not be "
                        "extracted for allowlist verification"
                    ),
                }
            return None

        results = self._nemo_net_rules

        # No NemoClaw network rules cached = not running with NemoClaw, skip
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

        # Group rows by rule URI so we can collect all binary restrictions and
        # all L7 allow rules (method + path glob) for the endpoint.
        rule_rows: dict[str, dict] = {}
        for row in results:
            uri = str(row["rule"])
            if uri not in rule_rows:
                enforcement = row.get("enforcement")
                enforcement_str = str(enforcement) if enforcement else "enforce"
                access_mode = row.get("accessMode")
                rule_rows[uri] = {
                    "host": row["host"],
                    "port": row.get("port"),
                    "protocol": row.get("protocol"),
                    "access_mode": str(access_mode) if access_mode is not None else None,
                    "binaries": set(),
                    "enforcement": enforcement_str,
                    # Set of (method, path_glob) allow rules; method is None when
                    # the rule did not declare one.
                    "allow_rules": set(),
                }
            binary = row.get("binary")
            if binary is not None:
                rule_rows[uri]["binaries"].add(str(binary))
            allow_path = row.get("allowPath")
            if allow_path is not None:
                allow_method = row.get("allowMethod")
                method_str = str(allow_method).upper() if allow_method is not None else None
                rule_rows[uri]["allow_rules"].add((method_str, str(allow_path)))

        command = action.params.get("command", "")

        # Filter out disabled rules before matching
        active_rules = {
            uri: info for uri, info in rule_rows.items() if info["enforcement"] != "disabled"
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

            # Protocol → scheme matching always applies. `access: full` only
            # disables L7 *path* filtering on the endpoint; it does NOT widen
            # the declared protocol. A `protocol: rest, access: full` endpoint
            # still only accepts http/https, never wss/ws.
            rule_protocol = info["protocol"]
            if rule_protocol is not None and str(rule_protocol):
                if not self._protocol_matches(str(rule_protocol), target_scheme):
                    continue

            binaries = info["binaries"]
            if binaries:
                if not self._binary_matches(action, binaries, command):
                    continue

            # L7 path/method allowlist. `access: full` (or an endpoint with no
            # explicit allow rules) carries no L7 path filtering, so any path on
            # the matched scheme is permitted (current behavior). Otherwise the
            # request path must match at least one allow rule's path glob, and
            # its method must match when both are known.
            allow_rules = info["allow_rules"]
            if info.get("access_mode") != "full" and allow_rules:
                if not self._path_method_allowed(action, target_scheme, url, allow_rules):
                    continue

            return None

        port_str = f":{target_port}" if target_port else ""
        return {
            "policy_uri": "nemoclaw:network-allowlist",
            "policy_type": "NemoNetworkRule",
            "reason": (f"Not in NemoClaw network allowlist: {target_host}{port_str}"),
        }

    # HTTP methods we recognise (NemoClaw also models websocket frames).
    _HTTP_METHODS = {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "CONNECT",
        "TRACE",
        "WEBSOCKET_TEXT",
    }
    # curl `-X POST` / `-XPOST` / `--request POST` / `--request=POST`;
    # wget/httpie `--method=POST`.
    _CMD_METHOD_RE = re.compile(r"(?:^|\s)(?:-X\s*|--request[=\s]+|--method[=\s]+)([A-Za-z]+)")
    # Commands that perform an HTTP request and default to GET when no method
    # flag/verb is given (curl, wget, fetch).
    _GET_DEFAULT_TOOLS = ("curl", "wget", "fetch")
    # httpie-style clients take the method as a positional verb (`http POST …`).
    _POSITIONAL_VERB_TOOLS = ("http", "https", "xh", "httpie")
    # curl/wget long flags that imply POST when no explicit -X is given.
    _CURL_POST_LONG = {
        "data",
        "data-raw",
        "data-binary",
        "data-ascii",
        "data-urlencode",
        "json",
        "form",
        "form-string",
        "post-data",
        "post-file",
    }

    @staticmethod
    def _method_from_command(command: str) -> str | None:
        """Parse the HTTP method from a shell command, or None if undeterminable."""
        m = PolicyChecker._CMD_METHOD_RE.search(command)
        if m and m.group(1).upper() in PolicyChecker._HTTP_METHODS:
            return m.group(1).upper()

        tokens = command.split()
        bases = [t.rsplit("/", 1)[-1] for t in tokens]
        # httpie/xh: method is the first non-flag positional after the client.
        for i, base in enumerate(bases):
            if base in PolicyChecker._POSITIONAL_VERB_TOOLS:
                for nxt in tokens[i + 1 :]:
                    if nxt.startswith("-"):
                        continue
                    return nxt.upper() if nxt.upper() in PolicyChecker._HTTP_METHODS else "GET"
                return "GET"
        # curl/wget/fetch: infer the implicit method from data/form/head flags,
        # otherwise GET. (Without this, `curl -d …` would read as GET and slip
        # past a method-scoped allowlist.)
        if any(b in PolicyChecker._GET_DEFAULT_TOOLS for b in bases):
            return PolicyChecker._implicit_curl_method(tokens) or "GET"
        return None

    @staticmethod
    def _implicit_curl_method(tokens: list[str]) -> str | None:
        """Infer the implicit HTTP method from curl/wget flags (no explicit -X).

        Handles both separated (``-d x``) and attached (``-dx``, ``-Tfile``)
        short options and bundled boolean flags (``-sI``). Precedence mirrors
        curl: ``-G/--get`` forces GET, then ``-I`` HEAD, ``-T`` PUT, data/form
        POST. Returns None when no method-affecting flag is present.
        """
        has_get = has_head = has_put = has_post = False
        for tok in tokens:
            if tok.startswith("--"):
                name = tok[2:].split("=", 1)[0]
                if name == "get":
                    has_get = True
                elif name == "head":
                    has_head = True
                elif name == "upload-file":
                    has_put = True
                elif name in PolicyChecker._CURL_POST_LONG:
                    has_post = True
            elif tok.startswith("-") and len(tok) > 1:
                # Short cluster: a value-taking flag (d/F/T/X) consumes the rest
                # of the token as its attached argument.
                for ch in tok[1:]:
                    if ch in ("d", "F"):
                        has_post = True
                        break
                    if ch == "T":
                        has_put = True
                        break
                    if ch == "X":
                        break  # explicit method already handled by _CMD_METHOD_RE
                    if ch == "I":
                        has_head = True
                    elif ch == "G":
                        has_get = True
        if has_get:
            return "GET"
        if has_head:
            return "HEAD"
        if has_put:
            return "PUT"
        if has_post:
            return "POST"
        return None

    @staticmethod
    def _request_method(action: ClassifiedAction, target_scheme: str) -> str | None:
        """Best-effort HTTP method for the request, normalised to upper case.

        An explicit ``method`` param wins. Direct fetch tools default to ``GET``
        (or ``WEBSOCKET_TEXT`` for ws(s)). For exec/network commands we parse the
        command string (``curl -X POST``, ``http PUT …`` etc.). Returns ``None``
        only when the method genuinely cannot be inferred (e.g. an opaque command
        that merely references a URL) — callers then FAIL CLOSED against any rule
        that constrains the method, rather than allowing on the path glob alone.
        """
        for key in ("method", "httpMethod", "http_method"):
            val = action.params.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().upper()

        if target_scheme in ("ws", "wss"):
            return "WEBSOCKET_TEXT"

        # Direct URL fetch tools: default to GET.
        if action.ontology_class in PolicyChecker._NETWORK_ACTION_CLASSES:
            return "GET"

        # Network activity inside an exec command — parse the method when we can.
        command = action.params.get("command", "")
        if command:
            return PolicyChecker._method_from_command(command)
        return None

    def _path_method_allowed(
        self,
        action: ClassifiedAction,
        target_scheme: str,
        url: str,
        allow_rules: set[tuple[str | None, str]],
    ) -> bool:
        """Return True if the request path/method matches an allow rule.

        The path glob is ALWAYS enforced: the request's URL path must match at
        least one allow rule's ``path`` glob. Method enforcement FAILS CLOSED: a
        rule that declares a method only authorises the request when the request
        method is known (parsed best-effort) and equal. If the request method
        cannot be determined, a method-constrained rule does NOT authorise the
        request — otherwise a method allowlist could be bypassed by an opaque
        command (e.g. ``curl -X POST`` to a ``GET``-only path). A rule with no
        method constraint authorises on path match alone. Globs reuse the
        codebase's ``**``-aware matcher.
        """
        request_path = urlparse(url).path or "/"
        request_method = self._request_method(action, target_scheme)

        for rule_method, path_glob in allow_rules:
            if not _glob_match(request_path, path_glob):
                continue
            if rule_method is None:
                # Rule does not constrain the method — path match is enough.
                return True
            if request_method is not None and rule_method == request_method:
                return True
            # Method-constrained rule with a mismatched/unknown request method:
            # do not authorise on this rule (fail closed); keep checking others.
        return False

    @classmethod
    def _protocol_matches(cls, rule_protocol: str, target_scheme: str) -> bool:
        """Check if a rule protocol matches the URL scheme.

        Per the NemoClaw v0.0.65 schema the protocol enum is ``rest`` |
        ``websocket``; these map to their valid scheme sets. Unknown protocol
        names (e.g. a literal URL scheme) fall back to exact string comparison
        (``https`` == ``https``).
        """
        allowed = cls._PROTOCOL_SCHEME_MAP.get(rule_protocol)
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
        tokens = command.split()
        for bp in binaries:
            # NemoClaw "/**" (and bare globs) mean "any binary".
            if bp in ("/**", "**", "*", "/*"):
                return True
            # Full path: match with word boundary to avoid /usr/bin/git matching
            # /usr/bin/github-cli
            if re.search(rf"(?:^|\s){re.escape(bp)}(?:\s|$)", command):
                return True
            binary_name = bp.rsplit("/", 1)[-1]
            # Glob path (e.g. /usr/bin/*): glob-match command tokens + basenames.
            if "*" in bp:
                if any(
                    _glob_match(tok, bp) or _glob_match(tok.rsplit("/", 1)[-1], binary_name)
                    for tok in tokens
                ):
                    return True
                continue
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
        Uses cached rules from _load_nemo_filesystem_rules().
        """
        if not self._is_file_action(action):
            return None

        target_path = os.path.normpath(self._extract_resource_path(action.params))
        if not target_path:
            return None

        results = self._nemo_fs_rules

        # No NemoClaw filesystem rules cached = skip
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
