"""Time and task-bound temporary permission grants."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from safeclaw.engine.class_hierarchy import ClassHierarchy


@dataclass
class TempGrant:
    """A temporary permission grant for an agent."""

    id: str
    agent_id: str
    permission: str  # action class name
    expires_at: float | None  # monotonic time, None = no time limit
    task_id: str | None
    granted_at: float


MAX_GRANTS = 10000


class TempPermissionManager:
    """Manages temporary, scoped permission grants."""

    def __init__(self, hierarchy: ClassHierarchy | None = None):
        self._grants: dict[str, TempGrant] = {}
        self._hierarchy = hierarchy

    def grant(
        self,
        agent_id: str,
        permission: str,
        duration_seconds: float | None = None,
        task_id: str | None = None,
    ) -> str:
        """Create a temporary permission grant.

        Must have at least one of duration_seconds or task_id.
        Returns the grant ID.
        """
        if duration_seconds is None and task_id is None:
            raise ValueError(
                "At least one of duration_seconds or task_id is required"
            )
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError(
                "duration_seconds must be positive"
            )

        now = monotonic()
        grant_id = str(uuid4())
        expires_at = (now + duration_seconds) if duration_seconds is not None else None

        self._grants[grant_id] = TempGrant(
            id=grant_id,
            agent_id=agent_id,
            permission=permission,
            expires_at=expires_at,
            task_id=task_id,
            granted_at=now,
        )
        self._enforce_limit()
        return grant_id

    def get_grant(self, grant_id: str) -> TempGrant | None:
        """Look up a grant by ID."""
        return self._grants.get(grant_id)

    def revoke(self, grant_id: str) -> None:
        """Revoke a specific grant."""
        self._grants.pop(grant_id, None)

    def check(self, agent_id: str, permission: str) -> bool:
        """Check if an agent has an active grant for a permission.

        When a ClassHierarchy is available, also checks if any parent
        class of ``permission`` has an active grant (i.e. a grant on a
        superclass covers all its subclasses).
        """
        self.cleanup_expired()
        now = monotonic()

        # Build the set of classes that would satisfy this permission check:
        # the permission itself plus all of its superclasses.
        if self._hierarchy:
            acceptable = self._hierarchy.get_superclasses(permission)
        else:
            acceptable = {permission}

        for g in self._grants.values():
            if g.agent_id != agent_id:
                continue
            if g.permission not in acceptable:
                continue
            if g.expires_at is not None and now > g.expires_at:
                continue
            return True
        return False

    def complete_task(self, task_id: str) -> int:
        """Remove all grants associated with a task. Returns count removed."""
        to_remove = [
            gid for gid, g in self._grants.items() if g.task_id == task_id
        ]
        for gid in to_remove:
            del self._grants[gid]
        return len(to_remove)

    def cleanup_expired(self) -> int:
        """Remove all expired grants. Returns count removed."""
        now = monotonic()
        to_remove = [
            gid
            for gid, g in self._grants.items()
            if g.expires_at is not None and now > g.expires_at
        ]
        for gid in to_remove:
            del self._grants[gid]
        return len(to_remove)

    def _enforce_limit(self) -> None:
        """Evict grants if over MAX_GRANTS: expired first, then oldest."""
        if len(self._grants) <= MAX_GRANTS:
            return
        self.cleanup_expired()
        if len(self._grants) <= MAX_GRANTS:
            return
        # Evict oldest by granted_at
        by_age = sorted(self._grants.items(), key=lambda kv: kv[1].granted_at)
        to_remove = len(self._grants) - MAX_GRANTS
        for gid, _ in by_age[:to_remove]:
            del self._grants[gid]

    def list_grants(self, agent_id: str | None = None) -> list[TempGrant]:
        """List active grants, optionally filtered by agent_id."""
        self.cleanup_expired()
        grants = list(self._grants.values())
        if agent_id is not None:
            grants = [g for g in grants if g.agent_id == agent_id]
        return grants
