# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace directory helpers for standalone chats."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")
FALLBACK_SLUG = "new-chat"
METADATA_DIR_NAME = ".metadata"


def prompt_to_slug(prompt: Any) -> str:
    """Build a filesystem slug from the first user prompt."""

    words = WORD_PATTERN.findall(_prompt_to_text(prompt))
    if not words:
        return FALLBACK_SLUG
    return "-".join(word.lower() for word in words)


def resolve_chat_workspace(
    *,
    task_id: int,
    prompt: Any,
    chats_root: str,
    now: datetime | None = None,
) -> str:
    """Return the stable workspace directory for a standalone chat task."""

    root = Path(os.path.expanduser(chats_root))
    mapping_path = root / METADATA_DIR_NAME / f"{task_id}.json"
    existing_path = _load_mapped_path(mapping_path)
    if existing_path:
        existing_path.mkdir(parents=True, exist_ok=True)
        return str(existing_path)

    day_dir = root / (now or datetime.now()).strftime("%Y-%m-%d")
    workspace_path = _create_unique_workspace_dir(day_dir, prompt_to_slug(prompt))
    _save_mapped_path(mapping_path, workspace_path)
    return str(workspace_path)


def _prompt_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_prompt_to_text(item) for item in value)
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "message", "prompt"):
            if key in value:
                parts.append(_prompt_to_text(value[key]))
        return " ".join(parts)
    return ""


def _load_mapped_path(mapping_path: Path) -> Path | None:
    try:
        with mapping_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    path = data.get("path") if isinstance(data, dict) else None
    if not path or not isinstance(path, str):
        return None
    return Path(os.path.expanduser(path))


def _save_mapped_path(mapping_path: Path, workspace_path: Path) -> None:
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with mapping_path.open("w", encoding="utf-8") as file:
        json.dump({"path": str(workspace_path)}, file)


def _create_unique_workspace_dir(day_dir: Path, slug: str) -> Path:
    day_dir.mkdir(parents=True, exist_ok=True)
    for index in range(10000):
        suffix = "" if index == 0 else f"-{index}"
        candidate = day_dir / f"{slug}{suffix}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Unable to allocate chat workspace under {day_dir}")
