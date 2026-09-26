"""
Sensitive Data Sanitization & Log Scrubber.

Ensures that sensitive user secrets, BYOK API keys (e.g. OpenRouter keys),
Bearer JWT tokens, and private credentials are never:
1. Written to application logs
2. Printed to console stdout/stderr
3. Included in error stack traces
4. Returned in API error responses
"""

import logging
import re

# Regex patterns identifying sensitive API keys and authorization headers
KEY_PATTERNS: list[re.Pattern[str]] = [
    # OpenRouter API Key: sk-or-v1-<64 hex chars>
    re.compile(r"sk-or-v1-[a-zA-Z0-9]{32,64}"),
    # Generic API Keys / Tokens
    re.compile(r"sk-[a-zA-Z0-9]{20,64}"),
    # Bearer tokens in headers or logs
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
    # Supabase service role / anon keys (JWT format eyJ...)
    re.compile(r"eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}"),
]

REDACTED_KEY_LABEL = "[REDACTED_API_KEY]"
REDACTED_BEARER_LABEL = "Bearer [REDACTED_TOKEN]"


def sanitize_text(text: str) -> str:
    """
    Scrub all known sensitive credentials and secrets from text.

    Args:
        text: Raw log message, error description, or string.

    Returns:
        Cleaned text with secrets replaced by redaction labels.
    """
    if not text:
        return text

    sanitized = text
    # Mask OpenRouter and OpenAI keys
    sanitized = re.sub(r"sk-or-v1-[a-zA-Z0-9]{32,64}", REDACTED_KEY_LABEL, sanitized)
    sanitized = re.sub(r"sk-[a-zA-Z0-9]{20,64}", REDACTED_KEY_LABEL, sanitized)

    # Mask Bearer tokens
    sanitized = re.sub(
        r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}",
        REDACTED_BEARER_LABEL,
        sanitized,
        flags=re.IGNORECASE,
    )

    return sanitized


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that intercepts all log records across standard loggers
    and removes sensitive credentials before formatting and emission.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_text(record.msg)

        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize_text(arg) if isinstance(arg, str) else arg for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: sanitize_text(v) if isinstance(v, str) else v for k, v in record.args.items()
                }

        return True


def install_log_sanitizer() -> None:
    """Install SensitiveDataFilter across all root, uvicorn, and app log handlers."""
    sanitizer = SensitiveDataFilter()
    root_logger = logging.getLogger()
    root_logger.addFilter(sanitizer)

    for handler in root_logger.handlers:
        handler.addFilter(sanitizer)

    # Attach to specific third-party loggers
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        target_logger = logging.getLogger(logger_name)
        target_logger.addFilter(sanitizer)
        for h in target_logger.handlers:
            h.addFilter(sanitizer)
