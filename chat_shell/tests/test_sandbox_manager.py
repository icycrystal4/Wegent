# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for sticky device backend routing in sandbox manager."""

import pytest

from chat_shell.tools.sandbox._base import SandboxManager


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_sandbox_manager_sticks_to_device_backend(monkeypatch):
    """Once a task is routed to a device, later commands stay on that device."""
    captured_payloads: list[dict] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers):
            captured_payloads.append(json)
            return _FakeResponse(
                {
                    "success": True,
                    "stdout": "ok",
                    "stderr": "",
                    "exit_code": 0,
                    "execution_time": 0.1,
                    "device_id": "device-1",
                    "backend": "device",
                }
            )

    monkeypatch.setattr(
        "chat_shell.tools.sandbox._base.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    manager = SandboxManager.get_instance(
        task_id=794,
        user_id=2,
        user_name="sifang",
    )

    try:
        assert manager.is_device_backend_bound() is False
        assert manager.should_use_device_backend_for_command("ls /home") is False

        await manager.execute_command_via_device(command="himalaya --help")

        assert manager.is_device_backend_bound() is True
        assert manager.should_use_device_backend_for_command("ls /home") is True

        await manager.execute_command_via_device(command="ls /home")

        assert captured_payloads[0]["task_id"] == 794
        assert captured_payloads[0]["device_id"] is None
        assert captured_payloads[1]["device_id"] == "device-1"
    finally:
        SandboxManager.remove_instance(794)
