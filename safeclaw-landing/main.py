import secrets
from datetime import date

import httpx
from fasthtml.common import *
from fasthtml.components import Footer as FooterTag
from fasthtml.oauth import redir_url

from auth import github_client, user_auth_before, get_current_user
from db import users, upsert_user

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
                    Span("openclaw plugins install openclaw-safeclaw-plugin", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"),
                    Span("export SAFECLAW_API_KEY=sc_your_key_here", cls="cmd"),
                ),
                cls="quickstart-terminal",
            ),
            P("That's it. The plugin connects to the hosted service by default.", cls="quickstart-desc"),
            Div(
                Div(
                    Span("# ", cls="comment"),
                    Span("Default: https://api.safeclaw.eu/api/v1", cls="comment"),
                ),
                Div(
                    Span("# ", cls="comment"),
                    Span("No configuration needed", cls="comment"),
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
                    P("The plugin is a thin client (~220 lines) with no governance logic of its own. "
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
                                Tr(Td(Code("closed")), Td("Block on service unavailability (default). Safer.")),
                                Tr(Td(Code("open")), Td("Allow on service failure. More available.")),
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
                    P("The TypeScript plugin (v0.1.2+) parses structured errors and provides "
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
                        Li("You're redirected to ", Code("/dashboard"), " with a session cookie"),
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
                                   Td("Set autonomy level, confirmation rules, file limits")),
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
                    P("The SQLite database is created automatically in ", Code("data/safeclaw.db"), "."),
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

                # ── 18. Configuration Reference ──
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
                                Tr(Td(Code("SAFECLAW_TIMEOUT_MS")), Td(Code("500")),
                                   Td("HTTP timeout for service calls")),
                                Tr(Td(Code("SAFECLAW_ENABLED")), Td(Code("true")),
                                   Td("Enable/disable the plugin")),
                                Tr(Td(Code("SAFECLAW_ENFORCEMENT")), Td(Code("enforce")),
                                   Td("Enforcement mode")),
                                Tr(Td(Code("SAFECLAW_FAIL_MODE")), Td(Code("closed")),
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
                            ),
                        ),
                        cls="docs-table-wrap",
                    ),
                ),

                # ── 19. SaaS Onboarding ──
                DocsSection("saas", "SaaS Onboarding",
                    P("SafeClaw is available as a hosted service at ",
                      Code("safeclaw.eu"), ". No server setup required."),
                    H3("1. Create an account", cls="docs-h3"),
                    P("Click ", Strong("Get Started"), " on the landing page. "
                      "Sign in with your GitHub account."),
                    H3("2. Onboarding wizard", cls="docs-h3"),
                    P("First-time users are guided through a two-step wizard:"),
                    Ul(
                        Li(Strong("Autonomy level"), " — choose how much control SafeClaw has "
                           "(cautious, moderate, or autonomous)"),
                        Li(Strong("API key"), " — a key is generated automatically. "
                           "Copy it immediately; it is shown only once."),
                        cls="docs-list",
                    ),
                    H3("3. Connect your agent", cls="docs-h3"),
                    P("Install the plugin and set your key:"),
                    Div(
                        Pre(
                            "$ openclaw plugins install openclaw-safeclaw-plugin\n"
                            "$ export SAFECLAW_API_KEY=sc_your_key_here",
                            cls="docs-pre",
                        ),
                    ),
                    P("The plugin connects to ", Code("https://api.safeclaw.eu/api/v1"),
                      " by default. No URL configuration needed."),
                    H3("4. Manage from the dashboard", cls="docs-h3"),
                    P("After onboarding, the dashboard at ", Code("safeclaw.eu/dashboard"),
                      " lets you:"),
                    Ul(
                        Li("Create and revoke API keys"),
                        Li("Set preferences (confirm before delete, max files per commit)"),
                        Li("View connected agents"),
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
    sess["auth"] = user.id
    if not user.onboarded:
        return RedirectResponse("/dashboard/onboard", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@rt("/logout")
def logout(sess):
    sess.pop("auth", None)
    return RedirectResponse("/", status_code=303)


# ── Dashboard Routes ──

from monsterui.all import Theme as MUITheme, DivLAligned
from dashboard.layout import DashboardLayout
from dashboard.overview import OverviewContent
from db import api_keys


@rt("/dashboard")
def dashboard(req, sess):
    user = req.scope.get("user")
    key_count = len(api_keys(where="user_id = ? AND is_active = 1", where_args=[user.id]))
    return (
        Title("Dashboard — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Overview", *OverviewContent(user, key_count), user=user, active="overview"),
    )


@rt("/dashboard/health-check")
async def health_check(req, sess):
    """HTMX partial: check service health."""
    import httpx
    try:
        import os
        if os.environ.get("SAFECLAW_MOUNT_SERVICE", "").lower() in ("1", "true", "yes"):
            service_url = f"{req.url.scheme}://{req.url.netloc}/api/v1"
        else:
            service_url = sess.get("service_url", "http://localhost:8420")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{service_url}/health")
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
from dashboard.onboard import OnboardStep1, OnboardStep2


@rt("/dashboard/keys")
def dashboard_keys(req, sess):
    user = req.scope.get("user")
    return (
        Title("API Keys — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("API Keys", *KeysContent(user.id), user=user, active="keys"),
    )


@rt("/dashboard/keys/create")
def create_key(req, sess, label: str = "", scope: str = "full"):
    user = req.scope.get("user")
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
    return Div(
        NewKeyModal(raw_key),
        KeyTable(user.id),
    )


@rt("/dashboard/keys/{key_pk}/revoke")
def revoke_key(req, sess, key_pk: int):
    user = req.scope.get("user")
    try:
        key = api_keys[key_pk]
    except Exception:
        return KeyTable(user.id)
    if key.user_id != user.id:
        return KeyTable(user.id)
    key.is_active = False
    api_keys.update(key)
    return KeyTable(user.id)


@rt("/dashboard/onboard")
def dashboard_onboard(req, sess):
    user = req.scope.get("user")
    if user.onboarded:
        return RedirectResponse("/dashboard", status_code=303)
    return (
        Title("Get Started — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Get Started", OnboardStep1(), user=user, active="onboard"),
    )


_VALID_AUTONOMY_LEVELS = {"cautious", "moderate", "autonomous"}


@rt("/dashboard/onboard/step1")
def onboard_step1(req, sess, autonomy_level: str = "moderate"):
    user = req.scope.get("user")
    if autonomy_level not in _VALID_AUTONOMY_LEVELS:
        autonomy_level = "moderate"
    user.autonomy_level = autonomy_level
    users.update(user)
    # Guard: don't create duplicate keys on re-submit
    existing = api_keys(where="user_id = ? AND label = ? AND is_active = 1",
                        where_args=[user.id, "Default"])
    if existing:
        return OnboardStep2("(key already generated — check your API Keys page)")
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
    return OnboardStep2(raw_key)


@rt("/dashboard/onboard/done")
def onboard_done(req, sess):
    user = req.scope.get("user")
    user.onboarded = True
    users.update(user)
    return RedirectResponse("/dashboard", status_code=303)


from dashboard.agents import AgentsContent, AgentTable


@rt("/dashboard/agents")
def dashboard_agents(req, sess):
    user = req.scope.get("user")
    return (
        Title("Agents — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Agents", *AgentsContent(), user=user, active="agents"),
    )


@rt("/dashboard/agents/load")
async def load_agents(req, sess, service_url: str = "", admin_password: str = ""):
    """Fetch agents from the service API."""
    from urllib.parse import urlparse
    parsed = urlparse(service_url or "http://localhost:8420")
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        return P("Service URL must be localhost or 127.0.0.1", cls=TextPresets.muted_sm)
    safe_url = f"{parsed.scheme}://{parsed.netloc}"
    sess["service_url"] = safe_url
    sess["admin_password"] = admin_password
    try:
        headers = {}
        if admin_password:
            headers["X-Admin-Password"] = admin_password
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{safe_url}/api/v1/agents", headers=headers)
            r.raise_for_status()
            agents = r.json().get("agents", [])
            return AgentTable(agents)
    except Exception as e:
        return P(f"Could not connect: {e}", cls=TextPresets.muted_sm)


@rt("/dashboard/agents/{agent_id}/kill")
async def kill_agent_proxy(req, sess, agent_id: str):
    """Proxy kill request to service."""
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{service_url}/api/v1/agents/{agent_id}/kill", headers=headers)
            r = await client.get(f"{service_url}/api/v1/agents", headers=headers)
            return AgentTable(r.json().get("agents", []))
    except Exception as e:
        return P(f"Error: {e}", cls=TextPresets.muted_sm)


@rt("/dashboard/agents/{agent_id}/revive")
async def revive_agent_proxy(req, sess, agent_id: str):
    """Proxy revive request to service."""
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{service_url}/api/v1/agents/{agent_id}/revive", headers=headers)
            r = await client.get(f"{service_url}/api/v1/agents", headers=headers)
            return AgentTable(r.json().get("agents", []))
    except Exception as e:
        return P(f"Error: {e}", cls=TextPresets.muted_sm)


from dashboard.prefs import PrefsContent


@rt("/dashboard/prefs")
async def dashboard_prefs(req, sess):
    user = req.scope.get("user")
    # Try to load prefs from service
    prefs = None
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{service_url}/api/v1/preferences/{user.github_login}",
                headers=headers,
            )
            if r.status_code == 200:
                prefs = r.json()
    except Exception:
        pass  # Use defaults

    return (
        Title("Preferences — SafeClaw"),
        *MUITheme.blue.headers(),
        DashboardLayout("Preferences", *PrefsContent(prefs), user=user, active="prefs"),
    )


@rt("/dashboard/prefs/save")
async def save_prefs(req, sess, autonomy_level: str = "moderate",
                     confirm_before_delete: bool = True, confirm_before_push: bool = True,
                     confirm_before_send: bool = True, max_files_per_commit: int = 10):
    user = req.scope.get("user")
    service_url = sess.get("service_url", "http://localhost:8420")
    headers = {"Content-Type": "application/json"}
    admin_pw = sess.get("admin_password", "")
    if admin_pw:
        headers["X-Admin-Password"] = admin_pw
    prefs_data = {
        "autonomyLevel": autonomy_level,
        "confirmBeforeDelete": confirm_before_delete,
        "confirmBeforePush": confirm_before_push,
        "confirmBeforeSend": confirm_before_send,
        "maxFilesPerCommit": max_files_per_commit,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{service_url}/api/v1/preferences/{user.github_login}",
                json=prefs_data, headers=headers,
            )
            r.raise_for_status()
            return P("Preferences saved.", style="color:#4ade80;")
    except Exception as e:
        return P(f"Could not save: {e}. Is the service running?", style="color:#f87171;")


serve(port=5002)

# ── Mount SafeClaw Service ──
import os

if os.environ.get("SAFECLAW_MOUNT_SERVICE", "").lower() in ("1", "true", "yes"):
    import sys
    from pathlib import Path

    # Add safeclaw-service to Python path
    service_dir = Path(__file__).parent.parent / "safeclaw-service"
    sys.path.insert(0, str(service_dir))

    # Set required env vars for the service
    db_path = str(Path(__file__).parent / "data" / "safeclaw.db")
    os.environ.setdefault("SAFECLAW_DB_PATH", db_path)
    os.environ.setdefault("SAFECLAW_REQUIRE_AUTH", "true")

    from safeclaw.main import app as safeclaw_api
    app.mount("/", safeclaw_api)
