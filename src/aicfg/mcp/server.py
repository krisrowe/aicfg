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
async def skills_marketplaces_list() -> dict[str, Any]:
    """List registered skill marketplaces.

    Marketplaces are where published skills live. The install_skill
    tool can only install skills that have been published to a
    marketplace. Use the publish_skill tool to push a locally-authored
    skill to a central (and typically remote) marketplace.

    IMPORTANT: Writing files to a local path or local repo clone will
    NOT make skills available to the install_skill tool. Marketplaces
    are typically configured as remote central repositories, and the
    install_skill tool reads from them accordingly. The publish_skill
    tool is the only reliable way to get a skill into a marketplace
    where the install_skill tool will find it.

    Returns:
        marketplaces: List of {alias, url} entries.
    """
    try:
        results = skills_sdk.marketplace_list()
        return {"marketplaces": results}
    except Exception as e:
        logger.error(f"Error listing marketplaces: {e}")
        return {"error": str(e)}

@mcp.tool()
async def list_skills(
    installed: Optional[str] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """List skills from all registered marketplaces and locally installed.

    Shows both published (available in marketplaces) and installed
    (copied to platform skill directories) skills.

    Each skill result includes:
      - name: Skill name.
      - description: From SKILL.md frontmatter.
      - effective_targets: Platforms this skill supports (['claude', 'gemini']).
      - installed: {platform: bool} showing install status per platform.
      - source: Which marketplace the skill came from. '-' if unknown.
      - source_path: Where the skill lives within its marketplace.
      - status (installed skills only): One of:
          'current'   — installed copy matches the marketplace.
          'modified'  — edited locally since install.
          'outdated'  — marketplace has a newer version.
          'conflict'  — both modified locally and outdated.
          'untracked' — installed but not from a marketplace.

    Args:
        installed: Filter by install status. None (default) shows all.
                   'any' = installed on at least one platform.
                   'none' = not installed anywhere.
                   'claude' = installed on claude.
                   'gemini' = installed on gemini.
        refresh: Force refresh of marketplace cache (5-minute TTL)
                 before reading. Avoid refreshing on every call.
    """
    try:
        results = skills_sdk.list_skills(installed=installed, refresh=refresh)
        return {"skills": results}
    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        return {"error": str(e)}

@mcp.tool()
async def get_skill(name: str, refresh: bool = False) -> dict[str, Any]:
    """Get full details of a skill including metadata and instructions.

    Returns installed status, SKILL.md content, and marketplace
    availability. Use refresh=True to force a cache update if you
    expect recent changes (5-minute TTL). Avoid refreshing on every
    call.

    Args:
        name: The skill name (e.g. 'find-session')
        refresh: Force refresh of marketplace cache before reading.
    """
    try:
        result = skills_sdk.get_skill(name, refresh=refresh)
        if result:
            return result
        return {"error": f"Skill '{name}' not found."}
    except Exception as e:
        logger.error(f"Error getting skill: {e}")
        return {"error": str(e)}

@mcp.tool()
async def install_skill(name: str, platform: Optional[str] = None) -> dict[str, Any]:
    """Install a skill to local platform directories.

    Given a skill name, this tool looks for it in a central marketplace
    (generally non-local). A skill must first be published to a
    marketplace using the publish_skill tool before this tool can find
    it. Writing a SKILL.md to a local directory will typically not
    make it installable.

    Result codes:
      - newly_installed: First install.
      - content_updated: Marketplace has newer content than what was
        previously installed.
      - document_unchanged: Already up to date (still copies to targets).
      - failed: Installation did not succeed.

    Response includes:
      - success (bool)
      - result (str): One of the result codes above.
      - installed (dict): Where the skill was installed from — source,
        url, path, document {version, hash, length}.
      - previous (dict, omitted for newly_installed/failed): What was
        installed before this update.
      - targets (list[str]): Platform directories where skill was copied.
      - message (str): Human-readable summary.

    Args:
        name: Skill name (e.g. 'find-session'), optionally prefixed
              with marketplace alias (e.g. 'krisrowe/skills/find-session').
        platform: Platform to install to ('claude' or 'gemini'). Default: all supported.
    """
    return skills_sdk.install_skill(name, platform=platform)

@mcp.tool()
async def uninstall_skill(name: str, platform: Optional[str] = None) -> dict[str, Any]:
    """Uninstall a skill from platforms.

    Args:
        name: The skill name (e.g. 'find-session')
        platform: Optional platform to uninstall from ('claude' or 'gemini'). Default: all.
    """
    try:
        removed = skills_sdk.uninstall_skill(name, platform=platform)
        return {"success": True, "removed": removed}
    except Exception as e:
        logger.error(f"Error uninstalling skill: {e}")
        return {"error": str(e)}

@mcp.tool()
async def publish_skill(
    name: str,
    platform: Optional[str] = None,
    marketplace: Optional[str] = None,
    path: Optional[str] = None,
    source_path: Optional[str] = None,
    message: Optional[str] = None,
) -> dict[str, Any]:
    """Publish a locally-authored skill to a marketplace.

    This is how skills become available to the install_skill tool.
    Takes a skill from a local source (either an installed platform
    copy or a directory on disk) and pushes it to the marketplace.

    Two source flows:
      - Skill already installed to a platform: pass name (and
        optionally platform to disambiguate).
      - Skill authored locally but not yet installed: pass name and
        source_path pointing to the directory containing SKILL.md.

    Result codes:
      - published: Pushed to marketplace successfully.
      - no_changes: Skill already matches what's in the marketplace.
      - failed: Publish did not succeed.

    The response includes a ``git_ops`` list with each step taken
    during publish — for review and debugging only.

    Args:
        name: Skill name (must exist locally or at source_path).
        platform: Which platform's installed copy to use ('claude' or
                  'gemini'). Auto-detected if omitted. Cannot be used
                  with source_path.
        marketplace: Target marketplace alias. Defaults to the
                     marketplace the skill is already associated with
                     (via a prior install_skill or publish_skill).
                     Required for skills not yet associated with any
                     marketplace.
        path: Destination path within the marketplace (e.g.
              'coding/my-skill'). Defaults to prior path or skill name.
        source_path: Absolute path to a local skill directory containing
                     SKILL.md. Use this for skills not yet installed to
                     any platform. Cannot be used with platform.
        message: Git commit message. Default: 'Publish skill: <name>'.
    """
    return skills_sdk.publish_skill(
        name, platform=platform, marketplace=marketplace,
        path=path, source_path=source_path, message=message,
    )

@mcp.resource("aicfg://commands")
async def commands_resource() -> str:
    """List of all slash commands as a JSON resource."""
    results = cmds_sdk.list_commands()
    return json.dumps(results, indent=2)

def run_server():
    mcp.run()

if __name__ == "__main__":
    run_server()