import os
from pathlib import Path
import json
import re
from typing import Optional, Dict, Any

from security_crypto import encrypt_data, decrypt_data

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

CONFIG_FILE = DATA_DIR / "settings.json"
PROFILE_FILE = DATA_DIR / "master_profile.json"
SESSIONS_DATA_DIR = DATA_DIR / "sessions"
SESSIONS_DATA_DIR.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "gemini_api_key": "",
    "openai_api_key": "",
    "preferred_llm": "gemini",  # "gemini" or "openai"
    "gemini_model": "gemini-1.5-flash",
    "target_city": "الرياض",
    "target_country": "Saudi Arabia",
    "easy_apply_only": True,
    "max_jobs_to_search": 15,
    "auto_apply_delay_seconds": 3,
}

# Sensitive keys that must be encrypted at rest (Point 12)
SENSITIVE_KEYS = {"gemini_api_key", "openai_api_key"}


def load_settings() -> Dict[str, Any]:
    """
    Loads application settings with automatic decryption of sensitive fields (Point 12).
    Also merges environment variables and Streamlit Cloud secrets securely.
    """
    settings = DEFAULT_SETTINGS.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    # Decrypt sensitive fields if encrypted
                    if k in SENSITIVE_KEYS and isinstance(v, str) and v.startswith("enc:"):
                        settings[k] = decrypt_data(v)
                    else:
                        settings[k] = v
        except Exception:
            pass

    # Read from environment variables if not present in settings (Point 2)
    env_gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    env_openai = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_gemini and not settings.get("gemini_api_key"):
        settings["gemini_api_key"] = env_gemini
    if env_openai and not settings.get("openai_api_key"):
        settings["openai_api_key"] = env_openai

    return settings


def save_settings(settings: Dict[str, Any]):
    """
    Saves settings atomically with sensitive fields encrypted at rest (Points 9, 12).
    """
    clean_settings = settings.copy()
    for k in SENSITIVE_KEYS:
        val = clean_settings.get(k, "")
        if val and isinstance(val, str) and not val.startswith("enc:"):
            clean_settings[k] = encrypt_data(val)

    tmp_file = CONFIG_FILE.with_suffix(f".tmp_{os.getpid()}")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(clean_settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, CONFIG_FILE)
    except Exception as e:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)
        raise e


# ----------------- SESSION-LEVEL DATA ISOLATION (POINT 10) -----------------
def save_session_profile(session_id: str, profile_data: dict):
    """Saves candidate profile in session-scoped storage (Row-Level Data Isolation) (Point 10)."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)
    s_dir = SESSIONS_DATA_DIR / clean_id
    s_dir.mkdir(parents=True, exist_ok=True)
    p_file = s_dir / "profile.json"
    with open(p_file, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)


def load_session_profile(session_id: str) -> Optional[dict]:
    """Loads candidate profile strictly from the user's isolated session (Point 10)."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)
    p_file = SESSIONS_DATA_DIR / clean_id / "profile.json"
    if p_file.exists():
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_master_profile(profile_data):
    """Legacy helper writing to local storage."""
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)


def load_master_profile():
    """Legacy helper reading from local storage."""
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
