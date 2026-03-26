"""Tests for #128: DecisionResponse computed 'decision' field.

Both confirmations and hard blocks used to return block=True with no way
for a naive client to distinguish them.  The computed ``decision`` field
resolves this ambiguity.
"""

from safeclaw.api.models import DecisionResponse


class TestDecisionResponseHasDecisionField:
    """test_decision_response_has_decision_field — three mutually exclusive states."""

    def test_blocked_returns_blocked(self):
        resp = DecisionResponse(block=True, confirmationRequired=False)
        assert resp.decision == "blocked"

    def test_confirmation_required_returns_needs_confirmation(self):
        resp = DecisionResponse(block=True, confirmationRequired=True)
        assert resp.decision == "needs_confirmation"

    def test_allowed_returns_allowed(self):
        resp = DecisionResponse(block=False, confirmationRequired=False)
        assert resp.decision == "allowed"

    def test_allowed_even_with_confirmation_flag(self):
        """If block is False the decision is 'allowed' regardless of confirmationRequired."""
        resp = DecisionResponse(block=False, confirmationRequired=True)
        assert resp.decision == "allowed"


class TestDecisionResponseJsonIncludesDecision:
    """test_decision_response_json_includes_decision — serialization check."""

    def test_blocked_in_json(self):
        resp = DecisionResponse(block=True)
        data = resp.model_dump()
        assert "decision" in data
        assert data["decision"] == "blocked"

    def test_needs_confirmation_in_json(self):
        resp = DecisionResponse(block=True, confirmationRequired=True)
        data = resp.model_dump()
        assert data["decision"] == "needs_confirmation"

    def test_allowed_in_json(self):
        resp = DecisionResponse(block=False)
        data = resp.model_dump()
        assert data["decision"] == "allowed"

    def test_json_string_includes_decision(self):
        """model_dump_json() should also contain the field."""
        resp = DecisionResponse(block=True, confirmationRequired=True)
        json_str = resp.model_dump_json()
        assert '"decision"' in json_str
        assert '"needs_confirmation"' in json_str
