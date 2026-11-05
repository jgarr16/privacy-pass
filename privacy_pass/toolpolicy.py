"""Tool-argument policy: classify by destination, protect free text.

Rules (README "Important tool-call rule"):

- Never rewrite values inside filesystem paths, URLs, commands, or IDs —
  that breaks tools or changes their meaning.
- On tools whose arguments reach an external service, rewrite free-text
  fields (queries, objectives) with session aliases.
- Local tools keep raw arguments (they do not leave the device); their
  results are sanitized before the model consumes them again.
- Unknown tools are left untouched: the model only ever sees aliased
  context, so its generated arguments contain aliases, not raw values.
  This is a usability fail-safe, documented in KNOWN_LIMITS.
"""

from __future__ import annotations

import copy

# Tools whose arguments are sent to third-party services.
EXTERNAL_TOOLS = frozenset(
    {
        "web_search",
        "web_extract",
        "web_fetch",
        "http_request",
        "image_gen",
    }
)

# Free-text argument keys that may carry user prose and can be aliased
# without changing what the tool does.
FREE_TEXT_KEYS = frozenset(
    {
        "query",
        "q",
        "objective",
        "prompt",
        "text",
        "keywords",
        "topic",
        "search_queries",
        "questions",
    }
)

# Structural keys that are never rewritten (destination or identifier).
STRUCTURAL_KEYS = frozenset(
    {
        "url",
        "urls",
        "link",
        "path",
        "paths",
        "file",
        "filename",
        "command",
        "cmd",
        "id",
        "ids",
        "name",
        "session_id",
        "task_id",
    }
)


def is_external(tool_name: str) -> bool:
    """True when the tool's arguments reach a third-party service.

    Explicit list first, then a conservative name heuristic so catalog and
    MCP tools with obvious outbound shapes are covered. Local-only names
    (files, terminal, session search) are never external.
    """
    lowered = (tool_name or "").strip().lower()
    if not lowered:
        return False
    if lowered in EXTERNAL_TOOLS:
        return True
    if lowered in {"read_file", "search_files", "terminal", "session_search",
                   "skill_view", "skills_list", "browser_snapshot", "vision_analyze"}:
        return False
    return "search" in lowered or lowered.startswith(("web_", "http_", "fetch_"))


def sanitize_tool_args(args: dict, engine) -> tuple[dict, int, bool]:
    """Return (new_args, detections, changed). Free-text fields on external
    tools are aliased; everything else passes through untouched."""
    new_args = copy.deepcopy(args)
    detections = 0
    changed = False
    for key, value in list(new_args.items()):
        if key in STRUCTURAL_KEYS or key not in FREE_TEXT_KEYS:
            continue
        if isinstance(value, str) and value:
            result = engine.sanitize_request(value)
            if result.detections:
                new_args[key] = result.sanitized_text
                detections += len(result.detections)
                changed = True
        elif isinstance(value, list):
            new_list = []
            hit = False
            for item in value:
                if isinstance(item, str) and item:
                    result = engine.sanitize_request(item)
                    if result.detections:
                        new_list.append(result.sanitized_text)
                        detections += len(result.detections)
                        hit = True
                    else:
                        new_list.append(item)
                else:
                    new_list.append(item)
            if hit:
                new_args[key] = new_list
                changed = True
    return new_args, detections, changed
