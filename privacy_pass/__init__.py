"""Privacy Pass: local PII sanitization gateway for AI models."""

from .sanitizer import (
    Detection,
    SanitizeResult,
    reveal,
    sanitize,
)

__all__ = ["Detection", "SanitizeResult", "reveal", "sanitize"]
