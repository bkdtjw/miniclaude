from __future__ import annotations

MAX_FEISHU_CONTENT_BYTES = 18000
FEISHU_TRUNCATION_NOTICE = "\n\n...[message truncated]"


def truncate_feishu_text(
    content: str,
    max_bytes: int = MAX_FEISHU_CONTENT_BYTES,
) -> str:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content
    notice_bytes = FEISHU_TRUNCATION_NOTICE.encode("utf-8")
    budget = max(max_bytes - len(notice_bytes), 0)
    truncated = encoded[:budget]
    while truncated:
        try:
            decoded = truncated.decode("utf-8")
            return f"{decoded}{FEISHU_TRUNCATION_NOTICE}"
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return FEISHU_TRUNCATION_NOTICE[:max_bytes]


__all__ = [
    "FEISHU_TRUNCATION_NOTICE",
    "MAX_FEISHU_CONTENT_BYTES",
    "truncate_feishu_text",
]
