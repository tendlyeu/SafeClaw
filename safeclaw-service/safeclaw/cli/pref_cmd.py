"""CLI preference commands - manage user preferences."""

import typer
from rich.console import Console

pref_app = typer.Typer(help="User preference commands")
console = Console()

VALID_PREFS = {
    "autonomyLevel": ("moderate", "cautious", "supervised", "autonomous"),
    "confirmBeforeDelete": ("true", "false"),
    "confirmBeforePush": ("true", "false"),
    "confirmBeforeSend": ("true", "false"),
}


@pref_app.command("show")
def show(user_id: str = typer.Option("default", help="User ID")):
    """Show user preferences."""
    from safeclaw.config import SafeClawConfig
    from safeclaw.engine.knowledge_graph import KnowledgeGraph
    from safeclaw.constraints.preference_checker import PreferenceChecker

    config = SafeClawConfig()
    kg = KnowledgeGraph()
    kg.load_directory(config.get_ontology_dir())

    checker = PreferenceChecker(kg)
    prefs = checker.get_preferences(user_id)

    console.print(f"[bold]Preferences for user: {user_id}[/bold]")
    console.print(f"  Autonomy level: {prefs.autonomy_level}")
    console.print(f"  Confirm before delete: {prefs.confirm_before_delete}")
    console.print(f"  Confirm before push: {prefs.confirm_before_push}")
    console.print(f"  Confirm before send: {prefs.confirm_before_send}")
    console.print(f"  Max files per commit: {prefs.max_files_per_commit}")


@pref_app.command("set")
def set_pref(
    key: str = typer.Argument(help="Preference key (e.g., confirmBeforeDelete)"),
    value: str = typer.Argument(help="Preference value (e.g., true/false)"),
    user_id: str = typer.Option("default", help="User ID"),
):
    """Set a user preference value."""
    from safeclaw.config import SafeClawConfig

    if key not in VALID_PREFS:
        console.print(f"[red]Unknown preference: {key}[/red]")
        console.print(f"Valid preferences: {', '.join(VALID_PREFS.keys())}")
        raise typer.Exit(1)

    valid_values = VALID_PREFS[key]
    if value.lower() not in valid_values:
        console.print(f"[red]Invalid value '{value}' for {key}[/red]")
        console.print(f"Valid values: {', '.join(valid_values)}")
        raise typer.Exit(1)

    config = SafeClawConfig()
    users_dir = config.get_ontology_dir() / "users"

    # Find or create user file
    user_file = users_dir / f"user-{user_id}.ttl"
    if not user_file.exists():
        default_file = users_dir / "user-default.ttl"
        if default_file.exists():
            import shutil
            shutil.copy2(default_file, user_file)
            console.print(f"Created user preferences file: {user_file.name}")
        else:
            console.print("No default preferences file found", err=True)
            raise typer.Exit(1)

    content = user_file.read_text()

    # Update the preference value in-place
    import re
    pattern = re.compile(
        rf'(su:{key}\s+)"([^"]*)"',
    )
    new_content, count = pattern.subn(rf'\1"{value}"', content)
    if count > 0:
        if count > 1:
            console.print(f"[yellow]Warning: found {count} matches for {key}, all were updated[/yellow]")
        user_file.write_text(new_content)
        console.print(f"[green]Set {key} = {value} for user {user_id}[/green]")
    else:
        console.print(f"[yellow]Preference {key} not found in file, skipping[/yellow]")
        raise typer.Exit(1)

    console.print("[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]")
