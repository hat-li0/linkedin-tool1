"""
Security Guard Module: Comprehensive Application Defense Engine.
Covers Checklist Points: 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16.
"""
import os
import re
import time
import socket
import urllib.parse
import ipaddress
import secrets
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List
from collections import defaultdict
import threading
import json

from config import DATA_DIR, OUTPUTS_DIR, load_settings
from security_crypto import verify_password, verify_totp, mask_secret
from security_logger import log_security_event

# ----------------- 1. SESSIONS & ROW-LEVEL DATA ISOLATION (POINT 10) -----------------
SESSIONS_OUTPUTS_DIR = OUTPUTS_DIR / "sessions"
SESSIONS_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def get_or_create_session_id(session_state_dict: Any) -> str:
    """
    Retrieves or generates a cryptographically random, isolated session ID (Point 10).
    """
    if "security_session_id" not in session_state_dict:
        session_state_dict["security_session_id"] = secrets.token_hex(16)
    return session_state_dict["security_session_id"]


def get_session_outputs_dir(session_id: str) -> Path:
    """
    Returns an isolated, per-user folder for generated files and tailored CVs (Point 10).
    Ensures that no user can see or overwrite another user's files.
    """
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)
    session_dir = SESSIONS_OUTPUTS_DIR / clean_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def is_file_accessible_by_session(file_path: Path, session_id: str) -> bool:
    """
    Verifies that the requested file belongs strictly to the user's isolated session (Point 10).
    Prevents Insecure Direct Object References (IDOR).
    """
    try:
        resolved = Path(file_path).resolve()
        session_dir = get_session_outputs_dir(session_id).resolve()
        return resolved.is_relative_to(session_dir) and resolved.exists()
    except Exception:
        return False


# ----------------- 2. PATH TRAVERSAL & SECURE STORAGE (POINT 9) -----------------
def sanitize_filename(filename: str) -> str:
    """
    Strips directory traversal sequences (../, \\), control chars, and special symbols (Point 9).
    """
    clean = os.path.basename(filename)
    clean = re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", clean)
    clean = re.sub(r"\.{2,}", ".", clean)  # Remove multiple dots
    clean = clean.strip(". ")
    return clean or f"file_{secrets.token_hex(4)}"


def safe_resolve_path(base_dir: Path, filename_or_rel_path: str) -> Optional[Path]:
    """
    Resolves a target path and ensures it stays strictly within base_dir (Point 9).
    Returns None if any traversal attempt is detected.
    """
    try:
        base_resolved = base_dir.resolve()
        target = (base_dir / filename_or_rel_path).resolve()
        if target.is_relative_to(base_resolved):
            return target
    except Exception:
        pass
    log_security_event(
        "PATH_TRAVERSAL_BLOCKED",
        {"target": str(filename_or_rel_path)},
        severity="WARNING"
    )
    return None


