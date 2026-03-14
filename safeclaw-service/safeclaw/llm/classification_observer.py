"""Classification Observer — suggests better classifications when regex falls back to defaults."""

import asyncio
import fcntl
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.llm.prompts import (
    CLASSIFICATION_OBSERVER_SYSTEM,
    build_classification_observer_user_prompt,
)

logger = logging.getLogger("safeclaw.llm.observer")

DEFAULT_ONTOLOGY_CLASS = "Action"


@dataclass
class ClassificationSuggestion:
    tool_name: str
    params_summary: str
    symbolic_class: str
    suggested_class: str
    suggested_risk: str
    reasoning: str
    timestamp: str


class ClassificationObserver:
    """Watches for classifier defaults and suggests better classifications."""

    def __init__(self, client, suggestions_file: Path):
        self.client = client
        self.suggestions_file = suggestions_file

    async def observe(
        self,
        tool_name: str,
        params: dict,
        symbolic_result: ClassifiedAction,
    ) -> ClassificationSuggestion | None:
        if symbolic_result.ontology_class != DEFAULT_ONTOLOGY_CLASS:
            return None

        user_prompt = build_classification_observer_user_prompt(
            tool_name=tool_name,
            params=params,
            symbolic_class=symbolic_result.ontology_class,
            risk_level=symbolic_result.risk_level,
        )
        result = await self.client.chat_json(
            messages=[
                {"role": "system", "content": CLASSIFICATION_OBSERVER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        if result is None:
            return None
        return await self._parse_and_save(result, tool_name, params, symbolic_result)

    async def _parse_and_save(self, data, tool_name, params, symbolic_result):
        try:
            summary = ", ".join(f"{k}={str(v)[:50]}" for k, v in list(params.items())[:5])
            suggestion = ClassificationSuggestion(
                tool_name=tool_name,
                params_summary=summary,
                symbolic_class=symbolic_result.ontology_class,
                suggested_class=data.get("suggested_class", "Action"),
                suggested_risk=data.get("suggested_risk", "MediumRisk"),
                reasoning=data.get("reasoning", ""),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            # Offload synchronous file I/O with file locking to a thread
            # to avoid blocking the async event loop (#114, #115)
            line = json.dumps(asdict(suggestion)) + "\n"
            await asyncio.to_thread(self._write_line, line)
            logger.info(
                "Classification suggestion: %s -> %s (%s)",
                tool_name,
                suggestion.suggested_class,
                suggestion.suggested_risk,
            )
            return suggestion
        except (KeyError, TypeError, ValueError):
            logger.warning("Failed to parse classification suggestion", exc_info=True)
            return None

    def _write_line(self, line: str) -> None:
        """Write a single JSONL line with file locking for multi-worker safety."""
        self.suggestions_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.suggestions_file, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
