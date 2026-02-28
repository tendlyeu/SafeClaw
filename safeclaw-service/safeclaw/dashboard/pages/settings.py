"""Dashboard settings page."""

from fasthtml.common import P

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/settings")
    def settings():
        engine = get_engine()  # noqa: F841
        return Page("Settings", P("Coming soon"), active="settings")
