"""Tests for delegation detection bypass hardening (#140).

Covers three bypass vectors that were previously possible:
1. Tool name aliases (e.g., "bash" instead of "exec")
2. Cross-session bypass (block in session 1, delegate in session 2)
3. Parameter variation (semantically equivalent commands with different formatting)
"""

from safeclaw.engine.delegation_detector import (
    DelegationDetector,
    _normalize_tool_name,
    _normalize_command_value,
    _TOOL_ALIASES,
)


class TestToolAliasBypass:
    """Verify that tool name aliases are normalized before comparison."""

    def test_tool_alias_bypass_exec_bash(self):
        """Block 'exec', then check delegation with 'bash' — must detect."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "rm -rf /tmp/data"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "exec", sig, params=params)
        result = dd.check_delegation("sess-1", "agent-2", "bash", sig, params=params)

        assert result.is_delegation is True
        assert result.original_agent_id == "agent-1"

    def test_tool_alias_bypass_bash_exec(self):
        """Block 'bash', then check delegation with 'exec' — must detect."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "ls -la"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "bash", sig, params=params)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig, params=params)

        assert result.is_delegation is True
        assert result.original_agent_id == "agent-1"

    def test_tool_alias_bypass_shell_sh(self):
        """Block 'shell', then check delegation with 'sh' — must detect."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "echo hello"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "shell", sig, params=params)
        result = dd.check_delegation("sess-1", "agent-2", "sh", sig, params=params)

        assert result.is_delegation is True
        assert result.original_agent_id == "agent-1"

    def test_tool_alias_bypass_write_file_variants(self):
        """Block 'write_file', then check with 'create_file' — must detect."""
        dd = DelegationDetector(mode="strict")
        params = {"path": "/etc/config", "content": "malicious"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "write_file", sig, params=params)
        result = dd.check_delegation("sess-1", "agent-2", "create_file", sig, params=params)

        assert result.is_delegation is True

    def test_tool_alias_bypass_delete_file_variants(self):
        """Block 'delete_file', then check with 'remove_file' — must detect."""
        dd = DelegationDetector(mode="strict")
        params = {"path": "/important/data.db"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "delete_file", sig, params=params)
        result = dd.check_delegation("sess-1", "agent-2", "remove_file", sig, params=params)

        assert result.is_delegation is True

    def test_non_alias_tool_names_unaffected(self):
        """Tools without aliases should still require exact match."""
        dd = DelegationDetector(mode="strict")
        params = {"query": "SELECT * FROM users"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "sql_query", sig, params=params)
        # Different, non-aliased tool should NOT match
        result = dd.check_delegation("sess-1", "agent-2", "db_query", sig, params=params)
        assert result.is_delegation is False

        # Same tool name should still match
        result = dd.check_delegation("sess-1", "agent-2", "sql_query", sig, params=params)
        assert result.is_delegation is True

    def test_normalize_tool_name_known_aliases(self):
        """All known aliases map to the canonical name."""
        for alias, canonical in _TOOL_ALIASES.items():
            assert _normalize_tool_name(alias) == canonical

    def test_normalize_tool_name_passthrough(self):
        """Unknown tool names pass through unchanged."""
        assert _normalize_tool_name("custom_tool") == "custom_tool"
        assert _normalize_tool_name("read") == "read"


class TestCrossSessionBypass:
    """Verify that blocks are detected across different sessions."""

    def test_cross_session_bypass(self):
        """Block in session 1, check in session 2 — must detect delegation."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "rm -rf /"}
        sig = dd.make_signature(params)

        # Agent-1 blocked in session-1
        dd.record_block("sess-1", "agent-1", "exec", sig, params=params)

        # Agent-2 tries same action in session-2 — must still be detected
        result = dd.check_delegation("sess-2", "agent-2", "exec", sig, params=params)
        assert result.is_delegation is True
        assert result.original_agent_id == "agent-1"
        assert "cross-session" in result.reason

    def test_cross_session_same_agent_not_delegation(self):
        """Same agent retrying in a different session is NOT delegation."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "rm -rf /"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "exec", sig, params=params)

        # Same agent in a new session — not delegation, just retry
        result = dd.check_delegation("sess-2", "agent-1", "exec", sig, params=params)
        assert result.is_delegation is False

    def test_cross_session_with_tool_alias(self):
        """Cross-session detection combined with tool alias normalization."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "cat /etc/passwd"}
        sig = dd.make_signature(params)

        # Block "exec" in session-1
        dd.record_block("sess-1", "agent-1", "exec", sig, params=params)

        # Check "bash" in session-2
        result = dd.check_delegation("sess-2", "agent-2", "bash", sig, params=params)
        assert result.is_delegation is True
        assert "cross-session" in result.reason

    def test_clear_session_only_affects_target_session(self):
        """Clearing session-1 should not affect blocks from session-2."""
        dd = DelegationDetector(mode="strict")
        params = {"command": "dangerous"}
        sig = dd.make_signature(params)

        dd.record_block("sess-1", "agent-1", "exec", sig, params=params)
        dd.record_block("sess-2", "agent-3", "exec", sig, params=params)

        # Clear session-1 only
        dd.clear_session("sess-1")

        # Block from session-2 should still be detectable
        result = dd.check_delegation("sess-3", "agent-2", "exec", sig, params=params)
        assert result.is_delegation is True
        assert result.original_agent_id == "agent-3"


