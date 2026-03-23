# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Event handlers for local executor mode.

This module implements handlers for events received from the Backend server.
"""

import asyncio
import base64
import grp
import mimetypes
import os
import pwd
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

import requests

from shared.logger import setup_logger
from shared.models.execution import ExecutionRequest

if TYPE_CHECKING:
    from executor.modes.local.runner import LocalRunner

logger = setup_logger("local_handlers")


class TaskHandler:
    """Handler for task-related events from Backend."""

    def __init__(self, runner: "LocalRunner"):
        """Initialize the task handler.

        Args:
            runner: The LocalRunner instance for task execution.
        """
        self.runner = runner

    async def handle_task_dispatch(self, data: Dict[str, Any]) -> None:
        """Handle task dispatch event from Backend.

        This is called when Backend pushes a new task to execute.

        Args:
            data: Task data dictionary containing:
                - task_id: Task ID
                - subtask_id: Subtask ID
                - prompt: Task prompt
                - bot: Bot configuration (includes agent_config.env for Claude API)
                - auth_token: JWT token for HTTP API calls (Skills, attachments)
                - attachments: List of attachments
                - git_url, branch_name, etc.
        """
        task_id = data.get("task_id", -1)
        subtask_id = data.get("subtask_id", -1)
        logger.info(
            f"Received task dispatch: task_id={task_id}, subtask_id={subtask_id}"
        )

        # Convert dict to ExecutionRequest and enqueue
        execution_request = ExecutionRequest.from_dict(data)
        await self.runner.enqueue_task(execution_request)

    async def handle_task_cancel(self, data: Dict[str, Any]) -> None:
        """Handle task cancel event from Backend.

        Args:
            data: Cancel data containing task_id.
        """
        task_id = data.get("task_id")
        if task_id is not None:
            logger.info(f"Received task cancel request: task_id={task_id}")
            await self.runner.cancel_task(task_id)
        else:
            logger.warning("Received cancel request without task_id")

    async def handle_task_close_session(self, data: Dict[str, Any]) -> None:
        """Handle task close session event from Backend.

        This completely terminates the task session and frees up the slot,
        unlike cancel which only pauses execution.

        Args:
            data: Close session data containing task_id.
        """
        task_id = data.get("task_id")
        if task_id is not None:
            logger.info(f"Received task close session request: task_id={task_id}")
            await self.runner.close_task_session(task_id)
        else:
            logger.warning("Received close session request without task_id")

    async def handle_chat_message(self, data: Dict[str, Any]) -> None:
        """Handle chat message event from Backend.

        This is used for follow-up messages in an existing chat session.

        Args:
            data: Chat message data (same structure as task dispatch).
        """
        task_id = data.get("task_id", -1)
        subtask_id = data.get("subtask_id", -1)
        logger.info(
            f"Received chat message: task_id={task_id}, subtask_id={subtask_id}"
        )

        # Chat messages are processed as tasks
        execution_request = ExecutionRequest.from_dict(data)
        await self.runner.enqueue_task(execution_request)


class ConnectionHandler:
    """Handler for connection-related events."""

    def __init__(self, runner: "LocalRunner"):
        """Initialize the connection handler.

        Args:
            runner: The LocalRunner instance.
        """
        self.runner = runner

    async def handle_connect(self) -> None:
        """Handle successful connection."""
        logger.info("Connected to Backend WebSocket")
        # Note: Registration is handled by LocalRunner.start() after connection
        # and by reconnection logic in the internal handlers.

    async def handle_disconnect(self) -> None:
        """Handle disconnection."""
        logger.warning("Disconnected from Backend WebSocket")
        # The WebSocket client will handle automatic reconnection

    async def handle_connect_error(self, data: Any) -> None:
        """Handle connection error.

        Args:
            data: Error information.
        """
        logger.error(f"WebSocket connection error: {data}")


class UpgradeHandler:
    """Handler for upgrade-related events from Backend."""

    def __init__(self, runner: "LocalRunner"):
        """Initialize the upgrade handler.

        Args:
            runner: The LocalRunner instance.
        """
        self.runner = runner
        self._upgrade_in_progress = False
        self._upgrade_lock = threading.Lock()

    async def handle_upgrade_command(self, data: Dict[str, Any]) -> None:
        """Handle device:upgrade event from Backend.

        This method receives upgrade commands from the backend and orchestrates
        the upgrade process, emitting status updates back to the backend.

        Args:
            data: Upgrade command data containing:
                - force: Force upgrade even if on latest version
                - auto_confirm: Skip user confirmation
                - verbose: Enable verbose logging
                - force_stop_tasks: Cancel running tasks before upgrade
                - registry: Optional registry URL override
                - registry_token: Optional registry auth token
        """
        device_id = self.runner.websocket_client.device_id

        # Check if upgrade already in progress
        with self._upgrade_lock:
            if self._upgrade_in_progress:
                await self._emit_status(
                    "error", "Upgrade already in progress", device_id=device_id
                )
                return
            self._upgrade_in_progress = True

        try:
            # Check for running tasks
            if self.runner.has_running_tasks():
                force_stop = data.get("force_stop_tasks", False)
                if not force_stop:
                    await self._emit_status(
                        "busy",
                        "Cannot upgrade: tasks are running",
                        device_id=device_id,
                    )
                    with self._upgrade_lock:
                        self._upgrade_in_progress = False
                    return
                else:
                    # Cancel all running tasks
                    logger.info("[UpgradeHandler] Cancelling all running tasks")
                    await self.runner.cancel_all_tasks()

            # Emit initial status
            await self._emit_status(
                "checking", "Checking for updates...", device_id=device_id
            )

            # Run upgrade in background thread to not block WebSocket
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._execute_upgrade_sync,
                data.get("force", False),
                data.get("auto_confirm", True),
                data.get("verbose", False),
                data.get("registry"),
                data.get("registry_token"),
            )

            # Emit final status based on result
            if result.success:
                if result.already_latest:
                    await self._emit_status(
                        "skipped",
                        "Already on latest version",
                        device_id=device_id,
                        old_version=result.old_version,
                    )
                else:
                    await self._emit_status(
                        "success",
                        "Upgrade completed successfully",
                        device_id=device_id,
                        old_version=result.old_version,
                        new_version=result.new_version,
                    )
                    # Emit restarting status before actual restart
                    await self._emit_status(
                        "restarting",
                        "Restarting executor...",
                        device_id=device_id,
                        new_version=result.new_version,
                    )
                    # Trigger auto-restart
                    await self._trigger_restart()
            else:
                await self._emit_status(
                    "error",
                    f"Upgrade failed: {result.error}",
                    device_id=device_id,
                    error=result.error,
                )

        except Exception as e:
            logger.exception(f"[UpgradeHandler] Error during upgrade: {e}")
            await self._emit_status(
                "error",
                f"Unexpected error: {str(e)}",
                device_id=device_id,
                error=str(e),
            )
        finally:
            with self._upgrade_lock:
                self._upgrade_in_progress = False

    def _execute_upgrade_sync(
        self,
        force: bool,
        auto_confirm: bool,
        verbose: bool,
        registry: Optional[str],
        registry_token: Optional[str],
    ) -> "UpdateResult":
        """Execute upgrade synchronously (runs in background thread).

        Args:
            force: Force upgrade even if on latest version
            auto_confirm: Skip user confirmation
            verbose: Enable verbose logging
            registry: Optional registry URL override
            registry_token: Optional registry auth token

        Returns:
            UpdateResult with the outcome of the update
        """
        import asyncio

        from executor.config.device_config import UpdateConfig
        from executor.services.updater.updater_service import UpdaterService

        # Get update config from device-config, or create empty one if not available
        if self.runner.device_config and self.runner.device_config.update:
            update_config = UpdateConfig(
                registry=self.runner.device_config.update.registry,
                registry_token=self.runner.device_config.update.registry_token,
            )
        else:
            update_config = UpdateConfig()

        # Override with values from backend request if provided
        if registry:
            update_config.registry = registry
        if registry_token:
            update_config.registry_token = registry_token

        # Create updater service
        service = UpdaterService(
            update_config=update_config,
            auto_confirm=auto_confirm,
            verbose=verbose,
        )

        # Run the update check and download
        return asyncio.run(service.check_and_update())

    async def _emit_status(
        self,
        status: str,
        message: str,
        device_id: Optional[str] = None,
        old_version: Optional[str] = None,
        new_version: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Emit upgrade status update to Backend.

        Args:
            status: Status string (checking, downloading, installing, etc.)
            message: Human-readable message
            device_id: Device ID (defaults to runner's device ID)
            old_version: Version before upgrade
            new_version: Version after upgrade
            progress: Download progress (0-100)
            error: Error details if status is error
        """
        if device_id is None:
            device_id = self.runner.websocket_client.device_id

        status_data = {
            "device_id": device_id,
            "status": status,
            "message": message,
        }

        if old_version is not None:
            status_data["old_version"] = old_version
        if new_version is not None:
            status_data["new_version"] = new_version
        if progress is not None:
            status_data["progress"] = progress
        if error is not None:
            status_data["error"] = error

        try:
            await self.runner.websocket_client.emit(
                "device:upgrade_status", status_data
            )
            logger.debug(f"[UpgradeHandler] Emitted status: {status}")
        except Exception as e:
            logger.error(f"[UpgradeHandler] Failed to emit status: {e}")

    async def _trigger_restart(self) -> None:
        """Trigger executor restart after successful upgrade.

        This schedules a restart to happen after the status is sent.
        """
        logger.info("[UpgradeHandler] Scheduling executor restart in 2 seconds...")

        async def delayed_restart():
            await asyncio.sleep(2)
            logger.info("[UpgradeHandler] Executing restart now")
            # Use the process manager to restart
            from executor.services.updater.process_manager import ProcessManager

            pm = ProcessManager()
            success = pm.restart_executor()
            if success:
                logger.info(
                    "[UpgradeHandler] New executor started, exiting current process"
                )
                import sys

                sys.exit(0)

        # Schedule the restart without awaiting it
        asyncio.create_task(delayed_restart())


