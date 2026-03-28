"""SDK for managing cross-tool AI agent skills."""

import shutil
from pathlib import Path
from typing import Optional

import yaml

from aicfg.sdk.config import (
    get_claude_skills_dir,
    get_gemini_skills_dir,
    get_skill_source_dir,
    get_user_cmds_dir,
)

AICFG_ONLY_FIELDS = {"only", "exclude", "invocation", "category", "claude", "gemini"}
SUPPORTED_PLATFORMS = {"claude", "gemini"}
VALID_INVOCATION_MODES = {"both", "slash-only", "ambient-only"}
def parse_skill_md(path: Path) -> tuple[dict, str]:
    """Parse a SKILL.md file into frontmatter dict and body string."""
    text = path.read_text()
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return frontmatter, body


def render_skill_md(frontmatter: dict, body: str) -> str:
    """Render frontmatter dict and body into a SKILL.md string."""
    if not frontmatter:
        return body
    fm = yaml.dump(
        frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True,
    ).rstrip()
    return f"---\n{fm}\n---\n\n{body}"


def validate_skill_meta(meta: dict) -> list[str]:
    """Validate skill frontmatter. Returns list of errors (empty = valid)."""
    errors = []
    if not meta.get("name"):
        errors.append("Missing required field: name")
    if not meta.get("description"):
        errors.append("Missing required field: description")

    has_only = "only" in meta
    has_exclude = "exclude" in meta
    if has_only and has_exclude:
        errors.append("Cannot specify both 'only' and 'exclude'")

    if has_only:
        for p in meta["only"]:
            if p not in SUPPORTED_PLATFORMS:
                errors.append(f"Unknown platform in 'only': {p}")

    if has_exclude:
        for p in meta["exclude"]:
            if p not in SUPPORTED_PLATFORMS:
                errors.append(f"Unknown platform in 'exclude': {p}")

    invocation = meta.get("invocation", "both")
    if invocation not in VALID_INVOCATION_MODES:
        errors.append(f"Invalid invocation mode: {invocation}. Must be one of: {', '.join(VALID_INVOCATION_MODES)}")

    return errors


def resolve_effective_targets(meta: dict) -> set[str]:
    """Determine which platforms a skill targets based on only/exclude."""
    if "only" in meta:
        return set(meta["only"])
    if "exclude" in meta:
        return SUPPORTED_PLATFORMS - set(meta["exclude"])
    return SUPPORTED_PLATFORMS.copy()


def detect_configured_platforms() -> set[str]:
    """Detect which platforms are configured on this machine."""
    platforms = set()
    if get_claude_skills_dir().parent.exists():
        platforms.add("claude")
    if get_gemini_skills_dir().parent.exists():
        platforms.add("gemini")
    return platforms


def _get_platform_install_dir(platform: str) -> Path:
    if platform == "claude":
        return get_claude_skills_dir()
    elif platform == "gemini":
        return get_gemini_skills_dir()
    raise ValueError(f"Unknown platform: {platform}")


def generate_platform_skill(meta: dict, body: str, target: str) -> str:
    """Generate a clean, platform-native SKILL.md for a target platform."""
    cleaned = {k: v for k, v in meta.items() if k not in AICFG_ONLY_FIELDS}

    # Merge platform-specific overrides
    platform_overrides = meta.get(target, {})
    if platform_overrides:
        cleaned.update(platform_overrides)

    # Apply invocation mode translations
    invocation = meta.get("invocation", "both")
    if invocation == "slash-only":
        if target == "claude":
            cleaned["disable-model-invocation"] = True
    elif invocation == "ambient-only":
        if target == "claude":
            cleaned["user-invocable"] = False

    return render_skill_md(cleaned, body)


def get_installed_status(name: str) -> dict[str, bool]:
    """Check if a skill is installed on each platform."""
    return {
        "claude": (get_claude_skills_dir() / name / "SKILL.md").exists(),
        "gemini": (get_gemini_skills_dir() / name / "SKILL.md").exists(),
    }


def _discover_installed_skills() -> dict[str, dict[str, bool]]:
    """Discover all skills installed on this machine, keyed by name."""
    installed = {}
    for platform, skills_dir in [("claude", get_claude_skills_dir()), ("gemini", get_gemini_skills_dir())]:
        if not skills_dir.is_dir():
            continue
        for skill_dir in skills_dir.iterdir():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            name = skill_dir.name
            if name not in installed:
                installed[name] = {"claude": False, "gemini": False}
            installed[name][platform] = True
    return installed