def safe_atomic_write(file_path: Path, content: Any, is_binary: bool = False) -> bool:
    """
    Atomically writes data using a temporary file to prevent corruption and race conditions (Point 9).
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = file_path.with_suffix(f".tmp_{secrets.token_hex(4)}")
        mode = "wb" if is_binary else "w"
        encoding = None if is_binary else "utf-8"
        with open(tmp_path, mode, encoding=encoding) as f:
            f.write(content)
        # Atomic replace
        os.replace(tmp_path, file_path)
        return True
    except Exception as e:
        log_security_event("ATOMIC_WRITE_ERROR", {"path": str(file_path), "error": str(e)}, severity="ERROR")
        return False


# ----------------- 3. FORM & UPLOAD SANITIZATION (POINT 14) -----------------
def sanitize_user_input(text: str, max_length: int = 150) -> str:
    """
    Sanitizes user input strings from forms: strips tags, removes control characters,
    and enforces maximum length constraints (Point 14).
    """
    if not text:
        return ""
    # Remove HTML tags and script wrappers
    cleaned = re.sub(r"<[^>]*?>", "", str(text))
    # Strip dangerous ASCII control characters
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


def validate_uploaded_cv(file_obj: Any, filename: str, max_size_bytes: int = 10 * 1024 * 1024) -> Tuple[bool, str]:
    """
    Strict file upload validation (Point 14):
    1. Size cap (max 10MB to prevent memory exhaustion DoS)
    2. Extension allowlist (.pdf, .docx, .txt)
    3. Magic byte signature verification
    """
    clean_name = sanitize_filename(filename)
    ext = os.path.splitext(clean_name)[1].lower()

    if ext not in (".pdf", ".docx", ".txt"):
        log_security_event("INVALID_FILE_EXTENSION", {"filename": clean_name}, severity="WARNING")
        return False, "نوع الملف غير مدعوم. الأنظمة تقبل فقط ملفات PDF أو Word (.docx) أو نصوص TXT."

    # Check size
    file_bytes = None
    if hasattr(file_obj, "size"):
        size = file_obj.size
    elif hasattr(file_obj, "getbuffer"):
        size = len(file_obj.getbuffer())
    elif hasattr(file_obj, "getvalue"):
        file_bytes = file_obj.getvalue()
        size = len(file_bytes)
    else:
        size = 0

    if size > max_size_bytes:
        log_security_event("FILE_OVERSIZE_BLOCKED", {"filename": clean_name, "size": size}, severity="WARNING")
        return False, f"حجم الملف يتجاوز الحد الأقصى المسموح به (10 ميجابايت). حجم ملفك: {size / (1024*1024):.1f}MB"
    if size < 20:
        return False, "الملف فارغ أو تالف."

    # Inspect magic bytes
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
            header = file_obj.read(16)
            file_obj.seek(0)
        elif file_bytes is not None:
            header = file_bytes[:16]
        else:
            header = b""

        if ext == ".pdf":
            if not header.startswith(b"%PDF-"):
                log_security_event("MAGIC_BYTES_MISMATCH", {"filename": clean_name, "expected": "pdf"}, severity="WARNING")
                return False, "تنبيه أمان: محتوى الملف لا يطابق توقيع ملفات PDF الأصلية (%PDF-)."
        elif ext == ".docx":
            if not header.startswith(b"PK\x03\x04"):
                log_security_event("MAGIC_BYTES_MISMATCH", {"filename": clean_name, "expected": "docx"}, severity="WARNING")
                return False, "تنبيه أمان: محتوى الملف لا يطابق بنية ملفات Word (.docx) الأصلية."
        elif ext == ".txt":
            # Ensure text does not contain dangerous binary null bytes
            sample = header[:16]
            if b"\x00" in sample:
                return False, "تنبيه أمان: يحتوي الملف على بيانات ثنائية غير نصية."
    except Exception as e:
        log_security_event("FILE_VALIDATION_ERROR", {"error": str(e)}, severity="ERROR")
        return False, "فشل فحص سلامة الملف المرفوع."

    return True, "الملف سليم ومطابق للشروط."


# ----------------- 4. SSRF & SECURE OUTBOUND REQUESTS (POINT 8) -----------------
ALLOWED_OUTBOUND_DOMAINS = [
    "linkedin.com",
    "www.linkedin.com",
    "saudi.tanqeeb.com",
    "tanqeeb.com",
    "remotive.com",
    "api.remotive.com",
    "generativelanguage.googleapis.com",
    "api.openai.com"
]


def is_safe_outbound_url(url: str) -> Tuple[bool, str]:
    """
    Prevents Server-Side Request Forgery (SSRF) (Point 8).
    - Requires https scheme
    - Rejects localhost, loopback, private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16)
    - Validates against an approved domain allowlist.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() != "https":
            return False, "فقط اتصالات HTTPS الآمنة والمشفرة مسموح بها."

        hostname = parsed.hostname
        if not hostname:
            return False, "عنوان URL غير صالح."

        # Domain allowlist check
        h_lower = hostname.lower()
        domain_match = any(h_lower == d or h_lower.endswith("." + d) for d in ALLOWED_OUTBOUND_DOMAINS)
        if not domain_match:
            log_security_event("SSRF_DOMAIN_BLOCKED", {"host": h_lower}, severity="WARNING")
            return False, f"تم حظر الاتصال بنطاق غير معتمد ({h_lower})."

        # Resolve IP to detect loopback or private ranges
        try:
            addr_info = socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for item in addr_info:
                ip_str = item[4][0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                    log_security_event("SSRF_PRIVATE_IP_BLOCKED", {"host": h_lower, "ip": str(ip)}, severity="CRITICAL")
                    return False, "تم حظر الاتصال بعنوان شبكة داخلية (SSRF Protection)."
        except socket.gaierror:
            pass  # DNS resolution failed; requests module will handle connection failure

        return True, "URL معتمد وآمن."
    except Exception as e:
        return False, f"خطأ في التحقق من صحة الرابط: {e}"


# ----------------- 5. RATE LIMITING ENGINE (POINT 15) -----------------
class RateLimiter:
    """
    Thread-safe Sliding Window Rate Limiter (Point 15).
    Tracks requests per session to stop brute-forcing and resource exhaustion.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._history = defaultdict(list)
        self._lockouts = {}

    def check(self, key: str, action: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, str]:
        now = time.time()
        bucket_key = f"{key}:{action}"

        with self._lock:
            # Check lockout
            if bucket_key in self._lockouts:
                until = self._lockouts[bucket_key]
                if now < until:
                    remaining = int(until - now)
                    return False, remaining, f"تم قفل المحاولات مؤقتاً لحماية الحساب. يرجى الانتظار {remaining} ثانية."
                else:
                    del self._lockouts[bucket_key]

            # Clean expired timestamps
            cutoff = now - window_seconds
            timestamps = [t for t in self._history[bucket_key] if t > cutoff]
            self._history[bucket_key] = timestamps

            if len(timestamps) >= max_requests:
                earliest = timestamps[0]
                retry_after = max(1, int(window_seconds - (now - earliest)))
                log_security_event(
                    "RATE_LIMIT_EXCEEDED",
                    {"action": action, "retry_after": retry_after},
                    severity="WARNING",
                    session_id=key
                )
                return False, retry_after, f"تجاوزت الحد المسموح به لهذه العملية. يرجى الانتظار {retry_after} ثانية."

            self._history[bucket_key].append(now)
            return True, 0, ""

    def record_auth_failure(self, key: str, max_failures: int = 5, lockout_seconds: int = 900):
        now = time.time()
        bucket_key = f"{key}:auth_fail"
        with self._lock:
            self._history[bucket_key] = [t for t in self._history[bucket_key] if t > (now - lockout_seconds)]
            self._history[bucket_key].append(now)
            if len(self._history[bucket_key]) >= max_failures:
                self._lockouts[f"{key}:auth_attempt"] = now + lockout_seconds
                log_security_event("ACCOUNT_LOCKED_BRUTE_FORCE", {"key": key, "duration": lockout_seconds}, severity="CRITICAL")

    def reset_auth(self, key: str):
        with self._lock:
            self._history.pop(f"{key}:auth_fail", None)
            self._lockouts.pop(f"{key}:auth_attempt", None)


_rate_limiter = RateLimiter()


def check_ai_rate_limit(session_id: str) -> Tuple[bool, int, str]:
    """Rate limit: Max 5 AI requests per minute per user session (Point 15)."""
    return _rate_limiter.check(session_id, "ai_query", max_requests=5, window_seconds=60)


def check_search_rate_limit(session_id: str) -> Tuple[bool, int, str]:
    """Rate limit: Max 10 job search queries per minute per user session (Point 15)."""
    return _rate_limiter.check(session_id, "job_search", max_requests=10, window_seconds=60)


def check_auth_rate_limit(session_id: str) -> Tuple[bool, int, str]:
    """Rate limit: Max 5 login attempts per 15 minutes before temporary lockout (Point 15)."""
    return _rate_limiter.check(session_id, "auth_attempt", max_requests=5, window_seconds=900)


def record_failed_auth(session_id: str):
    _rate_limiter.record_auth_failure(session_id)


def reset_failed_auth(session_id: str):
    _rate_limiter.reset_auth(session_id)


# ----------------- 6. SPENDING CAP & USAGE QUOTA GUARD (POINT 16) -----------------
QUOTA_FILE = DATA_DIR / "quota_usage.json"


def get_daily_quota_status(daily_cap: int = 20) -> Dict[str, Any]:
    """
    Retrieves the daily AI usage against the spending/request quota cap (Point 16).
    """
    today = time.strftime("%Y-%m-%d")
    data = {"date": today, "requests": 0, "estimated_tokens": 0}
    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("date") == today:
                    data = saved
        except Exception:
            pass

    used = data.get("requests", 0)
    remaining = max(0, daily_cap - used)
    is_exceeded = used >= daily_cap
    return {
        "date": today,
        "used_requests": used,
        "daily_cap": daily_cap,
        "remaining_requests": remaining,
        "estimated_tokens": data.get("estimated_tokens", 0),
        "is_exceeded": is_exceeded
    }


def record_ai_usage(tokens: int = 0):
    """
    Records an AI invocation against the daily quota ledger (Point 16).
    """
    today = time.strftime("%Y-%m-%d")
    data = {"date": today, "requests": 0, "estimated_tokens": 0}
    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("date") == today:
                    data = saved
        except Exception:
            pass

    data["requests"] += 1
    data["estimated_tokens"] += max(tokens, 1500)
    safe_atomic_write(QUOTA_FILE, json.dumps(data, indent=2))


# ----------------- 7. INFORMATION DISCLOSURE SUPPRESSION (POINT 13) -----------------
def clean_error_message(e: Exception) -> str:
    """
    Suppresses internal server paths, system traces, and leaks from user error displays (Point 13).
    """
    msg = str(e)
    # Strip drive letters and local system paths (including spaces)
    msg = re.sub(r"[a-zA-Z]:\\[^:\r\n<>\"?*]+[\\/]", "[SystemPath]\\", msg)
    msg = re.sub(r"/(?:mount/src|home|var|tmp)/[^:\r\n<>\"?*]+[\\/]", "[SystemPath]/", msg)
    msg = re.sub(r"File \".*?\", line \d+", "Error at handler", msg)
    # Clean generic API key leaks
    msg = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", msg)
    msg = re.sub(r"sk-[0-9A-Za-z-_]{30,}", "[REDACTED_API_KEY]", msg)
    return msg


def strip_internal_paths(text: str) -> str:
    """Removes server file paths from text, PDFs, and UI outputs (Point 13)."""
    text = re.sub(r"[a-zA-Z]:\\[^:\r\n<>\"?*]+[\\/]", "", text)
    text = re.sub(r"/(?:mount/src|home|var|tmp)/[^:\r\n<>\"?*]+[\\/]", "", text)
    return text


# ----------------- 8. AUTHENTICATION & RBAC (POINTS 4, 5, 6, 7) -----------------
def is_app_password_required() -> bool:
    """Checks whether an application gate passcode is configured."""
    return bool(os.environ.get("APP_ACCESS_PASSWORD", "").strip())


def verify_app_access_passcode(passcode: str) -> bool:
    """Verifies user entry against the environment/settings app passcode (Point 4)."""
    expected = os.environ.get("APP_ACCESS_PASSWORD", "").strip()
    if not expected:
        return True
    return secrets.compare_digest(passcode.strip(), expected)


def verify_admin_credentials(password: str, totp_code: Optional[str] = None) -> Tuple[bool, str]:
    """
    Verifies Administrator login with optional 2FA / TOTP (Points 4, 5, 6, 7).
    """
    expected_admin_pass = os.environ.get("APP_ADMIN_PASSWORD", "").strip()
    totp_secret = os.environ.get("APP_ADMIN_2FA_SECRET", "").strip()

    if not expected_admin_pass:
        # Default fallback for initial local setup if unset
        expected_admin_pass = "Admin@2026Secure!"

    if not secrets.compare_digest(password.strip(), expected_admin_pass):
        return False, "كلمة مرور المسؤول (Admin) غير صحيحة."

    # Check 2FA if configured
    if totp_secret:
        if not totp_code or not verify_totp(totp_secret, totp_code):
            return False, "رمز التحقق بخطوتين (2FA) غير صحيح أو منتهي الصلاحية."

    return True, "تم التحقق بنجاح بصلاحيات المسؤول."
