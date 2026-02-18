"""Phase 3 tests: message gate content policies, session tracker."""

import pytest

from safeclaw.constraints.message_gate import MessageGate
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.engine.session_tracker import SessionTracker


# --- Fixtures ---

@pytest.fixture
def kg():
    from pathlib import Path
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


# --- MessageGate Tests ---

class TestMessageGate:
    def test_normal_message_passes(self, kg):
        gate = MessageGate(kg)
        result = gate.check(to="alice@example.com", content="Hello!", session_id="s1")
        assert not result.block

    def test_never_contact_blocks(self, kg):
        gate = MessageGate(kg)
        gate.add_never_contact("blocked@example.com")
        result = gate.check(to="blocked@example.com", content="Hello!", session_id="s1")
        assert result.block
        assert result.check_type == "never_contact"
        assert "never-contact" in result.reason

    def test_never_contact_case_insensitive(self, kg):
        gate = MessageGate(kg)
        gate.add_never_contact("BLOCKED@EXAMPLE.COM")
        result = gate.check(to="blocked@example.com", content="Hi", session_id="s1")
        assert result.block

    def test_remove_never_contact(self, kg):
        gate = MessageGate(kg)
        gate.add_never_contact("temp@example.com")
        gate.remove_never_contact("temp@example.com")
        result = gate.check(to="temp@example.com", content="Hi", session_id="s1")
        assert not result.block

    def test_sensitive_data_api_key(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="Here's my API key: api_key=sk_live_abcdef1234567890",
            session_id="s1",
        )
        assert result.block
        assert result.check_type == "sensitive_data"

    def test_sensitive_data_github_token(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="Use this token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
            session_id="s1",
        )
        assert result.block
        assert result.check_type == "sensitive_data"
        assert "GitHub token" in result.reason

    def test_sensitive_data_aws_key(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="AWS key: AKIAIOSFODNN7EXAMPLE",
            session_id="s1",
        )
        assert result.block
        assert "AWS" in result.reason

    def test_sensitive_data_private_key(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK...",
            session_id="s1",
        )
        assert result.block
        assert "Private key" in result.reason

    def test_sensitive_data_password(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="Login with password=SuperSecret123",
            session_id="s1",
        )
        assert result.block
        assert "Password" in result.reason

    def test_normal_content_passes(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="The build passed! Deploying to staging now.",
            session_id="s1",
        )
        assert not result.block

    def test_openai_key_detected(self, kg):
        gate = MessageGate(kg)
        result = gate.check(
            to="alice@example.com",
            content="Please use sk-proj1234567890abcdefghij for the API",
            session_id="s1",
        )
        assert result.block
        assert "secret key" in result.reason.lower() or "OpenAI" in result.reason

    def test_message_rate_limit(self, kg):
        gate = MessageGate(kg)
        gate._message_rate_limit = 3  # Low limit for testing

        for _ in range(3):
            gate.record_message("s1")

        result = gate.check(to="alice@example.com", content="Another msg", session_id="s1")
        assert result.block
        assert result.check_type == "rate_limit"

    def test_rate_limit_boundary(self, kg):
        """Record N-1 messages: not blocked. Record Nth: blocked (R3-67)."""
        gate = MessageGate(kg)
        gate._message_rate_limit = 3

        # Record 2 messages (under limit)
        gate.record_message("s1")
        gate.record_message("s1")
        result = gate.check(to="alice@example.com", content="Still ok", session_id="s1")
        assert not result.block

        # Record 3rd message (at limit)
        gate.record_message("s1")
        result = gate.check(to="alice@example.com", content="Should block", session_id="s1")
        assert result.block
        assert result.check_type == "rate_limit"

    def test_rate_limit_per_session(self, kg):
        gate = MessageGate(kg)
        gate._message_rate_limit = 3

        for _ in range(3):
            gate.record_message("s1")

        # Different session should not be limited
        result = gate.check(to="alice@example.com", content="Hi", session_id="s2")
        assert not result.block


# --- SessionTracker Tests ---

class TestSessionTracker:
    def test_record_outcome(self):
        tracker = SessionTracker()
        tracker.record_outcome(
            session_id="s1",
            action_class="WriteFile",
            tool_name="write",
            success=True,
            params={"file_path": "/src/main.py"},
        )
        state = tracker.get_state("s1")
        assert state is not None
        assert len(state.facts) == 1
        assert state.facts[0].action_class == "WriteFile"
        assert state.facts[0].success

    def test_file_modifications_tracked(self):
        tracker = SessionTracker()
        tracker.record_outcome(
            session_id="s1",
            action_class="WriteFile",
            tool_name="write",
            success=True,
            params={"file_path": "/src/main.py"},
        )
        tracker.record_outcome(
            session_id="s1",
            action_class="EditFile",
            tool_name="edit",
            success=True,
            params={"file_path": "/src/utils.py"},
        )
        state = tracker.get_state("s1")
        assert "/src/main.py" in state.files_modified
        assert "/src/utils.py" in state.files_modified

    def test_no_duplicate_file_modifications(self):
        tracker = SessionTracker()
        for _ in range(3):
            tracker.record_outcome(
                session_id="s1",
                action_class="WriteFile",
                tool_name="write",
                success=True,
                params={"file_path": "/src/main.py"},
            )
        state = tracker.get_state("s1")
        assert state.files_modified.count("/src/main.py") == 1

    def test_failed_writes_not_tracked_as_modified(self):
        tracker = SessionTracker()
        tracker.record_outcome(
            session_id="s1",
            action_class="WriteFile",
            tool_name="write",
            success=False,
            params={"file_path": "/src/main.py"},
        )
        state = tracker.get_state("s1")
        assert len(state.files_modified) == 0

    def test_record_violation(self):
        tracker = SessionTracker()
        tracker.record_violation("s1", "Force push blocked")
        state = tracker.get_state("s1")
        assert state.violation_count == 1
        assert state.last_violation_reason == "Force push blocked"

    def test_session_summary(self):
        tracker = SessionTracker()
        tracker.record_outcome(
            session_id="s1",
            action_class="ReadFile",
            tool_name="read",
            success=True,
            params={"file_path": "/src/main.py"},
        )
        tracker.record_violation("s1", "Push blocked")
        summary = tracker.get_session_summary("s1")
        assert len(summary) > 0
        assert any("ReadFile" in line for line in summary)
        assert any("Violations: 1" in line for line in summary)

    def test_empty_session_summary(self):
        tracker = SessionTracker()
        summary = tracker.get_session_summary("unknown")
        assert summary == []

    def test_clear_session(self):
        tracker = SessionTracker()
        tracker.record_outcome(
            session_id="s1",
            action_class="ReadFile",
            tool_name="read",
            success=True,
            params={},
        )
        tracker.clear_session("s1")
        assert tracker.get_state("s1") is None

    def test_session_eviction(self):
        tracker = SessionTracker()
        for i in range(1001):
            tracker.record_outcome(
                session_id=f"s{i}",
                action_class="ReadFile",
                tool_name="read",
                success=True,
                params={},
            )
        assert tracker.get_state("s0") is None

    def test_command_detail_in_facts(self):
        tracker = SessionTracker()
        tracker.record_outcome(
            session_id="s1",
            action_class="ExecuteCommand",
            tool_name="exec",
            success=True,
            params={"command": "git status"},
        )
        state = tracker.get_state("s1")
        assert "git status" in state.facts[0].detail
