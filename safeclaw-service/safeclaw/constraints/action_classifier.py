"""Action classifier - maps OpenClaw tool calls to ontology action classes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
from uuid import uuid4

from rdflib import Graph, Literal, Namespace, RDF, XSD

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy

SC = Namespace("http://safeclaw.uku.ai/ontology/agent#")


@dataclass
class ClassifiedAction:
    ontology_class: str
    risk_level: str
    is_reversible: bool
    affects_scope: str
    tool_name: str
    params: dict
    chain_classes: list[str] = field(default_factory=list)

    def as_rdf_graph(self) -> Graph:
        """Create an RDF graph representing this action for SHACL validation."""
        g = Graph()
        g.bind("sc", SC)
        action_node = SC[f"action_{uuid4().hex}"]
        g.add((action_node, RDF.type, SC[self.ontology_class]))
        g.add((action_node, SC.hasRiskLevel, SC[self.risk_level]))
        g.add((action_node, SC.isReversible, Literal(self.is_reversible, datatype=XSD.boolean)))
        g.add((action_node, SC.affectsScope, SC[self.affects_scope]))
        if "command" in self.params:
            g.add((action_node, SC.commandText, Literal(self.params["command"])))
        file_path = self.params.get("file_path") or self.params.get("path")
        if file_path:
            g.add((action_node, SC.filePath, Literal(file_path)))
        return g


# Shell command patterns for subclass detection
# Patterns use _CMD to match commands invoked with optional path prefix
# (e.g. /usr/bin/rm) or command wrappers (command, env, exec).
_CMD = r"(?:(?:/[\w./]*/|(?:command|env|exec)\s+)*)"

SHELL_PATTERNS = [
    (_CMD + r"rm\s+(-[rRf]+\s+|.*--force)", "DeleteFile", "CriticalRisk", False, "LocalOnly"),
    (_CMD + r"rm\s+", "DeleteFile", "HighRisk", False, "LocalOnly"),
    (_CMD + r"git\s+push\b.*--force", "ForcePush", "CriticalRisk", False, "SharedState"),
    (_CMD + r"git\s+push\b", "GitPush", "HighRisk", False, "SharedState"),
    (_CMD + r"git\s+commit\b", "GitCommit", "MediumRisk", True, "LocalOnly"),
    (_CMD + r"git\s+reset\s+--hard", "GitResetHard", "CriticalRisk", False, "LocalOnly"),
    (_CMD + r"docker\s+(rm|rmi|prune)", "DockerCleanup", "HighRisk", False, "LocalOnly"),
    (_CMD + r"(?:curl|wget)\b", "NetworkRequest", "MediumRisk", True, "ExternalWorld"),
    (_CMD + r"npm\s+publish\b", "PackagePublish", "CriticalRisk", False, "ExternalWorld"),
    # Test runner patterns (#27: RunTests must be producible for dependency checks)
    (_CMD + r"(?:pytest|py\.test)\b", "RunTests", "LowRisk", True, "LocalOnly"),
    (_CMD + r"python\s+(?:-m\s+)?(?:pytest|unittest)\b", "RunTests", "LowRisk", True, "LocalOnly"),
    (_CMD + r"npm\s+(?:run\s+)?test\b", "RunTests", "LowRisk", True, "LocalOnly"),
    (_CMD + r"(?:cargo|go|make|mvn|gradle)\s+test\b", "RunTests", "LowRisk", True, "LocalOnly"),
]

# Default tool mappings
RISK_ORDER = {"CriticalRisk": 4, "HighRisk": 3, "MediumRisk": 2, "LowRisk": 1}

TOOL_MAPPINGS = {
    "read": ("ReadFile", "LowRisk", True, "LocalOnly"),
    "write": ("WriteFile", "MediumRisk", True, "LocalOnly"),
    "edit": ("EditFile", "MediumRisk", True, "LocalOnly"),
    "apply_patch": ("EditFile", "MediumRisk", True, "LocalOnly"),
    "web_fetch": ("WebFetch", "MediumRisk", True, "ExternalWorld"),
    "web_search": ("WebSearch", "LowRisk", True, "ExternalWorld"),
    # `message` is handled by _classify_message (action/channel-aware, #318).
    "browser": ("BrowserAction", "MediumRisk", True, "ExternalWorld"),
    # Memory / skill / media tools (v2026.6.8, #319)
    "memory_store": ("MemoryWrite", "HighRisk", False, "SharedState"),
    "memory_recall": ("MemoryRead", "LowRisk", True, "LocalOnly"),
    "skill_workshop": ("SkillAuthor", "HighRisk", False, "SharedState"),
    "image": ("GenerateMedia", "MediumRisk", True, "ExternalWorld"),
    "image_generate": ("GenerateMedia", "MediumRisk", True, "ExternalWorld"),
    "music_generate": ("GenerateMedia", "MediumRisk", True, "ExternalWorld"),
    "tts": ("GenerateMedia", "MediumRisk", True, "ExternalWorld"),
    "glob": ("ListFiles", "LowRisk", True, "LocalOnly"),
    "grep": ("SearchFiles", "LowRisk", True, "LocalOnly"),
    "find": ("ListFiles", "LowRisk", True, "LocalOnly"),
    "ls": ("ListFiles", "LowRisk", True, "LocalOnly"),
    "delete": ("DeleteFile", "CriticalRisk", False, "LocalOnly"),
    "delete_file": ("DeleteFile", "CriticalRisk", False, "LocalOnly"),
    "remove": ("DeleteFile", "CriticalRisk", False, "LocalOnly"),
    "remove_file": ("DeleteFile", "CriticalRisk", False, "LocalOnly"),
    "unlink": ("DeleteFile", "CriticalRisk", False, "LocalOnly"),
    "trash": ("DeleteFile", "HighRisk", False, "LocalOnly"),
}

# --- message tool action classification (#318) ---
# Real OpenClaw v2026.6.8 `message` action names (CHANNEL_MESSAGE_ACTION_NAMES).
# Creating a new delivery surface.
_MESSAGE_CREATE_ACTIONS = {
    "channel-create",
    "category-create",
    "topic-create",
    "thread-create",
    "event-create",
}
# Broadcasting to an explicit/other target — cross-context blast radius.
_MESSAGE_BROADCAST_ACTIONS = {"broadcast"}
# Membership / permission / destructive channel moderation.
_MESSAGE_MODERATE_ACTIONS = {
    "kick",
    "ban",
    "timeout",
    "addparticipant",
    "removeparticipant",
    "leavegroup",
    "renamegroup",
    "setgroupicon",
    "role-add",
    "role-remove",
    "permissions",
    "channel-edit",
    "channel-delete",
    "channel-move",
    "category-edit",
    "category-delete",
    "topic-edit",
}

# Tools whose body is code-mode source rather than a shell command line (#322).
_CODE_MODE_TOOLS = {"sandbox_exec", "sandbox_process"}
_SHELL_TOOLS = {"exec", "bash", "shell"}

# Dangerous JS/TS operations in code-mode bodies that shell patterns miss (#322).
# Matched against the RAW source (quotes intact), so embedded command strings
# like execSync("git push --force") are also visible to SHELL_PATTERNS.
# Node fs removal verbs (the distinctive method names).
_FS_DELETE_VERBS = r"(?:rmSync|rm|unlinkSync|unlink|rmdirSync|rmdir)"

JS_PATTERNS = [
    # Member access: fs / fs.promises / fsp .<delete>(
    (
        rf"\b(?:fs\.promises|fsp|fs)\.{_FS_DELETE_VERBS}\s*\(",
        "DeleteFile",
        "CriticalRisk",
        False,
        "LocalOnly",
    ),
    # Inline require chain: require("fs"|"node:fs"|"fs/promises").<delete>(
    (
        rf"""require\(\s*['"](?:node:)?fs(?:/promises)?['"]\s*\)\s*\.\s*{_FS_DELETE_VERBS}\s*\(""",
        "DeleteFile",
        "CriticalRisk",
        False,
        "LocalOnly",
    ),
    (
        r"\bDeno\.(?:remove|removeSync)\s*\(",
        "DeleteFile",
        "CriticalRisk",
        False,
        "LocalOnly",
    ),
    (
        r"\b(?:child_process|execSync|spawnSync|execFileSync)\b",
        "ExecuteCommand",
        "HighRisk",
        False,
        "LocalOnly",
    ),
    # JS-native network egress (no curl/wget analogue).
    (r"\bfetch\s*\(", "NetworkRequest", "MediumRisk", True, "ExternalWorld"),
]

