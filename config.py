import os
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

CONFIG_FILE = DATA_DIR / "settings.json"
PROFILE_FILE = DATA_DIR / "master_profile.json"

DEFAULT_SETTINGS = {
    "gemini_api_key": "",
    "openai_api_key": "",
    "preferred_llm": "gemini",  # "gemini" or "openai" or "local"
    "target_city": "الرياض",
    "target_country": "Saudi Arabia",
    "easy_apply_only": True,
    "max_jobs_to_search": 15,
    "auto_apply_delay_seconds": 3,
}

def load_settings():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                # merge with defaults in case new keys were added
                for k, v in DEFAULT_SETTINGS.items():
                    if k not in settings:
                        settings[k] = v
                return settings
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def save_master_profile(profile_data):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)

def load_master_profile():
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
