"""Server-side Supabase persistence for canonical chat history."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from app.config.settings import settings
from app.services.base.base_service import BaseService

logger = logging.getLogger(__name__)


class SupabaseService(BaseService):
    """Stores exact conversation history in Supabase/Postgres."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self) -> None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            logger.warning(
                "SupabaseService: missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY "
                "— chat history persistence is unavailable."
            )
            return
        self._session = aiohttp.ClientSession(
            base_url=settings.SUPABASE_URL.rstrip("/"),
            headers={
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
        )
        await super().initialize()
        logger.info("SupabaseService ready for canonical chat history")

    async def shutdown(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        await super().shutdown()

    async def health_check(self) -> bool:
        """Return whether the server-side Supabase client is ready."""
        return self.is_initialized and self._session is not None and not self._session.closed

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, str]] = None,
        payload: Any = None,
        prefer: Optional[str] = None,
    ) -> Any:
        self._ensure_initialized()
        assert self._session is not None
        headers = {"Prefer": prefer} if prefer else {}
        async with self._session.request(
            method, f"/rest/v1/{path.lstrip('/')}", params=params, json=payload, headers=headers
        ) as response:
            if response.status >= 400:
                detail = await response.text()
                raise RuntimeError(f"Supabase request failed ({response.status}): {detail}")
            if response.status == 204:
                return None
            # PostgREST returns 201/204 with an empty body when
            # Prefer: return=minimal is used. That is still a successful write.
            body = await response.text()
            if not body.strip():
                return None
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body

    async def save_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message_id: str,
        role: str,
        content: str,
        created_at: Optional[str] = None,
    ) -> None:
        """Upsert the conversation and append one exact message."""
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        await self._request(
            "POST",
            "conversations",
            payload={
                "id": conversation_id,
                "user_id": user_id,
                "updated_at": timestamp,
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )
        await self._request(
            "POST",
            "conversation_messages",
            payload={
                "id": message_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "created_at": timestamp,
            },
            prefer="resolution=ignore-duplicates,return=minimal",
        )

    async def get_messages(self, user_id: str, conversation_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            "conversation_messages",
            params={
                "select": "id,conversation_id,role,content,created_at",
                "user_id": f"eq.{user_id}",
                "conversation_id": f"eq.{conversation_id}",
                "order": "created_at.asc",
            },
        )

    async def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            "conversations",
            params={
                "select": "id,created_at,updated_at,conversation_messages(id,role,content,created_at)",
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc",
            },
        )

    async def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        await self._request(
            "DELETE",
            "conversations",
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
            },
        )
