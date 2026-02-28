"""Dashboard home page."""

from fasthtml.common import P

from safeclaw.dashboard.components import Page


def register(rt, get_engine):
    @rt("/")
    def home():
        engine = get_engine()  # noqa: F841
        return Page("Home", P("Coming soon"), active="home")
