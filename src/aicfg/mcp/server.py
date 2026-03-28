import json
import logging
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
from aicfg.sdk import commands as cmds_sdk
from aicfg.sdk import settings as settings_sdk
from aicfg.sdk import mcp_setup as mcp_sdk
from aicfg.sdk import skills as skills_sdk

logger = logging.getLogger(__name__)
mcp = FastMCP("aicfg")

@mcp.tool()
async def add_slash_command(
    name: str,
    prompt: str,
    description: Optional[str] = None,
    namespace: Optional[str] = None
) -> dict[str, Any]:
    """
    Add a new slash command to the local configuration.
    
    Args:
        name: Command name (e.g. 'fix-bug')
        prompt: The prompt text for the command
        description: Short description
        namespace: Optional namespace (subdirectory) for the command
    """
    try:
        path = cmds_sdk.add_command(name, prompt, description, namespace=namespace)
        return {"success": True, "path": str(path), "status": "PRIVATE"}
    except Exception as e:
        logger.error(f"Error adding command: {e}")
        return {"error": str(e)}

@mcp.tool()
async def publish_slash_command(name: str) -> dict[str, Any]:
    """
    Publish a local slash command to the common configuration registry.
    
    Args:
        name: The name of the command to publish (e.g., 'fix-bug').
    """
    try:
        registry_path = cmds_sdk.publish_command(name)
        return {
            "success": True, 
            "registry_path": str(registry_path), 
            "status": "PUBLISHED",
            "message": f"Command '{name}' published to registry. Remember to commit changes in gemini-common-config."
        }
    except Exception as e:
        logger.error(f"Error publishing command: {e}")
        return {"error": str(e)}

@mcp.tool()
async def get_slash_command(name: str) -> dict[str, Any]:
    """
    Retrieve the full definition of a slash command.
    
    Args:
        name: The name of the command to retrieve.
    """
    try:
        command = cmds_sdk.get_command(name)
        if command:
            return {"name": name, "definition": command}
        return {"error": f"Command '{name}' not found."}
    except Exception as e:
        logger.error(f"Error getting command: {e}")
        return {"error": str(e)}

@mcp.tool()
async def list_mcp_servers(
    scope: Optional[str] = None,
    filter_pattern: Optional[str] = None
) -> dict[str, Any]:
    """
    List all registered MCP servers with optional filtering.

    Args:
        scope: Optional scope filter ('user' or 'project'). Default shows all scopes.
        filter_pattern: Optional wildcard pattern to match against any output
                        column (scope, name, command/url). Case-insensitive.

    Returns:
        Dict with:
          - servers: List of {name, scope, config} entries
          - filters: Dict of active filters (scope, pattern) or None if no filters
    """
    try:
        return mcp_sdk.list_mcp_servers(scope=scope, filter_pattern=filter_pattern)
    except Exception as e:
        logger.error(f"Error listing MCP servers: {e}")
        return {"error": str(e)}

@mcp.tool()
async def list_slash_commands(filter_pattern: Optional[str] = None) -> dict[str, Any]:
    """
    List all available slash commands and their status.
    
    Args:
        filter_pattern: Optional shell-style wildcard pattern to filter by name (e.g. "commit*").

    Note: When presenting these to the user, it is recommended to use the following 'Icon [space] Scope Name' format for clarity:
    - 👤 User
    - ☁️ Registry
    - 🏠 Project
    """
    try:
        results = cmds_sdk.list_commands(filter_pattern=filter_pattern)
        return {"commands": results}
    except Exception as e:
        return {"error": str(e)}

# NOTE: add_context_path intentionally not exposed as MCP tool.
# See DESIGN.md "Context Include Paths (CLI-only)" for rationale.

@mcp.tool()
async def check_mcp_server_startup(command: str, args: Optional[list[str]] = None) -> dict[str, Any]:
    """
    Smoke test an MCP server command to see if it starts up correctly (STDIO).
    
    This is the best way to verify if an MCP server command is working or not if you've 
    already confirmed that it's registered with the agent (e.g. via 'gemini mcp list') 
    and you are seeing it listed with an unhealthy status (e.g. Disconnected).
    
    If you reference an MCP tool that the agent cannot find, first check the list of 
    registered MCP servers. If one reports unhealth, invoke this tool to diagnose the
    startup issue.
    
    Args:
        command: The command to execute (e.g., 'uv', 'python', 'my-mcp-server').
        args: Optional list of arguments for the command.
    """
    try:
        full_cmd = [command] + (args or [])
        return mcp_sdk.check_mcp_startup(full_cmd)
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def list_skills(
    target: Optional[str] = None,
) -> dict[str, Any]:
    """List available cross-tool skills with optional filtering.

    Args:
        target: Filter by platform ('claude' or 'gemini')
    """
    try:
        results = skills_sdk.list_skills(target=target)
        return {"skills": results}
    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        return {"error": str(e)}

@mcp.tool()
async def get_skill(name: str) -> dict[str, Any]:
    """Get full details of a skill including metadata and instructions.

    Args:
        name: The skill name (e.g. 'find-session')
    """
    try:
        result = skills_sdk.get_skill(name)
        if result:
            return result
        return {"error": f"Skill '{name}' not found."}
    except Exception as e:
        logger.error(f"Error getting skill: {e}")
        return {"error": str(e)}

@mcp.tool()
async def install_skill(name: str, target: Optional[str] = None) -> dict[str, Any]:
    """Install a skill to configured platforms.

    Args:
        name: The skill name (e.g. 'find-session')
        target: Optional platform to install to ('claude' or 'gemini'). Default: all supported.
    """
    try:
        installed = skills_sdk.install_skill(name, target=target)
        return {"success": True, "installed": installed}
    except Exception as e:
        logger.error(f"Error installing skill: {e}")
        return {"error": str(e)}

@mcp.tool()
async def uninstall_skill(name: str, target: Optional[str] = None) -> dict[str, Any]:
    """Uninstall a skill from platforms.

    Args:
        name: The skill name (e.g. 'find-session')
        target: Optional platform to uninstall from ('claude' or 'gemini'). Default: all.
    """
    try:
        removed = skills_sdk.uninstall_skill(name, target=target)
        return {"success": True, "removed": removed}
    except Exception as e:
        logger.error(f"Error uninstalling skill: {e}")
        return {"error": str(e)}

@mcp.resource("aicfg://commands")
async def commands_resource() -> str:
    """List of all slash commands as a JSON resource."""
    results = cmds_sdk.list_commands()
    return json.dumps(results, indent=2)

def run_server():
    mcp.run()

if __name__ == "__main__":
    run_server()