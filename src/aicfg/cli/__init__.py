import click
from aicfg.cli.commands import cmds
from aicfg.cli.context import context_cli
from aicfg.cli.settings import paths, settings, allowed_tools
from aicfg.cli.servers import mcp_servers
from aicfg.cli.sessions import claude_cli
from aicfg.cli.skills import skills

@click.group()
def cli():
    """AI Config Manager (aicfg)"""
    pass

cli.add_command(cmds)
cli.add_command(context_cli)
cli.add_command(paths)
cli.add_command(settings)
cli.add_command(allowed_tools)
cli.add_command(mcp_servers)
cli.add_command(claude_cli)
cli.add_command(skills)

if __name__ == "__main__":
    cli()