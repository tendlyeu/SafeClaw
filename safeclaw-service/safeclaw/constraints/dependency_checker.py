"""Dependency checker - ensures prerequisite actions have been performed."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy

MAX_SESSIONS = 1000


@dataclass
class DependencyCheckResult:
    unmet: bool
    required_action: str = ""
    reason: str = ""


# Action dependencies: action_class → list of required prerequisite classes
DEFAULT_DEPENDENCIES = {
    "GitPush": ["RunTests"],
    "ForcePush": ["RunTests"],
    "PackagePublish": ["RunTests"],
}


class DependencyChecker:
    """Checks if prerequisite actions have been performed in the session."""

    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        hierarchy: ClassHierarchy | None = None,
    ):
        self.kg = knowledge_graph
        self._hierarchy = hierarchy
        self._session_history: OrderedDict[str, list[str]] = OrderedDict()
        self._dependencies = dict(DEFAULT_DEPENDENCIES)
        self._load_dependencies()

    def _load_dependencies(self) -> None:
        """Load dependency constraints from knowledge graph."""
        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            PREFIX sc: <http://safeclaw.uku.ai/ontology/agent#>
            SELECT ?action ?required ?reason WHERE {{
                ?constraint a sp:DependencyConstraint ;
                            sp:appliesTo ?action ;
                            sp:requiresBefore ?required ;
                            sp:reason ?reason .
            }}
        """)
        for row in results:
            action = str(row["action"]).split("#")[-1]
            required = str(row["required"]).split("#")[-1]
            if action not in self._dependencies:
                self._dependencies[action] = []
            if required not in self._dependencies[action]:
                self._dependencies[action].append(required)

    def record_action(self, session_id: str, action_class: str) -> None:
        if session_id not in self._session_history:
            self._session_history[session_id] = []
            # Evict oldest sessions to prevent memory leak
            while len(self._session_history) > MAX_SESSIONS:
                self._session_history.popitem(last=False)
        else:
            self._session_history.move_to_end(session_id)  # Update LRU position
        self._session_history[session_id].append(action_class)
        if len(self._session_history[session_id]) > 1000:
            self._session_history[session_id] = self._session_history[session_id][-1000:]

    def clear_session(self, session_id: str) -> None:
        """Remove session history when session ends."""
        self._session_history.pop(session_id, None)

    def check(self, action: ClassifiedAction, session_id: str) -> DependencyCheckResult:
        """Check if all prerequisites for this action have been met.

        Uses ClassHierarchy (when available) to also check superclasses
        of the action for dependency rules, and to match history entries
        that are subclasses of a required prerequisite.
        """
        # Collect dependency rules: check the action class and its superclasses
        action_classes = [action.ontology_class]
        if self._hierarchy:
            action_classes = list(self._hierarchy.get_superclasses(action.ontology_class))

        required: list[str] = []
        for cls in action_classes:
            required.extend(self._dependencies.get(cls, []))
        if not required:
            return DependencyCheckResult(unmet=False)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_required: list[str] = []
        for r in required:
            if r not in seen:
                seen.add(r)
                unique_required.append(r)

        history = self._session_history.get(session_id, [])

        for req in unique_required:
            # Check if any entry in history satisfies this requirement
            # (either exact match or, with hierarchy, a subclass of the required class)
            satisfied = False
            for hist_entry in history:
                if hist_entry == req:
                    satisfied = True
                    break
                if self._hierarchy and self._hierarchy.is_subclass_of(hist_entry, req):
                    satisfied = True
                    break
            if not satisfied:
                return DependencyCheckResult(
                    unmet=True,
                    required_action=req,
                    reason=f"Prerequisite not met: '{req}' must be performed before '{action.ontology_class}'",
                )

        return DependencyCheckResult(unmet=False)
