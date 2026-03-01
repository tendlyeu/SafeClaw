"""Knowledge store - persists knowledge graph across sessions."""

import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("safeclaw.knowledge_store")

MAX_ENTRIES = 10000


class KnowledgeStore:
    """Persists cross-session knowledge: project structure, past decisions, preference evolution.

    Provides 'institutional memory' so the agent remembers what it learned
    about the codebase across sessions.
    """

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._facts: OrderedDict[str, dict] = OrderedDict()
        self._load()

    def _store_file(self) -> Path:
        return self.store_dir / "knowledge.jsonl"

    def _load(self) -> None:
        """Load persisted facts from disk."""
        store_file = self._store_file()
        if not store_file.exists():
            return
        with open(store_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        fact = json.loads(line)
                        self._facts[fact["id"]] = fact
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping corrupted knowledge store line: {e}")

    def _save(self) -> None:
        """Persist all facts to disk atomically."""
        store_file = self._store_file()
        tmp_file = store_file.with_suffix(".jsonl.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            for fact in self._facts.values():
                f.write(json.dumps(fact) + "\n")
        os.replace(tmp_file, store_file)

    def record_fact(
        self,
        fact_type: str,
        subject: str,
        detail: str,
        session_id: str = "",
    ) -> str:
        """Record a new fact. Returns the fact ID."""
        fact_id = f"{fact_type}:{subject}"
        self._facts[fact_id] = {
            "id": fact_id,
            "type": fact_type,
            "subject": subject,
            "detail": detail,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Move updated entry to end so it is treated as most-recent
        self._facts.move_to_end(fact_id)
        # Evict oldest entries (O(1) per eviction via OrderedDict.popitem)
        while len(self._facts) > MAX_ENTRIES:
            self._facts.popitem(last=False)
        self._save()
        return fact_id

    def get_facts(self, fact_type: str | None = None, limit: int = 50) -> list[dict]:
        """Get recent facts, optionally filtered by type."""
        facts = list(self._facts.values())
        if fact_type:
            facts = [f for f in facts if f["type"] == fact_type]
        return facts[-limit:]

    def get_fact(self, fact_id: str) -> dict | None:
        return self._facts.get(fact_id)

    def get_project_context(self) -> list[str]:
        """Get human-readable project context from stored facts."""
        lines = []
        # File structure facts
        file_facts = self.get_facts("file_structure", limit=20)
        if file_facts:
            lines.append("Known project files:")
            for f in file_facts[-10:]:
                lines.append(f"  - {f['subject']}: {f['detail']}")

        # Decision history
        decision_facts = self.get_facts("decision_pattern", limit=10)
        if decision_facts:
            lines.append("Known decision patterns:")
            for f in decision_facts[-5:]:
                lines.append(f"  - {f['detail']}")

        return lines

    def clear(self) -> None:
        """Clear all stored knowledge."""
        self._facts.clear()
        store_file = self._store_file()
        if store_file.exists():
            store_file.unlink()
