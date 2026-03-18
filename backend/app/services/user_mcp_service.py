# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""User-level MCP configuration helpers."""

from __future__ import annotations

import json
from typing import Any

from app.services.dingtalk_registry import get_dingtalk_service, list_dingtalk_services
from shared.utils.crypto import (
    decrypt_sensitive_data,
    encrypt_sensitive_data,
    is_data_encrypted,
)

DINGTALK_PROVIDER_KEY = "dingtalk"
DINGTALK_SERVICES_KEY = "services"
DINGTALK_CREDENTIALS_KEY = "credentials"
DINGTALK_URL_KEY = "url"
DINGTALK_DOCS_SERVICE_ID = "docs"
DINGTALK_DOCS_URL_KEY = "docs_url"


class UserMCPService:
    """Helper service for reading and writing user-scoped MCP settings."""

    @staticmethod
    def load_preferences(preferences: str | dict[str, Any] | None) -> dict[str, Any]:
        """Parse raw preferences payload into a dictionary."""
        if not preferences:
            return {}

        if isinstance(preferences, dict):
            return dict(preferences)

        try:
            parsed = json.loads(preferences)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def dump_preferences(preferences: dict[str, Any]) -> str:
        """Serialize preferences for persistence."""
        return json.dumps(preferences)

    @staticmethod
    def get_dingtalk_docs_config(
        preferences: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Get the decrypted DingTalk Docs MCP config from user preferences."""
        config = UserMCPService.get_dingtalk_service_config(
            preferences, DINGTALK_DOCS_SERVICE_ID
        )
        return {"enabled": config["enabled"], "docs_url": config["url"]}

    @staticmethod
    def get_dingtalk_service_config(
        preferences: str | dict[str, Any] | None, service_id: str
    ) -> dict[str, Any]:
        """Get a decrypted DingTalk MCP service config from user preferences."""
        prefs = UserMCPService.load_preferences(preferences)
        dingtalk = ((prefs.get("mcps") or {}).get(DINGTALK_PROVIDER_KEY) or {}).copy()
        services = (dingtalk.get(DINGTALK_SERVICES_KEY) or {}).copy()
        service = (services.get(service_id) or {}).copy()
        credentials = (service.get(DINGTALK_CREDENTIALS_KEY) or {}).copy()

        url = credentials.get(DINGTALK_URL_KEY, "")
        if not url and service_id == DINGTALK_DOCS_SERVICE_ID:
            # Backward-compatible fallback for previously stored docs config.
            legacy_credentials = (dingtalk.get(DINGTALK_CREDENTIALS_KEY) or {}).copy()
            service = service or {"enabled": bool(dingtalk.get("enabled", False))}
            url = legacy_credentials.get(DINGTALK_DOCS_URL_KEY, "")

        if isinstance(url, str) and url:
            if is_data_encrypted(url):
                decrypted = decrypt_sensitive_data(url)
                url = decrypted or ""
        else:
            url = ""

        return {
            "enabled": bool(service.get("enabled", False)),
            "url": url,
        }

    @staticmethod
    def list_dingtalk_service_configs(
        preferences: str | dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Return all registered DingTalk services merged with user config."""
        configs = []
        for service in list_dingtalk_services():
            config = UserMCPService.get_dingtalk_service_config(
                preferences, service["service_id"]
            )
            configs.append({**service, **config})
        return configs

    @staticmethod
    def set_dingtalk_docs_config(
        preferences: str | dict[str, Any] | None,
        *,
        enabled: bool,
        docs_url: str,
    ) -> dict[str, Any]:
        """Update DingTalk Docs MCP settings inside user preferences."""
        return UserMCPService.set_dingtalk_service_config(
            preferences,
            service_id=DINGTALK_DOCS_SERVICE_ID,
            enabled=enabled,
            url=docs_url,
        )

    @staticmethod
    def set_dingtalk_service_config(
        preferences: str | dict[str, Any] | None,
        *,
        service_id: str,
        enabled: bool,
        url: str,
    ) -> dict[str, Any]:
        """Update a DingTalk MCP service config inside user preferences."""
        if not get_dingtalk_service(service_id):
            raise ValueError(f"Unsupported DingTalk service: {service_id}")

        prefs = UserMCPService.load_preferences(preferences)
        mcps = dict(prefs.get("mcps") or {})
        dingtalk = dict(mcps.get(DINGTALK_PROVIDER_KEY) or {})
        services = dict(dingtalk.get(DINGTALK_SERVICES_KEY) or {})
        service = dict(services.get(service_id) or {})
        credentials = dict(service.get(DINGTALK_CREDENTIALS_KEY) or {})

        cleaned_url = url.strip()
        if cleaned_url:
            credentials[DINGTALK_URL_KEY] = (
                cleaned_url
                if is_data_encrypted(cleaned_url)
                else encrypt_sensitive_data(cleaned_url)
            )
        else:
            credentials.pop(DINGTALK_URL_KEY, None)

        service["enabled"] = enabled
        if credentials:
            service[DINGTALK_CREDENTIALS_KEY] = credentials
        else:
            service.pop(DINGTALK_CREDENTIALS_KEY, None)

        services[service_id] = service
        dingtalk[DINGTALK_SERVICES_KEY] = services

        if service_id == DINGTALK_DOCS_SERVICE_ID:
            # Remove deprecated docs-only fields once the config is saved in
            # the registry-driven structure.
            dingtalk.pop("enabled", None)
            legacy_credentials = dict(dingtalk.get(DINGTALK_CREDENTIALS_KEY) or {})
            legacy_credentials.pop(DINGTALK_DOCS_URL_KEY, None)
            if legacy_credentials:
                dingtalk[DINGTALK_CREDENTIALS_KEY] = legacy_credentials
            else:
                dingtalk.pop(DINGTALK_CREDENTIALS_KEY, None)

        mcps[DINGTALK_PROVIDER_KEY] = dingtalk
        prefs["mcps"] = mcps
        return prefs

    @staticmethod
    def list_dingtalk_mcp_servers(
        preferences: str | dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Build MCP server configs for all enabled DingTalk services."""
        servers = []
        for service in UserMCPService.list_dingtalk_service_configs(preferences):
            url = (service.get("url") or "").strip()
            if not service.get("enabled") or not url:
                continue

            servers.append(
                {
                    "name": service["server_name"],
                    "url": url,
                    "type": "streamable-http",
                }
            )

        return servers


user_mcp_service = UserMCPService()
