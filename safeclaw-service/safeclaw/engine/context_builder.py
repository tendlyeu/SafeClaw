"""Context builder - generates governance context for LLM system prompts."""

from collections import OrderedDict

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP, SU

MAX_SESSIONS = 1000


class ContextBuilder:
    """Builds natural language governance context from the knowledge graph."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self._violation_history: OrderedDict[str, list[str]] = OrderedDict()

    def record_violation(self, session_id: str, reason: str) -> None:
        """Record a constraint violation for inclusion in subsequent context."""
        if session_id not in self._violation_history:
            self._violation_history[session_id] = []
            while len(self._violation_history) > MAX_SESSIONS:
                self._violation_history.popitem(last=False)
        self._violation_history[session_id].append(reason)

    def clear_session(self, session_id: str) -> None:
        """Remove session data when session ends."""
        self._violation_history.pop(session_id, None)

    def build_context(
        self,
        user_id: str,
        session_id: str | None = None,
        session_history: list[str] | None = None,
    ) -> str:
        sections = [
            "## SafeClaw Governance Context\n",
            "### Your Behavioral Constraints",
            "You are operating under SafeClaw governance. Every action you propose",
            "will be validated against formal ontological constraints before execution.",
            "Actions that violate constraints will be blocked with an explanation.\n",
        ]

        # User preferences
        prefs = self._get_user_preferences(user_id)
        if prefs:
            sections.append(f"### Active User Preferences (user: {user_id})")
            for pref in prefs:
                sections.append(f"- {pref}")
            sections.append("")

        # Policies
        policies = self._get_active_policies()
        if policies:
            sections.append("### Active Domain Policies")
            for policy in policies:
                sections.append(f"- {policy}")
            sections.append("")

        # Recent violations (Phase 2: remind LLM about blocked actions)
        if session_id:
            violations = self._violation_history.get(session_id, [])
            if violations:
                sections.append("### Recent Violations in This Session")
                sections.append(
                    "The following actions were blocked. Do not retry the same approach.\n"
                )
                for v in violations[-5:]:  # Last 5 violations
                    sections.append(f"- BLOCKED: {v}")
                sections.append("")

        # Session facts
        if session_history:
            sections.append("### Session History")
            for action in session_history[-10:]:
                sections.append(f"- {action}")

        return "\n".join(sections)

    def _get_user_preferences(self, user_id: str) -> list[str]:
        import re
        safe_user_id = re.sub(r'[^a-zA-Z0-9_@.-]', '', user_id)
        results = self.kg.query(f"""
            PREFIX su: <{SU}>
            SELECT ?property ?value WHERE {{
                ?user su:hasPreference ?pref .
                ?pref ?property ?value .
                FILTER(STRENDS(STR(?user), "/{safe_user_id}"))
            }}
        """)
        return [f"{str(row['property']).split('#')[-1]}: {row['value']}" for row in results]

    def _get_active_policies(self) -> list[str]:
        results = self.kg.query(f"""
            PREFIX sp: <{SP}>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?policy ?type ?reason WHERE {{
                ?policy a ?type ;
                        sp:reason ?reason .
                ?type rdfs:subClassOf sp:Constraint .
            }}
        """)
        policies = []
        for row in results:
            policy_name = str(row["policy"]).split("#")[-1]
            policy_type = str(row["type"]).split("#")[-1]
            reason = str(row["reason"])
            policies.append(f"{policy_type.upper()}: {policy_name} (reason: {reason})")
        return policies
