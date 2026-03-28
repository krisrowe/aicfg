from pathlib import Path
import shutil
import fnmatch
from typing import List, Dict, Optional
from aicfg.sdk.config import (
    get_user_cmds_dir, 
    get_registry_cmds_dir, 
    get_project_cmds_dir, 
    ensure_dirs
)
from aicfg.sdk.utils import save_toml, load_toml, get_file_info

def add_command(name: str, prompt: Optional[str] = None, desc: Optional[str] = None, scope: str = "user", namespace: Optional[str] = None) -> Path:
    ensure_dirs()
    filename = f"{name}.toml"
    
    if scope == "project":
        base_dir = get_project_cmds_dir()
    elif scope == "registry":
        base_dir = get_registry_cmds_dir()
    else:
        base_dir = get_user_cmds_dir()
    
    target_dir = base_dir
    if namespace:
        target_dir = base_dir / namespace
        
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    
    data = {"description": desc or f"Command for {name}", "prompt": prompt or "Write your prompt here..."}
    save_toml(path, data)
    return path

def list_commands(filter_pattern: Optional[str] = None, scopes: Optional[List[str]] = None) -> List[Dict]:
    ensure_dirs()
    user_dir = get_user_cmds_dir()
    registry_dir = get_registry_cmds_dir()
    project_dir = get_project_cmds_dir()
    
    valid_scopes = {"user", "registry", "project"}
    active_scopes = set(scopes) if scopes else valid_scopes
    
    # Helper to get relative names (namespaces included)
    def get_command_names(directory: Path) -> set[str]:
        if not directory.exists(): return set()
        return {str(p.relative_to(directory).with_suffix('')) for p in directory.rglob("*.toml")}

    all_names = set()
    if "user" in active_scopes: all_names.update(get_command_names(user_dir))
    if "registry" in active_scopes: all_names.update(get_command_names(registry_dir))
    if "project" in active_scopes: all_names.update(get_command_names(project_dir))
    
    sorted_names = sorted(list(all_names))
    if filter_pattern: sorted_names = [n for n in sorted_names if fnmatch.fnmatch(n, filter_pattern)]
    
    results = []
    for name in sorted_names:
        # Reconstruct path using name (which might contain subdirs)
        user_path = user_dir / f"{name}.toml"
        reg_path = registry_dir / f"{name}.toml"
        proj_path = project_dir / f"{name}.toml"

        user_info = get_file_info(user_path) if "user" in active_scopes else {"exists": False, "hash": None}
        reg_info = get_file_info(reg_path) if "registry" in active_scopes else {"exists": False, "hash": None}
        proj_info = get_file_info(proj_path) if "project" in active_scopes else {"exists": False, "hash": None}
        
        relevant_infos = [info for scope, info in [("user", user_info), ("registry", reg_info), ("project", proj_info)] if scope in active_scopes]
        present_hashes = [info["hash"] for info in relevant_infos if info["exists"]]
        synced = len(set(present_hashes)) <= 1
            
        results.append({"name": name, "synced": synced, "user": user_info, "registry": reg_info, "project": proj_info})
    return results

def get_command(name: str) -> Optional[Dict]:
    ensure_dirs()
    proj_path = get_project_cmds_dir() / f"{name}.toml"
    user_path = get_user_cmds_dir() / f"{name}.toml"
    reg_path = get_registry_cmds_dir() / f"{name}.toml"
    
    if proj_path.exists(): return load_toml(proj_path)
    if user_path.exists(): return load_toml(user_path)
    if reg_path.exists(): return load_toml(reg_path)
    return None

def delete_command(name: str, scope: str = "user") -> bool:
    ensure_dirs()
    if scope == "user": path = get_user_cmds_dir() / f"{name}.toml"
    elif scope == "project": path = get_project_cmds_dir() / f"{name}.toml"
    elif scope == "registry": path = get_registry_cmds_dir() / f"{name}.toml"
    else: raise ValueError("Invalid scope")
    if path.exists():
        path.unlink()
        return True
    return False

def register_command(name: str, update: bool = False, source_scope: Optional[str] = None) -> Path:
    ensure_dirs()
    registry_dir = get_registry_cmds_dir()
    project_dir = get_project_cmds_dir()
    user_dir = get_user_cmds_dir()
    
    filename = f"{name}.toml"
    user_path = user_dir / filename
    proj_path = project_dir / filename if project_dir.exists() else None
    
    source_path, source_hash = None, None

    if source_scope == "user":
        if not user_path.exists(): raise FileNotFoundError(f"Command '{name}' not found in user scope.")
        source_path, source_hash = user_path, get_file_info(user_path)["hash"]
    elif source_scope == "project":
        if not proj_path or not proj_path.exists(): raise FileNotFoundError(f"Command '{name}' not found in project scope.")
        source_path, source_hash = proj_path, get_file_info(proj_path)["hash"]
    else:
        user_info = get_file_info(user_path)
        proj_info = get_file_info(proj_path) if proj_path else {"exists": False}
        if user_info["exists"] and proj_info["exists"]:
            if user_info["hash"] != proj_info["hash"]:
                raise ValueError(f"Ambiguous source: Command '{name}' exists in both user and project scopes with different content. Please resolve manually or specify --source-scope.")
            source_path, source_hash = proj_path, proj_info["hash"]
        elif user_info["exists"]: source_path, source_hash = user_path, user_info["hash"]
        elif proj_info["exists"]: source_path, source_hash = proj_path, proj_info["hash"]
        else: raise FileNotFoundError(f"Command '{name}' not found in user or project scope.")

    registry_path = registry_dir / filename
    
    # Ensure parent directory exists in registry
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    
    reg_info = get_file_info(registry_path)

    if reg_info["exists"]:
        if reg_info["hash"] == source_hash: return registry_path
        if not update: raise FileExistsError(f"Command '{name}' already exists in the registry with different content. Use --update to overwrite.")
    
    shutil.copy2(source_path, registry_path)
    return registry_path

def publish_command(name: str) -> Optional[Path]:
    ensure_dirs()
    reg_path = get_registry_cmds_dir() / f"{name}.toml"
    user_path = get_user_cmds_dir() / f"{name}.toml"
    if not user_path.exists(): raise FileNotFoundError(f"Command '{name}' not found in User scope.")
    
    # Ensure parent directory exists in registry
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    
    shutil.copy2(user_path, reg_path)
    return reg_path

def install_command(name: str) -> Optional[Path]:
    ensure_dirs()
    user_path = get_user_cmds_dir() / f"{name}.toml"
    reg_path = get_registry_cmds_dir() / f"{name}.toml"
    if not reg_path.exists(): raise FileNotFoundError(f"Command '{name}' not found in Registry.")
    
    # Ensure parent directory exists in user scope
    user_path.parent.mkdir(parents=True, exist_ok=True)
    
    shutil.copy2(reg_path, user_path)
    return user_path

def get_diff(name: str) -> Optional[tuple[List[str], List[str]]]:
    ensure_dirs()
    user_path = get_user_cmds_dir() / f"{name}.toml"
    reg_path = get_registry_cmds_dir() / f"{name}.toml"
    if not user_path.exists() or not reg_path.exists(): return None
    with open(reg_path) as f: reg_lines = f.readlines()
    with open(user_path) as f: user_lines = f.readlines()
    return (reg_lines, user_lines)