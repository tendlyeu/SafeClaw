"""CLI policy commands - manage governance policies."""

import typer
from rich.console import Console

policy_app = typer.Typer(
    help=(
        "Manage governance policies (prohibitions, obligations, permissions).\n\n"
        "Policies are stored as Turtle triples in safeclaw-policy.ttl and\n"
        "evaluated as part of the 9-step constraint pipeline."
    ),
)
console = Console()


def _escape_turtle(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


@policy_app.command("list")
def list_policies():
    """List all active policies from the ontology.

    Shows each policy's type (Prohibition/Obligation/Permission),
    name, and reason. Policies are loaded from the bundled and
    user-added .ttl files.
    """
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
    name: str = typer.Argument(
        help="Policy name — letters, digits, hyphens, underscores (e.g., NoStagingDeploy)"
    ),
    policy_type: str = typer.Option(
        "prohibition",
        "--type",
        "-t",
        help="prohibition = blocks actions, obligation = requires actions, permission = allows actions",
    ),
    reason: str = typer.Option(..., "--reason", "-r", help="Human-readable reason for this policy"),
    path_pattern: str = typer.Option(
        None, "--path-pattern", help="Regex for forbidden file paths (e.g., 'staging/.*')"
    ),
    command_pattern: str = typer.Option(
        None, "--command-pattern", help="Regex for forbidden commands (e.g., 'rm -rf /')"
    ),
):
    """Add a new policy rule to the ontology.

    Example:
      safeclaw policy add NoProdDeploy -t prohibition -r "Block production deploys" --path-pattern "prod/.*"

    Changes take effect after service restart or hot-reload (POST /api/v1/reload).
    """
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"

    if not policy_file.exists():
        console.print("[red]Error: Policy ontology file not found.[/red]")
        console.print(f"Expected: {policy_file}")
        console.print("Run [bold]safeclaw init[/bold] first, or check SAFECLAW_ONTOLOGY_DIR.")
        raise typer.Exit(1)

    type_map = {
        "prohibition": "sp:Prohibition",
        "obligation": "sp:Obligation",
        "permission": "sp:Permission",
    }
    owl_type = type_map.get(policy_type.lower())
    if not owl_type:
        console.print(f"[red]Error: Unknown policy type '{policy_type}'.[/red]")
        console.print("Valid types: prohibition, obligation, permission")
        raise typer.Exit(1)

    # Validate name is safe for use as a Turtle IRI local name (R3-41)
    import re as _re

    if not _re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", name):
        console.print(f"[red]Error: Invalid policy name '{name}'.[/red]")
        console.print(
            "Must start with a letter or underscore, followed by letters, digits, hyphens, or underscores."
        )
        console.print("Examples: NoProdDeploy, require_tests, block-rm-rf")
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
    console.print(
        "[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]"
    )


@policy_app.command("remove")
def remove_policy(
    name: str = typer.Argument(help="Policy name to remove (as shown in 'policy list')"),
):
    """Remove a policy by commenting it out in the ontology file.

    The policy is not deleted — its Turtle block is prefixed with '# REMOVED:'.
    This preserves an audit trail. To fully delete, edit the .ttl file directly.
    """
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"

    if not policy_file.exists():
        console.print("[red]Error: Policy ontology file not found.[/red]")
        console.print(f"Expected: {policy_file}")
        raise typer.Exit(1)

    content = policy_file.read_text()
    marker = f"sp:{name} "

    if marker not in content:
        console.print(f"[yellow]Policy '{name}' not found in the ontology.[/yellow]")
        console.print("Use [bold]safeclaw policy list[/bold] to see active policies.")
        raise typer.Exit(1)

    # Comment out the policy block (find from sp:Name to the next period+newline)
    import re

    pattern = re.compile(
        rf"(?:^# Added via CLI\n)?^sp:{re.escape(name)}\s[^\n]*(?:\n[ \t]+[^\n]*)*\s*\.\n?",
        re.MULTILINE,
    )
    new_content = pattern.sub(
        lambda m: "\n".join("# REMOVED: " + line for line in m.group(0).splitlines()) + "\n",
        content,
    )

    if new_content == content:
        console.print(f"[yellow]Could not locate the Turtle block for '{name}'.[/yellow]")
        console.print("The policy name exists but its block structure could not be parsed.")
        console.print(f"You may need to edit {policy_file} manually.")
        raise typer.Exit(1)

    policy_file.write_text(new_content)
    console.print(f"[green]Policy '{name}' removed (commented out)[/green]")
    console.print(
        "[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]"
    )


# Predicates that LLM-generated policies are allowed to use (policy data only).
# This blocks permission-granting predicates (allowsAction, deniesAction, etc.)
# and class hierarchy modifications (subClassOf, equivalentClass, etc.).
_ALLOWED_POLICY_PREDICATES = {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://safeclaw.uku.ai/ontology/policy#reason",
    "http://safeclaw.uku.ai/ontology/policy#appliesTo",
    "http://safeclaw.uku.ai/ontology/policy#forbiddenPathPattern",
    "http://safeclaw.uku.ai/ontology/policy#forbiddenCommandPattern",
    "http://safeclaw.uku.ai/ontology/policy#notBefore",
    "http://safeclaw.uku.ai/ontology/policy#notAfter",
    "http://safeclaw.uku.ai/ontology/policy#requiresBefore",
}

