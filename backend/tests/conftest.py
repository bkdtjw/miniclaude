from __future__ import annotations

from collections.abc import Generator

import pytest

from backend.config.settings import settings


@pytest.fixture(autouse=True)
def reset_feishu_settings() -> Generator[None, None, None]:
    original_url = settings.feishu_webhook_url
    original_secret = settings.feishu_webhook_secret
    original_app_id = settings.feishu_app_id
    original_app_secret = settings.feishu_app_secret
    original_verification_token = settings.feishu_verification_token
    original_encrypt_key = settings.feishu_encrypt_key
    settings.feishu_webhook_url = ""
    settings.feishu_webhook_secret = ""
    settings.feishu_app_id = ""
    settings.feishu_app_secret = ""
    settings.feishu_verification_token = ""
    settings.feishu_encrypt_key = ""
    yield
    settings.feishu_webhook_url = original_url
    settings.feishu_webhook_secret = original_secret
    settings.feishu_app_id = original_app_id
    settings.feishu_app_secret = original_app_secret
    settings.feishu_verification_token = original_verification_token
    settings.feishu_encrypt_key = original_encrypt_key
