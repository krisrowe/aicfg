import fnmatch
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from aicfg.sdk.config import get_aicfg_tool_repo_dir
from aicfg.sdk.settings import get_settings_path, load_json, save_json
from aicfg.sdk.utils import (
    derive_mcp_name,
    find_mcp_command_in_repo,
    is_valid_mcp_name,
    discover_self_mcp_command
)

def register_mcp(
    name: Optional[str] = None,
    path: Optional[str] = None,
    command: Optional[str] = None,
    url: Optional[str] = None,
    is_self: bool = False,
    scope: str = "user",
    args: Optional[str] = None,
) -> dict:
    """The core logic for registering an MCP server."""

    # 1. Determine Source & Command
    mcp_command = None
    repo_path = None

    if is_self:
        mcp_command = discover_self_mcp_command()
        if not mcp_command:
            raise RuntimeError("Could not discover aicfg's own MCP command. Is it installed correctly?")
        # For --self, ensure it's on PATH (pipx handles this)
        if not shutil.which(mcp_command):
            raise FileNotFoundError(f"aicfg's own MCP command '{mcp_command}' not found in PATH.")
    elif path:
        repo_path = Path(path).expanduser().resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"Path does not exist: {repo_path}")
        
        mcp_command = find_mcp_command_in_repo(repo_path)
        if not mcp_command:
            raise ValueError(f"Could not find an MCP server command (e.g., *-mcp) in {repo_path}")
    elif command:
        if not shutil.which(command):
            raise FileNotFoundError(f"Command not found in PATH: {command}")
        mcp_command = command
    elif url:
        mcp_command = url  # Store URL in command for now
    else:
        raise ValueError("Must provide a PATH, COMMAND, URL, or --self.")

    # 2. Derive and Validate Name
    trimmed_name = ""
    if name:
        trimmed_name = name.strip()
    elif not url: # Only derive if not a URL, URLs require explicit --name
        trimmed_name = derive_mcp_name(mcp_command)
    
    if not is_valid_mcp_name(trimmed_name):
        if url and not name:
             raise ValueError("The --name option is required when registering a URL.")
        raise ValueError(f"Invalid or empty server name: '{trimmed_name}'")

    final_name = trimmed_name
    
    # 3. Check for Conflicts
    settings_path = get_settings_path(scope)
    settings_data = load_json(settings_path)
    if final_name in settings_data.get("mcpServers", {}):
        raise FileExistsError(f"An MCP server with the name '{final_name}' is already registered in {settings_path}.")

    # 4. Validate Server Command (Startup Test for Stdio)
    config = {}
    cli_args = args.split() if args else []
    
    if url:
        config = {"url": url}
    else: # Stdio
        full_command = [mcp_command, "--stdio"] + cli_args
        result = check_mcp_startup(full_command)
        
        if not result["success"]:
             raise ConnectionError(f"Server command '{mcp_command}' failed startup validation. Error: {result.get('error')}")
        
        config = {"command": mcp_command, "args": ["--stdio"] + cli_args}

    # 5. Register and Save
    settings_data.setdefault("mcpServers", {})[final_name] = config
    save_json(settings_path, settings_data)
    
    return {"name": final_name, "config": config, "path": str(settings_path)}

