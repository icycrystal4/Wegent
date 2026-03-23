---
name: himalaya-mail
description: Use Himalaya CLI to manage email (accounts/folders, list/read/search messages, compose/send). Prefer safe triage flows and require confirmation before any destructive action.
---

# Himalaya Mail

## Overview

Use this skill to run email workflows through the `himalaya` CLI with a safety-first pattern:
1) discover exact commands from local help,
2) execute non-destructive actions,
3) require confirmation for destructive actions.

## Inputs To Confirm Up Front

Before running anything beyond `--help`, ask for or infer (then confirm) these:
- Account: which configured account to use (if more than one)
- Folder/mailbox: default should be explicit (e.g. `INBOX`)
- Scope limits: default list size (e.g. 20) and whether to include message bodies
- Sent folder name: do not assume `Sent`; use the server's actual folder name (e.g. `Sent`, `Sent Messages`, `已发送邮件`)
- Compose/send: always confirm the account used for SMTP and headers (use `-a <account>` for message compose/send commands)

## Workflow

Before running any bundled script, resolve the injected base directory from the leading line:
- `Base directory for this skill: <absolute-path>`

Then define these shell helpers once and reuse them in all subsequent commands:

```bash
SKILL_BASE_DIR="<absolute-path-from-Base-directory-line>"
HIMALAYA_CLI="bash \"$SKILL_BASE_DIR/scripts/himalaya-cli.sh\""
CHECK_HIMALAYA="bash \"$SKILL_BASE_DIR/scripts/check_himalaya.sh\""
```

In the examples below, assume those helpers are already defined.

### 1. Resolve Config Source First

Prefer private local config files instead of repository-stored credentials.

```bash
$HIMALAYA_CLI account list
```
If the output contains `WEGENT_ACTION_REQUIRED={"action":"himalaya_mail_config"...}`:
- Do not retry the command.
- Do not ask the user to paste the password into chat.
- Reply in the user's language with a short explanation and include a clickable scheme link to open the config dialog, for example:

```markdown
请先完成邮箱配置：[配置邮箱](wegent://modal/himalaya-mail-config)
```

### 1.1 Resolve Real Folder Names (Critical For Non-English Mailboxes)

Folder names are server-defined and often localized (for example `已发送邮件`, `已删除邮件`).
Never hardcode `Sent`/`Trash`. Before any move/copy/save-to-sent behavior, list folders and pick the exact name shown by the server.

First, discover the folder-list subcommand via local help (see step 2). Then list folders for the selected account and use the exact folder name from the CLI output in subsequent commands.

### 2. Discover Exact Command Shape

Himalaya command structures can vary by version. Always inspect local help before execution:

```bash
$HIMALAYA_CLI --help
$HIMALAYA_CLI <subcommand> --help
```

For nested commands, continue drilling down until flags and required args are explicit.

### 3. Perform Non-Destructive Operations First

Prefer this order:
1. Account/mailbox/folder discovery
2. Message listing
3. Message read/show
4. Search/filter
5. Draft/compose preview
6. Send or state-changing operations (confirmation required)

### 4. Execute Destructive Operations Safely

For operations that may send externally, delete, move, expunge, or mutate message state (including read/unread and flags):
1. List candidate message IDs first.
2. Ask for explicit confirmation.
3. Execute only confirmed IDs.

```bash
$HIMALAYA_CLI envelope list -a <account> -f <folder> -s 20
$HIMALAYA_CLI message <destructive-subcommand> -a <account> -f <folder> <id...>
```

Confirmation prompt template (use literally, and wait for user response):
- "About to run: <command>. Targets: account=<account>, folder=<folder>, ids=[...]. Reply with `CONFIRM` to proceed, or tell me what to change."

### 5. Report Results Clearly

After command execution, return:
1. Context (account/folder)
2. Result (counts, IDs, subject lines, status)
3. Next safest action

## Safety Rules

- Never run send/delete/move/expunge/flag-changing operations without confirmation.
- Prefer showing candidate IDs before any bulk action.
- Default to headers/envelopes only; do not print full message bodies unless the user explicitly asks.
- Do not echo tokens/passwords/config contents into chat.
- Do not download/open attachments unless the user explicitly asks and the destination path is clear.
- For listing/search, default to `-s 20` (or the closest equivalent in the local CLI).
- For bulk operations, require an explicit list of IDs; avoid "all in folder" actions unless the user insists and confirms.
- If command shape is uncertain, stop and re-check `--help` instead of guessing.

## Address Defaults (Compose/Send)

- Default for AI-authored emails: generate then send via templates (pre-fills correct `From:` from config):

```bash
$HIMALAYA_CLI template write -a <account> \
  -H 'To: <...>' -H 'Subject: ...' 'body...' \
| $HIMALAYA_CLI template send -a <account>
```

- Always pass `-a <account>` for compose/send.
- Do not use `himalaya message send` unless the user explicitly asks to send a raw RFC5322/MIME message; then validate `From:` exactly matches the selected account `email = "..."` from the resolved config file (no typos, no missing TLD).

## Common Failure Handling

- Basic sanity: `$CHECK_HIMALAYA`, `$HIMALAYA_CLI --version`, `$HIMALAYA_CLI --help`.
- Config/auth/network: show the exact CLI error; confirm the resolved config path and `-a <account>` are correct.
- Diagnose: `$HIMALAYA_CLI account doctor <account>`.
