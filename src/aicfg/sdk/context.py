"""SDK for managing AI assistant context files."""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


def _home_relative(path: Path) -> str:
    """Return path as ~/... if under home, else absolute."""
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def _get_git_root() -> Optional[Path]:
    """Get git repository root, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _get_file_paths(scope: str) -> dict:
    """
    Get the expected file paths for a given scope.

    Returns dict with keys: context, claude, gemini
    Each value is a Path object.
    """
    if scope == "user":
        return {
            "context": Path.home() / ".config" / "ai-common" / "CONTEXT.md",
            "claude": Path.home() / ".claude" / "CLAUDE.md",
            "gemini": Path.home() / ".gemini" / "GEMINI.md",
        }
    else:  # project
        git_root = _get_git_root() or Path.cwd()
        return {
            "context": git_root / ".config" / "ai-common" / "CONTEXT.md",
            "claude": git_root / ".claude" / "CLAUDE.md",
            "gemini": git_root / ".gemini" / "GEMINI.md",
        }


def _get_file_status(path: Path, unified_path: Path) -> dict:
    """Get status info for a single file."""
    status = {
        "path": _home_relative(path),
        "absolute_path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "is_symlink": False,
        "symlink_target": None,
        "points_to_unified": False,
    }

    if not path.exists():
        status["status"] = "missing"
    elif path.is_symlink():
        status["is_symlink"] = True
        target = path.resolve()
        status["symlink_target"] = _home_relative(target)
        if target == unified_path.resolve():
            status["status"] = "symlink (unified)"
            status["points_to_unified"] = True
        else:
            status["status"] = "symlink (other)"
    else:
        status["status"] = "present"

    return status


def get_context_status(scope: Optional[str] = None) -> dict:
    """
    Get the current state of context files.

    Args:
        scope: 'user', 'project', or None for both.

    Returns:
        Dict with file statuses organized by scope.
    """
    result = {
        "working_directory": str(Path.cwd()),
        "git_root": None,
        "scopes": {}
    }

    git_root = _get_git_root()
    if git_root:
        result["git_root"] = _home_relative(git_root)

    scopes_to_check = [scope] if scope in ("user", "project") else ["user", "project"]

    for s in scopes_to_check:
        paths = _get_file_paths(s)
        unified_path = paths["context"]

        scope_status = {
            "files": {
                "CONTEXT.md": _get_file_status(paths["context"], unified_path),
                "CLAUDE.md": _get_file_status(paths["claude"], unified_path),
                "GEMINI.md": _get_file_status(paths["gemini"], unified_path),
            }
        }

        # Determine scope state
        claude_unified = scope_status["files"]["CLAUDE.md"]["points_to_unified"]
        gemini_unified = scope_status["files"]["GEMINI.md"]["points_to_unified"]
        context_exists = scope_status["files"]["CONTEXT.md"]["exists"]

        if context_exists and claude_unified and gemini_unified:
            scope_status["state"] = "unified"
        elif claude_unified or gemini_unified:
            scope_status["state"] = "partial"
        elif context_exists:
            scope_status["state"] = "context_only"
        else:
            scope_status["state"] = "not_unified"

        result["scopes"][s] = scope_status

    return result


def _read_file_if_present(path: Path) -> Optional[str]:
    """Read file content if it exists and is not a symlink."""
    if not path.exists():
        return None
    if path.is_symlink():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def unify_context(scope: str = "user") -> dict:
    """
    Unify CLAUDE.md and GEMINI.md into a single CONTEXT.md with symlinks.

    Args:
        scope: 'user' or 'project'

    Returns:
        Dict with success status and details.
    """
    paths = _get_file_paths(scope)
    unified_path = paths["context"]

    result = {
        "success": False,
        "scope": scope,
        "unified_file": _home_relative(unified_path),
        "sources": [],
        "backups": [],
        "symlinks_created": [],
        "message": ""
    }

    # Validate existing symlinks don't point somewhere unexpected
    for key in ["claude", "gemini"]:
        path = paths[key]
        name = f"{key.upper()}.md"
        if path.is_symlink():
            target = path.resolve()
            if target != unified_path.resolve():
                result["error"] = f"{name} is a symlink pointing to unexpected location"
                result["message"] = (
                    f"Cannot proceed: {name} is a symlink pointing to {target}.\n"
                    f"Expected: {unified_path}\n"
                    "Please manually resolve this before running unify."
                )
                return result

    # Check if already unified
    claude_is_unified = paths["claude"].is_symlink() and paths["claude"].resolve() == unified_path.resolve()
    gemini_is_unified = paths["gemini"].is_symlink() and paths["gemini"].resolve() == unified_path.resolve()

    if claude_is_unified and gemini_is_unified:
        result["success"] = True
        result["message"] = f"Already unified. Both CLAUDE.md and GEMINI.md are symlinks to CONTEXT.md ({scope} scope)."
        return result

    # Read source content
    claude_content = _read_file_if_present(paths["claude"])
    gemini_content = _read_file_if_present(paths["gemini"])

    if not claude_content and not gemini_content:
        result["error"] = "No source files found"
        result["message"] = f"Neither CLAUDE.md nor GEMINI.md exists for {scope} scope. Nothing to unify."
        return result

    # Ensure unified directory exists
    unified_path.parent.mkdir(parents=True, exist_ok=True)

    # Build unified content
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing_content = ""
    if unified_path.exists() and not unified_path.is_symlink():
        existing_content = unified_path.read_text(encoding="utf-8")

    new_sections = []

    if claude_content:
        result["sources"].append({"name": "CLAUDE.md", "path": _home_relative(paths["claude"])})
        header = f"*** CONTEXT IMPORTED FROM CLAUDE.md ({timestamp}) ***"
        new_sections.append(f"{header}\n\n{claude_content.strip()}")

    if gemini_content:
        result["sources"].append({"name": "GEMINI.md", "path": _home_relative(paths["gemini"])})
        header = f"*** CONTEXT IMPORTED FROM GEMINI.md ({timestamp}) ***"
        new_sections.append(f"{header}\n\n{gemini_content.strip()}")

    # Combine content
    if existing_content:
        unified_content = existing_content.strip() + "\n\n" + "\n\n".join(new_sections)
    else:
        unified_content = "\n\n".join(new_sections)

    # Write unified file
    unified_path.write_text(unified_content + "\n", encoding="utf-8")

    # Backup and symlink sources
    for key in ["claude", "gemini"]:
        path = paths[key]
        if path.exists() and not path.is_symlink():
            backup_path = path.with_suffix(".md.bak")
            path.rename(backup_path)
            result["backups"].append(_home_relative(backup_path))

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(unified_path)
            result["symlinks_created"].append(_home_relative(path))

    result["success"] = True

    source_names = [s["name"] for s in result["sources"]]
    if len(source_names) == 2:
        result["message"] = (
            f"Unified {source_names[0]} and {source_names[1]} into {_home_relative(unified_path)}.\n\n"
            f"Both files were combined with section headers:\n"
            f"  - '*** CONTEXT IMPORTED FROM CLAUDE.md ({timestamp}) ***'\n"
            f"  - '*** CONTEXT IMPORTED FROM GEMINI.md ({timestamp}) ***'\n\n"
            "Please review and thoughtfully integrate the content in a cohesive, "
            "non-duplicative way. Remove redundant sections and organize logically."
        )
    elif len(source_names) == 1:
        result["message"] = (
            f"Copied {source_names[0]} to {_home_relative(unified_path)} and created symlinks.\n"
            "Only one source file existed, so no merging was needed."
        )

    return result


def _build_analyze_prompt(status: dict, scope: str, user_prompt: str) -> str:
    """Build the full prompt for Gemini analysis."""
    sections = []

    # Working directory context
    git_root = status.get("git_root")
    cwd = status.get("working_directory")
    if git_root:
        sections.append(f"Working directory: {cwd}\nGit repository root: {git_root}")
    else:
        sections.append(f"Working directory: {cwd} (not a git repository)")

    # Status JSON
    scope_status = status["scopes"].get(scope, {})
    sections.append(f"*** CONTEXT STATUS ({scope} scope) ***\n\n{json.dumps(scope_status, indent=2)}")

    # File contents
    paths = _get_file_paths(scope)
    for name, path in [("CONTEXT.md", paths["context"]),
                       ("CLAUDE.md", paths["claude"]),
                       ("GEMINI.md", paths["gemini"])]:
        content = _read_file_if_present(path)
        if content:
            sections.append(f"*** {_home_relative(path)} ***\n\n{content.strip()}")

    # User prompt
    sections.append(f"*** USER QUESTION ***\n\n{user_prompt}")

    return "\n\n".join(sections)


def analyze_context(scope: str, prompt: str, model: Optional[str] = None) -> dict:
    """
    Analyze context files using Gemini.

    Args:
        scope: 'user', 'project', or 'all'
        prompt: User's analysis question
        model: Optional model override

    Returns:
        Dict with analysis result.
    """
    try:
        from google import genai
    except ImportError:
        return {
            "success": False,
            "error": "google-genai not installed. Run: pip install google-genai"
        }

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "GEMINI_API_KEY environment variable not set"
        }

    # Get status for the requested scope(s)
    if scope == "all":
        status = get_context_status(None)  # Both scopes
    else:
        status = get_context_status(scope)

    # Build prompts for each scope
    if scope == "all":
        # Combine both scopes
        user_prompt = _build_analyze_prompt(status, "user", "")
        project_prompt = _build_analyze_prompt(status, "project", "")
        full_prompt = (
            "You are analyzing AI assistant context files from both user and project scopes.\n\n"
            f"{user_prompt}\n\n"
            f"{project_prompt}\n\n"
            f"*** USER QUESTION ***\n\n{prompt}"
        )
    else:
        full_prompt = (
            "You are analyzing AI assistant context files.\n\n"
            f"{_build_analyze_prompt(status, scope, prompt)}"
        )

    try:
        client = genai.Client(api_key=api_key)
        model_name = model or "gemini-2.0-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt
        )

        return {
            "success": True,
            "scope": scope,
            "response": response.text,
            "model": model_name
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def revise_context(scope: str, prompt: str, model: Optional[str] = None) -> dict:
    """
    Revise context file using Gemini.

    Args:
        scope: 'user' or 'project' (not 'all' - must pick one to revise)
        prompt: User's revision instructions
        model: Optional model override

    Returns:
        Dict with revision result.
    """
    if scope == "all":
        return {
            "success": False,
            "error": "Cannot revise 'all' scopes at once. Please specify 'user' or 'project'."
        }

    try:
        from google import genai
    except ImportError:
        return {
            "success": False,
            "error": "google-genai not installed. Run: pip install google-genai"
        }

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "GEMINI_API_KEY environment variable not set"
        }

    paths = _get_file_paths(scope)

    # Find the file to revise (prefer CONTEXT.md if unified, else try others)
    target_path = None
    target_content = None

    for name, path in [("CONTEXT.md", paths["context"]),
                       ("CLAUDE.md", paths["claude"]),
                       ("GEMINI.md", paths["gemini"])]:
        if path.exists() and not path.is_symlink():
            target_path = path
            target_content = path.read_text(encoding="utf-8")
            break

    if not target_path:
        return {
            "success": False,
            "error": f"No context file found for {scope} scope"
        }

    revision_prompt = (
        "You are an expert technical writer and configuration manager.\n"
        "Your task is to update the following Context File based on the user's request.\n"
        "Strictly adhere to these rules:\n"
        "1. Return ONLY the full content of the updated file. No markdown code blocks, no intro/outro text.\n"
        "2. Preserve all existing sections, formatting, and content unless the user's request specifically implies changing them.\n"
        "3. Ensure the result is valid Markdown.\n"
        "\n"
        f"--- CURRENT FILE: {_home_relative(target_path)} ---\n"
        f"{target_content}\n"
        "--- END CURRENT FILE ---\n"
        "\n"
        f"USER REQUEST: {prompt}"
    )

    try:
        client = genai.Client(api_key=api_key)
        model_name = model or "gemini-2.0-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=revision_prompt
        )

        new_content = response.text

        # Strip potential markdown code blocks
        if new_content.startswith("```markdown"):
            new_content = new_content[11:]
        elif new_content.startswith("```"):
            new_content = new_content[3:]
        if new_content.endswith("```"):
            new_content = new_content[:-3]
        new_content = new_content.strip()

        # Backup and write
        backup_path = target_path.with_suffix(".md.bak")
        import shutil
        shutil.copy2(target_path, backup_path)
        target_path.write_text(new_content, encoding="utf-8")

        return {
            "success": True,
            "scope": scope,
            "file": _home_relative(target_path),
            "backup": _home_relative(backup_path),
            "model": model_name,
            "message": f"Successfully revised {_home_relative(target_path)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