def check_mcp_startup(command_list: list) -> dict:
    """
    Checks if an MCP server starts up correctly by sending an initialize request.
    Returns a dict with 'success', 'response' (JSON), or 'error'.
    """
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "aicfg-check", "version": "1.0"}
        }
    }
    
    try:
        process = subprocess.run(
            command_list,
            input=json.dumps(init_payload).encode(),
            capture_output=True,
            timeout=5,
            check=False 
        )
        
        if process.returncode != 0 and not process.stdout:
             return {"success": False, "error": f"Process exited with code {process.returncode}. Stderr: {process.stderr.decode()}"}

        # Try to parse the first line of stdout
        output_lines = process.stdout.decode().strip().split('\n')
        if not output_lines:
             return {"success": False, "error": "No output received from server."}
             
        try:
            response = json.loads(output_lines[0])
            # Basic validation of JSON-RPC response
            if "result" in response or "error" in response:
                 return {"success": True, "response": response}
            else:
                 return {"success": False, "error": f"Invalid JSON-RPC response: {output_lines[0]}"}
        except json.JSONDecodeError:
             return {"success": False, "error": f"Non-JSON output received: {output_lines[0]}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Connection timed out (server took too long to respond)."}
    except FileNotFoundError:
        return {"success": False, "error": f"Command not found: {command_list[0]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def remove_mcp_server(name: str, scope: str) -> tuple[Path, bool]:
    settings_path = get_settings_path(scope)
    settings_data = load_json(settings_path)
    
    if name not in settings_data.get("mcpServers", {}):
        raise FileNotFoundError(f"MCP server '{name}' not found in {settings_path} ({scope} scope).")
        
    del settings_data["mcpServers"][name]
    save_json(settings_path, settings_data)
    return settings_path, True


def _load_servers_from_scope(scope: str) -> list[dict]:
    """Load servers from a single scope, returning list of {name, scope, config}."""
    results = []
    try:
        settings_path = get_settings_path(scope)
        settings_data = load_json(settings_path)
        servers = settings_data.get("mcpServers", {})
        for name, config in servers.items():
            results.append({
                "name": name,
                "scope": scope,
                "config": config
            })
    except Exception:
        pass
    return results


def _matches_filter(entry: dict, pattern: str) -> bool:
    """Check if any output field matches the wildcard pattern (case-insensitive)."""
    pattern_lower = pattern.lower()
    # Check scope
    if fnmatch.fnmatch(entry["scope"].lower(), pattern_lower):
        return True
    # Check name
    if fnmatch.fnmatch(entry["name"].lower(), pattern_lower):
        return True
    # Check command/url
    cfg = entry["config"]
    cmd_url = cfg.get("url") or cfg.get("command") or ""
    if fnmatch.fnmatch(cmd_url.lower(), pattern_lower):
        return True
    return False


def get_mcp_server(name: str, scope: Optional[str] = None) -> dict:
    """
    Get details for a single MCP server by name, including health check.

    Args:
        name: Server name to look up.
        scope: Optional scope filter ('user', 'project', or None for both).

    Returns:
        Dict with server details and health status, or error if not found.
    """
    result = list_mcp_servers(scope=scope)

    server = None
    for s in result["servers"]:
        if s["name"] == name:
            server = s
            break

    if not server:
        return {
            "found": False,
            "name": name,
            "scope_searched": scope or "all",
            "error": f"Server '{name}' not found"
        }

    cfg = server["config"]

    output = {
        "found": True,
        "name": server["name"],
        "scope": server["scope"],
        "type": "url" if cfg.get("url") else "stdio",
        "config": cfg,
    }

    # Health check for stdio servers
    if cfg.get("url"):
        output["health"] = {"status": "skip", "reason": "URL servers not checked"}
    else:
        full_cmd = [cfg["command"]] + cfg.get("args", [])
        check = check_mcp_startup(full_cmd)

        if check["success"]:
            server_info = check.get("response", {}).get("result", {}).get("serverInfo", {})
            output["health"] = {
                "status": "ok",
                "server_name": server_info.get("name"),
                "server_version": server_info.get("version"),
            }
        else:
            output["health"] = {
                "status": "failed",
                "error": check.get("error", "Unknown error"),
            }

    return output


def list_mcp_servers(
    scope: Optional[str] = None,
    filter_pattern: Optional[str] = None
) -> dict:
    """
    List MCP servers with optional scope and filter.

    Args:
        scope: Optional scope filter ('user', 'project', or None for all).
        filter_pattern: Optional wildcard pattern to match against any output
                        column (scope, name, command/url). Case-insensitive.

    Returns:
        Dict with:
          - servers: List of {name, scope, config} entries
          - filters: Dict of active filters {scope: ..., pattern: ...}
    """
    # Determine which scopes to load
    if scope in ("user", "project"):
        scopes_to_check = [scope]
    else:
        scopes_to_check = ["project", "user"]

    # Load servers from selected scopes
    results = []
    for s in scopes_to_check:
        results.extend(_load_servers_from_scope(s))

    # Track count after scope filter (before pattern filter)
    count_after_scope = len(results)

    # Apply wildcard filter if specified
    if filter_pattern:
        results = [e for e in results if _matches_filter(e, filter_pattern)]

    # Sort by scope (project first), then by name
    results.sort(key=lambda x: (0 if x["scope"] == "project" else 1, x["name"]))

    # Build summary with counts
    summary = {
        "total": count_after_scope,
        "shown": len(results)
    }
    if filter_pattern:
        summary["filter"] = filter_pattern

    return {
        "servers": results,
        "scope": scope if scope in ("user", "project") else "all",
        "summary": summary
    }