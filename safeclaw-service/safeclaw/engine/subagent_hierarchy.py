"""Subagent spawn hierarchy — tracks parentage by session key so the spawn gate
can enforce depth and fan-out limits and walk the full ancestry (#321).

The deprecated OpenClaw ``subagent_spawning`` hook gives session keys, not agent
ids, so parentage is keyed on session keys here. An optional agent-id mapping is
recorded per session key (when known) so ancestor kill/block checks can reach the
agent registry / delegation detector.

In-memory and bounded (oldest sessions evicted); spawn parentage is runtime
session state. Cross-restart persistence is a follow-up.
"""

from __future__ import annotations

from collections import OrderedDict

MAX_TRACKED_SESSIONS = 10_000


class SubagentHierarchy:
    def __init__(self, max_sessions: int = MAX_TRACKED_SESSIONS):
        self._max = max_sessions
        # child_session_key -> parent_session_key
        self._parent: OrderedDict[str, str] = OrderedDict()
        # parent_session_key -> ordered set of child_session_keys
        self._children: OrderedDict[str, list[str]] = OrderedDict()
        # session_key -> agent_id (when known)
        self._agent_id: dict[str, str] = {}

    def register_spawn(self, parent_key: str, child_key: str, child_agent_id: str = "") -> None:
        """Record an allowed spawn: child_key's parent is parent_key."""
        if not child_key:
            return
        if parent_key:
            self._parent[child_key] = parent_key
            self._parent.move_to_end(child_key)
            kids = self._children.setdefault(parent_key, [])
            self._children.move_to_end(parent_key)
            if child_key not in kids:
                kids.append(child_key)
        if child_agent_id:
            self._agent_id[child_key] = child_agent_id
        self._evict()

    def set_agent_id(self, session_key: str, agent_id: str) -> None:
        if session_key and agent_id:
            self._agent_id[session_key] = agent_id

    def agent_id_for(self, session_key: str) -> str | None:
        return self._agent_id.get(session_key)

    def depth(self, session_key: str) -> int:
        """Number of ancestors above ``session_key`` (a root has depth 0)."""
        depth = 0
        seen: set[str] = set()
        current = session_key
        while current in self._parent and current not in seen:
            seen.add(current)
            current = self._parent[current]
            depth += 1
        return depth

    def child_count(self, parent_key: str) -> int:
        return len(self._children.get(parent_key, ()))

    def ancestors(self, session_key: str) -> list[str]:
        """Ancestor session keys from the immediate parent upward."""
        out: list[str] = []
        seen: set[str] = set()
        current = session_key
        while current in self._parent and current not in seen:
            seen.add(current)
            current = self._parent[current]
            out.append(current)
        return out

    def _evict(self) -> None:
        while len(self._parent) > self._max:
            child, _ = self._parent.popitem(last=False)
            self._agent_id.pop(child, None)
        while len(self._children) > self._max:
            self._children.popitem(last=False)
