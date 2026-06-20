"""PR-2: plugin->service context plumbing.

Covers the cron trigger-origin escalation (#324), the new before_tool_call
discriminator fields reaching the engine (#316 forwarding half), and the
LLM I/O audit trail with provider/model/run/usage (#315 service side).
"""

import json
from pathlib import Path

import pytest

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import Decision, LlmIOEvent, ToolCallEvent
from safeclaw.engine.full_engine import STEP_CRON_NO_APPROVER, FullEngine


@pytest.fixture
def engine(tmp_path):
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
    )
    return FullEngine(config)


# --- #324: cron trigger-origin escalation ---


class TestCronNoApprover:
    def test_interactive_confirmation_is_preserved(self, engine):
        """An interactive run that needs confirmation stays needs-confirmation."""

        async def run():
            ev = ToolCallEvent(
                session_id="s-int",
                user_id="u",
                tool_name="delete",
                params={"file_path": "/tmp/a.txt"},
                triggered_by="interactive",
            )
            return await engine.evaluate_tool_call(ev)

        import asyncio

        dec = asyncio.run(run())
        assert dec.requires_confirmation is True
        assert dec.constraint_step != STEP_CRON_NO_APPROVER

    def test_cron_confirmation_escalates_to_block(self, engine):
        """The same action on a cron run has no approver -> fail-safe block."""

        async def run():
            ev = ToolCallEvent(
                session_id="s-cron",
                user_id="u",
                tool_name="delete",
                params={"file_path": "/tmp/a.txt"},
                triggered_by="cron",
                job_id="job-42",
            )
            return await engine.evaluate_tool_call(ev)

        import asyncio

        dec = asyncio.run(run())
        assert dec.block is True
        assert dec.requires_confirmation is False
        assert dec.constraint_step == STEP_CRON_NO_APPROVER
        assert "no interactive approver" in dec.reason
        # risk level is carried onto the escalated block for the API response
        assert getattr(dec, "_risk_level", None)

    def test_policy_unit_only_touches_confirmation_decisions(self, engine):
        """A plain allow/block decision is never altered by the cron policy."""
        allowed = Decision(block=False)
        ev = ToolCallEvent(
            session_id="s", user_id="u", tool_name="read", params={}, triggered_by="cron"
        )
        assert engine._apply_trigger_origin_policy(ev, allowed) is allowed

        hard_block = Decision(block=True, reason="nope", requires_confirmation=False)
        assert engine._apply_trigger_origin_policy(ev, hard_block) is hard_block

    def test_no_trigger_origin_behaves_as_interactive(self, engine):
        """Empty triggered_by (older plugins) must not escalate."""
        confirm = Decision(block=True, requires_confirmation=True)
        ev = ToolCallEvent(session_id="s", user_id="u", tool_name="delete", params={})
        assert engine._apply_trigger_origin_policy(ev, confirm) is confirm


# --- #316: before_tool_call discriminators reach the engine ---


class TestToolCallDiscriminators:
    def test_event_carries_discriminators(self):
        ev = ToolCallEvent(
            session_id="s",
            user_id="u",
            tool_name="exec",
            params={},
            tool_kind="code_mode_exec",
            tool_input_kind="javascript",
            derived_paths=["/work/a.ts", "/work/b.ts"],
        )
        assert ev.tool_kind == "code_mode_exec"
        assert ev.tool_input_kind == "javascript"
        assert ev.derived_paths == ["/work/a.ts", "/work/b.ts"]

    def test_request_model_accepts_and_defaults(self):
        from safeclaw.api.models import ToolCallRequest

        bare = ToolCallRequest(toolName="read")
        assert bare.toolKind == "" and bare.derivedPaths == [] and bare.triggeredBy == ""

        full = ToolCallRequest(
            toolName="exec",
            toolKind="code_mode_exec",
            toolInputKind="typescript",
            derivedPaths=["/x"],
            triggeredBy="cron",
            jobId="j1",
        )
        assert full.toolInputKind == "typescript"
        assert full.jobId == "j1"


# --- #315: LLM I/O audit trail ---


class TestLlmIOAudit:
    def test_log_llm_io_writes_attributed_record(self, engine, tmp_path):
        async def run():
            await engine.log_llm_io(
                LlmIOEvent(
                    session_id="sess-llm",
                    direction="output",
                    content="hello world",
                    provider="anthropic",
                    model="claude-opus-4-8",
                    run_id="run-7",
                    usage={"input_tokens": 5, "output_tokens": 2},
                )
            )

        import asyncio

        asyncio.run(run())

        files = list((tmp_path / "audit").rglob("llm-sess-llm.jsonl"))
        assert len(files) == 1
        rec = json.loads(files[0].read_text().strip())
        assert rec["provider"] == "anthropic"
        assert rec["model"] == "claude-opus-4-8"
        assert rec["runId"] == "run-7"
        assert rec["usage"] == {"input_tokens": 5, "output_tokens": 2}
        assert rec["direction"] == "output"
        assert rec["content"] == "hello world"
        # owner-only permissions, like the decision audit log
        assert (files[0].stat().st_mode & 0o777) == 0o600

    def test_log_llm_io_truncates_long_content(self, engine, tmp_path):
        async def run():
            await engine.log_llm_io(
                LlmIOEvent(
                    session_id="sess-big",
                    direction="input",
                    content="x" * 20_000,
                )
            )

        import asyncio

        asyncio.run(run())
        rec = json.loads(next((tmp_path / "audit").rglob("llm-sess-big.jsonl")).read_text().strip())
        assert rec["truncated"] is True
        assert len(rec["content"]) == 10_000
