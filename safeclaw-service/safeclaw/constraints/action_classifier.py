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
SHELL_PATTERNS = [
    (r"\brm\s+(-[rRf]+\s+|.*--force)", "DeleteFile", "CriticalRisk", False, "LocalOnly"),
    (r"\brm\s+", "DeleteFile", "HighRisk", False, "LocalOnly"),
    (r"\bgit\s+push\b.*--force", "ForcePush", "CriticalRisk", False, "SharedState"),
    (r"\bgit\s+push\b", "GitPush", "HighRisk", False, "SharedState"),
    (r"\bgit\s+commit\b", "GitCommit", "MediumRisk", True, "LocalOnly"),
    (r"\bgit\s+reset\s+--hard", "GitResetHard", "CriticalRisk", False, "LocalOnly"),
    (r"\bdocker\s+(rm|rmi|prune)", "DockerCleanup", "HighRisk", False, "LocalOnly"),
    (r"\bcurl\b|\bwget\b", "NetworkRequest", "MediumRisk", True, "ExternalWorld"),
    (r"\bnpm\s+publish\b", "PackagePublish", "CriticalRisk", False, "ExternalWorld"),
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
    "message": ("SendMessage", "HighRisk", False, "ExternalWorld"),
    "browser": ("BrowserAction", "MediumRisk", True, "ExternalWorld"),
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


class ActionClassifier:
    """Maps tool calls to ontology action classes."""

    def __init__(self, hierarchy: ClassHierarchy | None = None):
        self._hierarchy = hierarchy

    def classify(self, tool_name: str, params: dict) -> ClassifiedAction:
        # Shell commands need deeper inspection
        if tool_name in ("exec", "bash", "shell"):
            return self._classify_shell(params)

        # Direct tool mapping
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
    def _split_chain(command: str) -> list[str]:
        """Split command on chain operators (&&, ||, ;, |) respecting quotes."""
        parts: list[str] = []
        current: list[str] = []
        i = 0
        n = len(command)
        while i < n:
            ch = command[i]
            # Skip over quoted strings
            if ch in ('"', "'"):
                quote = ch
                current.append(ch)
                i += 1
                while i < n and command[i] != quote:
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
            if ch in (";", "|"):
                parts.append("".join(current))
                current = []
                i += 1
                continue
            current.append(ch)
            i += 1
        parts.append("".join(current))
        return [p.strip() for p in parts if p.strip()]

    def _classify_shell(self, params: dict) -> ClassifiedAction:
        command = params.get("command", "")

        # Split on command chaining operators, respecting quoted strings
        sub_commands = self._split_chain(command)
        highest_risk = None
        chain_classes: list[str] = []

        for sub_cmd in sub_commands:
            # Strip quoted strings from each sub-command before pattern matching
            # so that content inside quotes does not trigger false positives
            unquoted = re.sub(r'''(["'])(?:\\.|(?!\1).)*\1''', "", sub_cmd)
            matched_cls: str | None = None
            for pattern, cls, risk, reversible, scope in SHELL_PATTERNS:
                if re.search(pattern, unquoted, re.IGNORECASE):
                    matched_cls = cls
                    candidate = ClassifiedAction(
                        ontology_class=cls,
                        risk_level=risk,
                        is_reversible=reversible,
                        affects_scope=scope,
                        tool_name="exec",
                        params=params,
                    )
                    if highest_risk is None or RISK_ORDER.get(
                        risk, 0
                    ) > RISK_ORDER.get(highest_risk.risk_level, 0):
                        highest_risk = candidate
                    break
            if matched_cls:
                chain_classes.append(matched_cls)
            else:
                chain_classes.append("ExecuteCommand")

        if highest_risk:
            highest_risk.chain_classes = chain_classes
            return highest_risk

        # Default shell command classification
        return ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="HighRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
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
