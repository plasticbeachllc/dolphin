"""Shared validation for caller-held workspace cleanup capabilities."""

from __future__ import annotations

import re

CLEANUP_RECEIPT_PREFIX = "dolphin-cleanup-v1_"
CLEANUP_RECEIPT_TOKEN_LENGTH = 43
CLEANUP_RECEIPT_LENGTH = len(CLEANUP_RECEIPT_PREFIX) + CLEANUP_RECEIPT_TOKEN_LENGTH
CLEANUP_RECEIPT_PATTERN = rf"{CLEANUP_RECEIPT_PREFIX}[A-Za-z0-9_-]{{{CLEANUP_RECEIPT_TOKEN_LENGTH}}}"

_CLEANUP_RECEIPT_RE = re.compile(rf"\A{CLEANUP_RECEIPT_PATTERN}\Z")


def is_valid_cleanup_receipt(receipt: str) -> bool:
    """Accept one versioned, unpadded base64url-shaped 256-bit capability."""
    return _CLEANUP_RECEIPT_RE.fullmatch(receipt) is not None
