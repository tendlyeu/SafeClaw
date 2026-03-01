"""Preference checker - validates actions against user preferences."""

import fnmatch
from dataclasses import dataclass

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SU


@dataclass
class UserPreferences:
    autonomy_level: str = "moderate"
    confirm_before_delete: bool = True
    confirm_before_push: bool = True
    confirm_before_send: bool = True
    never_modify_paths: list[str] | None = None
    max_files_per_commit: int = 10


@dataclass
class PreferenceCheckResult:
    violated: bool
    preference_uri: str = ""
    reason: str = ""


class PreferenceChecker:
    """Checks actions against user preferences stored as OWL triples."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph

    def get_preferences(self, user_id: str) -> UserPreferences:
        """Load user preferences from knowledge graph."""
        prefs = UserPreferences()

        # Sanitize user_id to prevent SPARQL injection
        import re
        safe_user_id = re.sub(r'[^a-zA-Z0-9_@.-]', '', user_id)
        results = self.kg.query(f"""
            PREFIX su: <{SU}>
            SELECT ?property ?value WHERE {{
                su:user-{safe_user_id} a su:User ;
                      su:hasPreference ?pref .
                ?pref ?property ?value .
            }}
        """)

        for row in results:
            prop = str(row["property"]).split("#")[-1]
            val = str(row["value"])

            if prop == "autonomyLevel":
                prefs.autonomy_level = val
            elif prop == "confirmBeforeDelete":
                prefs.confirm_before_delete = val.lower() == "true"
            elif prop == "confirmBeforePush":
                prefs.confirm_before_push = val.lower() == "true"
            elif prop == "confirmBeforeSend":
                prefs.confirm_before_send = val.lower() == "true"
            elif prop == "neverModifyPath":
                if prefs.never_modify_paths is None:
                    prefs.never_modify_paths = []
                prefs.never_modify_paths.append(val)

        return prefs

    def check(self, action: ClassifiedAction, prefs: UserPreferences) -> PreferenceCheckResult:
        """Check if action violates user preferences."""
        # Check delete confirmation
        if action.ontology_class in ("DeleteFile", "DockerCleanup", "GitResetHard"):
            if prefs.confirm_before_delete:
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}confirmBeforeDelete",
                    reason="User preference requires confirmation before file deletion",
                )

        # Check push confirmation
        if action.ontology_class in ("GitPush", "ForcePush", "PackagePublish"):
            if prefs.confirm_before_push:
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}confirmBeforePush",
                    reason="User preference requires confirmation before pushing",
                )

        # Check send confirmation
        if action.ontology_class == "SendMessage":
            if prefs.confirm_before_send:
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}confirmBeforeSend",
                    reason="User preference requires confirmation before sending messages",
                )

        # Check never_modify_paths
        if prefs.never_modify_paths:
            file_path = action.params.get("file_path", "") or action.params.get("path", "")
            if file_path:
                for pattern in prefs.never_modify_paths:
                    if fnmatch.fnmatch(file_path, pattern):
                        return PreferenceCheckResult(
                            violated=True,
                            preference_uri=f"{SU}neverModifyPaths",
                            reason=f"Path '{file_path}' matches never-modify pattern '{pattern}'",
                        )

        # Check autonomy level
        if prefs.autonomy_level in ("cautious", "supervised"):
            if not action.is_reversible:
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}autonomyLevel",
                    reason=f"Autonomy level '{prefs.autonomy_level}' requires confirmation for irreversible actions",
                )

        return PreferenceCheckResult(violated=False)
