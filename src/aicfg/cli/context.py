"""CLI commands for managing AI assistant context files."""
import json
import click
from rich import print as rprint
from rich.table import Table
from aicfg.sdk import context as context_sdk
from aicfg.sdk import settings as settings_sdk


@click.group(name="context")
def context_cli():
    """Manage AI assistant context files."""
    pass


@context_cli.command("status")
@click.option("--scope", type=click.Choice(["user", "project"]), default=None,
              help="Filter to specific scope (default: show all)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def status(scope, output_format):
    """Show the current state of context files for both user and project scopes."""
    result = context_sdk.get_context_status(scope)

    if output_format == "json":
        rprint(json.dumps(result, indent=2))
        return

    rprint(f"[dim]Working directory:[/dim] {result['working_directory']}")
    if result.get("git_root"):
        rprint(f"[dim]Git root:[/dim] {result['git_root']}")
    rprint()

    for scope_name, scope_data in result["scopes"].items():
        table = Table(title=f"{scope_name.title()} Scope")
        table.add_column("File", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")

        for file_name, info in scope_data["files"].items():
            if not info["exists"]:
                file_status = "[yellow]missing[/yellow]"
                details = info["path"]
            elif info["is_symlink"]:
                if info.get("points_to_unified"):
                    file_status = "[green]symlink (unified)[/green]"
                else:
                    file_status = "[red]symlink (other)[/red]"
                details = f"-> {info['symlink_target']}"
            else:
                file_status = "present"
                details = info["path"]

            table.add_row(file_name, file_status, details)

        rprint(table)
        rprint(f"[dim]State: {scope_data['state']}[/dim]\n")


@context_cli.command("unify")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user",
              help="Scope to unify (default: user)")
def unify(scope):
    """
    Unify CLAUDE.md and GEMINI.md into a single shared CONTEXT.md.

    Combines context files into a unified location, then creates symlinks
    so both tools read from the same file.

    This operation is idempotent - running it multiple times is safe.
    """
    result = context_sdk.unify_context(scope)

    if result["success"]:
        rprint(f"[green]Success![/green]\n")
        rprint(result["message"])

        if result.get("backups"):
            rprint(f"\n[dim]Backups created:[/dim]")
            for backup in result["backups"]:
                rprint(f"  [dim]{backup}[/dim]")

        if result.get("symlinks_created"):
            rprint(f"\n[dim]Symlinks created:[/dim]")
            for symlink in result["symlinks_created"]:
                rprint(f"  [dim]{symlink}[/dim]")
    else:
        rprint(f"[red]Failed![/red]\n")
        rprint(result.get("message", result.get("error", "Unknown error")))
        raise SystemExit(1)


@context_cli.command("analyze")
@click.argument("scope", type=click.Choice(["user", "project", "all"]))
@click.argument("prompt")
@click.option("--model", default=None, help="Gemini model override")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def analyze(scope, prompt, model, output_format):
    """
    Analyze context files using Gemini.

    SCOPE: 'user', 'project', or 'all' to analyze both scopes together.

    PROMPT: Your question or analysis request about the context files.
    """
    result = context_sdk.analyze_context(scope, prompt, model)

    if output_format == "json":
        rprint(json.dumps(result, indent=2))
        return

    if result.get("success"):
        rprint(result["response"])
    else:
        rprint(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")
        raise SystemExit(1)


@context_cli.command("revise")
@click.argument("scope", type=click.Choice(["user", "project"]))
@click.argument("prompt")
@click.option("--model", default=None, help="Gemini model override")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def revise(scope, prompt, model, output_format):
    """
    Revise context file using Gemini.

    SCOPE: 'user' or 'project' (cannot revise both at once).

    PROMPT: Instructions for how to modify the context file.
    """
    result = context_sdk.revise_context(scope, prompt, model)

    if output_format == "json":
        rprint(json.dumps(result, indent=2))
        return

    if result.get("success"):
        rprint(f"[green]Success![/green] {result['message']}")
        rprint(f"[dim]Backup: {result['backup']}[/dim]")
    else:
        rprint(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")
        raise SystemExit(1)


# Subgroup for file-names management (Gemini-specific setting)
@context_cli.group(name="file-names")
def file_names():
    """Manage context.fileName setting (Gemini-specific)."""
    pass


@file_names.command("list")
def list_file_names():
    """List configured context file names."""
    path, files = settings_sdk.get_context_files()
    rprint(f"[bold]Config:[/bold] {path}")
    if not files:
        rprint("[yellow]No context files configured.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("File Name")
    for f in sorted(files):
        table.add_row(f)
    rprint(table)


@file_names.command("add")
@click.argument("filename")
def add_file_name(filename):
    """Add a context file name."""
    path = settings_sdk.add_context_file(filename)
    rprint(f"[green]Added[/green] '{filename}' to {path}")


@file_names.command("remove")
@click.argument("filename")
def remove_file_name(filename):
    """Remove a context file name."""
    path, removed = settings_sdk.remove_context_file(filename)
    if removed:
        rprint(f"[green]Removed[/green] '{filename}' from {path}")
    else:
        rprint(f"[red]File '{filename}' not found in {path}[/red]")
