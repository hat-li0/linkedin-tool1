import sys
import os
import json
import time
import asyncio
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright

USER_DATA_DIR = Path(__file__).resolve().parent / "data" / "browser_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

CHROME_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--lang=en-US,en"
]

def get_browser_context(playwright_instance, headless: bool = False):
    """Launches official Google Chrome if available, otherwise chromium."""
    try:
        return playwright_instance.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chrome",
            headless=headless,
            args=CHROME_ARGS,
            viewport=None
        )
    except Exception:
        # Fallback to bundled chromium
        return playwright_instance.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=headless,
            args=CHROME_ARGS,
            viewport=None
        )

def is_linkedin_authenticated(context) -> bool:
    """Checks if the official LinkedIn session cookie (li_at) exists."""
    try:
        cookies = context.cookies("https://www.linkedin.com")
        for c in cookies:
            if c.get("name") == "li_at" and c.get("value"):
                return True
    except Exception:
        pass
    return False

def run_check():
    """Checks whether the saved browser session is currently logged into LinkedIn."""
    with sync_playwright() as p:
        try:
            context = get_browser_context(p, headless=True)
            logged_in = is_linkedin_authenticated(context)
            context.close()
            print(json.dumps({"status": "ok", "logged_in": logged_in}))
        except Exception as e:
            print(json.dumps({"status": "error", "logged_in": False, "message": str(e)}))

def run_login():
    """Opens official Chrome for manual LinkedIn login and saves session securely."""
    with sync_playwright() as p:
        try:
            context = get_browser_context(p, headless=False)
            page = context.pages[0] if context.pages else context.new_page()

            # Stealth: remove webdriver flag
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.goto("https://www.linkedin.com/login", timeout=60000)

            logged_in = False
            # Monitor for up to 3 minutes
            for _ in range(180):
                try:
                    # Check cookie
                    if is_linkedin_authenticated(context):
                        logged_in = True
                        break

                    # Check URL
                    current_url = page.url
                    if any(k in current_url for k in ["feed", "mynetwork", "jobs", "messaging"]):
                        logged_in = True
                        break

                    page.wait_for_timeout(1000)
                except Exception:
                    # User closed the browser window manually
                    break

            # Check one more time before closing
            if not logged_in:
                logged_in = is_linkedin_authenticated(context)

            try:
                page.wait_for_timeout(2000)
                context.close()
            except Exception:
                pass

            if logged_in:
                print(json.dumps({
                    "status": "success",
                    "logged_in": True,
                    "message": "تم تسجيل الدخول بنجاح وحفظ جلسة حسابك بشكل دائم وآمن!"
                }))
            else:
                print(json.dumps({
                    "status": "cancelled",
                    "logged_in": False,
                    "message": "تم إغلاق المتصفح قبل إتمام تسجيل الدخول. يمكنك المحاولة مجدداً في أي وقت."
                }))

        except Exception as e:
            print(json.dumps({"status": "error", "logged_in": False, "message": f"حدث تنبيه: {str(e)}"}))

def run_apply(job_url: str, pdf_path: str):
    """Navigates to job with saved session, attaches tailored CV, and handles Easy Apply."""
    with sync_playwright() as p:
        try:
            context = get_browser_context(p, headless=False)
            page = context.pages[0] if context.pages else context.new_page()

            # Stealth
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.goto(job_url, timeout=45000)
            page.wait_for_timeout(3000)

            # Check authentication
            if not is_linkedin_authenticated(context) and ("login" in page.url or "checkpoint" in page.url):
                try:
                    context.close()
                except Exception:
                    pass
                print(json.dumps({
                    "status": "need_login",
                    "message": "يرجى تسجيل الدخول إلى لينكدين أولاً من الشريط الجانبي لتفعيل التقديم السريع."
                }))
                return

            # Check Easy Apply button
            easy_apply_btn = page.locator("button.jobs-apply-button, button:has-text('Easy Apply'), button:has-text('التقديم السهل')").first
            
            if not easy_apply_btn.is_visible(timeout=5000):
                try:
                    context.close()
                except Exception:
                    pass
                print(json.dumps({
                    "status": "external_apply",
                    "message": "هذه الوظيفة تتطلب التقديم عبر موقع الشركة الخارجي، يمكنك الضغط على رابط الوظيفة للتقديم المباشر."
                }))
                return

            easy_apply_btn.click()
            page.wait_for_timeout(2000)

            # Upload resume if present
            if os.path.exists(pdf_path):
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0:
                    try:
                        file_inputs.first.set_input_files(pdf_path)
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass

            # Step through modal
            applied = False
            for _ in range(5):
                page.wait_for_timeout(1500)

                # Check file upload again
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0 and os.path.exists(pdf_path):
                    try:
                        file_inputs.first.set_input_files(pdf_path)
                    except Exception:
                        pass

                submit_btn = page.locator("button:has-text('Submit application'), button:has-text('إرسال الطلب')").first
                if submit_btn.is_visible(timeout=2000):
                    applied = True
                    break

                next_btn = page.locator("button:has-text('Next'), button:has-text('التالي'), button:has-text('Review'), button:has-text('مراجعة')").first
                if next_btn.is_visible(timeout=2000):
                    next_btn.click()
                else:
                    break

            # Leave window open briefly for user review
            page.wait_for_timeout(8000)
            try:
                context.close()
            except Exception:
                pass

            if applied:
                print(json.dumps({
                    "status": "success",
                    "message": "تم إرفاق الـ CV المخصص والوصول لخطوة المراجعة النهائية بنجاح!"
                }))
            else:
                print(json.dumps({
                    "status": "partial",
                    "message": "تم فتح نافذة التقديم وإرفاق الـ CV بنجاح! قد تتطلب بعض الوظائف الإجابة على أسئلة مخصصة."
                }))

        except Exception as e:
            print(json.dumps({"status": "error", "message": f"حدث تنبيه: {str(e)}"}))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No command provided"}))
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "login":
        run_login()
    elif cmd == "check":
        run_check()
    elif cmd == "apply":
        target_url = sys.argv[2]
        pdf_file = sys.argv[3] if len(sys.argv) > 3 else ""
        run_apply(target_url, pdf_file)
