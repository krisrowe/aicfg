"""CLI commands for cross-tool skill management."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from aicfg.sdk import skills as sdk

console = Console()


@click.group()
def skills():
    """Manage cross-tool AI agent skills."""
    pass


@skills.command(name="list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--target", "-t", type=click.Choice(["claude", "gemini"]), help="Filter by platform")
@click.option("--installed", is_flag=True, default=None, help="Show only installed skills")
@click.option("--not-installed", is_flag=True, default=None, help="Show only not-installed skills")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
def list_skills(category, target, installed, not_installed, fmt):
    """List available skills."""
    if installed and not_installed:
        click.echo("Cannot specify both --installed and --not-installed", err=True)
        sys.exit(1)

    installed_filter = None
    if installed:
        installed_filter = True
    elif not_installed:
        installed_filter = False

    results = sdk.list_skills(category=category, target=target, installed=installed_filter)

    if fmt == "json":
        console.print_json(json.dumps(results))
        return

    if not results:
        click.echo("No skills found.")
        return

    table = Table(title="Skills", expand=True)
    table.add_column("Name", style="cyan", no_wrap=True, ratio=2)
    table.add_column("Description", no_wrap=True, overflow="ellipsis", ratio=4)
    table.add_column("Source", style="dim", no_wrap=True)
    table.add_column("Claude", justify="center", width=6)
    table.add_column("Gemini", justify="center", width=6)

    for s in results:
        claude_status = "[green]✓[/green]" if s["installed"]["claude"] else "[dim]-[/dim]"
        gemini_status = "[green]✓[/green]" if s["installed"]["gemini"] else "[dim]-[/dim]"
        if "claude" not in s["effective_targets"]:
            claude_status = "[dim]n/a[/dim]"
        if "gemini" not in s["effective_targets"]:
            gemini_status = "[dim]n/a[/dim]"

        source = s.get("source", "(local)")
        table.add_row(s["name"], s["description"], source, claude_status, gemini_status)

    console.print(table)


@skills.command()
@click.argument("name")
def show(name):
    """Show full details of a skill."""
    skill = sdk.get_skill(name)
    if not skill:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)

    from rich.panel import Panel
    from rich.text import Text

    console.print(f"\n[bold cyan]{skill['name']}[/bold cyan]")
    console.print(f"  [dim]Description:[/dim] {skill['description']}")
    console.print(f"  [dim]Category:[/dim]    {skill['category'] or '(none)'}")
    console.print(f"  [dim]Invocation:[/dim]  {skill['invocation']}")
    console.print(f"  [dim]Targets:[/dim]     {', '.join(skill['effective_targets'])}")

    for platform, is_installed in skill["installed"].items():
        if platform in skill["effective_targets"]:
            icon = "[green]✓ installed[/green]" if is_installed else "[dim]not installed[/dim]"
            console.print(f"  [dim]{platform}:[/dim]       {icon}")

    # Show body preview
    body_lines = skill["body"].strip().split("\n")
    preview = "\n".join(body_lines[:20])
    if len(body_lines) > 20:
        preview += f"\n... ({len(body_lines) - 20} more lines)"
    console.print(f"\n[dim]--- Body ---[/dim]\n{preview}\n")


@skills.command()
@click.argument("name")
@click.option("--target", "-t", type=click.Choice(["claude", "gemini"]), help="Install to specific platform only")
def install(name, target):
    """Install a skill to configured platforms."""
    try:
        installed = sdk.install_skill(name, target=target)
        for path in installed:
            console.print(f"  [green]✓[/green] {path}")
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@skills.command()
@click.argument("name")
@click.option("--target", "-t", type=click.Choice(["claude", "gemini"]), help="Uninstall from specific platform only")
def uninstall(name, target):
    """Uninstall a skill from platforms."""
    try:
        removed = sdk.uninstall_skill(name, target=target)
        if not removed:
            click.echo(f"'{name}' was not installed on any platform.")
            return
        for path in removed:
            console.print(f"  [red]✗[/red] {path}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
