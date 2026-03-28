import click
import toml
import json
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from aicfg.sdk import commands as sdk

console = Console()

@click.group()
def cmds():
    """Manage Gemini slash commands (TOML files)."""
    pass

@cmds.command()
@click.argument("name")
@click.argument("prompt", required=False)
@click.option("--desc", "-d", help="Description of the command")
@click.option("--scope", type=click.Choice(["user", "project"]),
default="user", help="Where to create the command (default: user)")
@click.option("--namespace", "-ns", help="Optional namespace (subdirectory) for the command")
def add(name, prompt, desc, scope, namespace):
    """Add a new command."""
    if not prompt:
        description = desc or "My custom command"
        default_content = (
            f'description = "{description}"\n'
            'prompt = """\n'
            'Write your prompt here...\n'
            '"""'
        )
        edited = click.edit(default_content, extension=".toml")
        if not edited:
            rprint("[red]Aborted.[/red] No content provided.")
            return
        try:
            data = toml.loads(edited)
            prompt = data.get("prompt")
            desc = data.get("description", desc)
        except Exception as e:
            rprint(f"[red]Invalid TOML:[/red] {e}")
            return

    path = sdk.add_command(name, prompt, desc, scope=scope, namespace=namespace)
    rprint(f"[green]Created[/green] {path} (Scope: [bold]{scope.upper()}[/bold])")

@cmds.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--format", type=click.Choice(["text", "json"]),
default="text", help="Output format.")
@click.option("--filter", "filter_pattern", help="Filter by name (supports wildcards e.g. 'commit*')")
@click.option("--scope", "scopes", multiple=True, type=click.Choice(["user", "registry", "project"]),
help="Filter by scope (can specify multiple)")
def list_cmds(as_json, format, filter_pattern, scopes):
    """List all commands. Optional filters for name and scope."""
    
    # Convert tuple to list for SDK, or None if empty (implies all) 
    scope_list = list(scopes) if scopes else None
    
    results = sdk.list_commands(filter_pattern=filter_pattern, scopes=scope_list)
    results = sorted(results, key=lambda x: x["name"])
    
    if as_json or format == "json":
        console.print_json(data=results)
        return

    table = Table(title="Custom Slash Commands")
    table.add_column("Command", style="cyan")
    
    # Determine which columns to show
    show_user = not scope_list or "user" in scope_list
    show_reg = not scope_list or "registry" in scope_list
    show_proj = not scope_list or "project" in scope_list
    
    if show_user: table.add_column("User", justify="center")
    if show_reg: table.add_column("Registry", justify="center")
    if show_proj: table.add_column("Project", justify="center")

    for item in results:
        # Define icons
        # Green check if identical (synced), Yellow not-equal sign if diff
        synced = item["synced"]
        icon = "[green]✅[/green]" if synced else "[yellow] ≠ [/yellow]"
        
        row = [item["name"]]
        
        if show_user:
            row.append(icon if item["user"]["exists"] else "[dim]- [/dim]")
        if show_reg:
            row.append(icon if item["registry"]["exists"] else "[dim]- [/dim]")
        if show_proj:
            row.append(icon if item["project"]["exists"] else "[dim]- [/dim]")
        
        table.add_row(*row)

    console.print(table)

@cmds.command()
@click.argument("name")
@click.option("--update", is_flag=True, help="Overwrite if command exists in registry and content differs.")
@click.option("--source-scope", type=click.Choice(["user", "project"]), help="Explicitly choose source scope for registration.")
def register(name, update, source_scope):
    """Register a command from user/project scope to the registry."""
    try:
        path = sdk.register_command(name, update=update, source_scope=source_scope)
        rprint(f"[green]Registered[/green] '{name}' to {path}")
        rprint(f"[blue]Note:[/blue] Changes to the registry repo ({path.parent}) will need to be committed and pushed to GitHub.")
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        rprint(f"[red]Error:[/red] {e}")
        exit(1)

@cmds.command()
@click.argument("name")
def show(name):
    """Show details of a command."""
    data = sdk.get_command(name)
    if not data:
        rprint(f"[red]Error:[/red] Command '{name}' not found.")
        return
    
    rprint(f"[bold]Description:[/bold] {data.get('description')}")
    rprint("[bold]Prompt:[/bold]")
    rprint(data.get("prompt"))

@cmds.command()
@click.argument("name")
@click.option("--scope", type=click.Choice(["user", "project", "registry"]),
default="user", help="Scope to remove from (default: user)")
def remove(name, scope):
    """Remove a command from local, project, or registry scope."""
    success = sdk.delete_command(name, scope=scope)
    if success:
        rprint(f"[green]Removed[/green] '{name}' from {scope} scope.")
    else:
        rprint(f"[red]Error:[/red] Command '{name}' not found in {scope} scope.")

@cmds.command()
@click.argument("name")
def publish(name):
    """Publish a command from User scope to the Registry."""
    try:
        path = sdk.publish_command(name)
        rprint(f"[green]Published[/green] '{name}' to Registry ({path})")
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")

@cmds.command()
@click.argument("name")
def install(name):
    """Install a command from Registry to User scope."""
    try:
        path = sdk.install_command(name)
        rprint(f"[green]Installed[/green] '{name}' to User scope ({path})")
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")

@cmds.command()
@click.argument("name")
def diff(name):
    """Show differences between User and Registry versions."""
    result = sdk.get_diff(name)
    if not result:
        rprint(f"Command '{name}' cannot be diffed (must exist in both User and Registry).")
        return

    repo_lines, xdg_lines = result
    import difflib
    
    diff = difflib.unified_diff(
        repo_lines, xdg_lines,
        fromfile=f"Registry ({name})",
        tofile=f"User ({name})",
        lineterm=""
    )
    
    for line in diff:
        if line.startswith("+"):
            console.print(line, style="green", end="")
        elif line.startswith("-"):
            console.print(line, style="red", end="")
        elif line.startswith("@"):
            console.print(line, style="cyan", end="")
        else:
            print(line, end="")
