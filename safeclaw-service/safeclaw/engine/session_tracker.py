"""Session tracker - records action outcomes and session facts for KG feedback."""

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_SESSIONS = 1000
MAX_FILES_PER_SESSION = 200
MAX_FACTS_PER_SESSION = 1000

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _sanitize_cmd(text: str) -> str:
    """Strip control characters and collapse whitespace."""
    text = _CONTROL_CHARS.sub("", text)
    return " ".join(text.split())


@dataclass
class SessionFact:
    """A fact about what happened in a session."""
    action_class: str
    tool_name: str
    success: bool
    timestamp: str
    detail: str = ""
    risk_level: str = ""


@dataclass
class SessionState:
    """Tracks the live state of a session for context injection."""
    facts: list[SessionFact] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    violation_count: int = 0
    last_violation_reason: str = ""


class SessionTracker:
    """Maintains per-session state as a live model for context injection.

    Records action outcomes, file modifications, and provides
    session summaries for the context builder.
    """

    def __init__(self):
        self._sessions: OrderedDict[str, SessionState] = OrderedDict()

    def _get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_id)
        return self._sessions[session_id]

    def record_outcome(
        self,
        session_id: str,
        action_class: str,
        tool_name: str,
        success: bool,
        params: dict | None = None,
        risk_level: str = "",
    ) -> None:
        """Record an action outcome as a session fact."""
        state = self._get_or_create(session_id)
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")

        detail = ""
        if params:
            if "file_path" in params:
                file_path = params["file_path"]
                detail = f"file: {file_path}"
                if success and tool_name in ("write", "edit", "apply_patch"):
                    if file_path not in state.files_modified and len(state.files_modified) < MAX_FILES_PER_SESSION:
                        state.files_modified.append(file_path)
            elif "command" in params:
                cmd = _sanitize_cmd(params["command"])
                detail = f"cmd: {cmd[:80]}"

        state.facts.append(SessionFact(
            action_class=action_class,
            tool_name=tool_name,
            success=success,
            timestamp=now,
            detail=detail,
            risk_level=risk_level,
        ))
        if len(state.facts) > MAX_FACTS_PER_SESSION:
            state.facts = state.facts[-MAX_FACTS_PER_SESSION:]

    def record_violation(self, session_id: str, reason: str) -> None:
        """Record a constraint violation."""
        state = self._get_or_create(session_id)
        state.violation_count += 1
        state.last_violation_reason = reason

    def get_session_summary(self, session_id: str) -> list[str]:
        """Get a human-readable summary of session facts for context injection."""
        state = self._sessions.get(session_id)
        if not state:
            return []

        lines = []
        # Recent actions (last 10)
        for fact in state.facts[-10:]:
            status = "OK" if fact.success else "FAILED"
            line = f"[{fact.timestamp}] {fact.action_class} ({status})"
            if fact.detail:
                line += f" - {fact.detail}"
            lines.append(line)

        # Files modified
        if state.files_modified:
            lines.append(f"Files modified this session: {', '.join(state.files_modified[-5:])}")

        # Violation summary
        if state.violation_count > 0:
            lines.append(
                f"Violations: {state.violation_count} total, "
                f"last: {state.last_violation_reason}"
            )

        return lines

    def get_risk_history(self, session_id: str) -> list[str]:
        """Get session history entries formatted for cumulative risk checking.

        Returns entries like 'MediumRisk:WriteFile' for use by the
        DerivedConstraintChecker's cumulative risk rule.
        """
        state = self._sessions.get(session_id)
        if not state:
            return []
        return [
            f"{fact.risk_level}:{fact.action_class}"
            for fact in state.facts
            if fact.risk_level
        ]

    def get_state(self, session_id: str) -> SessionState | None:
        """Get raw session state."""
        return self._sessions.get(session_id)

    def clear_session(self, session_id: str) -> None:
        """Remove session data."""
        self._sessions.pop(session_id, None)
