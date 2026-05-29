# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

from executor.services.chat_workspace import prompt_to_slug, resolve_chat_workspace


def test_prompt_to_slug_uses_alphanumeric_words():
    slug = prompt_to_slug("Build Codex UI: 2 buttons + 项目")

    assert slug == "build-codex-ui-2-buttons"


def test_prompt_to_slug_falls_back_when_no_alphanumeric_words():
    assert prompt_to_slug("项目归档") == "new-chat"


def test_resolve_chat_workspace_creates_date_directory_and_reuses_mapping(tmp_path):
    now = datetime(2026, 5, 29, 10, 30, 0)

    first_path = resolve_chat_workspace(
        task_id=1001,
        prompt="Create PR summary",
        chats_root=str(tmp_path),
        now=now,
    )
    second_path = resolve_chat_workspace(
        task_id=1001,
        prompt="Different follow-up message",
        chats_root=str(tmp_path),
        now=now,
    )

    assert first_path == second_path
    assert first_path.endswith("2026-05-29/create-pr-summary")


def test_resolve_chat_workspace_adds_suffix_for_duplicate_slug(tmp_path):
    now = datetime(2026, 5, 29, 10, 30, 0)
    existing = tmp_path / "2026-05-29" / "new-chat"
    existing.mkdir(parents=True)

    path = resolve_chat_workspace(
        task_id=1002,
        prompt="项目归档",
        chats_root=str(tmp_path),
        now=now,
    )

    assert path.endswith("2026-05-29/new-chat-1")
