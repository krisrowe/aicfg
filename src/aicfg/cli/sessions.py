"""CLI commands for Claude Code session search."""

import json
import re
import sys

import click

from aicfg.sdk.sessions import (
    collect_recent_session_files,
    find_sessions,
    format_results,
    DEFAULT_MOST_RECENT,
)


@click.group(name="claude")
def claude_cli():
    """Claude Code utilities."""
    pass


@claude_cli.command(name="find-session")
@click.argument("patterns", nargs=-1, required=True)
@click.option("--all", "match_all", is_flag=True, help="Require ALL patterns to match (default: any)")
@click.option("--most-recent", type=int, default=DEFAULT_MOST_RECENT, help=f"Sessions to search (default: {DEFAULT_MOST_RECENT})")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--max-snippets", type=int, default=3, help="Max snippets per session (default: 3)")
def find_session(patterns, match_all, most_recent, as_json, max_snippets):
    """Search recent Claude Code sessions for keywords or patterns.

    Multiple PATTERNS are OR by default. Use --all for AND.
    """
    for p in patterns:
        try:
            re.compile(p)
        except re.error as e:
            click.echo(f"Invalid pattern '{p}': {e}", err=True)
            sys.exit(1)

    matches = find_sessions(
        patterns=list(patterns),
        match_all=match_all,
        most_recent=most_recent,
        max_snippets=max_snippets,
    )

    if as_json:
        click.echo(json.dumps(matches, indent=2))
        return

    searched = len(collect_recent_session_files(most_recent))
    output = format_results(matches, list(patterns), match_all, most_recent, searched)
    click.echo(output)
