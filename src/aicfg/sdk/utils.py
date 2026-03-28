import toml
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import re
import os
import sys
import importlib.metadata

def load_toml(path: Path) -> dict:
    if not path.exists(): return {}
    with open(path, "r") as f: return toml.load(f)

def save_toml(path: Path, data: dict):
    with open(path, "w") as f: toml.dump(data, f)

def get_file_info(path: Path) -> dict:
    if not path.exists(): return {"exists": False, "hash": None, "mtime": None}
    with open(path, "rb") as f:
        content = f.read()
        md5 = hashlib.md5(content).hexdigest()
    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    return {"exists": True, "hash": md5, "mtime": mtime}

def find_mcp_command_in_repo(repo_path: Path) -> Optional[str]:
    setup_py = repo_path / "setup.py"
    pyproject_toml = repo_path / "pyproject.toml"

    if pyproject_toml.exists():
        try:
            data = toml.load(pyproject_toml)
            scripts = data.get("project", {}).get("scripts", {})
            for cmd in scripts:
                if "-mcp" in cmd: return cmd
            entry_points = data.get("project", {}).get("entry-points", {}).get("console_scripts", {})
            for cmd in entry_points:
                if "-mcp" in cmd: return cmd
        except Exception: pass

    if setup_py.exists():
        try:
            with open(setup_py, "r") as f:
                content = f.read()
                match = re.search(r"console_scripts\s*=\s*\[([^\]]+)\]", content, re.DOTALL)
                if match:
                    scripts_str = match.group(1)
                    for line in scripts_str.split('\n'):
                        # Match 'command-mcp=...' or "command-mcp=..."
                        script_match = re.search(r"['\"]([a-zA-Z0-9_-]+-mcp)=", line.strip())
                        if script_match: return script_match.group(1)
        except Exception: pass
            
    return None

def discover_self_mcp_command() -> Optional[str]:
    try:
        distribution = importlib.metadata.distribution("aicfg")
        entry_points = distribution.entry_points
        for entry_point in entry_points:
            if entry_point.group == "console_scripts" and "-mcp" in entry_point.name:
                return entry_point.name
    except importlib.metadata.PackageNotFoundError: pass
    except Exception: pass
    return None

def derive_mcp_name(command_name: str) -> str:
    trimmed_name = command_name.strip()
    if not is_valid_mcp_name(trimmed_name):
        raise ValueError(f"Invalid command name: '{command_name}'")
        
    simplified_name = re.sub(r'(_?mcp-?|_?-mcp_?)', '', trimmed_name, flags=re.IGNORECASE)
    simplified_name = simplified_name.strip('-_')
    
    return simplified_name if simplified_name else trimmed_name

def is_valid_mcp_name(name: str) -> bool:
    if not name: return False
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]+", name))