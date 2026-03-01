"""Shared UI components for the SafeClaw admin dashboard."""

from fasthtml.common import (
    A,
    Div,
    H1,
    Main,
    Nav,
    Script,
    Span,
    Style,
    Title,
)

# Mount prefix — set by create_dashboard() at startup.
MOUNT_PREFIX = ""


def DashboardCSS():
    """Return a Style element with the full dark-theme CSS for the dashboard."""
    return Style("""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg: #0a0a0a;
    --surface: #1a1a1a;
    --border: #2a2a2a;
    --text: #e5e5e5;
    --muted: #888888;
    --green: #4ade80;
    --red: #f87171;
    --blue: #60a5fa;
    --purple: #a78bfa;
    --orange: #fb923c;
    --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: var(--font-sans);
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
}

code, pre, .mono { font-family: var(--font-mono); }

/* ── Navigation ── */
.dashboard-nav {
    position: sticky; top: 0; z-index: 100;
    display: flex; align-items: center; gap: 2rem;
    padding: 0.75rem 2rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
}
.dashboard-nav .logo {
    font-weight: 700; font-size: 1.1rem;
    color: var(--green);
    text-decoration: none;
    display: flex; align-items: center; gap: 0.5rem;
}
.dashboard-nav .nav-links { display: flex; gap: 0.25rem; flex: 1; }
.dashboard-nav .nav-links a {
    padding: 0.4rem 0.75rem; border-radius: 6px;
    color: var(--muted); text-decoration: none;
    font-size: 0.9rem; font-weight: 500;
    transition: background 0.15s, color 0.15s;
}
.dashboard-nav .nav-links a:hover { color: var(--text); background: var(--border); }
.dashboard-nav .nav-links a.active { color: var(--text); background: var(--border); }
.dashboard-nav .nav-right { margin-left: auto; }
.dashboard-nav .nav-right a {
    color: var(--muted); text-decoration: none; font-size: 0.85rem;
}
.dashboard-nav .nav-right a:hover { color: var(--red); }

/* ── Container ── */
.dashboard-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}
.dashboard-container h1 {
    font-size: 1.75rem; font-weight: 700;
    margin-bottom: 1.5rem;
}

/* ── Stat grid / cards ── */
.stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}
.stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem;
}
.stat-card .stat-label {
    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--muted); margin-bottom: 0.25rem;
}
.stat-card .stat-value {
    font-size: 1.75rem; font-weight: 700; font-variant-numeric: tabular-nums;
}
.stat-card .stat-value.green { color: var(--green); }
.stat-card .stat-value.red { color: var(--red); }
.stat-card .stat-value.blue { color: var(--blue); }
.stat-card .stat-value.purple { color: var(--purple); }
.stat-card .stat-value.orange { color: var(--orange); }

/* ── Panel ── */
.panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}
.panel h2 {
    font-size: 1.1rem; font-weight: 600;
    margin-bottom: 1rem;
}

/* ── Tables ── */
table {
    width: 100%; border-collapse: collapse;
    font-size: 0.9rem;
}
thead th {
    text-align: left; padding: 0.6rem 0.75rem;
    color: var(--muted); font-weight: 500;
    border-bottom: 1px solid var(--border);
    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em;
}
tbody td {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
}
tbody tr:hover { background: rgba(255,255,255,0.02); }

/* ── Badges ── */
.badge {
    display: inline-block; padding: 0.15rem 0.5rem;
    border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.03em;
}
.badge-allowed { background: rgba(74,222,128,0.15); color: var(--green); }
.badge-blocked { background: rgba(248,113,113,0.15); color: var(--red); }
.badge-active  { background: rgba(74,222,128,0.15); color: var(--green); }
.badge-killed  { background: rgba(248,113,113,0.15); color: var(--red); }
.badge-low     { color: var(--green); }
.badge-medium  { color: var(--orange); }
.badge-high    { color: var(--red); }
.badge-critical { color: var(--red); font-weight: 700; }

/* ── Buttons ── */
.btn {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.5rem 1rem; border-radius: 6px;
    font-size: 0.85rem; font-weight: 500;
    border: 1px solid var(--border);
    background: var(--surface); color: var(--text);
    cursor: pointer; text-decoration: none;
    transition: background 0.15s, border-color 0.15s;
}
.btn:hover { background: var(--border); }
.btn-primary { background: var(--blue); color: #000; border-color: var(--blue); }
.btn-primary:hover { opacity: 0.9; }
.btn-danger { background: var(--red); color: #000; border-color: var(--red); }
.btn-danger:hover { opacity: 0.9; }
.btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }

/* ── Form inputs ── */
input[type="text"], input[type="password"], input[type="number"],
input[type="email"], select, textarea {
    width: 100%; padding: 0.6rem 0.75rem;
    background: var(--bg); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px;
    font-family: var(--font-sans); font-size: 0.9rem;
    outline: none; transition: border-color 0.15s;
}
input:focus, select:focus, textarea:focus { border-color: var(--blue); }

/* ── Login ── */
.login-container {
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh;
}
.login-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2.5rem;
    width: 100%; max-width: 380px;
    text-align: center;
}
.login-card h1 {
    font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--green);
}
.login-card p { color: var(--muted); margin-bottom: 1.5rem; font-size: 0.9rem; }
.login-card form { display: flex; flex-direction: column; gap: 1rem; }

/* ── Config grid ── */
.config-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 1rem;
}
@media (max-width: 768px) { .config-grid { grid-template-columns: 1fr; } }

/* ── Flash messages ── */
.flash {
    padding: 0.75rem 1rem; border-radius: 6px;
    margin-bottom: 1rem; font-size: 0.9rem;
}
.flash-error { background: rgba(248,113,113,0.15); color: var(--red); }
.flash-success { background: rgba(74,222,128,0.15); color: var(--green); }

/* ── Detail rows ── */
.detail-row {
    display: flex; padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
}
.detail-row .detail-label {
    width: 180px; flex-shrink: 0;
    color: var(--muted); font-size: 0.85rem;
}
.detail-row .detail-value { font-size: 0.9rem; }

/* ── Empty state ── */
.empty-state {
    text-align: center; padding: 3rem 1rem;
    color: var(--muted);
}
.empty-state p { font-size: 1.1rem; }

/* ── Text helpers ── */
.text-muted { color: var(--muted); }
.text-green { color: var(--green); }
.text-red { color: var(--red); }
.text-blue { color: var(--blue); }
.text-purple { color: var(--purple); }
.text-orange { color: var(--orange); }
.text-sm { font-size: 0.85rem; }
.text-xs { font-size: 0.75rem; }
.text-mono { font-family: var(--font-mono); }
.mt-1 { margin-top: 0.5rem; }
.mt-2 { margin-top: 1rem; }
.mb-1 { margin-bottom: 0.5rem; }
.mb-2 { margin-bottom: 1rem; }

/* ── Toast Notifications ── */
.toast-container {
    position: fixed; bottom: 1.5rem; right: 1.5rem;
    z-index: 9999; display: flex; flex-direction: column-reverse; gap: 0.5rem;
    max-width: 400px;
}
.toast {
    padding: 0.75rem 1rem; border-radius: 8px;
    font-size: 0.85rem; line-height: 1.4;
    background: var(--surface); border: 1px solid var(--border);
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    animation: toast-in 0.3s ease-out;
}
.toast-warning { border-left: 3px solid var(--orange); }
.toast-critical { border-left: 3px solid var(--red); }
.toast-info { border-left: 3px solid var(--blue); }
.toast .toast-title { font-weight: 600; margin-bottom: 0.2rem; }
.toast .toast-detail { color: var(--muted); font-size: 0.8rem; }
@keyframes toast-in {
    from { opacity: 0; transform: translateY(0.5rem); }
    to { opacity: 1; transform: translateY(0); }
}
""")


