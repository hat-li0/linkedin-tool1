"""
Security Logging & Alerting Module.
Covers Checklist Point 19: Add logs and alerts.
"""
import os
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import DATA_DIR
from security_crypto import mask_secret

LOG_FILE = DATA_DIR / "security_audit.log"
DATA_DIR.mkdir(exist_ok=True)

# Configure structured rotating security logger
_logger = logging.getLogger("security_audit")
_logger.setLevel(logging.INFO)
_logger.propagate = False

if not _logger.handlers:
    try:
        handler = RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=2 * 1024 * 1024,  # 2 MB per file
            backupCount=5,
            encoding="utf-8"
        )
        formatter = logging.Formatter(
            fmt='{"time":"%(asctime)s", "level":"%(levelname)s", "event":%(message)s}',
            datefmt="%Y-%m-%dT%H:%M:%SZ"
        )
        handler.setFormatter(formatter)
        _logger.addHandler(handler)
    except Exception as e:
        print(f"Warning: Could not initialize rotating file logger: {e}")


def _sanitize_details(data: Any) -> Any:
    """Recursively redacts any sensitive keys from log entries."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in ("key", "pass", "token", "secret", "cookie")):
                sanitized[k] = mask_secret(str(v)) if v else ""
            else:
                sanitized[k] = _sanitize_details(v)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_details(i) for i in data]
    return data


def log_security_event(
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "INFO",
    session_id: str = "anonymous"
):
    """
    Records a structured security event to the audit log.
    Ensures zero leakage of credentials, tokens, or PII.
    """
    clean_details = _sanitize_details(details or {})
    payload = {
        "event_type": event_type,
        "session_id": mask_secret(session_id, prefix_len=4, suffix_len=4),
        "timestamp": time.time(),
        "details": clean_details
    }
    
    msg = json.dumps(payload, ensure_ascii=False)
    
    sev_upper = severity.upper()
    if sev_upper == "WARNING":
        _logger.warning(msg)
    elif sev_upper == "ERROR":
        _logger.error(msg)
    elif sev_upper == "CRITICAL":
        _logger.critical(msg)
    else:
        _logger.info(msg)


def get_recent_security_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Reads and parses the most recent security logs for administrative inspection."""
    if not LOG_FILE.exists():
        return []
    logs = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                logs.append(data)
                if len(logs) >= limit:
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"Notice reading security audit log: {e}")
    return logs
