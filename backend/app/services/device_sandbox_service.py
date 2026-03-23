# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Device-backed sandbox execution helpers."""

import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.socketio import get_sio
from app.models.task import TaskResource
from app.schemas.device import DeviceType
from app.services.device_service import device_service

logger = logging.getLogger(__name__)

SANDBOX_BACKEND_LABEL = "sandboxBackend"
SANDBOX_DEVICE_ID_LABEL = "sandboxDeviceId"
DEVICE_BACKEND_NAME = "device"


class DeviceSandboxError(RuntimeError):
    """Raised when a device-backed sandbox command cannot be executed."""


class DeviceSandboxService:
    """Service for forwarding sandbox commands to an online user device."""

    async def execute_command(
        self,
        db: Session,
        user_id: int,
        command: str,
        working_dir: str = "/home/user",
        timeout_seconds: int = 300,
        required_capability: Optional[str] = None,
        device_id: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute a command on a user's online device via Socket.IO."""
        return await self._execute_device_event(
            db=db,
            user_id=user_id,
            task_id=task_id,
            event_name="sandbox:exec",
            payload={
                "command": command,
                "working_dir": working_dir,
                "timeout_seconds": timeout_seconds,
            },
            timeout_seconds=timeout_seconds,
            required_capability=required_capability,
            device_id=device_id,
        )

    async def read_file(
        self,
        db: Session,
        user_id: int,
        file_path: str,
        format: str = "text",
        device_id: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Read a file from the bound device."""
        return await self._execute_device_event(
            db=db,
            user_id=user_id,
            task_id=task_id,
            event_name="sandbox:read_file",
            payload={"file_path": file_path, "format": format},
            timeout_seconds=60,
            device_id=device_id,
        )

    async def list_files(
        self,
        db: Session,
        user_id: int,
        path: str = "/home/user",
        depth: int = 1,
        device_id: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """List files from the bound device."""
        return await self._execute_device_event(
            db=db,
            user_id=user_id,
            task_id=task_id,
            event_name="sandbox:list_files",
            payload={"path": path, "depth": depth},
            timeout_seconds=60,
            device_id=device_id,
        )

    async def write_file(
        self,
        db: Session,
        user_id: int,
        file_path: str,
        content: str,
        format: str = "text",
        create_dirs: bool = True,
        device_id: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Write a file to the bound device."""
        return await self._execute_device_event(
            db=db,
            user_id=user_id,
            task_id=task_id,
            event_name="sandbox:write_file",
            payload={
                "file_path": file_path,
                "content": content,
                "format": format,
                "create_dirs": create_dirs,
            },
            timeout_seconds=60,
            device_id=device_id,
        )

    async def download_attachment(
        self,
        db: Session,
        user_id: int,
        attachment_url: str,
        save_path: str,
        auth_token: str,
        api_base_url: str,
        timeout_seconds: int = 300,
        device_id: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Download a Wegent attachment to the bound device."""
        return await self._execute_device_event(
            db=db,
            user_id=user_id,
            task_id=task_id,
            event_name="sandbox:download_attachment",
            payload={
                "attachment_url": attachment_url,
                "save_path": save_path,
                "auth_token": auth_token,
                "api_base_url": api_base_url,
                "timeout_seconds": timeout_seconds,
            },
            timeout_seconds=timeout_seconds,
            device_id=device_id,
        )

    async def upload_attachment(
        self,
        db: Session,
        user_id: int,
        file_path: str,
        auth_token: str,
        api_base_url: str,
        overwrite_attachment_id: Optional[int] = None,
        timeout_seconds: int = 300,
        device_id: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Upload a device-local file back to Wegent attachments."""
        return await self._execute_device_event(
            db=db,
            user_id=user_id,
            task_id=task_id,
            event_name="sandbox:upload_attachment",
            payload={
                "file_path": file_path,
                "auth_token": auth_token,
                "api_base_url": api_base_url,
                "overwrite_attachment_id": overwrite_attachment_id,
                "timeout_seconds": timeout_seconds,
            },
            timeout_seconds=timeout_seconds,
            device_id=device_id,
        )

    async def _execute_device_event(
        self,
        db: Session,
        user_id: int,
        task_id: Optional[int],
        event_name: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        required_capability: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Select a device, persist sticky binding, and dispatch an event."""
        target_device = await self._select_target_device(
            db=db,
            user_id=user_id,
            required_capability=required_capability,
            device_id=device_id,
            task_id=task_id,
        )
        if target_device is None:
            raise DeviceSandboxError("No compatible online device is available")

        target_device_id = target_device["device_id"]
        socket_id = await self._get_target_socket_id(user_id, target_device_id)

        if task_id is not None:
            self._persist_task_binding(
                db=db,
                user_id=user_id,
                task_id=task_id,
                device_id=target_device_id,
            )

        sio = get_sio()
        started_at = time.monotonic()

        logger.info(
            "[DeviceSandboxService] Forwarding event to device: user_id=%s, "
            "device_id=%s, event=%s, timeout=%ss, required_capability=%s",
            user_id,
            target_device_id,
            event_name,
            timeout_seconds,
            required_capability,
        )

        try:
            response = await sio.call(
                event_name,
                payload,
                to=socket_id,
                namespace="/local-executor",
                timeout=max(timeout_seconds + 5, 30),
            )
        except Exception as exc:
            logger.error(
                "[DeviceSandboxService] Device event dispatch failed: user_id=%s, "
                "device_id=%s, event=%s, error=%s",
                user_id,
                target_device_id,
                event_name,
                exc,
            )
            raise DeviceSandboxError(f"Device event dispatch failed: {exc}") from exc

        if not isinstance(response, dict):
            raise DeviceSandboxError("Device returned an invalid sandbox response")

        execution_time = response.get("execution_time")
        if not isinstance(execution_time, (int, float)):
            execution_time = time.monotonic() - started_at

        normalized = dict(response)
        normalized.setdefault("success", False)
        normalized["execution_time"] = execution_time
        normalized["device_id"] = target_device_id
        normalized["backend"] = DEVICE_BACKEND_NAME

        logger.info(
            "[DeviceSandboxService] Device event completed: user_id=%s, device_id=%s, "
            "socket_id=%s, event=%s, success=%s, execution_time=%.2fs",
            user_id,
            target_device_id,
            socket_id,
            event_name,
            bool(normalized.get("success")),
            execution_time,
        )

        return normalized

    async def _get_target_socket_id(self, user_id: int, target_device_id: str) -> str:
        """Resolve the active socket ID for a selected device."""
        online_info = await device_service.get_device_online_info(
            user_id, target_device_id
        )
        if not online_info:
            raise DeviceSandboxError(f"Device '{target_device_id}' is offline")

        socket_id = online_info.get("socket_id")
        if not socket_id:
            raise DeviceSandboxError(
                f"Device '{target_device_id}' does not have an active socket session"
            )
        return socket_id

    async def _select_target_device(
        self,
        db: Session,
        user_id: int,
        required_capability: Optional[str],
        device_id: Optional[str],
        task_id: Optional[int],
    ) -> Optional[dict[str, Any]]:
        """Pick an online device for sandbox execution."""
        online_devices = await device_service.get_online_devices(db, user_id)
        if not online_devices:
            return None

        bound_device_id = None
        if task_id is not None:
            bound_device_id = self._get_bound_task_device_id(
                db=db,
                user_id=user_id,
                task_id=task_id,
            )

        resolved_device_id = bound_device_id or device_id

        if bound_device_id and not any(
            device.get("device_id") == bound_device_id for device in online_devices
        ):
            raise DeviceSandboxError(
                f"Bound sandbox device '{bound_device_id}' is offline"
            )

        compatible_devices = [
            device
            for device in online_devices
            if self._matches_device(
                device=device,
                required_capability=required_capability,
                device_id=resolved_device_id,
            )
        ]
        if not compatible_devices:
            if bound_device_id:
                raise DeviceSandboxError(
                    f"Bound sandbox device '{bound_device_id}' is unavailable"
                )
            return None

        def priority(device: dict[str, Any]) -> int:
            device_type = device.get("device_type")
            is_default = bool(device.get("is_default"))
            if is_default and device_type == DeviceType.CLOUD.value:
                return 0
            if is_default:
                return 1
            if device_type == DeviceType.CLOUD.value:
                return 2
            return 3

        compatible_devices.sort(key=priority)
        selected_device = compatible_devices[0]
        logger.info(
            "[DeviceSandboxService] Selected device: user_id=%s, device_id=%s, "
            "device_name=%s, device_type=%s, is_default=%s, required_capability=%s, "
            "requested_device_id=%s, bound_device_id=%s, task_id=%s, "
            "capabilities=%s, compatible_candidates=%s",
            user_id,
            selected_device.get("device_id"),
            selected_device.get("device_name"),
            selected_device.get("device_type"),
            selected_device.get("is_default"),
            required_capability,
            device_id,
            bound_device_id,
            task_id,
            selected_device.get("capabilities") or [],
            [
                {
                    "device_id": device.get("device_id"),
                    "device_name": device.get("device_name"),
                    "device_type": device.get("device_type"),
                    "is_default": device.get("is_default"),
                }
                for device in compatible_devices
            ],
        )
        return selected_device

    def _matches_device(
        self,
        device: dict[str, Any],
        required_capability: Optional[str],
        device_id: Optional[str],
    ) -> bool:
        """Check whether a device satisfies routing constraints."""
        if device_id and device.get("device_id") != device_id:
            return False

        if not required_capability:
            return True

        capabilities = device.get("capabilities") or []
        return required_capability in capabilities

    def _get_bound_task_device_id(
        self,
        db: Session,
        user_id: int,
        task_id: int,
    ) -> Optional[str]:
        """Return the task-bound device ID when device backend was already selected."""
        task = (
            db.query(TaskResource)
            .filter(
                TaskResource.id == task_id,
                TaskResource.user_id == user_id,
                TaskResource.kind == "Task",
                TaskResource.is_active == TaskResource.STATE_ACTIVE,
            )
            .first()
        )
        if not task:
            return None

        task_json = task.json if isinstance(task.json, dict) else {}
        labels = task_json.get("metadata", {}).get("labels", {})
        if labels.get(SANDBOX_BACKEND_LABEL) != DEVICE_BACKEND_NAME:
            return None
        return labels.get(SANDBOX_DEVICE_ID_LABEL)

    def _persist_task_binding(
        self,
        db: Session,
        user_id: int,
        task_id: int,
        device_id: str,
    ) -> None:
        """Persist the selected device backend on the task for sticky routing."""
        task = (
            db.query(TaskResource)
            .filter(
                TaskResource.id == task_id,
                TaskResource.user_id == user_id,
                TaskResource.kind == "Task",
                TaskResource.is_active == TaskResource.STATE_ACTIVE,
            )
            .first()
        )
        if not task:
            return

        task_json = task.json if isinstance(task.json, dict) else {}
        metadata = task_json.setdefault("metadata", {})
        labels = metadata.setdefault("labels", {})

        if (
            labels.get(SANDBOX_BACKEND_LABEL) == DEVICE_BACKEND_NAME
            and labels.get(SANDBOX_DEVICE_ID_LABEL) == device_id
        ):
            return

        labels[SANDBOX_BACKEND_LABEL] = DEVICE_BACKEND_NAME
        labels[SANDBOX_DEVICE_ID_LABEL] = device_id
        task.json = task_json
        flag_modified(task, "json")

        logger.info(
            "[DeviceSandboxService] Persisted task sandbox binding: user_id=%s, "
            "task_id=%s, backend=%s, device_id=%s",
            user_id,
            task_id,
            DEVICE_BACKEND_NAME,
            device_id,
        )


device_sandbox_service = DeviceSandboxService()
