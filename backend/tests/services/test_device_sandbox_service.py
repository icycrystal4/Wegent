# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for device-backed sandbox execution."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.services.device_sandbox_service import (
    DeviceSandboxError,
    device_sandbox_service,
)


class TestDeviceSandboxService:
    """Tests for DeviceSandboxService."""

    @pytest.mark.asyncio
    async def test_execute_command_prefers_default_cloud_device(self):
        """Default cloud devices should be preferred over other online devices."""
        online_devices = [
            {
                "device_id": "local-device",
                "device_type": "local",
                "is_default": True,
                "capabilities": [],
            },
            {
                "device_id": "cloud-device",
                "device_type": "cloud",
                "is_default": True,
                "capabilities": [],
            },
        ]
        mock_sio = MagicMock()
        mock_sio.call = AsyncMock(
            return_value={
                "success": True,
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 0.12,
            }
        )

        with (
            patch(
                "app.services.device_sandbox_service.device_service.get_online_devices",
                AsyncMock(return_value=online_devices),
            ),
            patch(
                "app.services.device_sandbox_service.device_service.get_device_online_info",
                AsyncMock(return_value={"socket_id": "socket-1"}),
            ) as mock_online_info,
            patch(
                "app.services.device_sandbox_service.get_sio",
                return_value=mock_sio,
            ),
        ):
            result = await device_sandbox_service.execute_command(
                db=MagicMock(),
                user_id=1,
                command="himalaya --help",
            )

        assert result["success"] is True
        assert result["device_id"] == "cloud-device"
        mock_online_info.assert_awaited_once_with(1, "cloud-device")
        mock_sio.call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_command_raises_when_no_online_device(self):
        """An explicit error should be raised when no online device is available."""
        with patch(
            "app.services.device_sandbox_service.device_service.get_online_devices",
            AsyncMock(return_value=[]),
        ):
            with pytest.raises(DeviceSandboxError, match="No compatible online device"):
                await device_sandbox_service.execute_command(
                    db=MagicMock(),
                    user_id=1,
                    command="himalaya --help",
                )

    @pytest.mark.asyncio
    async def test_execute_command_prefers_task_bound_device(self):
        """Task-bound device should override normal priority ordering."""
        online_devices = [
            {
                "device_id": "local-device",
                "device_type": "local",
                "is_default": False,
                "capabilities": [],
            },
            {
                "device_id": "cloud-device",
                "device_type": "cloud",
                "is_default": True,
                "capabilities": [],
            },
        ]
        mock_sio = MagicMock()
        mock_sio.call = AsyncMock(
            return_value={
                "success": True,
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 0.12,
            }
        )

        with (
            patch(
                "app.services.device_sandbox_service.device_service.get_online_devices",
                AsyncMock(return_value=online_devices),
            ),
            patch(
                "app.services.device_sandbox_service.device_service.get_device_online_info",
                AsyncMock(return_value={"socket_id": "socket-1"}),
            ) as mock_online_info,
            patch(
                "app.services.device_sandbox_service.get_sio",
                return_value=mock_sio,
            ),
            patch.object(
                device_sandbox_service,
                "_get_bound_task_device_id",
                return_value="local-device",
            ),
            patch.object(device_sandbox_service, "_persist_task_binding"),
        ):
            result = await device_sandbox_service.execute_command(
                db=MagicMock(),
                user_id=1,
                task_id=794,
                command="pwd",
            )

        assert result["success"] is True
        assert result["device_id"] == "local-device"
        mock_online_info.assert_awaited_once_with(1, "local-device")
        mock_sio.call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_command_persists_selected_device_on_task(self):
        """Selected device should be written back as sticky task binding."""
        online_devices = [
            {
                "device_id": "cloud-device",
                "device_type": "cloud",
                "is_default": True,
                "capabilities": [],
            }
        ]
        mock_sio = MagicMock()
        mock_sio.call = AsyncMock(
            return_value={
                "success": False,
                "stdout": "",
                "stderr": "config missing",
                "exit_code": 1,
                "execution_time": 0.08,
            }
        )

        with (
            patch(
                "app.services.device_sandbox_service.device_service.get_online_devices",
                AsyncMock(return_value=online_devices),
            ),
            patch(
                "app.services.device_sandbox_service.device_service.get_device_online_info",
                AsyncMock(return_value={"socket_id": "socket-1"}),
            ),
            patch(
                "app.services.device_sandbox_service.get_sio",
                return_value=mock_sio,
            ),
            patch.object(
                device_sandbox_service,
                "_get_bound_task_device_id",
                return_value=None,
            ),
            patch.object(
                device_sandbox_service,
                "_persist_task_binding",
            ) as mock_persist_task_binding,
        ):
            result = await device_sandbox_service.execute_command(
                db=MagicMock(),
                user_id=1,
                task_id=794,
                command="himalaya --help",
            )

        assert result["success"] is False
        mock_persist_task_binding.assert_called_once_with(
            db=ANY,
            user_id=1,
            task_id=794,
            device_id="cloud-device",
        )
