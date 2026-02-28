"""Dashboard audit log page."""

from fasthtml.common import P

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/audit")
    def audit():
        engine = get_engine()  # noqa: F841
        return Page("Audit Log", P("Coming soon"), active="audit")
