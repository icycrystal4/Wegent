# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for lightweight device sandbox command handling."""

import base64
import os
import subprocess
from unittest.mock import MagicMock, patch

from executor.modes.local.handlers import SandboxHandler


class TestSandboxHandler:
    """Tests for SandboxHandler."""

    def test_execute_command_sync_returns_process_output(self):
        """Successful subprocess output should be returned unchanged."""
        handler = SandboxHandler(runner=MagicMock())

        completed = subprocess.CompletedProcess(
            args=["echo", "hello"],
            returncode=0,
            stdout="hello\n",
            stderr="",
        )

        with patch(
            "executor.modes.local.handlers.subprocess.run", return_value=completed
        ):
            result = handler._execute_command_sync(
                command="echo hello",
                working_dir="/tmp",
                timeout_seconds=5,
            )

        assert result["success"] is True
        assert result["stdout"] == "hello\n"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0

    def test_execute_command_sync_returns_timeout_error(self):
        """Timeouts should surface as structured command failures."""
        handler = SandboxHandler(runner=MagicMock())

        with patch(
            "executor.modes.local.handlers.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd="sleep 10",
                timeout=1,
                output="partial",
                stderr="still running",
            ),
        ):
            result = handler._execute_command_sync(
                command="sleep 10",
                working_dir="/tmp",
                timeout_seconds=1,
            )

        assert result["success"] is False
        assert result["stdout"] == "partial"
        assert "timed out" in result["stderr"]
        assert result["exit_code"] == -1

    def test_read_file_sync_reads_text_content(self, tmp_path):
        """Text files should be read back with metadata."""
        handler = SandboxHandler(runner=MagicMock())
        target = tmp_path / "notes.txt"
        target.write_text("hello device", encoding="utf-8")

        result = handler._read_file_sync(str(target), "text")

        assert result["success"] is True
        assert result["content"] == "hello device"
        assert result["size"] == len("hello device")
        assert result["path"] == str(target)
        assert result["format"] == "text"

    def test_list_files_sync_returns_recursive_entries(self, tmp_path):
        """Directory listings should include nested entries up to depth."""
        handler = SandboxHandler(runner=MagicMock())
        nested_dir = tmp_path / "reports"
        nested_dir.mkdir()
        file_path = nested_dir / "weekly.txt"
        file_path.write_text("done", encoding="utf-8")

        result = handler._list_files_sync(str(tmp_path), 2)

        assert result["success"] is True
        assert result["path"] == str(tmp_path)
        assert result["total"] == 2
        paths = {entry["path"] for entry in result["entries"]}
        assert str(nested_dir) in paths
        assert str(file_path) in paths

    def test_write_file_sync_writes_text_content(self, tmp_path):
        """Text writes should create parent directories and persist content."""
        handler = SandboxHandler(runner=MagicMock())
        target = tmp_path / "mail" / "summary.txt"

        result = handler._write_file_sync(str(target), "device output", "text", True)

        assert result["success"] is True
        assert result["path"] == str(target)
        assert target.read_text(encoding="utf-8") == "device output"
        assert result["size"] == len("device output".encode("utf-8"))

    def test_write_file_sync_writes_binary_content(self, tmp_path):
        """Binary writes should decode base64 payloads before persisting."""
        handler = SandboxHandler(runner=MagicMock())
        target = tmp_path / "attachments" / "report.bin"
        payload = base64.b64encode(b"\x00\x01\x02").decode("ascii")

        result = handler._write_file_sync(str(target), payload, "bytes", True)

        assert result["success"] is True
        assert target.read_bytes() == b"\x00\x01\x02"
        assert result["size"] == 3

    def test_normalize_path_maps_home_user_to_local_home(self, tmp_path, monkeypatch):
        """Sandbox-style /home/user paths should resolve under the device home."""
        handler = SandboxHandler(runner=MagicMock())
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path))

        assert handler._normalize_path("/home/user") == str(tmp_path)
        assert handler._normalize_path("/home/user/mail/config.toml") == str(
            tmp_path / "mail" / "config.toml"
        )
        assert handler._normalize_path("relative.txt") == str(tmp_path / "relative.txt")

    def test_execute_command_sync_normalizes_sandbox_working_dir(self, tmp_path, monkeypatch):
        """Device exec should map /home/user to the local home before subprocess starts."""
        handler = SandboxHandler(runner=MagicMock())
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path))

        completed = subprocess.CompletedProcess(
            args=["pwd"],
            returncode=0,
            stdout=f"{tmp_path}\n",
            stderr="",
        )

        with patch(
            "executor.modes.local.handlers.subprocess.run",
            return_value=completed,
        ) as mock_run:
            result = handler._execute_command_sync(
                command="pwd",
                working_dir="/home/user",
                timeout_seconds=5,
            )

        assert result["success"] is True
        assert result["stdout"] == f"{tmp_path}\n"
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["cwd"] == str(tmp_path)