class TestParamVariationBypass:
    """Verify that semantically equivalent commands are detected."""

    def test_param_variation_bypass_flag_reorder(self):
        """Block 'rm -rf /', check 'rm -f -r /' — must detect (same flags)."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "rm -rf /"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "rm -f -r /"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig_check, params=params_check)

        assert result.is_delegation is True
        assert result.original_agent_id == "agent-1"

    def test_param_variation_bypass_flag_expansion(self):
        """Block 'rm -rf /', check 'rm -r -f /' — must detect."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "rm -rf /"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "rm -r -f /"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig_check, params=params_check)

        assert result.is_delegation is True

    def test_param_variation_whitespace_collapse(self):
        """Block 'rm  -rf  /' (extra spaces), check 'rm -rf /' — must detect."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "rm  -rf  /"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "rm -rf /"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig_check, params=params_check)

        assert result.is_delegation is True

    def test_param_variation_long_flags(self):
        """Block 'ls --all --long', check 'ls --long --all' — must detect."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "ls --all --long"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "ls --long --all"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig_check, params=params_check)

        assert result.is_delegation is True

    def test_param_variation_different_commands_not_detected(self):
        """Block 'rm -rf /', check 'ls -la' — must NOT detect (different commands)."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "rm -rf /"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "ls -la"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig_check, params=params_check)

        assert result.is_delegation is False

    def test_param_variation_cmd_key(self):
        """The 'cmd' parameter key is also normalized."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"cmd": "git push -f origin main"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"cmd": "git push   -f  origin   main"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "exec", sig_check, params=params_check)

        assert result.is_delegation is True

    def test_non_command_params_not_normalized(self):
        """Parameters not in _COMMAND_PARAM_KEYS are compared as-is."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"path": "/tmp/data", "content": "hello   world"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "write", sig_blocked, params=params_blocked)

        # Different whitespace in 'content' should NOT match (not a command key)
        params_check = {"path": "/tmp/data", "content": "hello world"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "write", sig_check, params=params_check)

        assert result.is_delegation is False


class TestNormalizeCommandValue:
    """Unit tests for the _normalize_command_value helper."""

    def test_combined_short_flags_expanded(self):
        assert _normalize_command_value("rm -rf /") == "rm -f -r /"

    def test_separate_short_flags_sorted(self):
        assert _normalize_command_value("rm -r -f /") == "rm -f -r /"

    def test_long_flags_sorted(self):
        assert _normalize_command_value("ls --all --long") == "ls --all --long"
        assert _normalize_command_value("ls --long --all") == "ls --all --long"

    def test_whitespace_collapsed(self):
        assert _normalize_command_value("rm  -rf   /") == "rm -f -r /"

    def test_positionals_preserved_order(self):
        assert _normalize_command_value("cp -r src dst") == "cp -r src dst"

    def test_double_dash_separator(self):
        result = _normalize_command_value("grep -- -pattern file")
        assert result.startswith("grep --")

    def test_empty_string(self):
        assert _normalize_command_value("") == ""

    def test_single_command_no_args(self):
        assert _normalize_command_value("ls") == "ls"

    def test_malformed_quotes_fallback(self):
        """Malformed quoting falls back to whitespace normalization."""
        result = _normalize_command_value("echo 'unterminated")
        # Should not raise; just normalizes whitespace
        assert "echo" in result


class TestCombinedBypassVectors:
    """Test combinations of multiple bypass vectors simultaneously."""

    def test_alias_plus_param_variation(self):
        """Block 'exec' with 'rm -rf /', check 'bash' with 'rm -f -r /'."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "rm -rf /"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "rm -f -r /"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-1", "agent-2", "bash", sig_check, params=params_check)

        assert result.is_delegation is True

    def test_alias_plus_cross_session_plus_param_variation(self):
        """All three bypass vectors combined — must still detect."""
        dd = DelegationDetector(mode="strict")

        params_blocked = {"command": "rm -rf /tmp/important"}
        sig_blocked = dd.make_signature(params_blocked)
        dd.record_block("sess-1", "agent-1", "exec", sig_blocked, params=params_blocked)

        params_check = {"command": "rm -f -r /tmp/important"}
        sig_check = dd.make_signature(params_check)
        result = dd.check_delegation("sess-2", "agent-2", "sh", sig_check, params=params_check)

        assert result.is_delegation is True
        assert "cross-session" in result.reason

    def test_disabled_mode_still_bypasses_all(self):
        """Disabled mode should not detect even with all bypass vectors."""
        dd = DelegationDetector(mode="disabled")

        params = {"command": "rm -rf /"}
        sig = dd.make_signature(params)
        dd.record_block("sess-1", "agent-1", "exec", sig, params=params)

        result = dd.check_delegation("sess-2", "agent-2", "bash", sig, params=params)
        assert result.is_delegation is False
