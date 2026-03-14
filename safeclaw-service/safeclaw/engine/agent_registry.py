"""Agent registration with per-agent tokens."""

import hashlib
import hmac
import logging
import os
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic

logger = logging.getLogger(__name__)

MAX_AGENTS = 500


@dataclass
class AgentRecord:
    """Registration record for an agent."""

    agent_id: str
    role: str
    parent_id: str | None
    session_id: str
    token_hash: str
    created_at: float
    killed: bool = False


class AgentRegistry:
    """Manages agent registration and per-agent token verification."""

    def __init__(self):
        self._agents: OrderedDict[str, AgentRecord] = OrderedDict()
        self._server_secret = os.urandom(32)

    def _hash_token(self, token: str) -> str:
        return hmac.new(self._server_secret, token.encode(), hashlib.sha256).hexdigest()

    def register_agent(
        self,
        agent_id: str,
        role: str,
        session_id: str,
        parent_id: str | None = None,
    ) -> str:
        """Register a new agent and return its raw token.

        If the agent_id already exists and is NOT killed, raises ValueError
        to prevent accidental overwrites. Killed agents may be re-registered
        (effectively resetting their state).
        """
        existing = self._agents.get(agent_id)
        if existing is not None and not existing.killed:
            raise ValueError(
                f"Agent '{agent_id}' is already registered and active. "
                "Kill it first or use a different agent_id."
            )
        token = secrets.token_urlsafe(32)
        record = AgentRecord(
            agent_id=agent_id,
            role=role,
            parent_id=parent_id,
            session_id=session_id,
            token_hash=self._hash_token(token),
            created_at=monotonic(),
        )
        self._agents[agent_id] = record
        while len(self._agents) > MAX_AGENTS:
            evicted_id, evicted_record = self._agents.popitem(last=False)
            logger.warning(
                "Evicted agent %s (role=%s, session=%s) due to MAX_AGENTS limit",
                evicted_id, evicted_record.role, evicted_record.session_id,
            )
        return token

    def verify_token(self, agent_id: str, token: str) -> bool:
        """Verify an agent's token using constant-time comparison.

        Returns False for killed agents (defense-in-depth).
        """
        record = self._agents.get(agent_id)
        if record is None:
            return False
        if record.killed:
            return False
        return hmac.compare_digest(
            record.token_hash, self._hash_token(token)
        )

    def kill_agent(self, agent_id: str) -> bool:
        record = self._agents.get(agent_id)
        if record:
            record.killed = True
            return True
        return False

    def revive_agent(self, agent_id: str) -> tuple[bool, str | None]:
        """Revive a killed agent and rotate its token.

        Returns (success, new_token). The new token must be used for
        subsequent authentication — the old token is invalidated.
        """
        record = self._agents.get(agent_id)
        if not record:
            return False, None
        new_token = secrets.token_urlsafe(32)
        record.token_hash = self._hash_token(new_token)
        record.killed = False
        return True, new_token

    def is_killed(self, agent_id: str) -> bool:
        """Check if an agent has been explicitly killed.

        Returns False for unregistered agents — the kill switch should
        only apply to agents that were explicitly killed.  Registration
        checks are handled separately by ``_require_token_auth``.
        """
        record = self._agents.get(agent_id)
        if record is None:
            return False
        return record.killed

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def get_hierarchy_ids(self, agent_id: str) -> set[str]:
        """Get all agent IDs in the same hierarchy tree, scoped to the agent's session."""
        agent_record = self._agents.get(agent_id)
        if agent_record is None:
            return {agent_id}
        session_id = agent_record.session_id

        root = agent_id
        visited: set[str] = set()
        current = agent_id
        while current and current not in visited:
            visited.add(current)
            record = self._agents.get(current)
            if record and record.parent_id:
                parent_record = self._agents.get(record.parent_id)
                # Handle dangling parent or cross-session parent: stop here
                if parent_record is None or parent_record.session_id != session_id:
                    root = current
                    break
                root = record.parent_id
                current = record.parent_id
            else:
                root = current
                break

        result = {root}
        result |= self._get_descendants(root, session_id=session_id)
        return result

    def _get_descendants(
        self,
        agent_id: str,
        visited: set[str] | None = None,
        session_id: str | None = None,
    ) -> set[str]:
        """Recursively collect all descendant agent IDs (cycle-safe, session-scoped)."""
        if visited is None:
            visited = set()
        descendants: set[str] = set()
        for record in self._agents.values():
            if record.parent_id == agent_id and record.agent_id not in visited:
                # Skip agents from different sessions
                if session_id is not None and record.session_id != session_id:
                    continue
                visited.add(record.agent_id)
                descendants.add(record.agent_id)
                descendants |= self._get_descendants(
                    record.agent_id, visited, session_id=session_id
                )
        return descendants
