from fasthtml.common import *
from fasthtml.components import Footer as FooterTag

GITHUB_URL = "https://github.com/tendlyeu/SafeClaw"
DOCS_URL = "#quickstart"

app, rt = fast_app(
    pico=False,
    static_path="static",
    hdrs=(
        Link(rel="stylesheet", href="/style.css"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Meta(name="description", content="SafeClaw — Neurosymbolic governance layer for autonomous AI agents"),
    ),
)


# ── Components ──

def Nav():
    return Header(
        Div(
            Div(
                Span("🛡️", cls="logo-icon"),
                Span("SafeClaw"),
                cls="nav-logo",
            ),
            Ul(
                Li(A("Features", href="#features")),
                Li(A("How It Works", href="#how-it-works")),
                Li(A("Architecture", href="#architecture")),
                Li(A("GitHub", href=GITHUB_URL, target="_blank")),
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
                  cls="btn btn-primary"),
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
            P("Up and running in three commands", cls="section-subtitle"),
            Div(
                Div(
                    Span("$ ", cls="prompt"), Span("pip install safeclaw", cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"), Span('safeclaw init --user-id yourname', cls="cmd"),
                ),
                Div(
                    Span("$ ", cls="prompt"), Span("safeclaw serve", cls="cmd"),
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
                Li(A("GitHub", href=GITHUB_URL, target="_blank")),
                Li(A("Documentation", href=DOCS_URL)),
                Li(A("MIT License", href=f"{GITHUB_URL}/blob/main/LICENSE")),
                cls="footer-links",
            ),
            P(f"© 2025 SafeClaw. Built with FastHTML."),
            cls="container",
        ),
        cls="footer",
    )


# ── Route ──

@rt
def index():
    return (
        Title("SafeClaw — Neurosymbolic Governance for AI Agents"),
        Nav(),
        Hero(),
        Features(),
        HowItWorks(),
        TerminalDemo(),
        Architecture(),
        QuickStart(),
        Footer(),
    )


serve(port=5002)