# Predicates that must never appear in LLM-generated output
_DANGEROUS_PREDICATES = {
    "http://safeclaw.uku.ai/ontology/policy#allowsAction",
    "http://safeclaw.uku.ai/ontology/policy#deniesAction",
    "http://safeclaw.uku.ai/ontology/policy#deniesWritePath",
    "http://safeclaw.uku.ai/ontology/policy#autonomyLevel",
    "http://safeclaw.uku.ai/ontology/policy#enforcementMode",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",
    "http://www.w3.org/2002/07/owl#equivalentClass",
    "http://www.w3.org/2002/07/owl#imports",
}


def _validate_turtle_semantics(turtle: str) -> list[str]:
    """Validate LLM-generated Turtle for semantic safety before writing to ontology.

    Returns a list of error strings (empty if valid).
    """
    from rdflib import Graph

    prefixes = (
        "@prefix sp: <http://safeclaw.uku.ai/ontology/policy#> .\n"
        "@prefix sc: <http://safeclaw.uku.ai/ontology/agent#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    )
    errors = []

    # Parse with RDFLib to inspect triples
    g = Graph()
    try:
        g.parse(data=prefixes + turtle, format="turtle")
    except Exception as e:
        return [f"Turtle parse error during semantic check: {e}"]

    for _s, p, _o in g:
        pred_str = str(p)

        # Explicit block on dangerous predicates
        if pred_str in _DANGEROUS_PREDICATES:
            short = pred_str.split("#")[-1] if "#" in pred_str else pred_str.split("/")[-1]
            errors.append(
                f"Forbidden predicate '{short}': "
                "LLM-generated policies cannot modify roles or class hierarchies"
            )

        # Allowlist check: only known policy predicates are permitted
        if pred_str not in _ALLOWED_POLICY_PREDICATES:
            # Skip well-known RDF/OWL structural predicates that aren't in either list
            # (e.g., rdf:type is in allowed, but we may see others from parsing)
            if pred_str not in _DANGEROUS_PREDICATES:
                short = pred_str.split("#")[-1] if "#" in pred_str else pred_str.split("/")[-1]
                errors.append(f"Unexpected predicate '{short}': not in allowed policy predicates")

    return errors


@policy_app.command("add-nl")
def add_nl(
    description: str = typer.Argument(
        help="Natural language description of the policy (e.g., 'never allow deleting production databases')"
    ),
):
    """Compile a natural language description into a policy rule using the LLM.

    Requires SAFECLAW_MISTRAL_API_KEY. The LLM generates a Turtle policy
    which is validated for safety (no privilege escalation predicates) and
    shown for confirmation before being applied.

    Example:
      safeclaw policy add-nl "block all file deletions in the /etc directory"
    """
    import asyncio
    from safeclaw.config import SafeClawConfig
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    if client is None:
        console.print(
            "[red]Error: LLM not configured.[/red]\n"
            "Set the SAFECLAW_MISTRAL_API_KEY environment variable:\n"
            "  export SAFECLAW_MISTRAL_API_KEY=your-key-here\n\n"
            "Or use [bold]safeclaw policy add[/bold] to add policies manually."
        )
        raise typer.Exit(1)

    from safeclaw.engine.knowledge_graph import KnowledgeGraph
    from safeclaw.llm.policy_compiler import PolicyCompiler

    kg = KnowledgeGraph()
    kg.load_directory(config.get_ontology_dir())
    compiler = PolicyCompiler(client, kg)

    console.print("[dim]Compiling natural language to Turtle policy...[/dim]")
    result = asyncio.run(compiler.compile(description))

    if not result.success:
        console.print("[red]Error: Failed to compile policy:[/red]")
        for err in result.validation_errors:
            console.print(f"  - {err}")
        console.print(
            "\nTry rephrasing your description or use [bold]safeclaw policy add[/bold] for manual entry."
        )
        raise typer.Exit(1)

    # Validate LLM-generated policy name is safe for Turtle IRI
    import re as _re_nl

    if not _re_nl.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", result.policy_name):
        console.print(
            f"[red]Error: LLM generated an invalid policy name: '{result.policy_name}'.[/red]\n"
            "Try rephrasing your description or use [bold]safeclaw policy add[/bold] for manual entry."
        )
        raise typer.Exit(1)

    # Semantic validation: reject LLM output containing dangerous predicates
    semantic_errors = _validate_turtle_semantics(result.turtle)
    if semantic_errors:
        console.print("[red]Error: LLM generated unsafe policy — rejected:[/red]")
        for err in semantic_errors:
            console.print(f"  - {err}")
        console.print("\nThis is a safety check. The LLM attempted to use forbidden predicates.")
        raise typer.Exit(1)

    console.print(f"\n[bold]Generated policy: {result.policy_name}[/bold]")
    console.print(f"Type: {result.policy_type}")
    console.print(f"\n[dim]{result.turtle}[/dim]\n")

    if typer.confirm("Apply this policy?"):
        policy_file = config.get_ontology_dir() / "safeclaw-policy.ttl"
        safe_desc = description.replace("\n", " ").replace("\r", " ")
        with open(policy_file, "a") as f:
            f.write(f"\n# Added via NL compiler: {safe_desc}\n{result.turtle}\n")
        console.print("[green]Policy applied successfully[/green]")
        console.print(
            "[yellow]Restart the service or use hot-reload for changes to take effect[/yellow]"
        )
    else:
        console.print("[yellow]Policy not applied[/yellow]")