_NAV_PATHS = [
    ("Home", "/", "home"),
    ("Audit", "/audit", "audit"),
    ("Agents", "/agents", "agents"),
    ("Settings", "/settings", "settings"),
]


def NavBar(active: str = "home"):
    """Sticky top navigation bar."""
    p = MOUNT_PREFIX
    links = [
        A(label, href=f"{p}{path}", cls="active" if key == active else "")
        for label, path, key in _NAV_PATHS
    ]
    return Nav(
        A("SafeClaw Admin", href=f"{p}/", cls="logo"),
        Div(*links, cls="nav-links"),
        Div(A("Logout", href=f"{p}/logout"), cls="nav-right"),
        cls="dashboard-nav",
    )


def NotificationListener():
    """JS EventSource listener that creates toast notifications from SSE events."""
    return (
        Div(id="toast-container", cls="toast-container"),
        Script("""
(function() {
  var src = new EventSource('/api/v1/events');
  src.addEventListener('safeclaw', function(e) {
    try {
      var d = JSON.parse(e.data);
      var container = document.getElementById('toast-container');
      if (!container) return;
      var cls = 'toast toast-' + (d.severity || 'info');
      var toast = document.createElement('div');
      toast.className = cls;
      function esc(s) { var t = document.createElement('span'); t.textContent = s; return t.innerHTML; }
      toast.innerHTML = '<div class="toast-title">' +
        esc(d.title) + '</div><div class="toast-detail">' +
        esc((d.detail || '').substring(0, 200)) + '</div>';
      container.appendChild(toast);
      setTimeout(function() { toast.remove(); }, 8000);
    } catch(ex) {}
  });
  src.onerror = function() { setTimeout(function() {}, 5000); };
})();
"""),
    )


def Page(title_text: str, *content, active: str = "home"):
    """Wrap page content with the standard dashboard layout."""
    return (
        Title(f"{title_text} - SafeClaw Admin"),
        DashboardCSS(),
        NavBar(active=active),
        Main(Div(H1(title_text), *content, cls="dashboard-container")),
        NotificationListener(),
    )


def StatCard(label: str, value, color: str = ""):
    """A statistics card with a label and a large numeric value."""
    value_cls = f"stat-value {color}".strip()
    return Div(
        Div(label, cls="stat-label"),
        Div(str(value), cls=value_cls),
        cls="stat-card",
    )


def DecisionBadge(decision: str):
    """Colored badge for allowed / blocked decisions."""
    lower = decision.lower()
    if lower == "allowed":
        return Span("allowed", cls="badge badge-allowed")
    return Span("blocked", cls="badge badge-blocked")


def RiskBadge(risk_level: str):
    """Colored text badge for risk levels (low / medium / high / critical)."""
    lower = risk_level.lower()
    cls_map = {
        "low": "badge-low",
        "medium": "badge-medium",
        "high": "badge-high",
        "critical": "badge-critical",
        "lowrisk": "badge-low",
        "mediumrisk": "badge-medium",
        "highrisk": "badge-high",
        "criticalrisk": "badge-critical",
    }
    cls = cls_map.get(lower, "")
    return Span(risk_level, cls=f"badge {cls}".strip())


def AgentStatusBadge(killed: bool):
    """Active / killed status badge for agents."""
    if killed:
        return Span("killed", cls="badge badge-killed")
    return Span("active", cls="badge badge-active")
