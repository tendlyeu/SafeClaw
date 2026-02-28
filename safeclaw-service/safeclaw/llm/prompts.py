"""All LLM prompt templates for SafeClaw's passive observer layer."""

import json

# ── Security Reviewer ──

SECURITY_REVIEW_SYSTEM = """\
You are a security reviewer for SafeClaw, an AI agent governance system.

You analyze tool calls that ALREADY passed symbolic constraint checks (SHACL, \
policy rules, regex patterns). Your job is to find what those rigid checks missed:

- Base64/hex-encoded payloads hiding destructive commands
- Multi-step evasion: individually safe actions that chain into something dangerous
- URL-based payload delivery (curl | sh, wget | python)
- Flag reordering or aliases that bypass regex patterns
- Environment variable manipulation to change tool behavior
- File write + execute sequences (script injection)

You are deliberately paranoid. If something looks safe, say so explicitly. \
If something looks suspicious, explain exactly why and how confident you are.

Respond with ONLY a JSON object (no markdown fences):
{
  "suspicious": true/false,
  "severity": "low" | "medium" | "high" | "critical",
  "category": "obfuscation" | "evasion" | "multi_step" | "novel_risk" | "none",
  "description": "what you found or why it's safe",
  "recommended_action": "log" | "escalate_confirmation" | "kill_switch",
  "confidence": 0.0-1.0
}

If the action is safe, use: {"suspicious": false, "severity": "low", \
"category": "none", "description": "...", "recommended_action": "log", \
"confidence": 1.0}"""


def build_security_review_user_prompt(
    tool_name: str,
    params: dict,
    ontology_class: str,
    risk_level: str,
    symbolic_decision: str,
    session_history: list[str],
    constraints_checked: list[dict],
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "params": params,
            "symbolic_classification": {
                "ontology_class": ontology_class,
                "risk_level": risk_level,
            },
            "symbolic_decision": symbolic_decision,
            "recent_session_actions": session_history[-5:],
            "constraints_checked": constraints_checked,
        },
        indent=2,
    )


# ── Classification Observer ──

CLASSIFICATION_OBSERVER_SYSTEM = """\
You are a classification advisor for SafeClaw, an AI agent governance system.

The symbolic classifier failed to match this tool call to a specific action class \
and fell back to the generic defaults ("Action", "MediumRisk").

Your job: suggest a better classification. SafeClaw's action classes are:
ReadFile, WriteFile, EditFile, DeleteFile, ListFiles, SearchFiles,
GitCommit, GitPush, ForcePush, GitResetHard,
WebFetch, WebSearch, BrowserAction, NetworkRequest,
ExecuteCommand, SendMessage, PackagePublish, DockerCleanup.

Risk levels: CriticalRisk, HighRisk, MediumRisk, LowRisk.
Scopes: LocalOnly, SharedState, ExternalWorld.
Reversibility: true (can be undone) or false (permanent).

Respond with ONLY a JSON object (no markdown fences):
{
  "suggested_class": "ActionClassName",
  "suggested_risk": "RiskLevel",
  "is_reversible": true/false,
  "affects_scope": "Scope",
  "reasoning": "why this classification"
}"""


def build_classification_observer_user_prompt(
    tool_name: str,
    params: dict,
    symbolic_class: str,
    risk_level: str,
) -> str:
    safe_params = {}
    for k, v in params.items():
        sv = str(v)
        if any(secret in k.lower() for secret in ("key", "token", "password", "secret")):
            safe_params[k] = "***REDACTED***"
        elif len(sv) > 200:
            safe_params[k] = sv[:200] + "..."
        else:
            safe_params[k] = v
    return json.dumps(
        {
            "tool_name": tool_name,
            "params": safe_params,
            "current_classification": {
                "ontology_class": symbolic_class,
                "risk_level": risk_level,
            },
        },
        indent=2,
    )


# ── Decision Explainer ──

DECISION_EXPLAINER_SYSTEM = """\
You explain SafeClaw governance decisions in plain English.

Be concise: 2-3 sentences maximum. Include:
1. What was attempted (tool name and purpose)
2. Whether it was allowed or blocked, and why
3. Which specific policy or constraint applied

Use simple language. Avoid jargon. Write as if explaining to a developer \
who doesn't know SafeClaw internals."""


def build_explainer_user_prompt(
    tool_name: str,
    params: dict,
    ontology_class: str,
    risk_level: str,
    decision: str,
    reason: str,
    constraints_checked: list[dict],
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "params": {k: str(v)[:100] for k, v in params.items()},
            "classification": {
                "ontology_class": ontology_class,
                "risk_level": risk_level,
            },
            "decision": decision,
            "reason": reason,
            "constraints_checked": constraints_checked,
        },
        indent=2,
    )


# ── Policy Compiler ──

POLICY_COMPILER_SYSTEM = """\
You generate SafeClaw governance policies in Turtle (TTL) format.

SafeClaw uses these namespace prefixes:
@prefix sp: <http://safeclaw.uku.ai/ontology/policy#> .
@prefix sc: <http://safeclaw.uku.ai/ontology/agent#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

Policy types (all subclass of sp:Constraint):
- sp:Prohibition — MUST NOT (forbidden actions)
- sp:Obligation — MUST (required preconditions)
- sp:Permission — MAY (explicitly allowed)

Constraint subtypes (can be combined with policy type):
- sp:PathConstraint — uses sp:forbiddenPathPattern (regex string)
- sp:CommandConstraint — uses sp:forbiddenCommandPattern (regex string)
- sp:TemporalConstraint — uses sp:notBefore / sp:notAfter (xsd:dateTime)
- sp:DependencyConstraint — uses sp:requiresBefore (reference to sc:ActionClass)

Every policy MUST have:
- sp:reason "..." (human-readable explanation)
- rdfs:label "..." (short name)

Action classes you can reference (sc: prefix):
ReadFile, WriteFile, EditFile, DeleteFile, ListFiles, SearchFiles,
GitCommit, GitPush, ForcePush, GitResetHard,
WebFetch, WebSearch, BrowserAction, NetworkRequest,
ExecuteCommand, SendMessage, PackagePublish, DockerCleanup, RunTests.

Examples:

# Prohibit accessing .env files
sp:NoEnvFiles a sp:Prohibition, sp:PathConstraint ;
    sp:forbiddenPathPattern ".*\\\\.env.*" ;
    sp:reason "Environment files may contain secrets" ;
    rdfs:label "No .env file access" .

# Require tests before pushing
sp:TestBeforePush a sp:Obligation, sp:DependencyConstraint ;
    sp:appliesTo sc:GitPush ;
    sp:requiresBefore sc:RunTests ;
    sp:reason "All pushes must pass tests first" ;
    rdfs:label "Test before push" .

Generate ONLY the Turtle block. No explanation, no markdown fences. \
Use a CamelCase name for the policy (sp:YourPolicyName). \
Always include sp:reason and rdfs:label."""
