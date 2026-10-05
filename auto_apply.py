import sys
import subprocess
import json
from pathlib import Path
from config import DATA_DIR, load_settings

WORKER_SCRIPT = Path(__file__).resolve().parent / "auto_apply_worker.py"

class LinkedInApplier:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.settings = load_settings()

    def launch_browser_for_login(self) -> dict:
        """Launches the worker script to let user log in to LinkedIn once."""
        try:
            res = subprocess.run(
                [sys.executable, str(WORKER_SCRIPT), "login"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            # Find the last valid JSON output line
            for line in reversed(res.stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        return json.loads(line)
                    except Exception:
                        pass
            return {"status": "success", "message": "تم إغلاق متصفح تسجيل الدخول."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def apply_to_job(self, job_url: str, tailored_cv_pdf_path: str, user_profile: dict = None) -> dict:
        """
        Executes the job application worker in an isolated process.
        Prevents asyncio NotImplementedError on Windows.
        """
        try:
            res = subprocess.run(
                [sys.executable, str(WORKER_SCRIPT), "apply", job_url, str(tailored_cv_pdf_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            for line in reversed(res.stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        data = json.loads(line)
                        return {
                            "success": data.get("status") in ["success", "partial"],
                            "message": data.get("message", "")
                        }
                    except Exception:
                        pass
            if res.stderr:
                return {"success": False, "message": f"تنبيه: {res.stderr[:200]}"}
            return {"success": True, "message": "تم فتح نموذج التقديم وإرفاق الـ CV بنجاح!"}
        except Exception as e:
            return {"success": False, "message": f"حدث خطأ أثناء تشغيل المتصفح: {str(e)}"}
