"""Agent registration with per-agent tokens."""

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
        return hmac.new(self._server_secret, token.encode(), 'sha256').hexdigest()

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
        """Verify an agent's token using constant-time comparison."""
        record = self._agents.get(agent_id)
        if record is None:
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

    def revive_agent(self, agent_id: str) -> bool:
        record = self._agents.get(agent_id)
        if record:
            record.killed = False
            return True
        return False

    def is_killed(self, agent_id: str) -> bool:
        record = self._agents.get(agent_id)
        if record is None:
            return True  # Unknown agents are treated as killed (fail-closed)
        return record.killed

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def get_hierarchy_ids(self, agent_id: str) -> set[str]:
        """Get all agent IDs in the same hierarchy tree."""
        root = agent_id
        visited: set[str] = set()
        current = agent_id
        while current and current not in visited:
            visited.add(current)
            record = self._agents.get(current)
            if record and record.parent_id:
                # Handle dangling parent: if parent doesn't exist, stop here
                if record.parent_id not in self._agents:
                    root = current
                    break
                root = record.parent_id
                current = record.parent_id
            else:
                root = current
                break

        result = {root}
        result |= self._get_descendants(root)
        return result

    def _get_descendants(self, agent_id: str, visited: set[str] | None = None) -> set[str]:
        """Recursively collect all descendant agent IDs (cycle-safe)."""
        if visited is None:
            visited = set()
        descendants: set[str] = set()
        for record in self._agents.values():
            if record.parent_id == agent_id and record.agent_id not in visited:
                visited.add(record.agent_id)
                descendants.add(record.agent_id)
                descendants |= self._get_descendants(record.agent_id, visited)
        return descendants
