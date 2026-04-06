import ipaddress
import os
import re
import secrets
import socket
from datetime import date
from urllib.parse import urlparse

import httpx
from fasthtml.common import *
from fasthtml.components import Footer as FooterTag
from fasthtml.oauth import redir_url

from auth import github_client, user_auth_before, get_current_user, sync_admin_on_login, is_user_admin, is_env_admin, require_admin
from db import users, upsert_user, hash_admin_password, verify_admin_password


def _validate_service_url(url: str) -> bool:
    """Validate a service URL against SSRF attacks (#73).

    Rejects non-http(s) schemes, private/loopback IP addresses,
    and hostnames that resolve to private/loopback IPs.
    Returns True if valid, raises ValueError otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme: {parsed.scheme}. Only http and https are allowed.")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("No hostname in URL.")

    # Block known dangerous hostnames (#73)
    blocked_suffixes = (".internal", ".local", ".localhost")
    if hostname == "localhost" or hostname.endswith(blocked_suffixes):
        raise ValueError(f"Hostname '{hostname}' is not allowed.")

    # Check IP literals directly
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_loopback or addr.is_private or addr.is_reserved or addr.is_link_local:
            raise ValueError(f"Private/loopback addresses are not allowed: {hostname}")
        return True
    except ValueError as e:
        if "Private" in str(e) or "loopback" in str(e) or "not allowed" in str(e):
            raise
        # hostname is not an IP literal — resolve it via DNS

    # Resolve DNS and check all resulting IPs (#73)
    try:
        addrinfo = socket.getaddrinfo(hostname, parsed.port or 443)
        for family, type_, proto, canonname, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(
                    f"Hostname '{hostname}' resolves to private/loopback address {sockaddr[0]}"
                )
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    return True


# ── CSRF token helpers (#39) ──


def _generate_csrf_token(sess) -> str:
    """Return the session's CSRF token, generating one only if it doesn't exist yet.

    Previously this generated a new token on every call, which invalidated
    tokens in other open tabs/forms (#2).  Now the token is stable for the
    lifetime of the session.
    """
    if "_csrf_token" not in sess:
        sess["_csrf_token"] = secrets.token_urlsafe(32)
    return sess["_csrf_token"]

def _verify_csrf(sess, submitted_token: str) -> str | None:
    """Verify a CSRF token submitted via form matches the session token.

    Returns None if valid, or an error message string if invalid.
    Called by all dashboard POST handlers to prevent cross-site request forgery (#39).

    Usage in handlers:
        def my_handler(req, sess, _csrf_token: str = "", ...):
            if err := _verify_csrf(sess, _csrf_token):
                return P(err, style="color:#f87171;")
    """
    expected = sess.get("_csrf_token", "")
    if not expected:
        return "Missing CSRF session. Please refresh and try again."
    if not submitted_token or not secrets.compare_digest(submitted_token, expected):
        return "Invalid CSRF token. Please refresh and try again."
    return None


GITHUB_URL = "https://github.com/tendlyeu/SafeClaw"
DOCS_URL = "/docs"

bware = Beforeware(
    user_auth_before,
    skip=[r'/favicon\.ico', r'/static/.*', r'.*\.css', r'.*\.js', '/login', '/auth/callback', '/logout', '/', '/docs'],
)

app, rt = fast_app(
    pico=False,
    static_path="static",
    before=bware,
    secret_key=os.environ.get("SAFECLAW_SECRET_KEY", secrets.token_hex(32)),
    hdrs=(
        Link(rel="stylesheet", href="/style.css"),
        Link(rel="icon", href="/favicon.ico", type="image/x-icon"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Meta(name="description", content="SafeClaw — Neurosymbolic governance layer for autonomous AI agents"),
    ),
)


# ── Components ──

def Nav(user=None):
    auth_link = (
        Li(A("Dashboard", href="/dashboard")) if user
        else Li(A("Sign In", href="/login", cls="btn btn-primary btn-sm"))
    )
    return Header(
        Div(
            Div(
                Span("🛡️", cls="logo-icon"),
                Span("SafeClaw"),
                cls="nav-logo",
            ),
            Ul(
                Li(A("Features", href="/#features")),
                Li(A("How It Works", href="/#how-it-works")),
                Li(A("Architecture", href="/#architecture")),
                Li(A("Docs", href="/docs")),
                Li(A("GitHub", href=GITHUB_URL, target="_blank", rel="noopener noreferrer")),
                auth_link,
                cls="nav-links", id="nav-links",
            ),
            Button("☰", cls="nav-mobile-toggle",
                   onclick="document.getElementById('nav-links').classList.toggle('open')"),
            cls="nav-inner container",
        ),
        cls="nav",
    )


def Hero():
    return Section(
        Div(
            H1("Neurosymbolic Governance for AI Agents"),
            P("Gate every action through formal ontological constraints. "
              "Audit every decision. Never let your agent go astray."),
            Div(
                A("View on GitHub", href=GITHUB_URL, target="_blank",
                  rel="noopener noreferrer", cls="btn btn-primary"),
                A("Quick Start", href="#quickstart", cls="btn btn-secondary"),
                cls="hero-buttons",
            ),
            cls="container",
        ),
        cls="hero",
    )


def Features():
    cards = [
        ("🧠", "OWL + SHACL Validation",
         "Formal ontology constraints, not just pattern matching. "
         "Your agent's actions are validated against a real knowledge graph."),
        ("🔗", "9-Step Pipeline",
         "Every tool call passes through classification, role checks, SHACL, "
         "policy, preferences, dependencies, and rate limits."),
        ("📋", "Full Audit Trail",
         "Append-only JSONL logs with machine-readable ontological justification "
         "for every allow and block decision."),
        ("👥", "Multi-Agent Governance",
         "Kill switches, delegation detection, role-based access control, "
         "and temporary scoped permissions."),
        ("💉", "Context Injection",
         "The knowledge graph feeds live constraints directly into "
         "the LLM's system prompt for better self-regulation."),
        ("🔌", "Zero Core Modifications",
         "Pure plugin architecture. OpenClaw updates independently. "
         "No fork drift, no vendor lock-in."),
    ]
    return Section(
        Div(
            H2("Key Features", cls="section-title"),
            P("Everything you need to keep autonomous agents safe", cls="section-subtitle"),
            Div(
                *[Div(
                    Span(icon, cls="feature-icon"),
                    H3(title),
                    P(desc),
                    cls="feature-card",
                ) for icon, title, desc in cards],
                cls="features-grid",
            ),
            cls="container",
        ),
        cls="section", id="features",
    )


def HowItWorks():
    return Section(
        Div(
            H2("How It Works", cls="section-title"),
            P("Three steps between intent and execution", cls="section-subtitle"),
            Div(
                Div(
                    Div("1", cls="step-number"),
                    H3("Agent Proposes"),
                    P("The AI agent requests a tool call — file write, shell command, API call."),
                    cls="step",
                ),
                Div("→", cls="step-arrow"),
                Div(
                    Div("2", cls="step-number"),
                    H3("SafeClaw Validates"),
                    P("The request passes through 9 constraint checks against the OWL ontology."),
                    cls="step",
                ),
                Div("→", cls="step-arrow"),
                Div(
                    Div("3", cls="step-number"),
                    H3("Allow or Block"),
                    P("SafeClaw returns a decision with a formal, auditable justification."),
                    cls="step",
                ),
                cls="steps",
            ),
            cls="container",
        ),
        cls="section", id="how-it-works",
    )


def TerminalDemo():
    lines = [
        (None, Span("$ ", cls="prompt"), Span("safeclaw serve", cls="cmd")),
        ("info", "SafeClaw engine ready on :8420"),
        None,  # blank line
        ("timestamp", "[14:32:01] ", "label-classify", "EVALUATE ",
         "cmd", 'exec("rm -rf /tmp/important")'),
        ("label-classify", "  → Classified: DeleteFile (CriticalRisk, irreversible)"),
        ("label-shacl", "  → SHACL: ForbiddenCommandShape violated"),
        ("blocked", '  → BLOCKED: "Recursive deletion of critical paths is prohibited"'),
        None,  # blank line
        ("timestamp", "[14:32:05] ", "label-classify", "EVALUATE ",
         "cmd", 'exec("git status")'),
        ("info", "  → Classified: ShellAction (LowRisk, reversible)"),
        ("info", "  → All 9 checks passed"),
        ("allowed", "  → ALLOWED"),
    ]

    rendered = []
    for i, line in enumerate(lines):
        is_last = i == len(lines) - 1
        extra_cls = " terminal-cursor" if is_last else ""
        if line is None:
            rendered.append(Div(NotStr("&nbsp;"), cls=f"terminal-line{extra_cls}"))
        elif len(line) == 2 and isinstance(line[0], str):
            cls_name, text = line
            rendered.append(Div(Span(text, cls=cls_name), cls=f"terminal-line{extra_cls}"))
        elif len(line) == 3 and line[0] is None:
            # prompt + cmd
            rendered.append(Div(line[1], line[2], cls=f"terminal-line{extra_cls}"))
        elif len(line) == 6:
            # timestamp + classify + cmd
            rendered.append(Div(
                Span(line[1], cls=line[0]),
                Span(line[3], cls=line[2]),
                Span(line[5], cls=line[4]),
                cls=f"terminal-line{extra_cls}",
            ))
        else:
            rendered.append(Div(str(line), cls=f"terminal-line{extra_cls}"))

    return Section(
        Div(
            H2("See It In Action", cls="section-title"),
            P("SafeClaw evaluating tool calls in real time", cls="section-subtitle"),
            Div(
                Div(
                    Span(cls="terminal-dot red"),
                    Span(cls="terminal-dot yellow"),
                    Span(cls="terminal-dot green"),
                    Span("safeclaw — terminal", cls="terminal-title"),
                    cls="terminal-header",
                ),
                Div(*rendered, cls="terminal-body"),
                cls="terminal",
            ),
            cls="container",
        ),
        cls="section",
    )


def Architecture():
    steps = [
        ("Agent\nRequest", "highlight"),
        ("Auth &\nGovernance", ""),
        ("Action\nClassifier", "warn"),
        ("Role\nAccess", ""),
        ("SHACL\nValidation", "warn"),
        ("Policy\nCheck", ""),
        ("Preference\nCheck", ""),
        ("Dependency\nCheck", ""),
        ("Rate\nLimits", ""),
        ("Allow /\nBlock", "ok"),
    ]
    items = []
    for i, (label, cls_extra) in enumerate(steps):
        items.append(Div(NotStr(label.replace("\n", "<br>")),
                         cls=f"pipeline-step {cls_extra}".strip()))
        if i < len(steps) - 1:
            items.append(Span("→", cls="pipeline-arrow"))

    return Section(
        Div(
            H2("The 9-Step Pipeline", cls="section-title"),
            P("Every tool call passes through these gates in order", cls="section-subtitle"),
            Div(*items, cls="pipeline"),
            cls="container",
        ),
        cls="section", id="architecture",
    )


def QuickStart():
    return Section(
        Div(
            H2("Quick Start", cls="section-title"),
            P("Get governed in under a minute", cls="section-subtitle"),
            # ── SaaS (primary) ──
            H3("Use the hosted service", cls="quickstart-heading"),
            P("Install the OpenClaw plugin and point it at our hosted service. No server setup needed.",
              cls="quickstart-desc"),
            Div(
                Div(
                    Span("# ", cls="prompt"),
                    Span("Sign up at safeclaw.eu and get your API key", cls="comment"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("npm install -g openclaw-safeclaw-plugin", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("safeclaw connect sc_your_key_here", cls="cmd"),
                ),
                cls="quickstart-terminal",
            ),
            P("That's it. ", Code("safeclaw connect"),
              " writes your key to ", Code("~/.safeclaw/config.json"),
              " and verifies the connection.", cls="quickstart-desc"),
            Div(
                Div(
                    Span("# ", cls="comment"),
                    Span("Default: https://api.safeclaw.eu/api/v1", cls="comment"),
                ),
                Div(
                    Span("# ", cls="comment"),
                    Span("No URL configuration needed", cls="comment"),
                ),
                cls="quickstart-terminal",
            ),
            # ── Self-hosted (secondary) ──
            H3("Or self-host", cls="quickstart-heading quickstart-heading-alt"),
            P("Run the SafeClaw engine on your own infrastructure.",
              cls="quickstart-desc"),
            Div(
                Div(
                    Span("$ ", cls="prompt"),
                    Span("git clone https://github.com/tendlyeu/SafeClaw.git", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("cd SafeClaw/safeclaw-service", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("python -m venv .venv && source .venv/bin/activate", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span('pip install -e ".[dev]"', cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("safeclaw init --user-id yourname", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("safeclaw serve", cls="cmd"),
                ),
                Div(
                    Span("# ", cls="comment"),
                    Span("Engine ready on http://localhost:8420", cls="comment"),
                ),
                cls="quickstart-terminal",
            ),
            cls="container",
        ),
        cls="section", id="quickstart",
    )


def Footer():
    return FooterTag(
        Div(
            P("SafeClaw — Neurosymbolic AI Governance", cls="footer-brand"),
            Ul(
                Li(A("GitHub", href=GITHUB_URL, target="_blank", rel="noopener noreferrer")),
                Li(A("Documentation", href=DOCS_URL)),
                Li(A("MIT License", href=f"{GITHUB_URL}/blob/main/LICENSE")),
                cls="footer-links",
            ),
            P(f"© {date.today().year} SafeClaw. Built with FastHTML."),
            cls="container",
        ),
        cls="footer",
    )


# ── Docs Page ──

def DocsToc():
    """Table of contents for docs page."""
    entries = [
        ("overview", "Overview"),
        ("hooks", "How SafeClaw Controls OpenClaw"),
        ("ontology", "The Ontology"),
        ("pipeline", "The 9-Step Constraint Pipeline"),
        ("policies", "Built-in Policies"),
        ("roles", "Roles & Permissions"),
        ("preferences", "User Preferences"),
        ("mistral", "How Mistral AI Enhances SafeClaw"),
        ("context", "Context Injection"),
        ("audit", "Audit Trail"),
        ("messages", "Message Governance"),
        ("errors", "Error Handling"),
        ("cli-diagnostics", "CLI & TUI"),
        ("events", "Real-Time Events (SSE)"),
        ("dashboard", "Admin Dashboard"),
        ("user-dashboard", "User Dashboard"),
        ("demos", "Demonstration Flows"),
        ("api-reference", "API Reference"),
        ("config", "Configuration Reference"),
        ("saas", "SaaS Onboarding"),
    ]
    return Div(
        H3("Contents"),
        Ul(*[Li(A(label, href=f"#doc-{anchor}")) for anchor, label in entries]),
        cls="docs-toc",
    )


def DocsSection(id, title, *children, level=2):
    """A docs section with anchored heading."""
    tag = H2 if level == 2 else H3
    return Section(
        tag(A(title, href=f"#doc-{id}", cls="docs-anchor"), id=f"doc-{id}",
            cls=f"docs-h{level}"),
        *children,
        cls="docs-section",
    )


def DocsPage():
    return Div(
        Div(
            DocsToc(),
            Div(
                # ── 1. Overview ──
                DocsSection("overview", "Overview",
                    P("SafeClaw is a neurosymbolic governance layer for autonomous AI agents. "
                      "It validates every tool call, message, and action against ",
                      Strong("OWL ontologies"), " and ", Strong("SHACL constraints"),
                      " before execution."),
                    P("The system has two components:"),
                    Ul(
                        Li(Strong("openclaw-safeclaw-plugin"), " — a TypeScript plugin that intercepts "
                           "OpenClaw events and forwards them to the SafeClaw service via HTTP."),
                        Li(Strong("safeclaw-service"), " — a Python FastAPI service that runs the "
                           "constraint pipeline against a knowledge graph of ontologies, policies, "
                           "and user preferences."),
                    ),
                    P("The plugin is a thin client (~275 lines) with no governance logic of its own. "
                      "All validation happens server-side, making it easy to update policies without "
                      "redeploying the agent."),
                ),

                # ── 2. How SafeClaw Controls OpenClaw ──
                DocsSection("hooks", "How SafeClaw Controls OpenClaw",
                    P("The plugin registers 6 event hooks with the OpenClaw runtime. "
                      "Each hook intercepts a specific lifecycle event:"),
                    Div(
                        Table(
                            Thead(Tr(Th("Hook"), Th("Endpoint"), Th("Purpose"), Th("Behavior"))),
                            Tbody(
                                Tr(Td(Code("before_tool_call")), Td(Code("/evaluate/tool-call")),
                                   Td("THE GATE — validates every tool call"), Td("Blocks execution on violation")),
                                Tr(Td(Code("before_agent_start")), Td(Code("/context/build")),
                                   Td("Context injection into system prompt"), Td("Prepends governance context")),
                                Tr(Td(Code("message_sending")), Td(Code("/evaluate/message")),
                                   Td("Outbound message governance"), Td("Cancels message on violation")),
                                Tr(Td(Code("after_tool_call")), Td(Code("/record/tool-result")),
                                   Td("Feedback loop for dependency tracking"), Td("Fire-and-forget")),
                                Tr(Td(Code("llm_input")), Td(Code("/log/llm-input")),
                                   Td("Audit logging of LLM inputs"), Td("Fire-and-forget")),
                                Tr(Td(Code("llm_output")), Td(Code("/log/llm-output")),
                                   Td("Audit logging of LLM outputs"), Td("Fire-and-forget")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Enforcement Modes", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Mode"), Th("Behavior"))),
                            Tbody(
                                Tr(Td(Code("enforce")), Td("Block actions that violate constraints (default)")),
                                Tr(Td(Code("warn-only")), Td("Log warnings but allow execution")),
                                Tr(Td(Code("audit-only")), Td("Log server-side only, no client-side action")),
                                Tr(Td(Code("disabled")), Td("Completely disable SafeClaw checks")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Fail Modes", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Mode"), Th("Behavior"))),
                            Tbody(
                                Tr(Td(Code("open")), Td("Allow on service failure (default). More available.")),
                                Tr(Td(Code("closed")), Td("Block on service unavailability. Safer.")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 3. The Ontology ──
                DocsSection("ontology", "The Ontology",
                    P(Strong("OWL"), " (Web Ontology Language) defines a formal class hierarchy of actions "
                      "your agent can take. ", Strong("SHACL"), " (Shapes Constraint Language) defines "
                      "structural constraints that validate the shape of each action's data."),
                    P("Together, they give SafeClaw a machine-readable understanding of what each action "
                      "means, how risky it is, and what constraints apply — not just pattern matching, "
                      "but genuine semantic reasoning."),
                    P("At startup, SafeClaw pre-computes the full ", Code("rdfs:subClassOf"),
                      " hierarchy via pure-Python SPARQL traversal (no Java required). "
                      "This enables hierarchy-aware policy checking — blocking ",
                      Code("ShellAction"), " automatically blocks all subclasses like ",
                      Code("GitPush"), " and ", Code("ForcePush"), ". Custom ontology extensions "
                      "inherit risk levels and constraints without Python code changes."),
                    H3("Action Class Hierarchy", cls="docs-h3"),
                    Div(
                        Pre(
                            "Action\n"
                            "├── FileAction\n"
                            "│   ├── ReadFile          (Low, reversible, LocalOnly)\n"
                            "│   ├── WriteFile         (Medium, reversible, LocalOnly)\n"
                            "│   ├── EditFile          (Medium, reversible, LocalOnly)\n"
                            "│   ├── DeleteFile        (Critical, irreversible, LocalOnly)\n"
                            "│   ├── ListFiles\n"
                            "│   └── SearchFiles\n"
                            "├── ShellAction\n"
                            "│   ├── ExecuteCommand    (High, reversible, LocalOnly)\n"
                            "│   ├── GitCommit         (Medium, reversible, LocalOnly)\n"
                            "│   ├── GitPush           (High, irreversible, SharedState)\n"
                            "│   ├── ForcePush         (Critical, irreversible, SharedState)\n"
                            "│   ├── GitResetHard      (Critical, irreversible, LocalOnly)\n"
                            "│   ├── RunTests          (Low, reversible, LocalOnly)\n"
                            "│   ├── DockerCleanup     (High, irreversible, LocalOnly)\n"
                            "│   └── PackagePublish    (Critical, irreversible, ExternalWorld)\n"
                            "├── NetworkAction\n"
                            "│   ├── WebFetch          (Medium, reversible, ExternalWorld)\n"
                            "│   ├── WebSearch         (Low, reversible, ExternalWorld)\n"
                            "│   └── NetworkRequest\n"
                            "├── MessageAction\n"
                            "│   └── SendMessage       (High, irreversible, ExternalWorld)\n"
                            "└── BrowserAction         (Medium, reversible, ExternalWorld)",
                            cls="docs-pre",
                        ),
                    ),
                    H3("Risk Levels", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Level"), Th("Meaning"), Th("Examples"))),
                            Tbody(
                                Tr(Td(Span("LowRisk", cls="risk-low")),
                                   Td("Safe, read-only or easily undone"),
                                   Td("ReadFile, RunTests, WebSearch")),
                                Tr(Td(Span("MediumRisk", cls="risk-medium")),
                                   Td("Modifies local state but reversible"),
                                   Td("WriteFile, EditFile, GitCommit, WebFetch")),
                                Tr(Td(Span("HighRisk", cls="risk-high")),
                                   Td("Affects shared state or hard to reverse"),
                                   Td("ExecuteCommand, GitPush, SendMessage")),
                                Tr(Td(Span("CriticalRisk", cls="risk-critical")),
                                   Td("Irreversible or affects external systems"),
                                   Td("DeleteFile, ForcePush, GitResetHard, PackagePublish")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Scopes", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Scope"), Th("Meaning"))),
                            Tbody(
                                Tr(Td(Code("LocalOnly")), Td("Affects only the local filesystem")),
                                Tr(Td(Code("SharedState")), Td("Affects shared resources (e.g., git remotes)")),
                                Tr(Td(Code("ExternalWorld")), Td("Reaches external systems (APIs, messages, network)")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 4. The 9-Step Pipeline ──
                DocsSection("pipeline", "The 9-Step Constraint Pipeline",
                    P("Every tool call passes through these gates in order. "
                      "Execution blocks at the first violation."),
                    Div(
                        _pipeline_step("1", "Agent Governance",
                            "Token authentication, kill switch check, delegation bypass detection.",
                            "Token invalid", "Agent killed", "Delegation bypass detected"),
                        _pipeline_step("2", "Action Classification",
                            "Maps tool name + parameters to an ontology class. "
                            "Assigns risk level, reversibility, and scope. "
                            "Covers all common tool variants: read, write, edit, delete, "
                            "remove, unlink, trash, shell, and more.",
                            "Unknown tool type", "Unclassifiable action"),
                        _pipeline_step("3", "Role-Based Access Control",
                            "Checks if the agent's role allows the classified action and resource path. "
                            "Resource paths are extracted from multiple param key variants "
                            "(file_path, path, filepath, dest, target, source, and more). "
                            "Uses ontology hierarchy: denying a parent class denies all subclasses. "
                            "Temporary permissions are checked first.",
                            "Role 'researcher' does not allow action 'WriteFile'",
                            "Access to /secrets/** denied"),
                        _pipeline_step("4", "SHACL Validation",
                            "Validates the action's RDF graph against shape constraints from the shapes/ directory.",
                            "ForbiddenCommandShape violated",
                            "CriticalPathShape violated"),
                        _pipeline_step("5", "Policy Check",
                            "Evaluates against policy rules from the knowledge graph (prohibitions, obligations). "
                            "Hierarchy-aware: blocking a parent class blocks all subclasses.",
                            "Environment files may contain secrets",
                            "Force push can destroy shared history"),
                        _pipeline_step("6", "Preference Check",
                            "User-specific preferences like 'confirm before delete' or 'never modify paths'.",
                            "User requires confirmation before delete",
                            "Path matches neverModifyPaths"),
                        _pipeline_step("7", "Dependency Check",
                            "Validates prerequisites are met. E.g., tests must pass before git push.",
                            "RunTests must succeed before GitPush"),
                        _pipeline_step("8", "Temporal + Rate Limits",
                            "Time-based constraints and per-session rate limiting.",
                            "Action not permitted at this time",
                            "Rate limit exceeded: 100 actions/hour"),
                        _pipeline_step("9", "Derived Rules",
                            "Combined rules from multiple constraints. May require user confirmation "
                            "rather than a hard block.",
                            "Cumulative risk threshold exceeded",
                            "Transitive prohibition applies"),
                    ),
                ),

                # ── 5. Built-in Policies ──
                DocsSection("policies", "Built-in Policies",
                    P("Default prohibitions and obligations defined in the ontology:"),
                    H3("Prohibitions", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Policy"), Th("Type"), Th("Pattern"), Th("Reason"))),
                            Tbody(
                                Tr(Td(Code("NoEnvFiles")), Td("Path"),
                                   Td(Code(".*\\.env.*")),
                                   Td("Environment files may contain secrets")),
                                Tr(Td(Code("NoCredentialFiles")), Td("Path"),
                                   Td(Code(".*(credentials|secrets|tokens).*")),
                                   Td("Credential files contain sensitive data")),
                                Tr(Td(Code("NoForcePush")), Td("Command"),
                                   Td(Code("git push.*--force")),
                                   Td("Force push can destroy shared history")),
                                Tr(Td(Code("NoRootDelete")), Td("Command"),
                                   Td(Code("rm\\s+-rf\\s+/")),
                                   Td("Recursive deletion of root paths is prohibited")),
                                Tr(Td(Code("NoResetHard")), Td("Command"),
                                   Td(Code("git reset --hard")),
                                   Td("Hard reset can destroy uncommitted work")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Obligations", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Policy"), Th("Action"), Th("Requires"), Th("Reason"))),
                            Tbody(
                                Tr(Td(Code("TestBeforePush")), Td("GitPush"),
                                   Td("RunTests (must succeed first)"),
                                   Td("All pushes must pass tests")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 6. Roles & Permissions ──
                DocsSection("roles", "Roles & Permissions",
                    P("SafeClaw ships with three roles. Custom roles can be defined in Turtle files."),
                    Div(
                        Table(
                            Thead(Tr(Th("Role"), Th("Autonomy"), Th("Enforcement"),
                                     Th("Allowed Actions"), Th("Denied Actions"), Th("Denied Paths"))),
                            Tbody(
                                Tr(Td(Strong("Admin")), Td("full"), Td("warn-only"),
                                   Td("All"), Td("None"), Td("None")),
                                Tr(Td(Strong("Developer")), Td("moderate"), Td("enforce"),
                                   Td("All (except denied)"),
                                   Td("ForcePush, DeleteFile, GitResetHard"),
                                   Td(Code("/secrets/**"), ", ", Code("/etc/**"))),
                                Tr(Td(Strong("Researcher")), Td("supervised"), Td("enforce"),
                                   Td("ReadFile, ListFiles, SearchFiles"),
                                   Td("WriteFile, EditFile, DeleteFile, GitPush, ForcePush, ShellAction, SendMessage"),
                                   Td("N/A")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 7. User Preferences ──
                DocsSection("preferences", "User Preferences",
                    P("Per-user preferences are stored as RDF triples and loaded from ",
                      Code("~/.safeclaw/"), " or the ontology's ", Code("users/"), " directory."),
                    H3("Safety Preferences", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Property"), Th("Type"), Th("Default"), Th("Effect"))),
                            Tbody(
                                Tr(Td(Code("autonomyLevel")), Td("string"), Td("moderate"),
                                   Td("Controls agent independence: full | high | moderate | cautious | supervised")),
                                Tr(Td(Code("confirmBeforeDelete")), Td("boolean"), Td("true"),
                                   Td("Require confirmation before any delete action")),
                                Tr(Td(Code("confirmBeforePush")), Td("boolean"), Td("true"),
                                   Td("Require confirmation before git push")),
                                Tr(Td(Code("confirmBeforeSend")), Td("boolean"), Td("true"),
                                   Td("Require confirmation before sending messages")),
                                Tr(Td(Code("neverModifyPaths")), Td("string"), Td("(none)"),
                                   Td("Glob patterns for paths the agent must never modify")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Coding Preferences", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Property"), Th("Type"), Th("Effect"))),
                            Tbody(
                                Tr(Td(Code("preferredLanguage")), Td("string"),
                                   Td("Programming language preference for agent suggestions")),
                                Tr(Td(Code("preferredTestFramework")), Td("string"),
                                   Td("Testing framework preference")),
                                Tr(Td(Code("maxFilesPerCommit")), Td("integer"),
                                   Td("Maximum files allowed per commit")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Communication Preferences", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Property"), Th("Type"), Th("Effect"))),
                            Tbody(
                                Tr(Td(Code("toneOfVoice")), Td("string"),
                                   Td("Communication tone/style preference")),
                                Tr(Td(Code("maxMessageLength")), Td("integer"),
                                   Td("Maximum message length constraint")),
                                Tr(Td(Code("neverContactList")), Td("string"),
                                   Td("Email/contact patterns to never contact")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 8. How Mistral AI Enhances SafeClaw ──
                DocsSection("mistral", "How Mistral AI Enhances SafeClaw",
                    P("SafeClaw includes an optional LLM layer powered by Mistral AI. "
                      "It is activated by setting ", Code("SAFECLAW_MISTRAL_API_KEY"), ". "
                      "This layer is ", Strong("purely passive and advisory"),
                      " — it never blocks the constraint pipeline."),
                    Div(
                        Table(
                            Thead(Tr(Th("Component"), Th("When"), Th("Purpose"))),
                            Tbody(
                                Tr(Td(Strong("Security Reviewer")),
                                   Td("After an action is allowed by symbolic checks"),
                                   Td("Background review for semantic risks: obfuscation, "
                                      "multi-step evasion chains, encoded payloads, "
                                      "script injection patterns")),
                                Tr(Td(Strong("Classification Observer")),
                                   Td("When action classifier falls back to generic 'Action'"),
                                   Td("Suggests improved ontology classifications for unknown tools — "
                                      "logged to classification_suggestions.jsonl")),
                                Tr(Td(Strong("Decision Explainer")),
                                   Td("When a constraint violation occurs"),
                                   Td("Generates plain-English explanations of why "
                                      "an action was blocked")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    P("The Security Reviewer specifically watches for:", cls="docs-detail-label"),
                    Ul(
                        Li("Base64/hex-encoded payloads hiding malicious commands"),
                        Li("Multi-step evasion chains (e.g., write script then execute)"),
                        Li("URL-based payload delivery (", Code("curl | sh"), " patterns)"),
                        Li("Flag reordering and command aliases"),
                        Li("Environment variable manipulation"),
                        cls="docs-list",
                    ),
                ),

                # ── 9. Context Injection ──
                DocsSection("context", "Context Injection",
                    P("Before each agent session starts, SafeClaw injects governance context "
                      "into the agent's system prompt via the ",
                      Code("before_agent_start"), " hook. This gives the LLM awareness of its "
                      "constraints before it even proposes an action."),
                    H3("Injected Context Includes", cls="docs-h3"),
                    Ul(
                        Li(Strong("Active user preferences"), " — autonomy level, confirmation requirements, "
                           "forbidden paths"),
                        Li(Strong("Active domain policies"), " — summarized constraints with reasoning"),
                        Li(Strong("Recent violations"), " — last 5 blocked actions and reasons, "
                           "so the agent avoids retrying the same approach"),
                        Li(Strong("Session history"), " — last 10 actions with outcomes, files modified, "
                           "and violation summary"),
                        Li(Strong("Agent role info"), " — role name, autonomy level, denied action classes"),
                        cls="docs-list",
                    ),
                    P("This context injection improves agent self-regulation: the LLM learns what's "
                      "prohibited and adjusts its behavior, reducing the number of blocked actions over "
                      "the course of a session."),
                ),

                # ── 10. Audit Trail ──
                DocsSection("audit", "Audit Trail",
                    P("Every decision — allow or block — is recorded as a ", Code("DecisionRecord"),
                      " in append-only JSONL files at ", Code("~/.safeclaw/audit/"), "."),
                    H3("DecisionRecord Structure", cls="docs-h3"),
                    Div(
                        Pre(
                            "{\n"
                            '  "id": "uuid",\n'
                            '  "timestamp": "ISO-8601",\n'
                            '  "session_id": "...",\n'
                            '  "user_id": "...",\n'
                            '  "agent_id": "...",\n'
                            '  "action": {\n'
                            '    "tool_name": "write_file",\n'
                            '    "params": { ... },\n'
                            '    "ontology_class": "WriteFile",\n'
                            '    "risk_level": "MediumRisk",\n'
                            '    "is_reversible": true,\n'
                            '    "affects_scope": "LocalOnly"\n'
                            '  },\n'
                            '  "decision": "allowed",\n'
                            '  "justification": {\n'
                            '    "constraints_checked": [\n'
                            '      { "constraint_uri": "...",\n'
                            '        "constraint_type": "...",\n'
                            '        "result": "satisfied",\n'
                            '        "reason": "..." }\n'
                            '    ],\n'
                            '    "preferences_applied": [ ... ],\n'
                            '    "elapsed_ms": 12.3\n'
                            '  }\n'
                            '}',
                            cls="docs-pre",
                        ),
                    ),
                    P("The dashboard at ", Code("/admin"), " provides a web interface for browsing "
                      "audit logs, viewing decision history, and managing the system."),
                ),

                # ── 11. Message Governance ──
                DocsSection("messages", "Message Governance",
                    P("Outbound messages are governed by the ", Code("message_sending"),
                      " hook with three checks:"),
                    H3("1. Never-Contact List", cls="docs-h3"),
                    P("Recipients on the never-contact list (configured via ",
                      Code("neverContactList"), " preference) are unconditionally blocked."),
                    H3("2. Sensitive Data Detection", cls="docs-h3"),
                    P("Message content is scanned against 7 regex patterns:"),
                    Div(
                        Table(
                            Thead(Tr(Th("Pattern"), Th("Detects"))),
                            Tbody(
                                Tr(Td("Base64 strings (40+ chars)"), Td("Encoded secrets")),
                                Tr(Td(Code("api_key|secret_key|access_token|auth_token")),
                                   Td("API keys and tokens")),
                                Tr(Td(Code("password|passwd|pwd")), Td("Passwords")),
                                Tr(Td(Code("ghp_|gho_|ghu_|ghs_|ghr_")), Td("GitHub tokens")),
                                Tr(Td(Code("sk-...")), Td("OpenAI / Stripe secret keys")),
                                Tr(Td(Code("AKIA...")), Td("AWS Access Key IDs")),
                                Tr(Td(Code("-----BEGIN PRIVATE KEY-----")),
                                   Td("PEM private keys")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("3. Rate Limiting", cls="docs-h3"),
                    P("Default: 50 messages per session per hour."),
                ),

                # ── 12. Error Handling ──
                DocsSection("errors", "Error Handling",
                    P("The SafeClaw service returns structured error responses with machine-readable "
                      "codes and human-readable hints for every failure:"),
                    Div(
                        Pre(
                            '{\n'
                            '  "error": "ENGINE_NOT_READY",\n'
                            '  "detail": "Engine not initialized — the service is still starting up.",\n'
                            '  "hint": "Wait a moment and retry, or check service logs."\n'
                            '}',
                            cls="docs-pre",
                        ),
                    ),
                    H3("Error Codes", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Code"), Th("HTTP"), Th("Meaning"))),
                            Tbody(
                                Tr(Td(Code("ENGINE_NOT_READY")), Td("503"),
                                   Td("Service is starting up, engine not yet initialized")),
                                Tr(Td(Code("INTERNAL_ERROR")), Td("500"),
                                   Td("Unhandled exception — check service logs")),
                                Tr(Td(Code("INVALID_REQUEST")), Td("400"),
                                   Td("Malformed request body or missing fields")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Plugin Error Handling", cls="docs-h3"),
                    P("The TypeScript plugin (v0.1.3+) parses structured errors and provides "
                      "context-specific warnings:"),
                    Ul(
                        Li(Strong("Timeout"), " — logs timeout duration and service URL"),
                        Li(Strong("Connection refused"), " — suggests checking if the service is running"),
                        Li(Strong("HTTP errors"), " — parses and displays the ", Code("detail"),
                           " and ", Code("hint"), " fields from the response"),
                        Li(Strong("Fail-closed blocks"), " — include the service URL in the block reason "
                           "for easier debugging"),
                        cls="docs-list",
                    ),
                ),

                # ── 13. CLI & TUI ──
                DocsSection("cli-diagnostics", "CLI & TUI",
                    P("SafeClaw provides CLI commands and an interactive terminal UI "
                      "for managing the service, diagnosing issues, and controlling OpenClaw."),

                    H3("safeclaw tui", cls="docs-h3"),
                    P("Opens the interactive settings TUI. The ", Strong("Status"),
                      " tab shows live health for both SafeClaw and the OpenClaw daemon:"),
                    Div(
                        Pre(
                            "  Service      ● Connected (localhost:8420)\n"
                            "  OpenClaw     ● Running\n"
                            "  Enforcement  enforce\n"
                            "  Fail Mode    closed\n"
                            "  Enabled      ON\n"
                            "\n"
                            "  Service v0.1.0\n"
                            "  Last check: 14:32:05\n"
                            "\n"
                            "  Press r to restart OpenClaw daemon",
                            cls="docs-pre",
                        ),
                    ),
                    P("The status auto-refreshes every 10 seconds. Press ",
                      Code("r"), " to restart the OpenClaw daemon directly from the TUI."),

                    H3("safeclaw connect", cls="docs-h3"),
                    P("Links your local agent to the SafeClaw service by writing "
                      "your API key to ", Code("~/.safeclaw/config.json"), ":"),
                    Div(
                        Pre(
                            "$ safeclaw connect sc_abc123...\n"
                            "Connected! Your API key has been saved to ~/.safeclaw/config.json",
                            cls="docs-pre",
                        ),
                    ),
                    P("The config file is created with ", Code("0600"),
                      " permissions (owner read/write only). "
                      "If a config file already exists, only the ",
                      Code("remote.apiKey"), " and ", Code("remote.serviceUrl"),
                      " fields are updated — other settings are preserved."),
                    P("By default the service URL is set to ",
                      Code("https://api.safeclaw.eu/api/v1"),
                      ". To connect to a self-hosted instance:"),
                    Div(
                        Pre(
                            "$ safeclaw connect sc_abc123... "
                            "--service-url http://localhost:8420/api/v1",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw restart-openclaw", cls="docs-h3"),
                    P("Restarts the OpenClaw daemon from the command line without opening the TUI:"),
                    Div(
                        Pre(
                            "$ safeclaw restart-openclaw\n"
                            "OpenClaw daemon restarted successfully.",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw status check", cls="docs-h3"),
                    P("Pings the running service and displays component-level health:"),
                    Div(
                        Pre(
                            "$ safeclaw status check\n"
                            "Service: ok\n"
                            "Version: 0.1.0\n"
                            "Engine ready: True\n"
                            "Uptime: 1234s\n"
                            "\n"
                            "┌───────────────┬────────────────────────┐\n"
                            "│ Component     │ Detail                 │\n"
                            "├───────────────┼────────────────────────┤\n"
                            "│ Knowledge Graph│ 847 triples           │\n"
                            "│ LLM           │ not configured         │\n"
                            "│ Sessions      │ 3 active               │\n"
                            "│ Agents        │ 2 registered, 1 active │\n"
                            "└───────────────┴────────────────────────┘",
                            cls="docs-pre",
                        ),
                    ),
                    P("If the service is not running, it shows a clear error with the suggested fix."),

                    H3("safeclaw status diagnose", cls="docs-h3"),
                    P("Runs offline checks without requiring the service to be running:"),
                    Ul(
                        Li("Config file at ", Code("~/.safeclaw/config.json")),
                        Li("Ontology ", Code(".ttl"), " files present"),
                        Li("Audit directory exists"),
                        Li("Mistral API key set (optional)"),
                        cls="docs-list",
                    ),
                    P("Each check prints ", Span("OK", cls="risk-low"), " or ",
                      Span("ISSUE", cls="risk-critical"), " with remediation hints."),

                    H3("safeclaw serve", cls="docs-h3"),
                    P("Starts the SafeClaw service:"),
                    Div(
                        Pre(
                            "$ safeclaw serve\n"
                            "$ safeclaw serve --host 0.0.0.0 --port 8420 --reload",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw init", cls="docs-h3"),
                    P("Generates a default ", Code("~/.safeclaw/config.json"), " with all sections:"),
                    Div(
                        Pre(
                            "$ safeclaw init --user-id myname\n"
                            "$ safeclaw init --user-id myname --mode remote "
                            "--service-url http://localhost:8420/api/v1",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw audit", cls="docs-h3"),
                    P("View and query audit records:"),
                    Div(
                        Pre(
                            "$ safeclaw audit show --last 20\n"
                            "$ safeclaw audit show --blocked\n"
                            "$ safeclaw audit report <session-id> --format markdown\n"
                            "$ safeclaw audit stats --last 100\n"
                            "$ safeclaw audit compliance\n"
                            "$ safeclaw audit explain <audit-id>",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw policy", cls="docs-h3"),
                    P("Manage governance policies:"),
                    Div(
                        Pre(
                            "$ safeclaw policy list\n"
                            "$ safeclaw policy add NoSecrets --type prohibition "
                            "--reason \"Secrets must not be committed\" "
                            "--path-pattern \".*\\.secret.*\"\n"
                            "$ safeclaw policy remove NoSecrets\n"
                            "$ safeclaw policy add-nl \"Never allow deploys on weekends\"",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw pref", cls="docs-h3"),
                    P("View or set user preferences:"),
                    Div(
                        Pre(
                            "$ safeclaw pref show --user-id myuser\n"
                            "$ safeclaw pref set autonomyLevel cautious --user-id myuser\n"
                            "$ safeclaw pref set confirmBeforeDelete true",
                            cls="docs-pre",
                        ),
                    ),

                    H3("safeclaw llm", cls="docs-h3"),
                    P("Manage LLM features (requires Mistral API key):"),
                    Div(
                        Pre(
                            "$ safeclaw llm suggestions\n"
                            "$ safeclaw llm findings",
                            cls="docs-pre",
                        ),
                    ),
                ),

                # ── 14. Real-Time Events (SSE) ──
                DocsSection("events", "Real-Time Events (SSE)",
                    P("SafeClaw provides a Server-Sent Events (SSE) endpoint for real-time "
                      "visibility into governance decisions. The endpoint requires admin "
                      "authentication."),
                    Div(
                        Pre(
                            "$ curl -N -H 'X-Admin-Password: yourpass' "
                            "http://localhost:8420/api/v1/events\n"
                            "\n"
                            'event: safeclaw\n'
                            'data: {"event_type":"blocked","severity":"warning",'
                            '"title":"Blocked: shell",'
                            '"detail":"[SafeClaw] Force push can destroy shared history",'
                            '"metadata":{"tool_name":"shell","ontology_class":"ForcePush"}}\n',
                            cls="docs-pre",
                        ),
                    ),
                    H3("Event Types", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Type"), Th("Severity"), Th("When"))),
                            Tbody(
                                Tr(Td(Code("blocked")), Td("warning"),
                                   Td("A tool call was blocked by the constraint pipeline")),
                                Tr(Td(Code("security_finding")), Td("warning / critical"),
                                   Td("The LLM security reviewer flagged a concern")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Event Bus Limits", cls="docs-h3"),
                    Ul(
                        Li("Max 100 concurrent SSE subscribers"),
                        Li("Max 100 queued events per subscriber (oldest dropped on overflow)"),
                        Li("No external dependencies — uses ", Code("asyncio.Queue"), " internally"),
                        cls="docs-list",
                    ),
                ),

                # ── 15. Admin Dashboard ──
                DocsSection("dashboard", "Admin Dashboard",
                    P("The admin dashboard is available at ", Code("/admin"),
                      " and provides a web interface for monitoring and managing SafeClaw."),
                    H3("Live Features", cls="docs-h3"),
                    Ul(
                        Li(Strong("Toast notifications"), " — real-time pop-up alerts when actions "
                           "are blocked or security findings are detected, powered by the SSE event stream"),
                        Li(Strong("Auto-refresh"), " — home page stats update every 5 seconds via HTMX"),
                        Li(Strong("Agent monitoring"), " — cards showing registered and active agent counts"),
                        cls="docs-list",
                    ),
                    H3("Audit Log Detail", cls="docs-h3"),
                    P("Clicking 'Details' on any audit record expands to show:"),
                    Ul(
                        Li("Action parameters (truncated to 500 chars)"),
                        Li("Constraint checks with type, result, and reason"),
                        Li("Preferences applied"),
                        Li("Session action history (last 5 entries)"),
                        Li("Block reason for early-exit blocks (agent governance, role checks)"),
                        cls="docs-list",
                    ),
                    H3("Dashboard Pages", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Page"), Th("Purpose"))),
                            Tbody(
                                Tr(Td(Strong("Home")), Td("System health, decision stats, recent activity")),
                                Tr(Td(Strong("Audit")), Td("Filterable audit log with detail expansion")),
                                Tr(Td(Strong("Agents")), Td("Agent management — register, kill, revive")),
                                Tr(Td(Strong("Settings")), Td("Configuration overview, ontology reload")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 16. User Dashboard ──
                DocsSection("user-dashboard", "User Dashboard",
                    P("The user dashboard at ", Code("/dashboard"),
                      " provides a self-service web interface for managing your SafeClaw integration. "
                      "Sign in with GitHub OAuth to access it."),
                    H3("Authentication Flow", cls="docs-h3"),
                    Ul(
                        Li("Click ", Strong("Sign In"), " in the nav bar to start GitHub OAuth"),
                        Li("Authorize the SafeClaw app on GitHub"),
                        Li("First-time users are redirected to the ",
                           A("onboarding wizard", href="#doc-saas"),
                           " to set preferences and get their API key"),
                        Li("Returning users go straight to ", Code("/dashboard")),
                        Li("All ", Code("/dashboard/*"), " routes are protected by Beforeware"),
                        cls="docs-list",
                    ),
                    H3("Dashboard Pages", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Page"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td(Strong("Overview")), Td(Code("/dashboard")),
                                   Td("Service health check, API key count, getting started guide")),
                                Tr(Td(Strong("API Keys")), Td(Code("/dashboard/keys")),
                                   Td("Generate and revoke API keys for service authentication")),
                                Tr(Td(Strong("Agents")), Td(Code("/dashboard/agents")),
                                   Td("View registered agents, kill/revive via service API")),
                                Tr(Td(Strong("Preferences")), Td(Code("/dashboard/prefs")),
                                   Td("Set autonomy level, confirmation rules, file limits, Mistral API key")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("API Keys", cls="docs-h3"),
                    P("API keys authenticate your agent's plugin against the SafeClaw service. "
                      "Each key has a ", Code("sc_"), " prefix and is shown only once at creation time."),
                    Ul(
                        Li(Strong("Label"), " — a human-readable name for the key"),
                        Li(Strong("Scope"), " — ", Code("full"), " (all endpoints) or ",
                           Code("evaluate"), " (evaluation endpoints only)"),
                        Li("Keys are stored as SHA-256 hashes; the raw key cannot be recovered"),
                        Li("Revoked keys are immediately invalidated"),
                        cls="docs-list",
                    ),
                    H3("Governance Preferences", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Setting"), Th("Options"), Th("Effect"))),
                            Tbody(
                                Tr(Td(Strong("Autonomy Level")), Td(Code("conservative / moderate / autonomous")),
                                   Td("Controls how strictly SafeClaw enforces constraints")),
                                Tr(Td(Strong("Confirm before delete")), Td("on / off"),
                                   Td("Require user confirmation before file deletions")),
                                Tr(Td(Strong("Confirm before push")), Td("on / off"),
                                   Td("Require user confirmation before git push")),
                                Tr(Td(Strong("Confirm before send")), Td("on / off"),
                                   Td("Require confirmation before sending messages")),
                                Tr(Td(Strong("Max files per commit")), Td("number"),
                                   Td("Limit files changed in a single commit")),
                                Tr(Td(Strong("Mistral API key")), Td("password"),
                                   Td("Your personal Mistral key for LLM-powered features")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Self-Hosting", cls="docs-h3"),
                    P("To run the landing site with user management locally:"),
                    Pre(Code(
                        "cd safeclaw-landing\n"
                        "pip install -r requirements.txt\n"
                        "export GITHUB_CLIENT_ID=your_id\n"
                        "export GITHUB_CLIENT_SECRET=your_secret\n"
                        "python main.py  # starts on port 5002"
                    )),
                    P("The SQLite database is created automatically in ", Code("~/.safeclaw-landing/safeclaw.db"), "."),
                ),

                # ── 17. Demonstration Flows ──
                DocsSection("demos", "Demonstration Flows",
                    P("These walkthroughs show what happens inside SafeClaw when an agent "
                      "attempts different actions. Each flow traces the request through the "
                      "constraint pipeline from prompt to final decision."),

                    H3("Flow 1: Blocking a File Deletion", cls="docs-h3"),
                    P(Strong("Prompt: "), "\"Delete /tmp/safeclaw-test.txt\""),
                    P(Strong("Tool Call"), " sent by the agent:"),
                    Pre(Code(
                        '{\n'
                        '  "tool": "delete",\n'
                        '  "params": { "path": "/tmp/safeclaw-test.txt" }\n'
                        '}'
                    ), cls="docs-pre"),
                    P(Strong("Classification: "), Code("DeleteFile"), " / ",
                      Code("CriticalRisk"),
                      " — the action classifier maps the ", Code("delete"),
                      " tool to the ", Code("sc:DeleteFile"), " ontology class."),
                    P(Strong("Decision: "), "The developer role does not include ",
                      Code("DeleteFile"), " in its allowed action classes. "
                      "Pipeline step 3 (Role-Based Access) blocks the call."),
                    P(Strong("Response:")),
                    Pre(Code(
                        '{\n'
                        '  "decision": "block",\n'
                        '  "reason": "Role developer does not permit DeleteFile actions",\n'
                        '  "constraintId": "role-access-check",\n'
                        '  "riskLevel": "critical",\n'
                        '  "pipelineStep": 3\n'
                        '}'
                    ), cls="docs-pre"),

                    H3("Flow 2: Blocking a Force Push", cls="docs-h3"),
                    P(Strong("Prompt: "), "\"Push my changes with --force\""),
                    P(Strong("Tool Call"), " sent by the agent:"),
                    Pre(Code(
                        '{\n'
                        '  "tool": "exec",\n'
                        '  "params": { "command": "git push --force" }\n'
                        '}'
                    ), cls="docs-pre"),
                    P(Strong("Classification: "), Code("ForcePush"), " / ",
                      Code("CriticalRisk"),
                      " — the shell-command pattern matcher recognises ",
                      Code("git push --force"), " and maps it to ", Code("sc:ForcePush"), "."),
                    P(Strong("Decision: "), "The developer role explicitly denies ",
                      Code("ForcePush"), ". Pipeline step 3 (Role-Based Access) blocks the call."),
                    P(Strong("Response:")),
                    Pre(Code(
                        '{\n'
                        '  "decision": "block",\n'
                        '  "reason": "Role developer does not permit ForcePush actions",\n'
                        '  "constraintId": "role-access-check",\n'
                        '  "riskLevel": "critical",\n'
                        '  "pipelineStep": 3\n'
                        '}'
                    ), cls="docs-pre"),

                    H3("Flow 3: Allowing a Safe Read", cls="docs-h3"),
                    P(Strong("Prompt: "), "\"Read the config file\""),
                    P(Strong("Tool Call"), " sent by the agent:"),
                    Pre(Code(
                        '{\n'
                        '  "tool": "read",\n'
                        '  "params": { "path": "./config.json" }\n'
                        '}'
                    ), cls="docs-pre"),
                    P(Strong("Classification: "), Code("ReadFile"), " / ",
                      Code("LowRisk"),
                      " — a simple read operation classified as ", Code("sc:ReadFile"), "."),
                    P(Strong("Decision: "), "All 9 pipeline steps pass. The developer role "
                      "permits ", Code("ReadFile"), ", SHACL shapes validate, no policies "
                      "or preferences restrict reading, and rate limits are within bounds."),
                    P(Strong("Response:")),
                    Pre(Code(
                        '{\n'
                        '  "decision": "allow",\n'
                        '  "reason": "All constraints satisfied",\n'
                        '  "riskLevel": "low",\n'
                        '  "pipelineStep": 9\n'
                        '}'
                    ), cls="docs-pre"),
                ),

                # ── 18. API Reference ──
                DocsSection("api-reference", "API Reference",
                    P("All endpoints are under ", Code("/api/v1"), ". "
                      "Admin endpoints require the ", Code("X-Admin-Password"),
                      " header or API key authentication."),
                    H3("Evaluation & Context", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("POST"), Td(Code("/evaluate/tool-call")),
                                   Td("Main constraint gate — validates tool calls")),
                                Tr(Td("POST"), Td(Code("/evaluate/message")),
                                   Td("Message governance (content, recipients)")),
                                Tr(Td("POST"), Td(Code("/context/build")),
                                   Td("Build governance context for agent system prompt")),
                                Tr(Td("POST"), Td(Code("/session/end")),
                                   Td("Clean up per-session state")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Recording & Logging", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("POST"), Td(Code("/record/tool-result")),
                                   Td("Record action outcomes for dependency tracking")),
                                Tr(Td("POST"), Td(Code("/log/llm-input")),
                                   Td("Audit log LLM input")),
                                Tr(Td("POST"), Td(Code("/log/llm-output")),
                                   Td("Audit log LLM output")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Audit & Reporting (admin)", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("GET"), Td(Code("/audit")),
                                   Td("Query audit records (filters: sessionId, blocked, limit)")),
                                Tr(Td("GET"), Td(Code("/audit/statistics")),
                                   Td("Aggregate audit statistics")),
                                Tr(Td("GET"), Td(Code("/audit/report/{session_id}")),
                                   Td("Generate session report (markdown/JSON/CSV)")),
                                Tr(Td("GET"), Td(Code("/audit/compliance")),
                                   Td("Generate compliance report")),
                                Tr(Td("GET"), Td(Code("/audit/{audit_id}/explain")),
                                   Td("LLM-powered decision explanation (requires Mistral)")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Ontology (admin)", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("POST"), Td(Code("/reload")),
                                   Td("Hot-reload ontologies and reinitialize checkers")),
                                Tr(Td("GET"), Td(Code("/ontology/graph")),
                                   Td("D3-compatible knowledge graph visualization data")),
                                Tr(Td("GET"), Td(Code("/ontology/search")),
                                   Td("Fuzzy search for ontology nodes")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Preferences (admin)", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("GET"), Td(Code("/preferences/{user_id}")),
                                   Td("Get user preferences")),
                                Tr(Td("POST"), Td(Code("/preferences/{user_id}")),
                                   Td("Update user preferences (writes Turtle file)")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Agent Management (admin)", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("POST"), Td(Code("/agents/register")),
                                   Td("Register a new agent with role and token")),
                                Tr(Td("GET"), Td(Code("/agents")),
                                   Td("List all registered agents with metadata")),
                                Tr(Td("POST"), Td(Code("/agents/{agent_id}/kill")),
                                   Td("Kill switch — block all actions from agent")),
                                Tr(Td("POST"), Td(Code("/agents/{agent_id}/revive")),
                                   Td("Revive a killed agent")),
                                Tr(Td("POST"), Td(Code("/agents/{agent_id}/temp-grant")),
                                   Td("Grant time-limited or task-scoped permission")),
                                Tr(Td("DELETE"), Td(Code("/agents/{agent_id}/temp-grant/{grant_id}")),
                                   Td("Revoke a temporary permission grant")),
                                Tr(Td("POST"), Td(Code("/tasks/{task_id}/complete")),
                                   Td("Mark task complete, revoke associated grants")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Health & Connection", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("GET"), Td(Code("/health")),
                                   Td("Service health (version, uptime, component status)")),
                                Tr(Td("POST"), Td(Code("/heartbeat")),
                                   Td("Plugin heartbeat with config drift detection")),
                                Tr(Td("POST"), Td(Code("/handshake")),
                                   Td("Validate API key and log connection event")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("LLM Features", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("POST"), Td(Code("/policies/compile")),
                                   Td("Compile natural language policy to Turtle (admin, requires Mistral)")),
                                Tr(Td("GET"), Td(Code("/llm/findings")),
                                   Td("Query LLM security findings")),
                                Tr(Td("GET"), Td(Code("/llm/suggestions")),
                                   Td("Get classification suggestions from observation log")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Real-Time", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Method"), Th("Path"), Th("Purpose"))),
                            Tbody(
                                Tr(Td("GET"), Td(Code("/events")),
                                   Td("SSE stream of governance events (admin)")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 19. Configuration Reference ──
                DocsSection("config", "Configuration Reference",
                    H3("Plugin Environment Variables", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Variable"), Th("Default"), Th("Description"))),
                            Tbody(
                                Tr(Td(Code("SAFECLAW_URL")),
                                   Td(Code("https://api.safeclaw.eu/api/v1")),
                                   Td("SafeClaw service URL")),
                                Tr(Td(Code("SAFECLAW_API_KEY")), Td("(none)"),
                                   Td("Bearer token for service authentication")),
                                Tr(Td(Code("SAFECLAW_TIMEOUT_MS")), Td(Code("5000")),
                                   Td("HTTP timeout for service calls (ms)")),
                                Tr(Td(Code("SAFECLAW_ENABLED")), Td(Code("true")),
                                   Td("Enable/disable the plugin")),
                                Tr(Td(Code("SAFECLAW_ENFORCEMENT")), Td(Code("enforce")),
                                   Td("Enforcement mode")),
                                Tr(Td(Code("SAFECLAW_FAIL_MODE")), Td(Code("open")),
                                   Td("Behavior on service failure")),
                                Tr(Td(Code("SAFECLAW_AGENT_ID")), Td("(none)"),
                                   Td("Agent identifier")),
                                Tr(Td(Code("SAFECLAW_AGENT_TOKEN")), Td("(none)"),
                                   Td("Agent authentication token")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Service Environment Variables", cls="docs-h3"),
                    Div(
                        Table(
                            Thead(Tr(Th("Variable"), Th("Default"), Th("Description"))),
                            Tbody(
                                Tr(Td(Code("SAFECLAW_HOST")), Td(Code("127.0.0.1")),
                                   Td("Bind address")),
                                Tr(Td(Code("SAFECLAW_PORT")), Td(Code("8420")),
                                   Td("Service port")),
                                Tr(Td(Code("SAFECLAW_DATA_DIR")), Td(Code("~/.safeclaw")),
                                   Td("Data directory")),
                                Tr(Td(Code("SAFECLAW_AUDIT_DIR")), Td(Code("~/.safeclaw/audit")),
                                   Td("Audit log directory")),
                                Tr(Td(Code("SAFECLAW_REQUIRE_AUTH")), Td(Code("false")),
                                   Td("Require API key authentication")),
                                Tr(Td(Code("SAFECLAW_LOG_LEVEL")), Td(Code("INFO")),
                                   Td("Log level")),
                                Tr(Td(Code("SAFECLAW_ADMIN_PASSWORD")), Td("(none)"),
                                   Td("Dashboard admin password")),
                                Tr(Td(Code("SAFECLAW_MISTRAL_API_KEY")), Td("(none)"),
                                   Td("Enable LLM layer (Mistral)")),
                                Tr(Td(Code("SAFECLAW_MISTRAL_MODEL")), Td(Code("mistral-small-latest")),
                                   Td("Mistral model for fast tasks")),
                                Tr(Td(Code("SAFECLAW_MISTRAL_MODEL_LARGE")), Td(Code("mistral-large-latest")),
                                   Td("Mistral model for complex tasks")),
                                Tr(Td(Code("SAFECLAW_MISTRAL_TIMEOUT_MS")), Td(Code("3000")),
                                   Td("LLM call timeout")),
                                Tr(Td(Code("SAFECLAW_CORS_ORIGIN_REGEX")),
                                   Td(Code(r"https?://localhost:\d+$")),
                                   Td("CORS allowed origin regex")),
                                Tr(Td(Code("SAFECLAW_DB_PATH")), Td("(none)"),
                                   Td("SQLite path for multi-tenant API key storage")),
                                Tr(Td(Code("SAFECLAW_LLM_SECURITY_REVIEW_ENABLED")), Td(Code("true")),
                                   Td("Enable LLM security review observer")),
                                Tr(Td(Code("SAFECLAW_LLM_CLASSIFICATION_OBSERVE")), Td(Code("true")),
                                   Td("Enable LLM classification observer")),
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                    H3("Config File (~/.safeclaw/config.json)", cls="docs-h3"),
                    P("The ", Code("safeclaw connect"), " command writes a JSON config file "
                      "that the plugin reads at startup. The ", Code("safeclaw init"),
                      " command generates a full config with all sections:"),
                    Div(
                        Pre(Code(
                            '{\n'
                            '  "enabled": true,\n'
                            '  "userId": "",\n'
                            '  "mode": "embedded | remote | hybrid",\n'
                            '  "remote": {\n'
                            '    "serviceUrl": "https://api.safeclaw.eu/api/v1",\n'
                            '    "apiKey": "sc_abc123...",\n'
                            '    "timeoutMs": 500\n'
                            '  },\n'
                            '  "hybrid": {\n'
                            '    "circuitBreaker": {\n'
                            '      "failureThreshold": 3,\n'
                            '      "resetTimeoutSec": 30,\n'
                            '      "fallbackMode": "local-only"\n'
                            '    }\n'
                            '  },\n'
                            '  "enforcement": {\n'
                            '    "mode": "enforce",\n'
                            '    "blockMessage": "[SafeClaw] Action blocked: {reason}",\n'
                            '    "maxReasonerTimeMs": 200\n'
                            '  },\n'
                            '  "contextInjection": {\n'
                            '    "enabled": true,\n'
                            '    "includePreferences": true,\n'
                            '    "includePolicies": true,\n'
                            '    "includeSessionFacts": true,\n'
                            '    "includeRecentViolations": true,\n'
                            '    "maxContextChars": 2000\n'
                            '  },\n'
                            '  "audit": {\n'
                            '    "enabled": true,\n'
                            '    "logLlmIO": true,\n'
                            '    "logAllowedActions": true,\n'
                            '    "logBlockedActions": true,\n'
                            '    "retentionDays": 90,\n'
                            '    "format": "jsonl"\n'
                            '  },\n'
                            '  "roles": {\n'
                            '    "defaultRole": "developer"\n'
                            '  }\n'
                            '}'
                        ), cls="docs-pre"),
                    ),
                    P("The ", Code("remote"), " section takes precedence over environment variables for ",
                      Code("SAFECLAW_API_KEY"), " and ", Code("SAFECLAW_URL"),
                      ". The file is created with ", Code("0600"), " permissions."),
                ),

                # ── 19. SaaS Onboarding ──
                DocsSection("saas", "SaaS Onboarding",
                    P("SafeClaw is available as a hosted service at ",
                      Code("safeclaw.eu"), ". No server setup required."),
                    H3("1. Create an account", cls="docs-h3"),
                    P("Click ", Strong("Get Started"), " on the landing page. "
                      "Sign in with your GitHub account."),
                    H3("2. Onboarding wizard", cls="docs-h3"),
                    P("First-time users are guided through a three-step wizard:"),
                    Ul(
                        Li(Strong("Step 1 — Autonomy level"), " — choose how much control "
                           "SafeClaw has (cautious, moderate, or autonomous)"),
                        Li(Strong("Step 2 — Mistral API key"), " (optional) — provide your own "
                           "Mistral API key to enable LLM-powered features such as semantic "
                           "action classification. You can skip this step and add it later from "
                           "the dashboard."),
                        Li(Strong("Step 3 — API key & connection"), " — a SafeClaw API key is "
                           "generated automatically. The wizard shows the ",
                           Code("safeclaw connect"), " command to run in your terminal."),
                        cls="docs-list",
                    ),
                    H3("3. Connect your agent", cls="docs-h3"),
                    P("Install the plugin and connect using the command shown in the wizard:"),
                    Div(
                        Pre(
                            "$ npm install -g openclaw-safeclaw-plugin\n"
                            "$ safeclaw connect sc_your_key_here",
                            cls="docs-pre",
                        ),
                    ),
                    P(Code("safeclaw connect"), " writes the key to ",
                      Code("~/.safeclaw/config.json"), " and verifies the connection to ",
                      Code("https://api.safeclaw.eu/api/v1"), ". No manual environment "
                      "variables needed."),
                    H3("4. Manage from the dashboard", cls="docs-h3"),
                    P("After onboarding, the dashboard at ", Code("safeclaw.eu/dashboard"),
                      " lets you:"),
                    Ul(
                        Li("Create and revoke API keys"),
                        Li("Set preferences (confirm before delete, max files per commit)"),
                        Li("View connected agents"),
                        Li("Add or update your Mistral API key"),
                        cls="docs-list",
                    ),
                ),

                cls="docs-content",
            ),
            cls="docs-layout container",
        ),
        cls="docs-page",
    )


def _pipeline_step(num, title, description, *example_blocks):
    """Render a single pipeline step."""
    examples = []
    if example_blocks:
        examples = [
            P("Example block reasons:", cls="docs-detail-label"),
            Ul(*[Li(Code(ex)) for ex in example_blocks], cls="docs-list"),
        ]
    return Div(
        Div(Span(num, cls="pipeline-num"), H3(title), cls="pipeline-header"),
        P(description),
        *examples,
        cls="docs-pipeline-step",
    )


# ── Routes ──

@rt
def index(sess):
    user = get_current_user(sess)
    return (
        Title("SafeClaw — Neurosymbolic Governance for AI Agents"),
        Nav(user),
        Hero(),
        Features(),
        HowItWorks(),
        TerminalDemo(),
        Architecture(),
        QuickStart(),
        Footer(),
    )


@rt("/docs")
def docs(sess):
    user = get_current_user(sess)
    return (
        Title("Documentation — SafeClaw"),
        Nav(user),
        DocsPage(),
        Footer(),
    )


# ── Auth Routes ──

@rt("/login")
def login(req, sess):
    if not github_client:
        return Titled("Login",
            P("GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET."))
    state = secrets.token_urlsafe(32)
    sess["oauth_state"] = state
    redir = redir_url(req, "/auth/callback")
    return RedirectResponse(github_client.login_link(redir, state=state), status_code=303)


@rt("/auth/callback")
def auth_callback(req, sess, code: str = "", state: str = ""):
    if not github_client or not code:
        return RedirectResponse("/", status_code=303)
    if state != sess.pop("oauth_state", ""):
        return RedirectResponse("/login", status_code=303)
    redir = redir_url(req, "/auth/callback")
    try:
        info = github_client.retr_info(code, redir)
    except Exception:
        return RedirectResponse("/login", status_code=303)
    github_id = info.get("id")
    if not github_id:
        return RedirectResponse("/login", status_code=303)
    user = upsert_user(
        github_id=github_id,
        github_login=info.get("login", ""),
        name=info.get("name", info.get("login", "")),
        avatar_url=info.get("avatar_url", ""),
        email=info.get("email", ""),
    )
    sync_admin_on_login(user)
    if user.is_disabled:
        return RedirectResponse("/login", status_code=303)
    sess["auth"] = user.id
    if not user.onboarded:
        return RedirectResponse("/dashboard/onboard", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@rt("/logout", methods=["POST"])
def logout(sess):
    sess.pop("auth", None)
    return RedirectResponse("/", status_code=303)


# ── Dashboard Routes ──

from monsterui.all import Theme as MUITheme, DivLAligned, TextPresets
from starlette.responses import JSONResponse
from dashboard.layout import DashboardLayout
from dashboard.overview import OverviewContent
from dashboard.audit import AuditContent, AuditTable
from db import api_keys, audit_log


@rt("/dashboard")
def dashboard(req, sess):
    user = req.scope.get("user")
    key_count = len(api_keys(where="user_id = ? AND is_active = 1", where_args=[user.id]))
    return (
        Title("Dashboard — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Overview",
                        *OverviewContent(user, key_count, has_llm_key=bool(user.llm_config or user.mistral_api_key)),
                        user=user, active="overview", is_admin=is_user_admin(user)),
    )


@rt("/dashboard/health-check")
async def health_check(req, sess):
    """HTMX partial: check self-hosted service health."""
    import httpx
    user = req.scope.get("user")
    if not user.self_hosted:
        return DivLAligned(
            Span("●", style="color:#4ade80; font-size:20px;"),
            Span("Connected to hosted service"),
        )
    try:
        service_url = user.service_url or "http://localhost:8420"
        if user.service_url:
            _validate_service_url(service_url)  # Only validate user-provided URLs
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Normalize the health URL: append /api/v1/health if not already present (#87)
            if service_url.rstrip("/").endswith("/api/v1"):
                health_url = f"{service_url.rstrip('/')}/health"
            else:
                health_url = f"{service_url.rstrip('/')}/api/v1/health"
            r = await client.get(health_url)
            data = r.json()
            status = data.get("status", "unknown")
            if status == "ok":
                return DivLAligned(
                    Span("●", style="color:#4ade80; font-size:20px;"),
                    Span("Service healthy"),
                )
            return DivLAligned(
                Span("●", style="color:#fb923c; font-size:20px;"),
                Span(f"Status: {status}"),
            )
    except Exception:
        return DivLAligned(
            Span("●", style="color:#f87171; font-size:20px;"),
            Span("Service unreachable"),
        )


from datetime import datetime, timezone

from dashboard.keys import KeysContent, KeyTable, generate_api_key, hash_key, NewKeyModal
from dashboard.onboard import OnboardStep1, OnboardStep2LLM, OnboardStep3


@rt("/dashboard/keys")
def dashboard_keys(req, sess):
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    return (
        Title("API Keys — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("API Keys", *KeysContent(user.id, csrf_token=token), user=user, active="keys", is_admin=is_user_admin(user)),
    )


@rt("/dashboard/keys/create", methods=["POST"])
def create_key(req, sess, label: str = "", scope: str = "full", _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    # Validate scope server-side (#106)
    valid_scopes = {"full", "evaluate_only"}
    if scope not in valid_scopes:
        scope = "full"
    raw_key, key_id = generate_api_key()
    api_keys.insert(
        user_id=user.id,
        key_id=key_id,
        key_hash=hash_key(raw_key),
        label=label or "Unnamed key",
        scope=scope,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=True,
    )
    # Return OOB swap for the alert area + update key list in place (#102)
    return (
        Div(NewKeyModal(raw_key), id="new-key-alert", hx_swap_oob="true"),
        KeyTable(user.id, csrf_token=token),
    )


@rt("/dashboard/keys/{key_pk}/revoke", methods=["POST"])
def revoke_key(req, sess, key_pk: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    try:
        key = api_keys[key_pk]
    except Exception:
        return KeyTable(user.id, csrf_token=token)
    if key.user_id != user.id:
        return KeyTable(user.id, csrf_token=token)
    key.is_active = False
    api_keys.update(key)
    return KeyTable(user.id, csrf_token=token)


@rt("/dashboard/onboard")
def dashboard_onboard(req, sess):
    user = req.scope.get("user")
    if user.onboarded:
        return RedirectResponse("/dashboard", status_code=303)
    token = _generate_csrf_token(sess)
    return (
        Title("Get Started — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Get Started", OnboardStep1(csrf_token=token), user=user, active="onboard", is_admin=is_user_admin(user)),
    )


_VALID_AUTONOMY_LEVELS = {"cautious", "moderate", "autonomous"}


@rt("/dashboard/onboard/step1", methods=["POST"])
def onboard_step1(req, sess, autonomy_level: str = "moderate", _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        autonomy_level = "moderate"
    user.autonomy_level = autonomy_level
    users.update(user)
    return OnboardStep2LLM(csrf_token=token)


@rt("/dashboard/onboard/step2", methods=["POST"])
def onboard_step2(req, sess, llm_provider: str = "", llm_api_key: str = "",
                  mistral_api_key: str = "", _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    import json as _json
    provider = llm_provider.strip()
    key = llm_api_key.strip() or mistral_api_key.strip()
    if provider and key:
        llm_cfg = {"active_provider": provider, "keys": {provider: key}}
        user.llm_config = _json.dumps(llm_cfg)
    elif key:
        user.mistral_api_key = key
    if key:
        users.update(user)
    # Guard: don't create duplicate keys on re-submit
    existing = api_keys(where="user_id = ? AND label = ? AND is_active = 1",
                        where_args=[user.id, "Default"])
    if existing:
        return OnboardStep3("(key already generated — check your API Keys page)", csrf_token=token)
    raw_key, key_id = generate_api_key()
    api_keys.insert(
        user_id=user.id,
        key_id=key_id,
        key_hash=hash_key(raw_key),
        label="Default",
        scope="full",
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=True,
    )
    return OnboardStep3(raw_key, csrf_token=token)


@rt("/dashboard/onboard/done", methods=["POST"])
def onboard_done(req, sess, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    user.onboarded = True
    users.update(user)
    return RedirectResponse("/dashboard", status_code=303)


from dashboard.agents import HostedAgentsContent, SelfHostedAgentsContent, AgentTable


@rt("/dashboard/agents")
def dashboard_agents(req, sess):
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    if user.self_hosted:
        content = SelfHostedAgentsContent(service_url=user.service_url, csrf_token=token)
    else:
        content = HostedAgentsContent()
    return (
        Title("Agents — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Agents", *content, user=user, active="agents", is_admin=is_user_admin(user)),
    )


@rt("/dashboard/agents/load", methods=["POST"])
async def load_agents(req, sess, service_url: str = "", admin_password: str = "", _csrf_token: str = ""):
    """Fetch agents from the self-hosted service API."""
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    if not user.self_hosted:
        return P("Agent management requires self-hosted mode.", style="color:#f87171;")
    token = _generate_csrf_token(sess)
    url = (service_url or user.service_url or "http://localhost:8420").rstrip("/")
    try:
        _validate_service_url(url)
    except ValueError as e:
        return P(f"Invalid service URL: {e}", cls=TextPresets.muted_sm)
    try:
        headers = {}
        if admin_password:
            headers["X-Admin-Password"] = admin_password
            # Cache password in session for kill/revive proxy calls (#5).
            # The DB stores a hash, so we keep the cleartext in the
            # ephemeral server-side session only.
            sess["_admin_password"] = admin_password
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{url}/api/v1/agents", headers=headers)
            r.raise_for_status()
            agents = r.json().get("agents", [])
            return AgentTable(agents, csrf_token=token)
    except Exception as e:
        return P(f"Could not connect: {e}", cls=TextPresets.muted_sm)


@rt("/dashboard/agents/{agent_id}/kill", methods=["POST"])
async def kill_agent_proxy(req, sess, agent_id: str, _csrf_token: str = ""):
    """Proxy kill request to self-hosted service."""
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', agent_id):
        return P("Invalid agent ID.", cls=TextPresets.muted_sm)
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    # Guard: only self-hosted users can proxy to a service (#103)
    if not user.self_hosted:
        return P("Agent management requires self-hosted mode.", cls=TextPresets.muted_sm)
    if not user.service_url:
        return P("No service URL configured. Set it in Preferences.", cls=TextPresets.muted_sm)
    url = user.service_url.rstrip("/")
    try:
        _validate_service_url(url)
    except ValueError as e:
        return P(f"Invalid service URL: {e}", cls=TextPresets.muted_sm)
    headers = {}
    # Read admin password from session cache, not DB (DB stores hash) (#5)
    cached_pw = sess.get("_admin_password", "")
    if cached_pw:
        headers["X-Admin-Password"] = cached_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            kill_r = await client.post(f"{url}/api/v1/agents/{agent_id}/kill", headers=headers)
            # Check response status to surface errors (#104)
            if kill_r.status_code >= 400:
                detail = kill_r.json().get("detail", kill_r.text) if kill_r.text else f"HTTP {kill_r.status_code}"
                return P(f"Kill failed: {detail}", style="color:#f87171;")
            r = await client.get(f"{url}/api/v1/agents", headers=headers)
            return AgentTable(r.json().get("agents", []), csrf_token=token)
    except Exception as e:
        return P(f"Error: {e}", cls=TextPresets.muted_sm)


@rt("/dashboard/agents/{agent_id}/revive", methods=["POST"])
async def revive_agent_proxy(req, sess, agent_id: str, _csrf_token: str = ""):
    """Proxy revive request to self-hosted service."""
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', agent_id):
        return P("Invalid agent ID.", cls=TextPresets.muted_sm)
    user = req.scope.get("user")
    token = _generate_csrf_token(sess)
    # Guard: only self-hosted users can proxy to a service (#103)
    if not user.self_hosted:
        return P("Agent management requires self-hosted mode.", cls=TextPresets.muted_sm)
    if not user.service_url:
        return P("No service URL configured. Set it in Preferences.", cls=TextPresets.muted_sm)
    url = user.service_url.rstrip("/")
    try:
        _validate_service_url(url)
    except ValueError as e:
        return P(f"Invalid service URL: {e}", cls=TextPresets.muted_sm)
    headers = {}
    # Read admin password from session cache, not DB (DB stores hash) (#5)
    cached_pw = sess.get("_admin_password", "")
    if cached_pw:
        headers["X-Admin-Password"] = cached_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            revive_r = await client.post(f"{url}/api/v1/agents/{agent_id}/revive", headers=headers)
            # Check response status to surface errors (#104)
            if revive_r.status_code >= 400:
                detail = revive_r.json().get("detail", revive_r.text) if revive_r.text else f"HTTP {revive_r.status_code}"
                return P(f"Revive failed: {detail}", style="color:#f87171;")
            r = await client.get(f"{url}/api/v1/agents", headers=headers)
            return AgentTable(r.json().get("agents", []), csrf_token=token)
    except Exception as e:
        return P(f"Error: {e}", cls=TextPresets.muted_sm)


from dashboard.prefs import PrefsContent


@rt("/dashboard/prefs")
async def dashboard_prefs(req, sess):
    user = req.scope.get("user")
    prefs = {
        "autonomy_level": user.autonomy_level,
        "confirm_before_delete": bool(user.confirm_before_delete),
        "confirm_before_push": bool(user.confirm_before_push),
        "confirm_before_send": bool(user.confirm_before_send),
        "max_files_per_commit": user.max_files_per_commit,
        "self_hosted": bool(user.self_hosted),
        "service_url": user.service_url,
        "admin_password": "",  # Never echo password back in HTML (#99)
        "audit_logging": bool(user.audit_logging),
    }

    from dashboard.prefs import _parse_llm_config
    llm_config = _parse_llm_config(user.llm_config)
    if not llm_config.get("active_provider") and user.mistral_api_key:
        llm_config = {"active_provider": "mistral", "keys": {"mistral": user.mistral_api_key}}
    masked_key = ""

    token = _generate_csrf_token(sess)
    return (
        Title("Preferences — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Preferences", *PrefsContent(prefs, llm_config=llm_config, csrf_token=token), user=user, active="prefs", is_admin=is_user_admin(user)),
    )


@rt("/dashboard/prefs/save", methods=["POST"])
async def save_prefs(req, sess, autonomy_level: str = "moderate",
                     confirm_before_delete: str = "", confirm_before_push: str = "",
                     confirm_before_send: str = "", max_files_per_commit: int = 10,
                     mistral_api_key: str = "", self_hosted: str = "",
                     service_url: str = "", admin_password: str = "",
                     audit_logging: str = "", _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")

    # Validate autonomy_level against allowed values (#83)
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        return P("Invalid autonomy level. Must be one of: cautious, moderate, autonomous.",
                 style="color:#f87171;")
    user.autonomy_level = autonomy_level

    # HTML checkboxes send "on" when checked, nothing when unchecked
    user.confirm_before_delete = confirm_before_delete == "on"
    user.confirm_before_push = confirm_before_push == "on"
    user.confirm_before_send = confirm_before_send == "on"

    # Validate max_files_per_commit server-side (#107)
    if max_files_per_commit < 1 or max_files_per_commit > 100:
        return P("Max files per commit must be between 1 and 100.", style="color:#f87171;")
    user.max_files_per_commit = max_files_per_commit

    user.self_hosted = self_hosted == "on"
    user.audit_logging = audit_logging == "on"
    if service_url.strip():
        try:
            _validate_service_url(service_url.strip())
        except ValueError as e:
            return P(f"Invalid service URL: {e}", style="color:#f87171;")
    user.service_url = service_url.strip()

    # Only update admin password if the user entered a new one (#99, #5).
    # Hash it with PBKDF2 before storing — never store plaintext (#14).
    if admin_password:
        user.admin_password = hash_admin_password(admin_password)

    # Save LLM provider keys from the card inputs
    import json as _json
    from dashboard.prefs import _parse_llm_config
    existing_llm = _parse_llm_config(user.llm_config)

    try:
        from providers import PROVIDERS
    except ImportError:
        PROVIDERS = None

    if PROVIDERS:
        form_data = await req.form()
        keys = existing_llm.get("keys", {})
        for pid in PROVIDERS:
            form_key = form_data.get(f"llm_key_{pid}", "")
            if form_key and not form_key.startswith("\u2022\u2022\u2022\u2022"):
                keys[pid] = form_key.strip()
            elif form_key == "":
                keys.pop(pid, None)
        existing_llm["keys"] = keys
        custom_base = form_data.get("custom_base_url", "")
        custom_model = form_data.get("custom_model", "")
        if custom_base:
            parsed = urlparse(custom_base.strip())
            if parsed.scheme not in ("http", "https"):
                return P("Custom base URL must use http or https.", style="color:#f87171;")
            existing_llm["custom_base_url"] = custom_base.strip()
        if custom_model:
            existing_llm["custom_model"] = custom_model.strip()
        user.llm_config = _json.dumps(existing_llm)

    if existing_llm.get("active_provider") == "mistral":
        user.mistral_api_key = existing_llm.get("keys", {}).get("mistral", "")

    users.update(user)
    return P("Preferences saved.", style="color:#4ade80;")


@rt("/dashboard/prefs/set-llm-provider", methods=["POST"])
async def set_llm_provider(req, sess, provider: str = "", _csrf_token: str = ""):
    """Switch the active LLM provider (HTMX partial)."""
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    user = req.scope.get("user")
    import json as _json
    from dashboard.prefs import _parse_llm_config, _llm_cards_section

    llm_config = _parse_llm_config(user.llm_config)
    if not llm_config.get("active_provider") and user.mistral_api_key:
        llm_config = {"active_provider": "mistral", "keys": {"mistral": user.mistral_api_key}}

    try:
        from providers import PROVIDERS
        if provider and provider not in PROVIDERS:
            return P("Unknown provider.", style="color:#f87171;")
    except ImportError:
        pass

    llm_config["active_provider"] = provider
    user.llm_config = _json.dumps(llm_config)
    users.update(user)

    return _llm_cards_section(llm_config)


@rt("/dashboard/audit")
def dashboard_audit(req, sess):
    user = req.scope.get("user")
    admin = is_user_admin(user)
    if admin:
        rows = audit_log(order_by="-id", limit=50)
        user_map = {u.id: u for u in users()}
        for r in rows:
            u = user_map.get(r.user_id)
            r._github_login = u.github_login if u else ""
        all_logins = sorted({u.github_login for u in user_map.values()})
        disabled_logins = {u.github_login for u in user_map.values() if u.is_disabled}
    else:
        rows = audit_log(where="user_id = ?", where_args=[user.id], order_by="-id", limit=50)
        all_logins = None
        disabled_logins = None
    return (
        Title("Audit Log — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Audit Log",
                        *AuditContent(rows, is_admin=admin, all_logins=all_logins,
                                      show_user_column=admin, disabled_logins=disabled_logins),
                        user=user, active="audit", is_admin=admin),
    )


@rt("/dashboard/audit/results")
def audit_results(req, sess, filter: str = "all", session_id: str = "",
                  user_filter: str = ""):
    """HTMX partial: filtered audit log results."""
    user = req.scope.get("user")
    admin = is_user_admin(user)

    conditions = []
    args = []

    if admin and user_filter:
        target_users = users(where="github_login = ?", where_args=[user_filter])
        if target_users:
            conditions.append("user_id = ?")
            args.append(target_users[0].id)
    elif not admin:
        conditions.append("user_id = ?")
        args.append(user.id)

    if filter == "blocked":
        conditions.append("decision = ?")
        args.append("blocked")
    elif filter == "allowed":
        conditions.append("decision = ?")
        args.append("allowed")
    if session_id.strip():
        conditions.append("session_id = ?")
        args.append(session_id.strip())

    where = " AND ".join(conditions) if conditions else None
    rows = audit_log(where=where, where_args=args if args else None, order_by="-id", limit=50)

    show_user_col = admin and not user_filter
    disabled_logins = set()
    if show_user_col:
        user_map = {u.id: u for u in users()}
        for r in rows:
            u = user_map.get(r.user_id)
            r._github_login = u.github_login if u else ""
        disabled_logins = {u.github_login for u in user_map.values() if u.is_disabled}

    return AuditTable(rows, show_user_column=show_user_col, disabled_logins=disabled_logins)


# ── Admin: User Management Routes ──

from dashboard.users import UsersPageContent, UserTable, UserDetailContent, UserPrefsTab, UserKeysTab, UserAuditTab, UserDetailHeader
from auth import get_env_admins


@rt("/dashboard/users")
def dashboard_users(req, sess):
    user = req.scope.get("user")
    if err := require_admin(user):
        return err
    token = _generate_csrf_token(sess)
    all_users = users(order_by="id")
    env_admins = get_env_admins()
    return (
        Title("Users — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout("Users",
                        *UsersPageContent(all_users, user, env_admins, csrf_token=token),
                        user=user, active="users", is_admin=True),
    )


@rt("/dashboard/users/{user_id}/promote", methods=["POST"])
def promote_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    target.is_admin = True
    users.update(target)
    token = _generate_csrf_token(sess)
    env_admins = get_env_admins()
    hx_target = req.headers.get("hx-target", "")
    if hx_target == "user-detail-header":
        target = users[user_id]
        return UserDetailHeader(target, admin, env_admins, csrf_token=token)
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}/demote", methods=["POST"])
def demote_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    if target.id == admin.id:
        return P("Cannot demote yourself.", style="color:#f87171;")
    if is_env_admin(target):
        return P("Cannot demote env var admins.", style="color:#f87171;")
    target.is_admin = False
    users.update(target)
    token = _generate_csrf_token(sess)
    env_admins = get_env_admins()
    hx_target = req.headers.get("hx-target", "")
    if hx_target == "user-detail-header":
        target = users[user_id]
        return UserDetailHeader(target, admin, env_admins, csrf_token=token)
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}/disable", methods=["POST"])
def disable_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    if target.id == admin.id:
        return P("Cannot disable yourself.", style="color:#f87171;")
    if is_env_admin(target):
        return P("Cannot disable env var admins.", style="color:#f87171;")
    target.is_disabled = True
    users.update(target)
    # Revoke all active API keys (#259)
    target_keys = api_keys(where="user_id = ? AND is_active = 1", where_args=[target.id])
    for k in target_keys:
        k.is_active = False
        api_keys.update(k)
    token = _generate_csrf_token(sess)
    env_admins = get_env_admins()
    hx_target = req.headers.get("hx-target", "")
    if hx_target == "user-detail-header":
        target = users[user_id]
        return UserDetailHeader(target, admin, env_admins, csrf_token=token)
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}/enable", methods=["POST"])
def enable_user(req, sess, user_id: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    target.is_disabled = False
    users.update(target)
    token = _generate_csrf_token(sess)
    env_admins = get_env_admins()
    hx_target = req.headers.get("hx-target", "")
    if hx_target == "user-detail-header":
        target = users[user_id]
        return UserDetailHeader(target, admin, env_admins, csrf_token=token)
    return UserTable(users(order_by="id"), admin, env_admins, csrf_token=token)


@rt("/dashboard/users/{user_id}")
def dashboard_user_detail(req, sess, user_id: int):
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return RedirectResponse("/dashboard/users", status_code=303)
    token = _generate_csrf_token(sess)
    env_admins = get_env_admins()
    key_count = len(api_keys(where="user_id = ? AND is_active = 1", where_args=[target.id]))
    from datetime import timedelta
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    decision_count = len(audit_log(where="user_id = ? AND timestamp > ?",
                                   where_args=[target.id, thirty_days_ago]))
    block_count = len(audit_log(where="user_id = ? AND timestamp > ? AND decision = ?",
                                where_args=[target.id, thirty_days_ago, "blocked"]))
    return (
        Title(f"{target.name} — Users — SafeClaw"),
        *MUITheme.blue.headers(mode='dark'),
        DashboardLayout(f"User: {target.name}",
                        *UserDetailContent(target, admin, env_admins, key_count,
                                           decision_count, block_count, csrf_token=token),
                        user=admin, active="users", is_admin=True),
    )


@rt("/dashboard/users/{user_id}/tab/prefs")
def user_tab_prefs(req, sess, user_id: int):
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    token = _generate_csrf_token(sess)
    return UserPrefsTab(target, csrf_token=token)


@rt("/dashboard/users/{user_id}/tab/keys")
def user_tab_keys(req, sess, user_id: int):
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    token = _generate_csrf_token(sess)
    keys_list = api_keys(where="user_id = ?", where_args=[target.id], order_by="-id")
    return UserKeysTab(target, keys_list, csrf_token=token)


@rt("/dashboard/users/{user_id}/tab/audit")
def user_tab_audit(req, sess, user_id: int):
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    rows = audit_log(where="user_id = ?", where_args=[target.id], order_by="-id", limit=50)
    return UserAuditTab(rows)


@rt("/dashboard/users/{user_id}/prefs", methods=["POST"])
def save_user_prefs(req, sess, user_id: int,
                    autonomy_level: str = "moderate",
                    confirm_before_delete: str = "",
                    confirm_before_push: str = "",
                    confirm_before_send: str = "",
                    max_files_per_commit: int = 10,
                    audit_logging: str = "",
                    _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
    except Exception:
        return P("User not found.", style="color:#f87171;")
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        return P("Invalid autonomy level.", style="color:#f87171;")
    if max_files_per_commit < 1 or max_files_per_commit > 100:
        return P("Max files per commit must be between 1 and 100.", style="color:#f87171;")
    target.autonomy_level = autonomy_level
    target.confirm_before_delete = confirm_before_delete == "on"
    target.confirm_before_push = confirm_before_push == "on"
    target.confirm_before_send = confirm_before_send == "on"
    target.max_files_per_commit = max_files_per_commit
    target.audit_logging = audit_logging == "on"
    users.update(target)
    return P("Preferences saved.", style="color:#4ade80;")


@rt("/dashboard/users/{user_id}/keys/{key_pk}/revoke", methods=["POST"])
def revoke_user_key(req, sess, user_id: int, key_pk: int, _csrf_token: str = ""):
    if err := _verify_csrf(sess, _csrf_token):
        return P(err, style="color:#f87171;")
    admin = req.scope.get("user")
    if err := require_admin(admin):
        return err
    try:
        target = users[user_id]
        key = api_keys[key_pk]
    except Exception:
        return P("Not found.", style="color:#f87171;")
    if key.user_id != target.id:
        return P("Key does not belong to this user.", style="color:#f87171;")
    key.is_active = False
    api_keys.update(key)
    token = _generate_csrf_token(sess)
    keys_list = api_keys(where="user_id = ?", where_args=[target.id], order_by="-id")
    return UserKeysTab(target, keys_list, csrf_token=token)


# ── Mount SafeClaw Service ──

if os.environ.get("SAFECLAW_MOUNT_SERVICE", "").lower() in ("1", "true", "yes"):
    import sys
    from pathlib import Path

    # Add safeclaw-service to Python path
    service_dir = Path(__file__).parent.parent / "safeclaw-service"
    sys.path.insert(0, str(service_dir))

    # Set required env vars for the service — use same path as db.py (#252)
    db_path = str(Path(os.environ.get("SAFECLAW_DB_DIR",
        os.path.expanduser("~/.safeclaw-landing"))) / "safeclaw.db")
    os.environ.setdefault("SAFECLAW_DB_PATH", db_path)
    os.environ.setdefault("SAFECLAW_REQUIRE_AUTH", "true")

    from safeclaw.main import app as safeclaw_api
    app.mount("/api/v1", safeclaw_api)

serve(port=5002)
