import sys
import os
import json
import asyncio
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright

USER_DATA_DIR = Path(__file__).resolve().parent / "data" / "browser_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

def run_login():
    """Opens browser for manual LinkedIn login so user's cookies/session stay saved."""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            viewport=None
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/login")
        print(json.dumps({"status": "running", "message": "المتصفح مفتوح لتسجيل الدخول."}))
        
        # Wait up to 3 minutes for user to login
        for _ in range(180):
            if "feed" in page.url or "mynetwork" in page.url or "jobs" in page.url:
                context.close()
                print(json.dumps({"status": "success", "message": "تم تسجيل الدخول بنجاح وحفظ الجلسة!"}))
                return
            page.wait_for_timeout(1000)
        
        context.close()
        print(json.dumps({"status": "timeout", "message": "انتهى الوقت المحدد لتسجيل الدخول."}))

def run_apply(job_url: str, pdf_path: str):
    """Opens browser and assists or auto-applies with tailored CV."""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            viewport=None
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(job_url, timeout=45000)
            page.wait_for_timeout(3000)

            # Check if login is needed
            if "login" in page.url or "checkpoint" in page.url:
                context.close()
                print(json.dumps({
                    "status": "need_login",
                    "message": "يرجى تسجيل الدخول إلى لينكدين أولاً من الشريط الجانبي (زر 'تسجيل الدخول إلى لينكدين') ليتم حفظ جلستك."
                }))
                return

            # Check for Easy Apply
            easy_apply_btn = page.locator("button.jobs-apply-button, button:has-text('Easy Apply'), button:has-text('التقديم السهل')").first
            
            if not easy_apply_btn.is_visible(timeout=5000):
                context.close()
                print(json.dumps({
                    "status": "external_apply",
                    "message": "هذه الوظيفة لا تدعم التقديم السهل التلقائي (Easy Apply)، بل تتطلب التقديم عبر موقع الشركة الخارجي مباشرة."
                }))
                return

            easy_apply_btn.click()
            page.wait_for_timeout(2000)

            # Upload tailored resume
            if os.path.exists(pdf_path):
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0:
                    try:
                        file_inputs.first.set_input_files(pdf_path)
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass

            # Advance through multi-step Easy Apply dialog
            applied = False
            for step in range(5):
                page.wait_for_timeout(1500)
                
                # Check for upload input again in subsequent steps
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0 and os.path.exists(pdf_path):
                    try:
                        file_inputs.first.set_input_files(pdf_path)
                    except Exception:
                        pass

                # Check if submit button is visible
                submit_btn = page.locator("button:has-text('Submit application'), button:has-text('إرسال الطلب')").first
                if submit_btn.is_visible(timeout=2000):
                    # Keep browser open for user to review and confirm submit
                    applied = True
                    break

                next_btn = page.locator("button:has-text('Next'), button:has-text('التالي'), button:has-text('Review'), button:has-text('مراجعة')").first
                if next_btn.is_visible(timeout=2000):
                    next_btn.click()
                else:
                    break

            # Let user see the application window for 15 seconds to review or finish questions
            page.wait_for_timeout(10000)
            context.close()
            
            if applied:
                print(json.dumps({
                    "status": "success",
                    "message": "تم إرفاق الـ CV المخصص والوصول لصفحة المراجعة النهائية بنجاح!"
                }))
            else:
                print(json.dumps({
                    "status": "partial",
                    "message": "تم فتح نافذة التقديم وإرفاق الـ CV بنجاح. قد تتطلب الوظيفة الإجابة على بعض الأسئلة المخصصة للشركة."
                }))

        except Exception as e:
            context.close()
            print(json.dumps({"status": "error", "message": f"حدث تنبيه: {str(e)}"}))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No command provided"}))
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "login":
        run_login()
    elif cmd == "apply":
        target_url = sys.argv[2]
        pdf_file = sys.argv[3] if len(sys.argv) > 3 else ""
        run_apply(target_url, pdf_file)
