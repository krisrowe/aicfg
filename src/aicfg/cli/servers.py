import click
from rich import print as rprint
from rich.table import Table
from aicfg.sdk import mcp_setup

@click.group(name="mcp")
def mcp_servers():
    """Manage MCP servers."""
    pass

@mcp_servers.command("add")
@click.option("--name", help="Name for the server")
@click.option("--path", help="Local repository path")
@click.option("--command", help="Existing command name")
@click.option("--url", help="Server URL for remote servers")
@click.option("--self", "is_self", is_flag=True, help="Register aicfg itself")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user", help="Where to save")
@click.option("--args", help="CLI arguments for the server")
def add_mcp(name, path, command, url, is_self, scope, args):
    """Register a new MCP server."""
    try:
        result = mcp_setup.register_mcp(
            name=name, path=path, command=command, url=url, 
            is_self=is_self, scope=scope, args=args
        )
        rprint(f"[green]Registered[/green] '{result['name']}' in {result['path']}")
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")

@mcp_servers.command("remove")
@click.argument("name")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user")
def remove_mcp(name, scope):
    """Remove an MCP server."""
    try:
        path, success = mcp_setup.remove_mcp_server(name, scope)
        rprint(f"[green]Removed[/green] '{name}' from {path}")
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")

@mcp_servers.command("list")
@click.option("--scope", type=click.Choice(["user", "project"]), default=None,
              help="Filter by scope (default: show all)")
@click.option("--filter", "filter_pattern", default=None,
              help="Wildcard pattern to filter by any column (e.g., '*food*')")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table",
              help="Output format (default: table)")
def list_mcp(scope, filter_pattern, output_format):
    """List registered MCP servers from project and/or user settings."""
    import json
    result = mcp_setup.list_mcp_servers(scope=scope, filter_pattern=filter_pattern)

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
        return

    # Build title with scope indicator
    title = "MCP Servers"
    if result["scope"] != "all":
        title += f" ({result['scope']} scope)"

    table = Table(title=title)
    table.add_column("Scope", style="magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Command/URL", style="green")

    for entry in result["servers"]:
        cfg = entry["config"]
        cmd_url = cfg.get("url") or cfg.get("command")
        table.add_row(entry["scope"], entry["name"], cmd_url)

    rprint(table)

    # Build footer from summary
    summary = result["summary"]
    if "filter" in summary:
        footer = f"Filter: {summary['filter']} ({summary['shown']} of {summary['total']})"
    else:
        footer = f"{summary['total']} total"
    rprint(f"[dim]{footer}[/dim]")

@mcp_servers.command("show")
@click.argument("name")
@click.option("--scope", type=click.Choice(["user", "project"]), default=None,
              help="Scope to search (default: search both, project first)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def show_mcp(name, scope, output_format):
    """
    Show details for a registered MCP server, including health check.

    Looks up the server by NAME and runs a startup validation to check health.
    """
    import json
    import sys

    result = mcp_setup.get_mcp_server(name, scope=scope)

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
        if not result["found"]:
            sys.exit(1)
        return

    if not result["found"]:
        rprint(f"[red]Error:[/red] {result['error']}")
        sys.exit(1)

    cfg = result["config"]
    health = result["health"]
    status = health["status"]

    # Health badge - big and obvious
    if status == "ok":
        badge = "[bold white on green] ✓ HEALTHY [/bold white on green]"
        version_info = ""
        if health.get("server_name"):
            version_info = f"  [dim]{health['server_name']} v{health.get('server_version', '?')}[/dim]"
        rprint(f"{badge}{version_info}")
    elif status == "skip":
        rprint(f"[bold black on yellow] ⊘ SKIPPED [/bold black on yellow]  [dim]{health.get('reason', '')}[/dim]")
    else:
        rprint(f"[bold white on red] ✗ FAILED [/bold white on red]  [red]{health.get('error', 'Unknown')}[/red]")

    rprint()

    # Details in a simple table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()

    table.add_row("Name", result["name"])
    table.add_row("Scope", result["scope"])
    table.add_row("Type", result["type"])

    if result["type"] == "url":
        table.add_row("URL", cfg.get("url"))
    else:
        table.add_row("Command", cfg.get("command"))
        args = cfg.get("args", [])
        if args:
            table.add_row("Args", " ".join(args))

    rprint(table)
