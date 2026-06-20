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

    def test_moderation_actions(self, clf):
        for action in ("ban", "kick", "timeout", "role-add", "channel-delete", "permissions"):
            a = _c(clf, "message", {"action": action})
            assert a.ontology_class == "ModerateChannel", action
            assert a.risk_level == "HighRisk"

    def test_action_is_case_insensitive(self, clf):
        assert _c(clf, "message", {"action": "BROADCAST"}).ontology_class == "CrossContextMessage"


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
