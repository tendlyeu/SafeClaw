"""Multi-agent governance - propagates constraints to sub-agents."""

from dataclasses import dataclass, field
from collections import OrderedDict

MAX_AGENTS = 500


@dataclass
class AgentContext:
    """Governance context for an individual agent."""
    agent_id: str
    parent_id: str | None = None
    session_id: str = ""
    constraint_overrides: dict = field(default_factory=dict)


class MultiAgentGovernor:
    """Manages constraint propagation in multi-agent hierarchies.

    When OpenClaw spawns sub-agents, this ensures each child agent
    operates within the same ontological envelope, with optional
    tighter constraints set by the parent.
    """

    def __init__(self):
        self._agents: OrderedDict[str, AgentContext] = OrderedDict()

    def register_agent(
        self,
        agent_id: str,
        session_id: str,
        parent_id: str | None = None,
    ) -> AgentContext:
        """Register a new agent in the governance hierarchy."""
        ctx = AgentContext(
            agent_id=agent_id,
            parent_id=parent_id,
            session_id=session_id,
        )
        self._agents[agent_id] = ctx
        while len(self._agents) > MAX_AGENTS:
            self._agents.popitem(last=False)
        return ctx

    def get_agent(self, agent_id: str) -> AgentContext | None:
        return self._agents.get(agent_id)

    def get_children(self, agent_id: str) -> list[AgentContext]:
        """Get all direct child agents."""
        return [a for a in self._agents.values() if a.parent_id == agent_id]

    def get_ancestry(self, agent_id: str) -> list[str]:
        """Get the full ancestry chain from root to this agent."""
        chain = []
        visited: set[str] = set()
        current = agent_id
        while current and current not in visited:
            visited.add(current)
            chain.append(current)
            ctx = self._agents.get(current)
            current = ctx.parent_id if ctx else None
        chain.reverse()
        return chain

    def set_constraint_override(
        self, agent_id: str, constraint_key: str, value: str
    ) -> None:
        """Set a tighter constraint for a specific agent."""
        ctx = self._agents.get(agent_id)
        if ctx:
            ctx.constraint_overrides[constraint_key] = value

    def get_effective_constraints(self, agent_id: str) -> dict:
        """Get merged constraints from the full ancestry chain (parent → child)."""
        ancestry = self.get_ancestry(agent_id)
        merged: dict = {}
        for ancestor_id in ancestry:
            ctx = self._agents.get(ancestor_id)
            if ctx:
                merged.update(ctx.constraint_overrides)
        return merged

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from governance."""
        self._agents.pop(agent_id, None)
