import click
from rich import print as rprint
from rich.table import Table
from aicfg.sdk import settings as sdk

@click.group()
def paths():
    """Manage context.includeDirectories."""
    pass

@paths.command("list")
@click.option("--scope", type=click.Choice(["user", "project"]), default="project",
              help="Scope (default: project)")
def list_paths(scope):
    path, dirs = sdk.get_include_directories(scope=scope)
    rprint(f"[bold]Config ({scope}):[/bold] {path}")
    if not dirs:
        rprint("[yellow]No paths configured.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Path")
    for d in sorted(dirs): table.add_row(d)
    rprint(table)

@paths.command("add")
@click.argument("path_to_add")
@click.option("--scope", type=click.Choice(["user", "project"]), default="project",
              help="Scope (default: project)")
def add_path(path_to_add, scope):
    config_path = sdk.add_include_directory(path_to_add, scope=scope)
    rprint(f"[green]Added[/green] '{path_to_add}' to {config_path}")
    rprint(f"[blue]Tip:[/blue] Run [bold]/dir add {path_to_add}[/bold] in Gemini to apply instantly.")

@paths.command("remove")
@click.argument("path_to_remove")
@click.option("--scope", type=click.Choice(["user", "project"]), default="project",
              help="Scope (default: project)")
def remove_path(path_to_remove, scope):
    config_path, removed = sdk.remove_include_directory(path_to_remove, scope=scope)
    if removed:
        rprint(f"[green]Removed[/green] '{path_to_remove}' from {config_path}")
        rprint(f"[blue]Tip:[/blue] Run [bold]/dir remove {path_to_remove}[/bold] in Gemini to apply instantly.")
    else:
        rprint(f"[red]Error:[/red] Path '{path_to_remove}' not found in {config_path}")

@click.group(name="allowed-tools")
def allowed_tools():
    """Manage tools.allowed list."""
    pass

@allowed_tools.command("list")
@click.option("--scope", type=click.Choice(["user", "project"]), required=True, help="REQUIRED: Scope for list")
def list_allowed_tools(scope):
    path, tools = sdk.get_allowed_tools(scope)
    rprint(f"[bold]Config ({scope}):[/bold] {path}")
    if not tools:
        rprint("[yellow]No allowed tools configured.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold green")
    table.add_column("Tool Name")
    for t in sorted(tools): table.add_row(t)
    rprint(table)

@allowed_tools.command("add")
@click.argument("tool_name")
@click.option("--scope", type=click.Choice(["user", "project"]), required=True, help="REQUIRED: Scope to add to")
def add_allowed_tool(tool_name, scope):
    path = sdk.add_allowed_tool(tool_name, scope)
    rprint(f"[green]Added[/green] '{tool_name}' to {path}")

@allowed_tools.command("remove")
@click.argument("tool_name")
@click.option("--scope", type=click.Choice(["user", "project"]), required=True, help="REQUIRED: Scope to remove from")
def remove_allowed_tool(tool_name, scope):
    path, success = sdk.remove_allowed_tool(tool_name, scope)
    if success:
        rprint(f"[green]Removed[/green] '{tool_name}' from {path}")
    else:
        rprint(f"[red]Error:[/red] Tool '{tool_name}' not found in {path}")

# NOTE: context-file-names commands moved to aicfg context file-names subgroup.
# See aicfg/cli/context.py

@click.group()
def settings():
    """
    Manage aliased Gemini settings.
    
    This tool manages a curated subset of configuration options.
    For a full list of settings and their effects, see:
    https://geminicli.com/docs/get-started/configuration/
    """
    pass

@settings.command("list")
@click.option("--filter", "-f", help="Filter aliases by name or description")
def list_settings(filter):
    path, aliases, values = sdk.list_settings_by_alias()
    rprint(f"[bold]Active Config:[/bold] {path}")
    table = Table(title="Setting Aliases")
    table.add_column("Alias", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Value", style="green")
    table.add_column("Description", style="italic white")
    for alias in sorted(aliases.keys()):
        info = aliases[alias]
        desc = info.get("description", "")
        if filter and filter.lower() not in alias.lower() and filter.lower() not in desc.lower():
            continue
        val = values.get(alias)
        table.add_row(
            alias, 
            info["path"], 
            str(val) if val is not None else "[dim]not set[/dim]",
            desc
        )
    rprint(table)

@settings.command("set")
@click.argument("alias")
@click.argument("value")
def set_setting(alias, value):
    """
    Set a configuration value by its alias.
    
    To see available aliases and their descriptions, run:
    [bold]aicfg settings list[/bold]
    """
    try:
        path, typed_val, restart = sdk.set_setting_by_alias(alias, value)
        rprint(f"[green]Set[/green] {alias} = {typed_val}")
        if restart:
            rprint("[yellow]Note: You must [bold]/quit[/bold] and run [bold]gemini -r[/bold] to apply this change.[/yellow]")
    except ValueError as e:
        rprint(f"[red]Error:[/red] {e}")

@settings.command("get")
@click.argument("alias")
def get_setting(alias):
    try:
        path, val = sdk.get_setting_by_alias(alias)
        rprint(val)
    except ValueError as e:
        rprint(f"[red]Error:[/red] {e}")