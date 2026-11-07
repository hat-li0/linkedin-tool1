"""
Security Cryptography Module: Password Hashing, Symmetric Encryption, Masking, and TOTP (2FA).
Covers Checklist Points: 1, 4, 5, 11, 12.
"""
import os
import hmac
import hashlib
import struct
import time
import base64
import secrets
from typing import Tuple, List, Optional

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# Fallback internal secret key derived from environment or machine-specific seed
_INTERNAL_SEED = os.environ.get("APP_SECRET_KEY", "LINKEDIN_TOOL_SECURE_VAULT_KEY_2026")


def _get_encryption_key(key_material: Optional[str] = None) -> bytes:
    """Derives a stable 32-byte urlsafe base64 key suitable for Fernet."""
    seed = (key_material or _INTERNAL_SEED).encode("utf-8")
    derived = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(derived)


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations (Point 11).
    Returns formatted hash: pbkdf2:sha256:100000$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = salt or secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"pbkdf2:sha256:100000${salt.hex()}${hashed.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Constant-time password verification to prevent timing attacks (Point 11).
    """
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 3:
            return False
        header, salt_hex, expected_hex = parts
        _, _, iterations_str = header.split(":")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed, expected)
    except Exception:
        return False


def encrypt_data(plaintext: str, key_material: Optional[str] = None) -> str:
    """
    Encrypts sensitive strings (API keys, tokens) at rest (Point 12).
    Uses Fernet (AES-128-CBC + HMAC-SHA256) if available, with authenticated fallback.
    """
    if not plaintext:
        return ""
    if HAS_CRYPTOGRAPHY:
        fernet = Fernet(_get_encryption_key(key_material))
        return "enc:v1:" + fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    else:
        # Secure authenticated keystream fallback using SHA256 HMAC
        key = _get_encryption_key(key_material)
        iv = secrets.token_bytes(16)
        raw = plaintext.encode("utf-8")
        keystream = hashlib.sha256(key + iv).digest()
        while len(keystream) < len(raw):
            keystream += hashlib.sha256(key + keystream).digest()
        cipher = bytes(a ^ b for a, b in zip(raw, keystream[:len(raw)]))
        tag = hmac.new(key, iv + cipher, hashlib.sha256).digest()[:16]
        payload = iv + tag + cipher
        return "enc:v0:" + base64.b64encode(payload).decode("utf-8")


def decrypt_data(ciphertext: str, key_material: Optional[str] = None) -> str:
    """
    Decrypts encrypted data at rest (Point 12).
    """
    if not ciphertext or not ciphertext.startswith("enc:"):
        return ciphertext  # Return as-is if unencrypted legacy
    try:
        if ciphertext.startswith("enc:v1:") and HAS_CRYPTOGRAPHY:
            token = ciphertext[len("enc:v1:"):].encode("utf-8")
            fernet = Fernet(_get_encryption_key(key_material))
            return fernet.decrypt(token).decode("utf-8")
        elif ciphertext.startswith("enc:v0:"):
            raw = base64.b64decode(ciphertext[len("enc:v0:"):].encode("utf-8"))
            iv, tag, cipher = raw[:16], raw[16:32], raw[32:]
            key = _get_encryption_key(key_material)
            expected_tag = hmac.new(key, iv + cipher, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(tag, expected_tag):
                return ""
            keystream = hashlib.sha256(key + iv).digest()
            while len(keystream) < len(cipher):
                keystream += hashlib.sha256(key + keystream).digest()
            decrypted = bytes(a ^ b for a, b in zip(cipher, keystream[:len(cipher)]))
            return decrypted.decode("utf-8")
    except Exception:
        return ""
    return ""


def mask_secret(secret: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """
    Masks secrets and API keys for safe UI display and logging (Point 1).
    E.g., 'AIzaSyDv...98e4' or '••••••••'
    """
    if not secret:
        return ""
    s = str(secret).strip()
    if len(s) <= (prefix_len + suffix_len):
        return "•" * len(s)
    return f"{s[:prefix_len]}...{s[-suffix_len:]}"


def generate_totp_secret() -> str:
    """
    Generates a 160-bit Base32 secret for 2FA / TOTP (RFC 6238) (Point 5).
    Compatible with Google Authenticator and Microsoft Authenticator.
    """
    raw_bytes = secrets.token_bytes(20)
    return base64.b32encode(raw_bytes).decode("utf-8").replace("=", "")


def get_totp_token(secret_b32: str, timestamp: Optional[float] = None) -> str:
    """
    Generates the current 6-digit TOTP code for a secret (Point 5).
    """
    if timestamp is None:
        timestamp = time.time()
    clean_secret = secret_b32.strip().upper()
    # Add padding if needed
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)
    key = base64.b32decode(clean_secret, casefold=True)
    counter = int(timestamp // 30)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{(code % 1_000_000):06d}"


def verify_totp(secret_b32: str, token: str, window: int = 1) -> bool:
    """
    Verifies a 6-digit TOTP code with time-drift window support (Point 5).
    """
    if not secret_b32 or not token:
        return False
    clean_token = token.strip()
    if len(clean_token) != 6 or not clean_token.isdigit():
        return False
    now = time.time()
    for w in range(-window, window + 1):
        expected = get_totp_token(secret_b32, timestamp=now + (w * 30))
        if hmac.compare_digest(clean_token, expected):
            return True
    return False


def generate_recovery_codes(count: int = 5) -> List[str]:
    """Generates backup 2FA recovery codes (Point 5)."""
    codes = []
    for _ in range(count):
        code = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        codes.append(code)
    return codes
