"""SDK for searching Claude Code session files."""

import datetime
import json
import os
import re


PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
HOME = os.path.expanduser("~")
DEFAULT_MOST_RECENT = 10


def decode_project_dir(dirname: str) -> str:
    """Convert encoded project dir name back to a filesystem path."""
    raw = dirname.lstrip("-")
    parts = raw.split("-")
    resolved = "/"
    i = 0
    while i < len(parts):
        candidate = os.path.join(resolved, parts[i])
        if os.path.isdir(candidate):
            resolved = candidate
            i += 1
        else:
            found = False
            for j in range(len(parts), i, -1):
                hyphenated = "-".join(parts[i:j])
                candidate = os.path.join(resolved, hyphenated)
                if os.path.isdir(candidate):
                    resolved = candidate
                    i = j
                    found = True
                    break
            if not found:
                resolved = os.path.join(resolved, "-".join(parts[i:]))
                break
    return resolved


def friendly_path(path: str) -> str:
    if path.startswith(HOME):
        return "~" + path[len(HOME):]
    return path


def format_age(mtime: float) -> str:
    now = datetime.datetime.now()
    mod_dt = datetime.datetime.fromtimestamp(mtime)
    delta = now - mod_dt
    if delta.total_seconds() < 60:
        return "just now"
    elif delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() // 60)}m ago"
    elif delta.total_seconds() < 86400:
        return f"{int(delta.total_seconds() // 3600)}h ago"
    elif delta.days == 1:
        return "yesterday"
    else:
        return f"{delta.days}d ago"


def get_first_user_message(jsonl_path: str) -> tuple[str, str | None]:
    """Extract first user message and custom title."""
    summary = ""
    name = None
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if not summary and obj.get("type") == "user" and obj.get("message", {}).get("role") == "user":
                        content = obj["message"]["content"]
                        if isinstance(content, str):
                            summary = content.replace("\n", " ").strip()
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    summary = part["text"].replace("\n", " ").strip()
                                    break
                    elif obj.get("type") == "custom-title":
                        name = obj.get("customTitle")
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return summary, name


def collect_recent_session_files(most_recent: int = DEFAULT_MOST_RECENT) -> list[dict]:
    """Collect the N most recent top-level session JSONL files."""
    if not os.path.isdir(PROJECTS_DIR):
        return []

    all_files = []
    for proj_dir_name in os.listdir(PROJECTS_DIR):
        proj_path = os.path.join(PROJECTS_DIR, proj_dir_name)
        if not os.path.isdir(proj_path):
            continue

        real_path = decode_project_dir(proj_dir_name)
        display_path = friendly_path(real_path)

        for f in os.listdir(proj_path):
            if not f.endswith(".jsonl"):
                continue
            jsonl_path = os.path.join(proj_path, f)
            session_id = f[:-6]
            mtime = os.path.getmtime(jsonl_path)
            all_files.append({
                "jsonl_path": jsonl_path,
                "session_id": session_id,
                "path": display_path,
                "modified": mtime,
            })

    all_files.sort(key=lambda x: x["modified"], reverse=True)
    return all_files[:most_recent]


def search_session(jsonl_path: str, pattern: re.Pattern, max_snippets: int = 3) -> list[str]:
    """Search a session JSONL for lines matching pattern. Returns snippet strings."""
    snippets = []
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                texts = []
                msg = obj.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                texts.append(part.get("text", ""))
                            elif part.get("type") == "tool_use":
                                inp = part.get("input", {})
                                if isinstance(inp, dict):
                                    texts.append(inp.get("prompt", ""))
                                    texts.append(inp.get("command", ""))

                if obj.get("type") == "tool_result":
                    result_content = obj.get("content", "")
                    if isinstance(result_content, str):
                        texts.append(result_content)

                for text in texts:
                    if not text:
                        continue
                    match = pattern.search(text)
                    if match:
                        start = max(0, match.start() - 60)
                        end = min(len(text), match.end() + 60)
                        snippet = text[start:end].replace("\n", " ").strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(text):
                            snippet = snippet + "..."
                        snippets.append(snippet)
                        if len(snippets) >= max_snippets:
                            return snippets
    except Exception:
        pass
    return snippets


def find_sessions(
    patterns: list[str],
    match_all: bool = False,
    most_recent: int = DEFAULT_MOST_RECENT,
    max_snippets: int = 3,
) -> list[dict]:
    """Search recent Claude Code sessions for patterns.

    Returns list of matching session dicts with keys:
        session_id, path, age, modified, summary, name, snippets
    """
    compiled = []
    for p in patterns:
        compiled.append(re.compile(p, re.IGNORECASE))

    sessions = collect_recent_session_files(most_recent)
    if not sessions:
        return []

    matches = []
    for s in sessions:
        all_snippets = []
        matched_patterns = set()
        for i, pat in enumerate(compiled):
            snippets = search_session(s["jsonl_path"], pat, max_snippets=max_snippets)
            if snippets:
                matched_patterns.add(i)
                all_snippets.extend(snippets)

        if match_all and len(matched_patterns) < len(compiled):
            continue
        if not match_all and not matched_patterns:
            continue

        seen = set()
        unique_snippets = []
        for snip in all_snippets:
            if snip not in seen:
                seen.add(snip)
                unique_snippets.append(snip)

        summary, name = get_first_user_message(s["jsonl_path"])
        matches.append({
            "session_id": s["session_id"],
            "path": s["path"],
            "age": format_age(s["modified"]),
            "modified": s["modified"],
            "summary": summary[:120],
            "name": name,
            "snippets": unique_snippets[:max_snippets],
        })

    return matches


def format_results(
    matches: list[dict],
    patterns: list[str],
    match_all: bool,
    most_recent: int,
    searched_count: int,
) -> str:
    """Format search results as human-readable text."""
    label = ", ".join(f"'{p}'" for p in patterns)
    if len(patterns) == 1:
        mode_desc = f"'{patterns[0]}'"
    else:
        mode = "ALL of" if match_all else "any of"
        mode_desc = f"{mode} [{label}]"

    if not matches:
        return f"No matches for {mode_desc} in the {most_recent} most recent sessions."

    lines = [f"Found {mode_desc} in {len(matches)} session(s) (searched {searched_count}):\n"]
    for i, m in enumerate(matches, 1):
        display = m["name"] if m.get("name") else m["summary"]
        if m.get("name"):
            display = f"[{display}]"
        if len(display) > 90:
            display = display[:87] + "..."
        sid_short = m["session_id"][:8]
        lines.append(f"  {i}. {m['age']:<12} {m['path']}")
        lines.append(f"     {display}")
        lines.append(f"     Resume: cd {m['path']} && claude -r {sid_short}")
        for snippet in m["snippets"]:
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            lines.append(f"       > {snippet}")
        lines.append("")

    return "\n".join(lines)