# --- Lightweight fs alias/binding tracker (#322 follow-up) ---
# Regex JS analysis can't catch every obfuscation, but renamed destructuring and
# dynamic-import namespace aliases are common, non-adversarial forms that must
# not bypass DeleteFile. We track three binding shapes over the whole command.
_FS_MOD = r"""['"](?:node:)?fs(?:/promises)?['"]"""
_FS_VERB_SET = ("rmSync", "rm", "unlinkSync", "unlink", "rmdirSync", "rmdir")
_ID = r"[A-Za-z_$][\w$]*"

# Namespace binding: `const X = require("fs")` / `= await import("fs")`,
# `import X from "fs"`, `import * as X from "fs"`.
_FS_NS_BINDING_RE = re.compile(
    rf"""(?:const|let|var)\s+({_ID})\s*=\s*(?:await\s+)?(?:require|import)\(\s*{_FS_MOD}\s*\)"""
    rf"""|import\s+(?:\*\s+as\s+)?({_ID})\s+from\s*{_FS_MOD}"""
)
# Destructured/named-import block from fs (require/import), OR from a known
# namespace alias (filled in at match time). Capture the `{...}` body.
_FS_DESTRUCT_FROM_MODULE_RE = re.compile(
    rf"""(?:const|let|var)\s*\{{([^}}]*)\}}\s*=\s*(?:await\s+)?(?:require|import)\(\s*{_FS_MOD}\s*\)"""
    rf"""|import\s*\{{([^}}]*)\}}\s*from\s*{_FS_MOD}"""
)
_DESTRUCT_RENAME_RE = re.compile(r"\s*(?::|\bas\b)\s*")

