"""Preference checker - validates actions against user preferences."""

import fnmatch
from dataclasses import dataclass

from safeclaw.constants import PATH_PARAM_KEYS
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

        safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "", user_id)
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
            elif prop == "neverModifyPaths":
                if prefs.never_modify_paths is None:
                    prefs.never_modify_paths = []
                prefs.never_modify_paths.append(val)
            elif prop == "maxFilesPerCommit":
                try:
                    prefs.max_files_per_commit = int(val)
                except (ValueError, TypeError):
                    pass

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

        # Check never_modify_paths (check all known path param keys).
        # Skip read-only action classes — never_modify_paths should only block writes.
        READ_ONLY_ACTIONS = {"ReadFile", "ListFiles", "SearchFiles", "ViewFile", "StatFile"}
        if prefs.never_modify_paths and action.ontology_class not in READ_ONLY_ACTIONS:
            for key in PATH_PARAM_KEYS:
                file_path = action.params.get(key, "")
                if file_path and isinstance(file_path, str):
                    for pattern in prefs.never_modify_paths:
                        if fnmatch.fnmatch(file_path, pattern):
                            return PreferenceCheckResult(
                                violated=True,
                                preference_uri=f"{SU}neverModifyPaths",
                                reason=f"Path '{file_path}' matches never-modify pattern '{pattern}'",
                            )

        # Check max_files_per_commit for git commit actions
        if action.ontology_class == "GitCommit" and prefs.max_files_per_commit:
            files = action.params.get("files") or action.params.get("file_list") or []
            if isinstance(files, list) and len(files) > prefs.max_files_per_commit:
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}maxFilesPerCommit",
                    reason=(
                        f"Commit includes {len(files)} files, exceeding the "
                        f"limit of {prefs.max_files_per_commit}"
                    ),
                )

        # Check autonomy level
        # "autonomous" — no extra restrictions beyond explicit preferences above
        # "moderate" — confirm irreversible actions at CriticalRisk level
        # "cautious" / "supervised" — confirm all irreversible actions
        if prefs.autonomy_level == "moderate":
            if not action.is_reversible and action.risk_level == "CriticalRisk":
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}autonomyLevel",
                    reason=(
                        "Autonomy level 'moderate' requires confirmation for "
                        "irreversible critical-risk actions"
                    ),
                )
        elif prefs.autonomy_level in ("cautious", "supervised"):
            if not action.is_reversible:
                return PreferenceCheckResult(
                    violated=True,
                    preference_uri=f"{SU}autonomyLevel",
                    reason=f"Autonomy level '{prefs.autonomy_level}' requires confirmation for irreversible actions",
                )

        return PreferenceCheckResult(violated=False)
