"""Identifier screening and tamper-evident, in-memory HMAC audit trail.

Identifier screening is best-effort and is NOT HIPAA de-identification.
For durable audit verification, supply AUDIT_SECRET_KEY securely to each process.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PHI_PATTERNS = [
    re.compile(r"\bMRN[:#\s-]*\d{4,10}\b", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:DOB|Date of Birth)[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\b(?:Patient\s+Name|Patient)[:\s]+[A-Z][a-z]+\s+[A-Z][a-z]+\b", re.IGNORECASE),
    re.compile(r"\b(?:John\s+Doe|Jane\s+Smith|Alice\s+Johnson)\b", re.IGNORECASE),
]


class SecurityException(Exception):
    """Detected a potential sensitive identifier."""


class ResourceLimitExceededException(Exception):
    """Computational parameters exceed safety bounds."""


def assert_no_phi(text: Any) -> None:
    if text is None:
        return
    value = str(text)
    if any(pattern.search(value) for pattern in PHI_PATTERNS):
        raise SecurityException("Potential sensitive identifier detected; request rejected.")


class PHIGuard:
    @staticmethod
    def assert_no_phi(text: Any) -> None:
        assert_no_phi(text)

    @staticmethod
    def redact_phi(text: str) -> str:
        result = str(text)
        for pattern in PHI_PATTERNS:
            result = pattern.sub("[REDACTED_IDENTIFIER]", result)
        return result


class AuditTrail:
    """Per-process, tamper-evident chain; not durable storage."""

    GENESIS = "GENESIS_BLOCK_0000000000000000"
    SIGNED_FIELDS = (
        "audit_id", "timestamp", "actor", "actor_tier",
        "event_type", "payload_hash", "prev_hash",
    )

    def __init__(self, secret_key: Optional[str] = None):
        supplied = secret_key if secret_key is not None else os.getenv("AUDIT_SECRET_KEY")
        if supplied is not None and not supplied:
            raise ValueError("AUDIT_SECRET_KEY cannot be empty")
        # Random process-local key is safe for development, but cannot verify after restart.
        self.secret_key = supplied.encode("utf-8") if supplied else secrets.token_bytes(32)
        self.logs: List[Dict[str, str]] = []

    def _signature(self, entry: Dict[str, str]) -> str:
        message = "|".join(entry[field] for field in self.SIGNED_FIELDS)
        return hmac.new(self.secret_key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def log(self, actor: str, actor_tier: str, event_type: str,
            details: Dict[str, Any]) -> Dict[str, str]:
        payload = json.dumps(details, sort_keys=True, allow_nan=False, default=str)
        for text in (actor, actor_tier, event_type, payload):
            assert_no_phi(text)
        entry = {
            "audit_id": f"AUDIT-{secrets.token_hex(12)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": str(actor),
            "actor_tier": str(actor_tier),
            "event_type": str(event_type),
            "payload_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "prev_hash": self.logs[-1]["current_hash"] if self.logs else self.GENESIS,
        }
        entry["current_hash"] = self._signature(entry)
        self.logs.append(entry)
        return entry.copy()

    def verify_integrity(self) -> bool:
        previous = self.GENESIS
        for entry in self.logs:
            try:
                if entry["prev_hash"] != previous:
                    return False
                expected = self._signature(entry)
                if not hmac.compare_digest(entry["current_hash"], expected):
                    return False
                previous = entry["current_hash"]
            except (KeyError, TypeError, AttributeError):
                return False
        return True

    def get_trail(self) -> List[Dict[str, str]]:
        return [entry.copy() for entry in self.logs]


GLOBAL_AUDIT = AuditTrail()


class AuditLogger:
    @staticmethod
    def log(actor: str, actor_tier: str, event_type: str,
            details: Dict[str, Any]) -> Dict[str, str]:
        return GLOBAL_AUDIT.log(actor, actor_tier, event_type, details)

    @staticmethod
    def get_trail() -> List[Dict[str, str]]:
        return GLOBAL_AUDIT.get_trail()

    @staticmethod
    def verify_integrity() -> bool:
        return GLOBAL_AUDIT.verify_integrity()


class ActionExecutor:
    @staticmethod
    def execute_with_audit(actor: str, actor_tier: str, action_type: str,
                           fn, *args, **kwargs):
        result = fn(*args, **kwargs)
        AuditLogger.log(actor, actor_tier, action_type, {"status": "SUCCESS"})
        return result
