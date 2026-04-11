from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from pydantic import BaseModel

from backend.common import AgentError
from backend.common.feishu import truncate_feishu_text
from backend.schemas.feishu import FeishuReplyRequest, FeishuSendRequest, FeishuTokenState

DEFAULT_FEISHU_BASE_URL = "https://open.feishu.cn"


class FeishuClientError(AgentError):
    pass


class FeishuClientConfig(BaseModel):
    app_id: str
    app_secret: str
    base_url: str = DEFAULT_FEISHU_BASE_URL
    timeout_seconds: float = 10.0


class FeishuApiRequest(BaseModel):
    body: dict[str, Any]
    path: str
    use_token: bool = True


class FeishuClient:
    def __init__(self, config: FeishuClientConfig) -> None:
        self._config = config
        self._token_lock = asyncio.Lock()
        self._token_state = FeishuTokenState()

    async def get_tenant_token(self) -> str:
        try:
            if self._token_state.token and self._token_state.expires_at > time.time():
                return self._token_state.token
            async with self._token_lock:
                if self._token_state.token and self._token_state.expires_at > time.time():
                    return self._token_state.token
                data = await self._post_json(
                    FeishuApiRequest(
                        path="/open-apis/auth/v3/tenant_access_token/internal/",
                        body={
                            "app_id": self._config.app_id,
                            "app_secret": self._config.app_secret,
                        },
                        use_token=False,
                    )
                )
                token = str(data.get("tenant_access_token", "")).strip()
                if not token:
                    raise FeishuClientError("FEISHU_TOKEN_EMPTY", "tenant_access_token is missing")
                expires_in = int(data.get("expire", 7200))
                self._token_state = FeishuTokenState(
                    token=token,
                    expires_at=time.time() + max(expires_in - 60, 60),
                )
                return token
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FeishuClientError("FEISHU_TOKEN_ERROR", str(exc)) from exc

    async def send_message(self, request: FeishuSendRequest) -> dict[str, Any]:
        try:
            return await self._post_json(
                FeishuApiRequest(
                    path="/open-apis/im/v1/messages?receive_id_type=chat_id",
                    body={
                        "receive_id": request.receive_id,
                        "msg_type": request.msg_type,
                        "content": self._build_content(request.content, request.msg_type),
                    },
                )
            )
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FeishuClientError("FEISHU_SEND_MESSAGE_ERROR", str(exc)) from exc

    async def reply_message(self, request: FeishuReplyRequest) -> dict[str, Any]:
        try:
            return await self._post_json(
                FeishuApiRequest(
                    path=f"/open-apis/im/v1/messages/{request.message_id}/reply",
                    body={
                        "msg_type": request.msg_type,
                        "content": self._build_content(request.content, request.msg_type),
                    },
                )
            )
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FeishuClientError("FEISHU_REPLY_MESSAGE_ERROR", str(exc)) from exc

    async def _post_json(self, request: FeishuApiRequest) -> dict[str, Any]:
        try:
            headers = {"Content-Type": "application/json; charset=utf-8"}
            if request.use_token:
                headers["Authorization"] = f"Bearer {await self.get_tenant_token()}"
            async with httpx.AsyncClient(
                timeout=self._config.timeout_seconds,
                trust_env=False,
            ) as client:
                response = await client.post(
                    f"{self._config.base_url}{request.path}",
                    json=request.body,
                    headers=headers,
                )
            if response.status_code >= 400:
                raise FeishuClientError(
                    "FEISHU_HTTP_ERROR",
                    f"HTTP {response.status_code}",
                )
            data = response.json()
            if int(data.get("code", 0)) != 0:
                raise FeishuClientError(
                    "FEISHU_API_ERROR",
                    str(data.get("msg", data)),
                )
            return data.get("data", data)
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FeishuClientError("FEISHU_POST_ERROR", str(exc)) from exc

    def _build_content(self, content: str, msg_type: str) -> str:
        normalized = truncate_feishu_text(content.strip())
        if msg_type == "text":
            return json.dumps({"text": normalized}, ensure_ascii=False)
        return normalized


__all__ = [
    "DEFAULT_FEISHU_BASE_URL",
    "FeishuClient",
    "FeishuClientConfig",
    "FeishuClientError",
]
