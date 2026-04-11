from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pydantic import BaseModel, Field

from backend.common import AgentError


class FeishuSecurityError(AgentError):
    pass


class FeishuSecurityConfig(BaseModel):
    encrypt_key: str = ""
    verification_token: str = ""


class FeishuRequestContext(BaseModel):
    body: dict[str, Any]
    body_text: str
    headers: dict[str, str] = Field(default_factory=dict)


def build_request_context(
    raw_body: bytes,
    headers: Mapping[str, str],
) -> FeishuRequestContext:
    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
        if not isinstance(body, dict):
            raise FeishuSecurityError("FEISHU_BODY_INVALID", "Feishu callback body must be an object")
        lowered = {key.lower(): value for key, value in headers.items()}
        return FeishuRequestContext(
            body=body,
            body_text=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            headers=lowered,
        )
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FeishuSecurityError("FEISHU_BODY_PARSE_ERROR", str(exc)) from exc


def parse_callback_payload(
    context: FeishuRequestContext,
    config: FeishuSecurityConfig,
) -> dict[str, Any]:
    try:
        _verify_signature(context, config)
        payload = context.body
        if "encrypt" in payload and config.encrypt_key:
            payload = json.loads(_decrypt_payload(str(payload["encrypt"]), config.encrypt_key))
        token = str(payload.get("token", "")).strip()
        if config.verification_token and token and token != config.verification_token:
            raise FeishuSecurityError("FEISHU_TOKEN_INVALID", "Verification token mismatch")
        return payload
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FeishuSecurityError("FEISHU_CALLBACK_PARSE_ERROR", str(exc)) from exc


def _verify_signature(
    context: FeishuRequestContext,
    config: FeishuSecurityConfig,
) -> None:
    signature = context.headers.get("x-lark-signature", "").strip()
    timestamp = context.headers.get("x-lark-request-timestamp", "").strip()
    nonce = context.headers.get("x-lark-request-nonce", "").strip()
    if not signature or not timestamp or not nonce:
        return
    if config.encrypt_key:
        digest = hashlib.sha256(
            f"{timestamp}{nonce}{config.encrypt_key}{context.body_text}".encode("utf-8")
        ).hexdigest()
        if digest != signature:
            raise FeishuSecurityError("FEISHU_SIGNATURE_INVALID", "Invalid Feishu request signature")
        return
    if config.verification_token:
        digest = hashlib.sha1(
            f"{timestamp}{nonce}{config.verification_token}{context.body_text}".encode("utf-8")
        ).hexdigest()
        if digest != signature:
            raise FeishuSecurityError("FEISHU_SIGNATURE_INVALID", "Invalid Feishu request signature")


def _decrypt_payload(encrypted: str, encrypt_key: str) -> str:
    try:
        encrypted_bytes = base64.b64decode(encrypted)
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        return plain.decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise FeishuSecurityError("FEISHU_DECRYPT_ERROR", str(exc)) from exc


__all__ = [
    "FeishuRequestContext",
    "FeishuSecurityConfig",
    "FeishuSecurityError",
    "build_request_context",
    "parse_callback_payload",
]
