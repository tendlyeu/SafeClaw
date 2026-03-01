"""Policy checker - evaluates proposed actions against policy ontology."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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


_PATH_PARAM_KEYS = (
    "file_path", "path", "filepath", "filename", "dest", "destination",
    "target", "source", "src", "dir", "directory", "folder",
)


class PolicyChecker:
    """Checks actions against policy prohibitions and obligations."""

    @staticmethod
    def _extract_resource_path(params: dict) -> str:
        """Extract resource path from params, checking common key variants."""
        for key in _PATH_PARAM_KEYS:
            val = params.get(key, "")
            if val and isinstance(val, str):
                return val
        return ""

    def __init__(
        self, knowledge_graph: KnowledgeGraph, hierarchy: ClassHierarchy | None = None
    ):
        self.kg = knowledge_graph
        self._hierarchy = hierarchy
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
            (str(r["policy"]), str(r["pattern"]).strip("/"), str(r["reason"]))
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
            self._class_prohibitions.append(
                (str(r["policy"]), target_class, str(r["reason"]))
            )

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
                    all_violations.append({
                        "policy_uri": policy_uri,
                        "policy_type": "Prohibition",
                        "reason": reason,
                    })

        # Check command constraints
        command = action.params.get("command", "")
        if command:
            for policy_uri, pattern, reason in self._forbidden_commands:
                if self._safe_match(pattern, command):
                    all_violations.append({
                        "policy_uri": policy_uri,
                        "policy_type": "Prohibition",
                        "reason": reason,
                    })

        # Check class-level prohibitions (hierarchy-aware)
        if self._class_prohibitions:
            action_classes = (
                self._hierarchy.get_superclasses(action.ontology_class)
                if self._hierarchy
                else {action.ontology_class}
            )
            for policy_uri, target_class, reason in self._class_prohibitions:
                if target_class in action_classes:
                    all_violations.append({
                        "policy_uri": policy_uri,
                        "policy_type": "Prohibition",
                        "reason": reason,
                    })

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
