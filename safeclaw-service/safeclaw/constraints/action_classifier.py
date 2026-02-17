"""Action classifier - maps OpenClaw tool calls to ontology action classes."""

import re
from dataclasses import dataclass

from rdflib import Graph, Literal, Namespace, RDF, XSD

SC = Namespace("http://safeclaw.ai/ontology/agent#")


@dataclass
class ClassifiedAction:
    ontology_class: str
    risk_level: str
    is_reversible: bool
    affects_scope: str
    tool_name: str
    params: dict

    def as_rdf_graph(self) -> Graph:
        """Create an RDF graph representing this action for SHACL validation."""
        g = Graph()
        g.bind("sc", SC)
        action_node = SC[f"action_{id(self)}"]
        g.add((action_node, RDF.type, SC[self.ontology_class]))
        g.add((action_node, SC.hasRiskLevel, SC[self.risk_level]))
        g.add((action_node, SC.isReversible, Literal(self.is_reversible, datatype=XSD.boolean)))
        g.add((action_node, SC.affectsScope, SC[self.affects_scope]))
        if "command" in self.params:
            g.add((action_node, SC.commandText, Literal(self.params["command"])))
        if "file_path" in self.params:
            g.add((action_node, SC.filePath, Literal(self.params["file_path"])))
        return g


# Shell command patterns for subclass detection
SHELL_PATTERNS = [
    (r"\brm\s+(-[rRf]+\s+|.*--force)", "DeleteFile", "CriticalRisk", False, "LocalOnly"),
    (r"\bgit\s+push\b.*--force", "ForcePush", "CriticalRisk", False, "SharedState"),
    (r"\bgit\s+push\b", "GitPush", "HighRisk", False, "SharedState"),
    (r"\bgit\s+commit\b", "GitCommit", "MediumRisk", True, "LocalOnly"),
    (r"\bgit\s+reset\s+--hard", "GitResetHard", "CriticalRisk", False, "LocalOnly"),
    (r"\bdocker\s+(rm|rmi|prune)", "DockerCleanup", "HighRisk", False, "LocalOnly"),
    (r"\bcurl\b|\bwget\b", "NetworkRequest", "MediumRisk", True, "ExternalWorld"),
    (r"\bnpm\s+publish\b", "PackagePublish", "CriticalRisk", False, "ExternalWorld"),
]

# Default tool mappings
TOOL_MAPPINGS = {
    "read": ("ReadFile", "LowRisk", True, "LocalOnly"),
    "write": ("WriteFile", "MediumRisk", True, "LocalOnly"),
    "edit": ("EditFile", "MediumRisk", True, "LocalOnly"),
    "apply_patch": ("EditFile", "MediumRisk", True, "LocalOnly"),
    "web_fetch": ("WebFetch", "MediumRisk", True, "ExternalWorld"),
    "web_search": ("WebSearch", "LowRisk", True, "ExternalWorld"),
    "message": ("SendMessage", "HighRisk", False, "ExternalWorld"),
    "browser": ("BrowserAction", "MediumRisk", True, "ExternalWorld"),
    "glob": ("ReadFile", "LowRisk", True, "LocalOnly"),
    "grep": ("ReadFile", "LowRisk", True, "LocalOnly"),
}


class ActionClassifier:
    """Maps tool calls to ontology action classes."""

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
        return ClassifiedAction(
            ontology_class="Action",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name=tool_name,
            params=params,
        )

    def _classify_shell(self, params: dict) -> ClassifiedAction:
        command = params.get("command", "")

        for pattern, cls, risk, reversible, scope in SHELL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return ClassifiedAction(
                    ontology_class=cls,
                    risk_level=risk,
                    is_reversible=reversible,
                    affects_scope=scope,
                    tool_name="exec",
                    params=params,
                )

        # Default shell command classification
        return ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="HighRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params=params,
        )
