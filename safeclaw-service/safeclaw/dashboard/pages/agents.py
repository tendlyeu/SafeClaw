"""Dashboard agents page."""

from fasthtml.common import P

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/agents")
    def agents():
        engine = get_engine()  # noqa: F841
        return Page("Agents", P("Coming soon"), active="agents")