# MCP / dynamically-exposed plugin tools use a namespaced name (#325).
_MCP_PREFIX = "mcp__"


class ActionClassifier:
    """Maps tool calls to ontology action classes."""

    def __init__(self, hierarchy: ClassHierarchy | None = None):
        self._hierarchy = hierarchy

    def classify(
        self,
        tool_name: str,
        params: dict,
        tool_kind: str = "",
        tool_input_kind: str = "",
    ) -> ClassifiedAction:
        # Code-mode exec (JS/TS) and sandbox exec/process are still command
        # execution — route them through the shell classifier (#322).
        if (
            tool_name in _SHELL_TOOLS
            or tool_name in _CODE_MODE_TOOLS
            or tool_kind == "code_mode_exec"
        ):
            code_mode = tool_name in _CODE_MODE_TOOLS or tool_kind == "code_mode_exec"
            return self._classify_shell(params, tool_name=tool_name, code_mode=code_mode)

        # The `message` tool is multi-action: branch on the action/channel params
        # so channel-create and cross-context broadcasts are not seen as a plain
        # reply (#318).
        if tool_name == "message":
            return self._classify_message(params)

        # Direct tool mapping (Python tuple is authoritative — matches the ttl).
        # Checked BEFORE the mcp__ prefix default so an explicit classification
        # for a trusted `mcp__*` tool wins over the conservative default (#325).
        if tool_name in TOOL_MAPPINGS:
            cls, risk, reversible, scope = TOOL_MAPPINGS[tool_name]
            return ClassifiedAction(
                ontology_class=cls,
                risk_level=risk,
                is_reversible=reversible,
                affects_scope=scope,
                tool_name=tool_name,
                params=params,
            )

        # MCP / dynamically-exposed plugin tools have arbitrary namespaced names
        # and can perform external writes; default to a conservative HighRisk
        # ExternalWorld class until explicitly classified (#325).
        if tool_name.startswith(_MCP_PREFIX):
            return ClassifiedAction(
                ontology_class="McpToolCall",
                risk_level="HighRisk",
                is_reversible=False,
                affects_scope="ExternalWorld",
                tool_name=tool_name,
                params=params,
            )

        # Unknown tool - conservative default
        action = ClassifiedAction(
            ontology_class="Action",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name=tool_name,
            params=params,
        )
        return self._enrich_from_ontology(action)

    @staticmethod
    def _as_bool(value: object) -> bool:
        """Interpret a JSON-ish flag as bool. Crucially, the STRING "false"
        (and other falsey strings) must be False — `bool("false")` is True."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "on")
        return bool(value)

    def _classify_message(self, params: dict) -> ClassifiedAction:
        """Classify a `message` tool call by its action / channel context (#318)."""
        action = str(params.get("action") or "send").strip().lower()
        cross_context = self._as_bool(params.get("crossContext"))

        if action in _MESSAGE_CREATE_ACTIONS:
            cls, risk, scope = "CreateChannel", "HighRisk", "ExternalWorld"
        elif cross_context or action in _MESSAGE_BROADCAST_ACTIONS:
            cls, risk, scope = "CrossContextMessage", "CriticalRisk", "ExternalWorld"
        elif action in _MESSAGE_MODERATE_ACTIONS:
            cls, risk, scope = "ModerateChannel", "HighRisk", "ExternalWorld"
        else:
            cls, risk, scope = "SendMessage", "HighRisk", "ExternalWorld"

        return ClassifiedAction(
            ontology_class=cls,
            risk_level=risk,
            is_reversible=False,
            affects_scope=scope,
            tool_name="message",
            params=params,
        )

    @staticmethod
    def _split_chain(command: str) -> list[str]:
        """Split command on chain operators (&&, ||, ;, |) respecting quotes.

        Single-quoted strings are treated per POSIX: no escape sequences are
        recognised inside them (unlike double-quoted strings where backslash
        escaping is supported).
        """
        parts: list[str] = []
        current: list[str] = []
        i = 0
        n = len(command)
        while i < n:
            ch = command[i]
            # Skip over single-quoted strings (no escapes in bash single quotes)
            if ch == "'":
                current.append(ch)
                i += 1
                while i < n and command[i] != "'":
                    current.append(command[i])
                    i += 1
                if i < n:
                    current.append(command[i])  # closing quote
                    i += 1
                continue
            # Skip over double-quoted strings (backslash escapes supported)
            if ch == '"':
                current.append(ch)
                i += 1
                while i < n and command[i] != '"':
                    if command[i] == "\\" and i + 1 < n:
                        current.append(command[i])
                        i += 1
                    current.append(command[i])
                    i += 1
                if i < n:
                    current.append(command[i])  # closing quote
                    i += 1
                continue
            # Check for chain operators
            if ch == "&" and i + 1 < n and command[i + 1] == "&":
                parts.append("".join(current))
                current = []
                i += 2
                continue
            if ch == "|" and i + 1 < n and command[i + 1] == "|":
                parts.append("".join(current))
                current = []
                i += 2
                continue
            if ch in (";", "|", "\n"):
                parts.append("".join(current))
                current = []
                i += 1
                continue
            current.append(ch)
            i += 1
        parts.append("".join(current))
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _fs_alias_delete_patterns(command: str) -> list[tuple]:
        """Build DeleteFile patterns for fs removal calls reached via aliases.

        Covers: namespace bindings (`const m = require("fs")` / `await import`,
        `import * as m`/default) → `m.<verb>(` and `m.promises.<verb>(`; a
        destructured `promises` namespace (`const {promises} = require("fs")`,
        `import {promises as p} from "node:fs"`) → `promises.<verb>(`/`p.<verb>(`;
        and renamed/destructured delete-verb bindings (`const {rmSync: del} =
        require("fs")`, `import {rm as nuke} from "fs"`, destructuring from a
        namespace alias) → bare `del(`/`nuke(`.

        Deliberately heuristic: deeper indirection (computed property access like
        `fs["rm"+"Sync"]`, passing the function as a value) is not tracked and
        falls back to the code-mode ExecuteCommand floor. Renames of NON-delete
        verbs are not flagged.
        """
        ns_aliases: set[str] = set()
        for m in _FS_NS_BINDING_RE.finditer(command):
            ns_aliases.add(m.group(1) or m.group(2))

        verb_aliases: set[str] = set()

        def _collect(block: str) -> None:
            for entry in block.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                halves = _DESTRUCT_RENAME_RE.split(entry, maxsplit=1)
                orig = halves[0].strip()
                local = halves[-1].strip() if len(halves) > 1 else orig
                if not re.fullmatch(_ID, local):
                    continue
                if orig in _FS_VERB_SET:
                    verb_aliases.add(local)
                elif orig == "promises":
                    # The destructured fs.promises API is itself a namespace whose
                    # members include the delete verbs (#322 follow-up).
                    ns_aliases.add(local)

        for m in _FS_DESTRUCT_FROM_MODULE_RE.finditer(command):
            _collect(m.group(1) or m.group(2) or "")

        # Propagate to a fixpoint so chains work: assignment aliases
        # (`const p = fs` or `const p = fs.promises`, where fs is a known alias)
        # become namespace aliases, and destructures from a known alias
        # (`const {rm} = fs`) are collected. Aliases only grow (bounded by the
        # identifiers in the command), so this terminates.
        changed = True
        while changed:
            before = (len(ns_aliases), len(verb_aliases))
            for alias in tuple(ns_aliases):
                # `const X = <alias>` / `const X = <alias>.promises` — the negative
                # lookahead rejects function-value aliases like `= fs.promises.rm`.
                for am in re.finditer(
                    rf"(?:const|let|var)\s+({_ID})\s*=\s*{re.escape(alias)}(?:\.promises)?(?![\w$.])",
                    command,
                ):
                    ns_aliases.add(am.group(1))
                # `const {rmSync} = <alias>`
                for dm in re.finditer(
                    rf"(?:const|let|var)\s*\{{([^}}]*)\}}\s*=\s*{re.escape(alias)}\b", command
                ):
                    _collect(dm.group(1))
            changed = (len(ns_aliases), len(verb_aliases)) != before

        verbs = "|".join(_FS_VERB_SET)
        extra: list[tuple] = []
        for alias in ns_aliases:
            # Allow an optional `.promises` hop so `<fsAlias>.promises.<verb>(` is
            # caught alongside `<fsAlias>.<verb>(` and `<promisesAlias>.<verb>(`.
            extra.append(
                (
                    rf"\b{re.escape(alias)}(?:\.promises)?\.(?:{verbs})\s*\(",
                    "DeleteFile",
                    "CriticalRisk",
                    False,
                    "LocalOnly",
                )
            )
        if verb_aliases:
            alt = "|".join(re.escape(a) for a in verb_aliases)
            extra.append((rf"\b(?:{alt})\s*\(", "DeleteFile", "CriticalRisk", False, "LocalOnly"))
        return extra

    def _classify_shell(
        self, params: dict, tool_name: str = "exec", code_mode: bool = False
    ) -> ClassifiedAction:
        command = params.get("command") or ""

        # Split on command chaining operators, respecting quoted strings
        sub_commands = self._split_chain(command)
        highest_risk = None
        chain_classes: list[str] = []

        # Code-mode bodies are source, not a shell line: scan them RAW (so an
        # embedded command string like execSync("git push --force") is visible)
        # and also apply JS/TS dangerous-op patterns. Plain shell strips quoted
        # data first to avoid false positives from quoted arguments. (#322)
        if code_mode:
            # Add patterns derived from fs bindings in this body (namespace and
            # renamed/destructured aliases), so deletes via aliased names are
            # caught — checked over the WHOLE command since `;` may split a
            # binding from its later use. (#322 follow-up)
            patterns = SHELL_PATTERNS + JS_PATTERNS + self._fs_alias_delete_patterns(command)
        else:
            patterns = SHELL_PATTERNS

        for sub_cmd in sub_commands:
            if code_mode:
                scan = sub_cmd
            else:
                # Strip quoted strings, then expand subshell/process substitutions
                # so their contents are also visible to pattern matching (#23).
                scan = re.sub(r"""(["'])(?:\\.|(?!\1).)*\1""", "", sub_cmd)
                scan = re.sub(r"\$\(([^)]*)\)", r" \1 ", scan)
                scan = re.sub(r"`([^`]*)`", r" \1 ", scan)
            matched_cls: str | None = None
            for pattern, cls, risk, reversible, scope in patterns:
                if re.search(pattern, scan, re.IGNORECASE):
                    matched_cls = cls
                    candidate = ClassifiedAction(
                        ontology_class=cls,
                        risk_level=risk,
                        is_reversible=reversible,
                        affects_scope=scope,
                        tool_name=tool_name,
                        params=params,
                    )
                    if highest_risk is None or RISK_ORDER.get(risk, 0) > RISK_ORDER.get(
                        highest_risk.risk_level, 0
                    ):
                        highest_risk = candidate
                    break
            if matched_cls:
                chain_classes.append(matched_cls)
            elif code_mode:
                # An unclassified segment in a code-mode body cannot be proven
                # safe, so it contributes a CodeModeExec/HighRisk CANDIDATE (not a
                # passive chain entry) — otherwise an earlier known-safe statement
                # (e.g. `runTests("npm test"); console.log("x")`) would launder the
                # whole body past the confirmation floor.
                chain_classes.append("CodeModeExec")
                if highest_risk is None or RISK_ORDER.get("HighRisk", 0) > RISK_ORDER.get(
                    highest_risk.risk_level, 0
                ):
                    highest_risk = ClassifiedAction(
                        ontology_class="CodeModeExec",
                        risk_level="HighRisk",
                        is_reversible=False,
                        affects_scope="LocalOnly",
                        tool_name=tool_name,
                        params=params,
                    )
            else:
                chain_classes.append("ExecuteCommand")

        if highest_risk:
            highest_risk.chain_classes = chain_classes
            return highest_risk

        # Default classification for an UNMATCHED command. Code/sandbox source
        # execution (code_mode) runs arbitrary source SafeClaw could not pin to a
        # known-safe or known-dangerous class, so it gets a distinct CodeModeExec
        # class that the derived checker confirms by default (the durable backstop
        # behind the best-effort JS pattern/alias detection). Plain shell stays
        # ExecuteCommand so interactive `exec`/`bash` is unaffected.
        default_class = "CodeModeExec" if code_mode else "ExecuteCommand"
        return ClassifiedAction(
            ontology_class=default_class,
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="LocalOnly",
            tool_name=tool_name,
            params=params,
            chain_classes=chain_classes,
        )

    def _enrich_from_ontology(self, action: ClassifiedAction) -> ClassifiedAction:
        """Override Python-default risk/scope with ontology-defined values when available."""
        if not self._hierarchy:
            return action
        defaults = self._hierarchy.get_defaults(action.ontology_class)
        if defaults:
            return replace(
                action,
                risk_level=defaults["risk_level"],
                is_reversible=defaults["is_reversible"],
                affects_scope=defaults["affects_scope"],
            )
        return action