class SandboxHandler:
    """Handler for lightweight sandbox-style device commands."""

    MAX_READ_FILE_SIZE = 10 * 1024 * 1024
    MAX_WRITE_FILE_SIZE = 10 * 1024 * 1024
    MAX_UPLOAD_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self, runner: "LocalRunner"):
        """Initialize the sandbox handler."""
        self.runner = runner

    async def handle_exec(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a shell command on the device and return an ack payload."""
        command = str(data.get("command", "")).strip()
        if not command:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command is required",
                "exit_code": -1,
                "execution_time": 0.0,
            }

        working_dir = str(data.get("working_dir") or os.path.expanduser("~"))
        timeout_seconds = int(data.get("timeout_seconds") or 300)

        logger.info(
            "[SandboxHandler] Executing device command: cwd=%s, timeout=%ss, command=%s",
            working_dir,
            timeout_seconds,
            command[:200],
        )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._execute_command_sync,
            command,
            working_dir,
            timeout_seconds,
        )

    async def handle_read_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file from the device filesystem."""
        file_path = str(data.get("file_path", "")).strip()
        file_format = str(data.get("format") or "text")
        if not file_path:
            return self._error_response("file_path is required")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._read_file_sync,
            file_path,
            file_format,
        )

    async def handle_list_files(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """List files from the device filesystem."""
        path = str(data.get("path") or os.path.expanduser("~"))
        depth = int(data.get("depth") or 1)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._list_files_sync,
            path,
            depth,
        )

    async def handle_write_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Write a file to the device filesystem."""
        file_path = str(data.get("file_path", "")).strip()
        content = data.get("content")
        file_format = str(data.get("format") or "text")
        create_dirs = bool(data.get("create_dirs", True))

        if not file_path:
            return self._error_response("file_path is required")
        if content is None or content == "":
            return self._error_response("content is required")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._write_file_sync,
            file_path,
            str(content),
            file_format,
            create_dirs,
        )

    async def handle_download_attachment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Download a Wegent attachment onto the device."""
        attachment_url = str(data.get("attachment_url", "")).strip()
        save_path = str(data.get("save_path", "")).strip()
        auth_token = str(data.get("auth_token", "")).strip()
        api_base_url = str(data.get("api_base_url", "")).rstrip("/")
        timeout_seconds = int(data.get("timeout_seconds") or 300)

        if not attachment_url or not save_path:
            return self._error_response("attachment_url and save_path are required")
        if not auth_token:
            return self._error_response("auth_token is required")
        if not api_base_url:
            return self._error_response("api_base_url is required")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._download_attachment_sync,
            attachment_url,
            save_path,
            auth_token,
            api_base_url,
            timeout_seconds,
        )

    async def handle_upload_attachment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upload a device-local file back to Wegent attachments."""
        file_path = str(data.get("file_path", "")).strip()
        auth_token = str(data.get("auth_token", "")).strip()
        api_base_url = str(data.get("api_base_url", "")).rstrip("/")
        overwrite_attachment_id = data.get("overwrite_attachment_id")
        timeout_seconds = int(data.get("timeout_seconds") or 300)

        if not file_path:
            return self._error_response("file_path is required")
        if not auth_token:
            return self._error_response("auth_token is required")
        if not api_base_url:
            return self._error_response("api_base_url is required")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._upload_attachment_sync,
            file_path,
            auth_token,
            api_base_url,
            overwrite_attachment_id,
            timeout_seconds,
        )

    def _execute_command_sync(
        self,
        command: str,
        working_dir: str,
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        """Execute a command synchronously in a worker thread."""
        started_at = time.monotonic()
        resolved_working_dir = self._normalize_path(working_dir)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=resolved_working_dir,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "stdout": exc.stdout or "",
                "stderr": (exc.stderr or "")
                + f"\nCommand timed out after {timeout_seconds}s",
                "exit_code": -1,
                "execution_time": time.monotonic() - started_at,
            }
        except Exception as exc:
            logger.error(
                "[SandboxHandler] Device command failed: cwd=%s, resolved_cwd=%s, error=%s",
                working_dir,
                resolved_working_dir,
                exc,
            )
            return {
                "success": False,
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
                "execution_time": time.monotonic() - started_at,
            }

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "exit_code": result.returncode,
            "execution_time": time.monotonic() - started_at,
        }

    def _read_file_sync(self, file_path: str, file_format: str) -> Dict[str, Any]:
        """Read a file synchronously."""
        started_at = time.monotonic()
        try:
            resolved_path = self._normalize_path(file_path)
            if not os.path.exists(resolved_path):
                return self._error_response(
                    f"File not found: {resolved_path}",
                    execution_time=time.monotonic() - started_at,
                    path=resolved_path,
                    size=0,
                    content="",
                )
            if not os.path.isfile(resolved_path):
                return self._error_response(
                    f"Path is not a file: {resolved_path}",
                    execution_time=time.monotonic() - started_at,
                    path=resolved_path,
                    size=0,
                    content="",
                )

            file_size = os.path.getsize(resolved_path)
            if file_size > self.MAX_READ_FILE_SIZE:
                return self._error_response(
                    f"File too large: {file_size} bytes",
                    execution_time=time.monotonic() - started_at,
                    path=resolved_path,
                    size=file_size,
                    content="",
                )

            if file_format == "bytes":
                with open(resolved_path, "rb") as file_obj:
                    content = base64.b64encode(file_obj.read()).decode("ascii")
            else:
                with open(
                    resolved_path,
                    "r",
                    encoding="utf-8",
                    errors="replace",
                ) as file_obj:
                    content = file_obj.read()

            return {
                "success": True,
                "content": content,
                "size": file_size,
                "path": resolved_path,
                "format": file_format,
                "modified_time": self._iso_mtime(resolved_path),
                "execution_time": time.monotonic() - started_at,
            }
        except Exception as exc:
            logger.error("[SandboxHandler] Device read_file failed: %s", exc)
            return self._error_response(
                str(exc),
                execution_time=time.monotonic() - started_at,
                path=file_path,
                size=0,
                content="",
            )

    def _list_files_sync(self, path: str, depth: int) -> Dict[str, Any]:
        """List files synchronously."""
        started_at = time.monotonic()
        try:
            resolved_path = self._normalize_path(path)
            if not os.path.exists(resolved_path):
                return self._error_response(
                    f"Path not found: {resolved_path}",
                    execution_time=time.monotonic() - started_at,
                    path=resolved_path,
                    entries=[],
                    total=0,
                )
            if not os.path.isdir(resolved_path):
                return self._error_response(
                    f"Path is not a directory: {resolved_path}",
                    execution_time=time.monotonic() - started_at,
                    path=resolved_path,
                    entries=[],
                    total=0,
                )

            entries = self._collect_entries(resolved_path, max(depth, 1))
            return {
                "success": True,
                "entries": entries,
                "total": len(entries),
                "path": resolved_path,
                "execution_time": time.monotonic() - started_at,
            }
        except Exception as exc:
            logger.error("[SandboxHandler] Device list_files failed: %s", exc)
            return self._error_response(
                str(exc),
                execution_time=time.monotonic() - started_at,
                path=path,
                entries=[],
                total=0,
            )

    def _write_file_sync(
        self,
        file_path: str,
        content: str,
        file_format: str,
        create_dirs: bool,
    ) -> Dict[str, Any]:
        """Write a file synchronously."""
        started_at = time.monotonic()
        try:
            resolved_path = self._normalize_path(file_path)
            parent_dir = os.path.dirname(resolved_path)
            if create_dirs and parent_dir:
                Path(parent_dir).mkdir(parents=True, exist_ok=True)

            if file_format == "bytes":
                content_bytes = base64.b64decode(content)
                mode = "wb"
            else:
                content_bytes = content.encode("utf-8")
                mode = "w"

            if len(content_bytes) > self.MAX_WRITE_FILE_SIZE:
                return self._error_response(
                    f"Content too large: {len(content_bytes)} bytes",
                    execution_time=time.monotonic() - started_at,
                    path=resolved_path,
                    size=len(content_bytes),
                )

            with open(
                resolved_path,
                mode,
                encoding=None if mode == "wb" else "utf-8",
            ) as file_obj:
                if mode == "wb":
                    file_obj.write(content_bytes)
                else:
                    file_obj.write(content)

            file_size = os.path.getsize(resolved_path)
            return {
                "success": True,
                "path": resolved_path,
                "size": file_size,
                "format": file_format,
                "modified_time": self._iso_mtime(resolved_path),
                "execution_time": time.monotonic() - started_at,
            }
        except Exception as exc:
            logger.error("[SandboxHandler] Device write_file failed: %s", exc)
            return self._error_response(
                str(exc),
                execution_time=time.monotonic() - started_at,
                path=file_path,
                size=0,
            )

    def _download_attachment_sync(
        self,
        attachment_url: str,
        save_path: str,
        auth_token: str,
        api_base_url: str,
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        """Download an attachment synchronously."""
        started_at = time.monotonic()
        resolved_path = self._normalize_path(save_path)
        try:
            Path(os.path.dirname(resolved_path)).mkdir(parents=True, exist_ok=True)
            download_url = (
                attachment_url
                if attachment_url.startswith(("http://", "https://"))
                else f"{api_base_url}{attachment_url if attachment_url.startswith('/') else '/' + attachment_url}"
            )
            response = requests.get(
                download_url,
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=timeout_seconds,
                stream=True,
            )
            response.raise_for_status()
            with open(resolved_path, "wb") as file_obj:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_obj.write(chunk)

            file_size = os.path.getsize(resolved_path)
            return {
                "success": True,
                "file_path": resolved_path,
                "file_size": file_size,
                "message": "File downloaded successfully",
                "execution_time": time.monotonic() - started_at,
            }
        except Exception as exc:
            logger.error("[SandboxHandler] Device download_attachment failed: %s", exc)
            return self._error_response(
                f"Failed to download file: {exc}",
                execution_time=time.monotonic() - started_at,
                file_path=resolved_path,
                file_size=0,
            )

    def _upload_attachment_sync(
        self,
        file_path: str,
        auth_token: str,
        api_base_url: str,
        overwrite_attachment_id: Optional[int],
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        """Upload an attachment synchronously."""
        started_at = time.monotonic()
        resolved_path = self._normalize_path(file_path)
        try:
            if not os.path.exists(resolved_path):
                return self._error_response(
                    f"File not found: {resolved_path}",
                    execution_time=time.monotonic() - started_at,
                    attachment_id=None,
                    filename=os.path.basename(resolved_path),
                    file_size=0,
                    download_url="",
                )
            if not os.path.isfile(resolved_path):
                return self._error_response(
                    f"Path is not a file: {resolved_path}",
                    execution_time=time.monotonic() - started_at,
                    attachment_id=None,
                    filename=os.path.basename(resolved_path),
                    file_size=0,
                    download_url="",
                )

            file_size = os.path.getsize(resolved_path)
            if file_size > self.MAX_UPLOAD_FILE_SIZE:
                return self._error_response(
                    f"File too large: {file_size} bytes",
                    execution_time=time.monotonic() - started_at,
                    attachment_id=None,
                    filename=os.path.basename(resolved_path),
                    file_size=file_size,
                    download_url="",
                )

            upload_url = f"{api_base_url}/api/attachments/upload"
            if overwrite_attachment_id is not None:
                upload_url = (
                    f"{upload_url}?overwrite_attachment_id={overwrite_attachment_id}"
                )

            with open(resolved_path, "rb") as file_obj:
                response = requests.post(
                    upload_url,
                    headers={"Authorization": f"Bearer {auth_token}"},
                    files={"file": (os.path.basename(resolved_path), file_obj)},
                    timeout=timeout_seconds,
                )
            response.raise_for_status()

            payload = response.json()
            if "detail" in payload:
                detail = payload["detail"]
                detail_message = (
                    detail.get("message") if isinstance(detail, dict) else str(detail)
                )
                return self._error_response(
                    f"Upload API error: {detail_message}",
                    execution_time=time.monotonic() - started_at,
                    attachment_id=None,
                    filename=os.path.basename(resolved_path),
                    file_size=file_size,
                    download_url="",
                )

            attachment_id = payload.get("id")
            return {
                "success": True,
                "attachment_id": attachment_id,
                "filename": payload.get("filename", os.path.basename(resolved_path)),
                "file_size": payload.get("file_size", file_size),
                "mime_type": payload.get(
                    "mime_type",
                    mimetypes.guess_type(resolved_path)[0]
                    or "application/octet-stream",
                ),
                "download_url": f"/api/attachments/{attachment_id}/download",
                "message": "File uploaded successfully",
                "execution_time": time.monotonic() - started_at,
            }
        except Exception as exc:
            logger.error("[SandboxHandler] Device upload_attachment failed: %s", exc)
            return self._error_response(
                f"Failed to upload file: {exc}",
                execution_time=time.monotonic() - started_at,
                attachment_id=None,
                filename=os.path.basename(resolved_path),
                file_size=0,
                download_url="",
            )

    def _normalize_path(self, path: str) -> str:
        """Map sandbox-style paths onto the local device home directory."""
        home_dir = os.path.expanduser("~")
        normalized = os.path.expanduser(path)
        if not os.path.isabs(normalized):
            return os.path.join(home_dir, normalized)
        if normalized == "/home/user":
            return home_dir
        if normalized.startswith("/home/user/"):
            suffix = normalized[len("/home/user/") :]
            return os.path.join(home_dir, suffix)
        return normalized

    def _collect_entries(self, root_path: str, depth: int) -> list[Dict[str, Any]]:
        """Collect directory entries recursively up to the requested depth."""
        entries: list[Dict[str, Any]] = []

        def walk(current_path: str, remaining_depth: int) -> None:
            with os.scandir(current_path) as iterator:
                for entry in iterator:
                    entry_path = entry.path
                    stat_result = entry.stat(follow_symlinks=False)
                    entries.append(
                        {
                            "name": entry.name,
                            "path": entry_path,
                            "type": self._entry_type(entry),
                            "size": stat_result.st_size,
                            "permissions": oct(stat_result.st_mode & 0o777),
                            "owner": self._resolve_owner(stat_result.st_uid),
                            "group": self._resolve_group(stat_result.st_gid),
                            "modified_time": self._iso_mtime(entry_path),
                            **(
                                {"symlink_target": os.readlink(entry_path)}
                                if entry.is_symlink()
                                else {}
                            ),
                        }
                    )
                    if remaining_depth > 1 and entry.is_dir(follow_symlinks=False):
                        walk(entry_path, remaining_depth - 1)

        walk(root_path, depth)
        return entries

    def _entry_type(self, entry: os.DirEntry[str]) -> str:
        """Return the normalized entry type."""
        if entry.is_symlink():
            return "symlink"
        if entry.is_dir(follow_symlinks=False):
            return "directory"
        return "file"

    def _resolve_owner(self, uid: int) -> str:
        """Resolve an owner name from uid."""
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError:
            return str(uid)

    def _resolve_group(self, gid: int) -> str:
        """Resolve a group name from gid."""
        try:
            return grp.getgrgid(gid).gr_name
        except KeyError:
            return str(gid)

    def _iso_mtime(self, path: str) -> str:
        """Return an ISO timestamp for a file's modification time."""
        return time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(path))
        )

    def _error_response(self, message: str, **kwargs: Any) -> Dict[str, Any]:
        """Build a consistent sandbox handler error response."""
        return {
            "success": False,
            "error": message,
            **kwargs,
        }
