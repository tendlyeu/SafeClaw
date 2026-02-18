"""Dependency checker - ensures prerequisite actions have been performed."""

from collections import OrderedDict
from dataclasses import dataclass, field

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP

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

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
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
        self._session_history[session_id].append(action_class)

    def clear_session(self, session_id: str) -> None:
        """Remove session history when session ends."""
        self._session_history.pop(session_id, None)

    def check(self, action: ClassifiedAction, session_id: str) -> DependencyCheckResult:
        """Check if all prerequisites for this action have been met."""
        required = self._dependencies.get(action.ontology_class, [])
        if not required:
            return DependencyCheckResult(unmet=False)

        history = self._session_history.get(session_id, [])

        for req in required:
            if req not in history:
                return DependencyCheckResult(
                    unmet=True,
                    required_action=req,
                    reason=f"Prerequisite not met: '{req}' must be performed before '{action.ontology_class}'",
                )

        return DependencyCheckResult(unmet=False)
