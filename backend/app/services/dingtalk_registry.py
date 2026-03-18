# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Registry for supported DingTalk MCP services."""

from __future__ import annotations

from typing import TypedDict


class DingTalkServiceDefinition(TypedDict):
    """Static definition for a DingTalk MCP service."""

    service_id: str
    server_name: str
    detail_url: str


DINGTALK_SERVICE_REGISTRY: dict[str, DingTalkServiceDefinition] = {
    "docs": {
        "service_id": "docs",
        "server_name": "dingtalk_docs",
        "detail_url": "https://mcp.dingtalk.com/#/detail?mcpId=9629",
    },
    "sheets": {
        "service_id": "sheets",
        "server_name": "dingtalk_sheets",
        "detail_url": "https://mcp.dingtalk.com/#/detail?mcpId=9555",
    }
}


def list_dingtalk_services() -> list[DingTalkServiceDefinition]:
    """Return all supported DingTalk MCP services."""
    return list(DINGTALK_SERVICE_REGISTRY.values())


def get_dingtalk_service(service_id: str) -> DingTalkServiceDefinition | None:
    """Look up a DingTalk MCP service by id."""
    return DINGTALK_SERVICE_REGISTRY.get(service_id)
