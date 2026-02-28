"""CLI policy commands - manage governance policies."""

import typer
from rich.console import Console

policy_app = typer.Typer(help="Policy management commands")
console = Console()


def _escape_turtle(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


@policy_app.command("list")
def list_policies():
    """List active policies."""
    from safeclaw.config import SafeClawConfig
    from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP

    config = SafeClawConfig()
    kg = KnowledgeGraph()
    kg.load_directory(config.get_ontology_dir())

    results = kg.query(f"""
        PREFIX sp: <{SP}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?policy ?type ?reason WHERE {{
            ?policy a ?type ;
                    sp:reason ?reason .
            ?type rdfs:subClassOf* sp:Constraint .
        }}
    """)

    if not results:
        console.print("[yellow]No policies found[/yellow]")
        return

    for row in results:
        name = str(row["policy"]).split("#")[-1]
        ptype = str(row["type"]).split("#")[-1]
        reason = str(row["reason"])
        style = "red" if "Prohibition" in ptype else "green" if "Obligation" in ptype else "dim"
        console.print(f"  [{style}]{ptype}[/{style}] {name}: {reason}")


@policy_app.command("add")
def add_policy(
    name: str = typer.Argument(help="Policy name (e.g., NoStagingDeploy)"),
    policy_type: str = typer.Option("prohibition", "--type", "-t", help="Policy type: prohibition, obligation, permission"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why this policy exists"),
    path_pattern: str = typer.Option(None, "--path-pattern", help="Forbidden file path regex"),
    command_pattern: str = typer.Option(None, "--command-pattern", help="Forbidden command regex"),
):
    """Add a new policy to the ontology."""
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"

    if not policy_file.exists():
        console.print("[red]Policy ontology file not found[/red]")
        raise typer.Exit(1)

    type_map = {
        "prohibition": "sp:Prohibition",
        "obligation": "sp:Obligation",
        "permission": "sp:Permission",
    }
    owl_type = type_map.get(policy_type.lower())
    if not owl_type:
        console.print(f"[red]Unknown policy type: {policy_type}[/red]")
        raise typer.Exit(1)

    # Validate name is safe for use as a Turtle IRI local name (R3-41)
    import re as _re
    if not _re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]*', name):
        console.print(f"[red]Invalid policy name '{name}': must match [a-zA-Z_][a-zA-Z0-9_-]*[/red]")
        raise typer.Exit(1)

    # Build Turtle snippet
    safe_name = _escape_turtle(name)
    safe_reason = _escape_turtle(reason)
    lines = [f"\nsp:{name} a {owl_type}"]
    if path_pattern:
        lines[0] += ", sp:PathConstraint"
        lines.append(f'    sp:forbiddenPathPattern "{_escape_turtle(path_pattern)}"')
    if command_pattern:
        lines[0] += ", sp:CommandConstraint"
        lines.append(f'    sp:forbiddenCommandPattern "{_escape_turtle(command_pattern)}"')
    lines.append(f'    sp:reason "{safe_reason}"')
    lines.append(f'    rdfs:label "{safe_name}"')

    turtle_block = " ;\n".join(lines) + " .\n"

    with open(policy_file, "a") as f:
        f.write(f"\n# Added via CLI\n{turtle_block}")

    console.print(f"[green]Policy '{name}' added successfully[/green]")
    console.print("[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]")


@policy_app.command("remove")
def remove_policy(
    name: str = typer.Argument(help="Policy name to remove"),
):
    """Remove a policy by commenting it out in the ontology file."""
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"

    if not policy_file.exists():
        console.print("[red]Policy ontology file not found[/red]")
        raise typer.Exit(1)

    content = policy_file.read_text()
    marker = f"sp:{name} "

    if marker not in content:
        console.print(f"[yellow]Policy '{name}' not found[/yellow]")
        raise typer.Exit(1)

    # Comment out the policy block (find from sp:Name to the next period+newline)
    import re
    pattern = re.compile(
        rf"(^sp:{re.escape(name)}\s[^\n]*(?:\n[ \t]+[^\n]*)*\.)\s*$",
        re.MULTILINE,
    )
    new_content = pattern.sub(
        lambda m: "\n".join("# REMOVED: " + line for line in m.group(0).splitlines()),
        content,
    )

    if new_content == content:
        console.print(f"[yellow]Could not locate policy block for '{name}'[/yellow]")
        raise typer.Exit(1)

    policy_file.write_text(new_content)
    console.print(f"[green]Policy '{name}' removed (commented out)[/green]")
    console.print("[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]")


@policy_app.command("add-nl")
def add_nl(
    description: str = typer.Argument(help="Natural language policy description"),
):
    """Add a policy using natural language (requires LLM)."""
    import asyncio
    from safeclaw.config import SafeClawConfig
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    if client is None:
        console.print("[red]LLM not configured. Set SAFECLAW_MISTRAL_API_KEY environment variable.[/red]")
        raise typer.Exit(1)

    from safeclaw.engine.knowledge_graph import KnowledgeGraph
    from safeclaw.llm.policy_compiler import PolicyCompiler

    kg = KnowledgeGraph()
    kg.load_directory(config.get_ontology_dir())
    compiler = PolicyCompiler(client, kg)

    result = asyncio.run(compiler.compile(description))

    if not result.success:
        console.print("[red]Failed to compile policy:[/red]")
        for err in result.validation_errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Generated policy: {result.policy_name}[/bold]")
    console.print(f"Type: {result.policy_type}")
    console.print(f"\n[dim]{result.turtle}[/dim]\n")

    if typer.confirm("Apply this policy?"):
        policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"
        with open(policy_file, "a") as f:
            f.write(f"\n# Added via NL compiler: {description}\n{result.turtle}\n")
        console.print("[green]Policy applied successfully[/green]")
        console.print("[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]")
    else:
        console.print("[yellow]Policy not applied[/yellow]")