def list_skills(
    category: Optional[str] = None,
    target: Optional[str] = None,
    installed: Optional[bool] = None,
) -> list[dict]:
    """List skills from all sources (marketplace + locally installed)."""
    seen_names = set()
    results = []

    # 1. Skills from marketplace source directories
    source_dir = get_skill_source_dir()
    if source_dir.is_dir():
        for skill_dir in sorted(source_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            meta, body = parse_skill_md(skill_md)
            errors = validate_skill_meta(meta)
            if errors:
                continue

            name = meta["name"]
            seen_names.add(name)
            effective_targets = resolve_effective_targets(meta)
            status = get_installed_status(name)

            if category and meta.get("category") != category:
                continue
            if target and target not in effective_targets:
                continue
            if installed is True and not any(status.values()):
                continue
            if installed is False and any(status.values()):
                continue

            results.append({
                "name": name,
                "description": meta.get("description", ""),
                "category": meta.get("category", ""),
                "invocation": meta.get("invocation", "both"),
                "effective_targets": sorted(effective_targets),
                "installed": status,
                "source": "aicfg",
            })

    # 2. Locally installed skills not in any marketplace
    all_installed = _discover_installed_skills()
    for name, status in sorted(all_installed.items()):
        if name in seen_names:
            continue

        # Try to read frontmatter from the installed copy for metadata
        desc = ""
        skill_category = ""
        for platform_dir in [get_claude_skills_dir(), get_gemini_skills_dir()]:
            skill_md = platform_dir / name / "SKILL.md"
            if skill_md.exists():
                meta, _ = parse_skill_md(skill_md)
                desc = meta.get("description", "")
                skill_category = meta.get("category", "")
                break

        effective_targets = sorted(SUPPORTED_PLATFORMS)

        if category and skill_category != category:
            continue
        if target and target not in effective_targets:
            continue
        if installed is True and not any(status.values()):
            continue
        if installed is False and any(status.values()):
            continue

        results.append({
            "name": name,
            "description": desc,
            "category": skill_category,
            "invocation": "unknown",
            "effective_targets": effective_targets,
            "installed": status,
            "source": "-",
        })

    return results


def get_skill(name: str) -> Optional[dict]:
    """Get full details of a skill by name."""
    source_dir = get_skill_source_dir()
    skill_md = source_dir / name / "SKILL.md"
    if not skill_md.exists():
        return None

    meta, body = parse_skill_md(skill_md)
    return {
        "name": meta.get("name", name),
        "description": meta.get("description", ""),
        "category": meta.get("category", ""),
        "invocation": meta.get("invocation", "both"),
        "effective_targets": sorted(resolve_effective_targets(meta)),
        "installed": get_installed_status(meta.get("name", name)),
        "meta": meta,
        "body": body,
    }


def install_skill(name: str, target: Optional[str] = None) -> list[str]:
    """Install a skill to configured platforms. Returns list of installed paths."""
    source_dir = get_skill_source_dir() / name
    skill_md = source_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"Skill not found: {name}")

    meta, body = parse_skill_md(skill_md)
    errors = validate_skill_meta(meta)
    if errors:
        raise ValueError(f"Invalid skill '{name}': {'; '.join(errors)}")

    effective = resolve_effective_targets(meta)

    if target:
        if target not in effective:
            raise ValueError(
                f"'{name}' does not support {target} "
                f"(effective targets: {', '.join(sorted(effective))})"
            )
        install_targets = {target}
    else:
        install_targets = effective & detect_configured_platforms()

    if not install_targets:
        raise ValueError(f"No configured platforms found for '{name}'")

    installed = []
    for t in sorted(install_targets):
        dest_dir = _get_platform_install_dir(t) / name
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Write platform-specific SKILL.md (instructions only, no scripts)
        platform_content = generate_platform_skill(meta, body, t)
        (dest_dir / "SKILL.md").write_text(platform_content)

        installed.append(str(dest_dir))

    return installed


def uninstall_skill(name: str, target: Optional[str] = None) -> list[str]:
    """Uninstall a skill from platforms. Returns list of removed paths."""
    # If source exists, use it for effective targets; otherwise check all
    source_skill = get_skill_source_dir() / name / "SKILL.md"
    if source_skill.exists():
        meta, _ = parse_skill_md(source_skill)
        effective = resolve_effective_targets(meta)
    else:
        effective = SUPPORTED_PLATFORMS.copy()

    if target:
        if target not in effective:
            raise ValueError(
                f"'{name}' does not support {target} "
                f"(effective targets: {', '.join(sorted(effective))})"
            )
        uninstall_targets = {target}
    else:
        uninstall_targets = effective

    removed = []
    for t in sorted(uninstall_targets):
        dest_dir = _get_platform_install_dir(t) / name
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
            removed.append(str(dest_dir))

    # Clean up gemini TOML command if slash-only
    if source_skill.exists():
        meta, _ = parse_skill_md(source_skill)
        if meta.get("invocation") == "slash-only" and "gemini" in uninstall_targets:
            toml_path = get_user_cmds_dir() / f"{name}.toml"
            if toml_path.exists():
                toml_path.unlink()
                removed.append(str(toml_path))

    return removed
