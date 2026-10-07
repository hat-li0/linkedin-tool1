import streamlit as st
import os
import json
import base64
from pathlib import Path
from config import OUTPUTS_DIR
import sys
import importlib

try:
    import job_searcher
    if not hasattr(job_searcher, 'search_multi_source_jobs'):
        importlib.reload(job_searcher)
except Exception:
    if 'job_searcher' in sys.modules:
        del sys.modules['job_searcher']

from job_searcher import (
    search_multi_source_jobs,
    search_linkedin_jobs,
    fetch_job_description,
    analyze_job_qualification,
    CITY_MAP
)
from cv_tailor import evaluate_and_tailor_cv, generate_pdf_resume
from auto_apply import LinkedInApplier

st.set_page_config(
    page_title="مساعد التوظيف الذكي و مخصص الـ CV",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize Session-Isolated State
if "master_profile" not in st.session_state:
    st.session_state["master_profile"] = None
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""
if "openai_api_key" not in st.session_state:
    st.session_state["openai_api_key"] = ""
if "preferred_llm" not in st.session_state:
    st.session_state["preferred_llm"] = "gemini"
if "search_results" not in st.session_state:
    st.session_state["search_results"] = []
if "session_generated_pdfs" not in st.session_state:
    st.session_state["session_generated_pdfs"] = []

# ==================== MULTI-DEVICE RESPONSIVE DARK THEME ====================
if "selected_device_mode" not in st.session_state:
    st.session_state["selected_device_mode"] = "auto"

# ----------------- SIDEBAR SETTINGS & DEVICE SELECTOR -----------------
with st.sidebar:
    st.header("⚙️ إعدادات الذكاء الاصطناعي")
    
    llm_choice = st.selectbox(
        "مزود الذكاء الاصطناعي:",
        options=["gemini", "openai"],
        format_func=lambda x: "Google Gemini (موصى به - مجاني)" if x == "gemini" else "OpenAI GPT-4o-mini",
        index=0 if st.session_state.get("preferred_llm") == "gemini" else 1
    )
    st.session_state["preferred_llm"] = llm_choice

    gemini_key = st.text_input(
        "Google Gemini API Key:",
        value=st.session_state.get("gemini_api_key", ""),
        type="password",
        help="احصل على مفتاح مجاني فوري من: https://aistudio.google.com/app/apikey"
    )
    if gemini_key != st.session_state.get("gemini_api_key"):
        st.session_state["gemini_api_key"] = gemini_key.strip()
        
    openai_key = st.text_input(
        "OpenAI API Key (اختياري):",
        value=st.session_state.get("openai_api_key", ""),
        type="password"
    )
    if openai_key != st.session_state.get("openai_api_key"):
        st.session_state["openai_api_key"] = openai_key.strip()

    if st.button("💾 حفظ الإعدادات"):
        st.session_state["gemini_api_key"] = gemini_key.strip()
        st.session_state["openai_api_key"] = openai_key.strip()
        st.success("تم حفظ الإعدادات بنجاح!")

    st.markdown("---")
    st.header("🖥️ نمط العرض ونوع الجهاز")
    st.caption("يتكيف الموقع تلقائياً مع حجم شاشة جهازك، أو يمكنك التبديل بين الواجهات يدوياً:")
    current_device = st.selectbox(
        "واجهة العرض:",
        options=["auto", "desktop", "tablet", "mobile"],
        format_func=lambda x: {
            "auto": "🌐 تلقائي (حسب شاشة جهازك الذكي)",
            "desktop": "💻 كمبيوتر مكتبي (Desktop Layout)",
            "tablet": "📟 تابلت / آيباد (iPad / Tablet)",
            "mobile": "📱 هاتف جوال (Mobile Layout)"
        }[x],
        index=["auto", "desktop", "tablet", "mobile"].index(st.session_state.get("selected_device_mode", "auto")),
        key="selected_device_mode"
    )

    st.markdown("---")
    st.subheader("🌐 جلسة لينكدين للتقديم")
    st.caption("ميزة اختيارية لتشغيل التقديم التلقائي على جهاز الكمبيوتر:")
    
    applier = LinkedInApplier()
    is_logged = st.session_state.get("linkedin_logged_in", None)
    if is_logged is None:
        is_logged = applier.check_session()
        st.session_state["linkedin_logged_in"] = is_logged

    if is_logged:
        st.success("🟢 حساب لينكدين متصل ونشط!")
    else:
        st.info("⚪ لم يتم حفظ جلسة لينكدين بعد.")

    if st.button("🔑 تسجيل الدخول إلى لينكدين"):
        st.info("💡 سيفتح متصفح Chrome الآن. يرجى إدخال بريدك وكلمة المرور في المتصفح. بمجرد تسجيل الدخول سيتم حفظ جلستك تلقائياً.")
        with st.spinner("المتصفح مفتوح بانتظار تسجيل دخولك..."):
            res = applier.launch_browser_for_login()
            if res.get("logged_in") or res.get("status") == "success":
                st.session_state["linkedin_logged_in"] = True
                st.success(res.get("message", "تم تسجيل الدخول بنجاح!"))
            else:
                st.warning(res.get("message", "تم إغلاق المتصفح."))

# ----------------- DYNAMIC CSS GENERATION -----------------
desktop_css_rules = """
    .block-container {
        max-width: 1160px !important;
        padding-top: 1.5rem !important;
        padding-bottom: 4rem !important;
    }
    .dark-hero {
        border-radius: 20px !important;
        padding: 26px 32px !important;
        margin-bottom: 20px !important;
    }
    .dark-hero-title {
        font-size: 1.95rem !important;
    }
    .dark-hero-desc {
        font-size: 1.05rem !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        justify-content: flex-start !important;
        direction: rtl !important;
        gap: 10px !important;
        padding-bottom: 10px !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px !important;
        padding: 10px 22px !important;
        font-size: 15px !important;
    }
    [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 16px !important;
    }
    .dark-card, .job-card-dark {
        padding: 22px 26px !important;
        border-radius: 18px !important;
        margin-bottom: 16px !important;
    }
    [data-testid="stMetric"] {
        border-radius: 14px !important;
        padding: 16px 18px !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 14px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 24px !important;
    }
    .stButton > button, .stDownloadButton > button {
        padding: 0.65rem 1.6rem !important;
        font-size: 15px !important;
        min-height: 44px !important;
    }
    .chip {
        padding: 5px 14px !important;
        font-size: 13.5px !important;
        margin: 4px 6px 4px 0 !important;
    }
    .pdf-iframe {
        height: 640px !important;
    }
"""

tablet_css_rules = """
    .block-container {
        max-width: 860px !important;
        padding: 1.2rem 1.4rem 3.5rem 1.4rem !important;
    }
    .dark-hero {
        border-radius: 16px !important;
        padding: 20px 24px !important;
        margin-bottom: 16px !important;
    }
    .dark-hero-title {
        font-size: 1.6rem !important;
    }
    .dark-hero-desc {
        font-size: 0.95rem !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        justify-content: flex-start !important;
        direction: rtl !important;
        gap: 8px !important;
        padding-bottom: 8px !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        padding: 9px 18px !important;
        font-size: 14px !important;
    }
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 12px !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        flex: 1 1 calc(50% - 12px) !important;
        min-width: 45% !important;
    }
    .dark-card, .job-card-dark {
        padding: 18px 20px !important;
        border-radius: 16px !important;
        margin-bottom: 14px !important;
    }
    [data-testid="stMetric"] {
        border-radius: 12px !important;
        padding: 14px 16px !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 13px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 21px !important;
    }
    .stButton > button, .stDownloadButton > button {
        min-height: 48px !important;
        font-size: 15px !important;
        padding: 0.6rem 1.4rem !important;
    }
    .chip {
        padding: 4px 12px !important;
        font-size: 13px !important;
        margin: 3px 4px 3px 0 !important;
    }
    .pdf-iframe {
        height: 520px !important;
    }
"""

mobile_css_rules = """
    .block-container {
        max-width: 100% !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        padding-top: 0.6rem !important;
        padding-bottom: 3.5rem !important;
    }
    .dark-hero {
        border-radius: 14px !important;
        padding: 15px 14px !important;
        margin-bottom: 12px !important;
    }
    .dark-hero-title {
        font-size: 1.25rem !important;
        line-height: 1.35 !important;
    }
    .dark-hero-desc {
        font-size: 0.85rem !important;
        line-height: 1.5 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        justify-content: flex-start !important;
        direction: rtl !important;
        gap: 5px !important;
        padding-bottom: 6px !important;
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px !important;
        padding: 7px 11px !important;
        font-size: 12px !important;
        white-space: nowrap !important;
    }
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 8px !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
        margin-bottom: 6px !important;
    }
    .dark-card, .job-card-dark {
        padding: 14px 12px !important;
        border-radius: 13px !important;
        margin-bottom: 12px !important;
    }
    [data-testid="stMetric"] {
        border-radius: 11px !important;
        padding: 10px 12px !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 18px !important;
    }
    .stButton > button, .stDownloadButton > button {
        width: 100% !important;
        min-height: 50px !important;
        font-size: 15px !important;
        margin-top: 4px !important;
        margin-bottom: 4px !important;
    }
    .chip {
        padding: 3px 9px !important;
        font-size: 12px !important;
        margin: 2px 2px !important;
    }
    .pdf-iframe {
        height: 420px !important;
    }
"""

if current_device == "desktop":
    device_specific_css = f"/* FORCED DESKTOP LAYOUT */\n{desktop_css_rules}"
elif current_device == "tablet":
    device_specific_css = f"/* FORCED TABLET / iPAD LAYOUT */\n{tablet_css_rules}"
elif current_device == "mobile":
    device_specific_css = f"/* FORCED MOBILE LAYOUT */\n{mobile_css_rules}"
else:
    # Auto Responsive Media Queries (Adapts automatically to user screen)
    device_specific_css = f"""
    @media (min-width: 1024px) {{
        {desktop_css_rules}
    }}
    @media (min-width: 768px) and (max-width: 1023px) {{
        {tablet_css_rules}
    }}
    @media (max-width: 767px) {{
        {mobile_css_rules}
    }}
    """

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap');
    
    /* Scoped Typography - Protect Material Symbols icons */
    html, body, p, h1, h2, h3, h4, h5, h6, label, input, textarea, select, button, .stMarkdown, [data-testid="stMarkdownContainer"] {{
        font-family: 'Cairo', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}

    [data-testid="stIcon"],
    [data-testid="stSidebarCollapseButton"] *,
    [data-testid="stToolbar"] *,
    [data-testid="stStatusWidget"] *,
    [data-testid="stDecoration"] *,
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons,
    [class*="material-symbols"],
    [class*="material-icons"] {{
        font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
        font-feature-settings: 'liga' 1;
        text-rendering: optimizeLegibility;
    }}

    /* Dark App Container & RTL Direction */
    .stApp {{
        background-color: #0B0F19 !important;
        color: #F8FAFC !important;
    }}

    [data-testid="stMainBlockContainer"],
    .dark-card,
    .job-card-dark,
    .stMarkdown,
    [data-testid="stExpander"],
    .stAlert {{
        direction: rtl;
        text-align: right;
    }}

    [data-testid="stHeader"] {{
        background: rgba(11, 15, 25, 0.85) !important;
        backdrop-filter: blur(8px);
    }}

    /* Device Mode Pill Badge */
    .device-badge-tag {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 5px 12px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 700;
        background: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.35);
        white-space: nowrap;
    }}

    /* Base Hero Header */
    .dark-hero {{
        background: linear-gradient(135deg, #111827 0%, #1E293B 50%, #0F172A 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.08);
        direction: rtl;
        text-align: right;
    }}
    .dark-hero-title {{
        font-weight: 800;
        margin: 0 0 6px 0;
        background: linear-gradient(135deg, #FFFFFF 30%, #38BDF8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .dark-hero-desc {{
        color: #94A3B8;
        margin: 0;
        line-height: 1.6;
    }}

    /* Dark Cards & Surfaces */
    .dark-card {{
        background: #161F30;
        border: 1px solid #283548;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }}

    .job-card-dark {{
        background: #161F30;
        border: 1px solid #283548;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
        transition: all 0.2s ease;
    }}
    .job-card-dark:hover {{
        border-color: #38BDF8;
        box-shadow: 0 8px 24px rgba(56, 189, 248, 0.15);
    }}

    /* Glowing Dark Chips */
    .chip {{
        display: inline-flex;
        align-items: center;
        border-radius: 9999px;
        font-weight: 700;
    }}
    .chip-cyan {{
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .chip-emerald {{
        background: rgba(52, 211, 153, 0.12);
        color: #34D399;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }}
    .chip-amber {{
        background: rgba(251, 191, 36, 0.12);
        color: #FBBF24;
        border: 1px solid rgba(251, 191, 36, 0.3);
    }}
    .chip-purple {{
        background: rgba(192, 132, 252, 0.12);
        color: #C084FC;
        border: 1px solid rgba(192, 132, 252, 0.3);
    }}

    /* Buttons */
    .stButton > button {{
        border-radius: 12px !important;
        font-weight: 800 !important;
        transition: all 0.2s ease !important;
        border: 1px solid #334155 !important;
        background-color: #1E293B !important;
        color: #F8FAFC !important;
    }}
    .stButton > button:hover {{
        border-color: #38BDF8 !important;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.25) !important;
    }}
    .stButton > button[kind="primary"], .stDownloadButton > button {{
        background: linear-gradient(135deg, #0284C7 0%, #38BDF8 100%) !important;
        color: #0F172A !important;
        border: none !important;
        box-shadow: 0 4px 18px rgba(56, 189, 248, 0.35) !important;
    }}
    .stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{
        box-shadow: 0 6px 24px rgba(56, 189, 248, 0.5) !important;
    }}

    /* Tabs Base Styling: Hide native underline and highlight bar */
    .stTabs [data-baseweb="tab-border"],
    .stTabs [data-baseweb="tab-highlight"],
    [data-testid="stTabs"] [data-baseweb="tab-border"],
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
        display: none !important;
        background: transparent !important;
        height: 0 !important;
    }}

    .stTabs [data-baseweb="tab-list"],
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        justify-content: flex-start !important;
        direction: rtl !important;
        gap: 8px !important;
        border: none !important;
        scrollbar-width: none;
    }}
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar,
    [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar {{
        display: none;
    }}

    /* All Tabs: Rounded luxury dark pill buttons with high specificity */
    .stTabs [data-baseweb="tab"],
    [data-testid="stTabs"] [data-baseweb="tab"],
    button[data-baseweb="tab"],
    div[data-baseweb="tab-list"] button {{
        background-color: #161F30 !important;
        border: 1px solid #283548 !important;
        border-radius: 12px !important;
        color: #94A3B8 !important;
        font-weight: 700 !important;
        font-size: 14px !important;
        padding: 9px 18px !important;
        white-space: nowrap !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
        transition: all 0.2s ease !important;
        outline: none !important;
    }}

    .stTabs [data-baseweb="tab"]:hover,
    [data-testid="stTabs"] [data-baseweb="tab"]:hover,
    div[data-baseweb="tab-list"] button:hover {{
        border-color: #38BDF8 !important;
        color: #F8FAFC !important;
        background-color: #1E293B !important;
    }}

    /* Selected Active Tab: Glowing Cyan Pill Button */
    .stTabs [aria-selected="true"],
    [data-testid="stTabs"] [aria-selected="true"],
    button[data-baseweb="tab"][aria-selected="true"],
    div[data-baseweb="tab-list"] button[aria-selected="true"] {{
        background: linear-gradient(135deg, #0284C7 0%, #38BDF8 100%) !important;
        color: #0F172A !important;
        font-weight: 900 !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 14px rgba(56, 189, 248, 0.4) !important;
    }}

    /* Ensure text inside active tab is dark obsidian for high contrast */
    .stTabs [aria-selected="true"] p,
    [data-testid="stTabs"] [aria-selected="true"] p,
    button[data-baseweb="tab"][aria-selected="true"] p {{
        color: #0F172A !important;
        font-weight: 900 !important;
    }}

    /* Inactive tab text */
    .stTabs [aria-selected="false"] p,
    [data-testid="stTabs"] [aria-selected="false"] p,
    button[data-baseweb="tab"][aria-selected="false"] p {{
        color: #94A3B8 !important;
    }}

    /* File Uploader Fix: Keep internal dropzone in LTR so Browse button & text never collide */
    [data-testid="stFileUploader"] {{
        direction: ltr !important;
    }}
    [data-testid="stFileUploader"] section {{
        direction: ltr !important;
        text-align: left !important;
    }}
    [data-testid="stFileUploaderDropzone"] {{
        direction: ltr !important;
        text-align: left !important;
        padding: 1rem 1.5rem !important;
    }}

    /* Metrics & Expanders */
    [data-testid="stMetric"] {{
        background: #161F30 !important;
        border: 1px solid #283548 !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
    }}
    [data-testid="stMetricLabel"] {{
        font-weight: 700 !important;
        color: #94A3B8 !important;
    }}
    [data-testid="stMetricValue"] {{
        font-weight: 900 !important;
        color: #38BDF8 !important;
    }}
    .streamlit-expanderHeader {{
        background-color: #161F30 !important;
        border-radius: 12px !important;
        border: 1px solid #283548 !important;
        color: #F8FAFC !important;
        font-weight: 700 !important;
    }}
    [data-testid="stExpander"] {{
        background-color: #161F30 !important;
        border: 1px solid #283548 !important;
        border-radius: 14px !important;
    }}
    .stTextInput > div > div > input, .stTextArea > div > div > textarea {{
        background-color: #161F30 !important;
        border: 1px solid #334155 !important;
        color: #F8FAFC !important;
        border-radius: 10px !important;
    }}
    .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {{
        border-color: #38BDF8 !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.2) !important;
    }}

    /* Injected Device-Specific Rules */
    {device_specific_css}
</style>
""", unsafe_allow_html=True)

def render_pdf_preview(pdf_bytes: bytes, height: int = 540):
    """Renders a responsive PDF preview with fallback for mobile devices."""
    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_html = f'''
    <div style="margin: 12px 0; border: 1px solid #334155; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.3); background: #1E293B;">
        <iframe class="pdf-iframe" src="data:application/pdf;base64,{b64_pdf}" width="100%" height="{height}px" type="application/pdf" style="border: none;">
            <p style="padding: 20px; text-align: center; color: #94A3B8;">
                📱 جهازك لا يدعم المعاينة المباشرة داخل المتصفح. اضغط على زر التحميل أدناه لحفظ الملف فوراً.
            </p>
        </iframe>
    </div>
    '''
    st.markdown(pdf_html, unsafe_allow_html=True)

@st.dialog("🔑 مطلوب إدخال مفتاح Google Gemini للبدء")
def prompt_api_key_dialog():
    st.markdown("""
    **مرحباً بك!** 👋  
    لقراءة سيرتك الذاتية وتحديد تخصصك ومؤهلاتك بدقة وفحص الـ ATS وتخصيص الـ CV، يلزم إدخال مفتاح **Google Gemini**.
    
    ✨ **المفتاح مجاني 100% وفوري وبدون أي اشتراك أو بطاقة بنكية!**  
    احصل على مفتاحك المجاني خلال ثوانٍ من الرابط التالي:  
    👉 [**اضغط هنا لفتح Google AI Studio ونسخ المفتاح مجاناً**](https://aistudio.google.com/app/apikey)
    """)
    
    new_key = st.text_input("ألصق مفتاح Google Gemini API هنا:", type="password")
    
    if st.button("💾 حفظ المفتاح ومتابعة التحليل", type="primary"):
        clean_key = new_key.strip()
        if clean_key:
            st.session_state["gemini_api_key"] = clean_key
            st.session_state["preferred_llm"] = "gemini"
            st.session_state["auto_trigger_analysis"] = True
            st.success("تم حفظ المفتاح بنجاح! جاري المتابعة...")
            st.rerun()
        else:
            st.error("يرجى إدخال المفتاح أولاً للمتابعة.")

# ----------------- MAIN HERO BANNER -----------------
st.markdown("""
<div class="dark-hero">
    <h1 class="dark-hero-title">💼 مساعد التوظيف الذكي و مخصص الـ CV</h1>
    <p class="dark-hero-desc">ارفع سيرتك الذاتية، افحص جاهزية الـ ATS الصارم، واستكشف وظائف LinkedIn المتاحة مع تخصيص الـ CV بنقرة زر واحدة!</p>
</div>
""", unsafe_allow_html=True)

# Quick Key Check for Mobile Users
has_key = bool(st.session_state.get("gemini_api_key", "").strip() or st.session_state.get("openai_api_key", "").strip())
if not has_key:
    c_banner1, c_banner2 = st.columns([2.7, 1.3])
    with c_banner1:
        st.info("💡 للبدء بتحليل السيرة وفحص الـ ATS وتخصيص الـ CV، يلزم إدخال مفتاح Google Gemini (مجاني وفوري 100%).")
    with c_banner2:
        if st.button("🔑 إدخال المفتاح مجاناً", type="primary"):
            prompt_api_key_dialog()

master_profile = st.session_state.get("master_profile", None)

tabs = st.tabs([
    "📄 السيرة و ATS",
    "🔍 البحث عن وظائف",
    "🎯 تخصيص الـ CV",
    "📁 ملفاتي"
])

# ----------------- TAB 1: MASTER CV & ATS AUDIT -----------------
with tabs[0]:
    st.subheader("📄 رفع السيرة الذاتية وفحص الـ ATS (Master CV)")
    st.caption("ارفع سيرتك الذاتية ليقوم الذكاء الاصطناعي باستخراج تخصصك بدقة وفحص جاهزيتها لأنظمة الـ ATS العالمية:")
    
    uploaded_file = st.file_uploader(
        "اختر ملف السيرة الذاتية (PDF أو Word أو TXT):",
        type=["pdf", "docx", "txt"],
        key="master_cv_uploader"
    )
    
    if uploaded_file is not None:
        analyze_clicked = st.button("🚀 تحليل السيرة الذاتية وفحص الـ ATS", type="primary")
        should_analyze = analyze_clicked or st.session_state.pop("auto_trigger_analysis", False)

        if should_analyze:
            active_key = st.session_state.get("gemini_api_key", "").strip()
            active_openai = st.session_state.get("openai_api_key", "").strip()

            if not active_key and not active_openai:
                prompt_api_key_dialog()
            else:
                with st.spinner(f"جاري قراءة الملف ({uploaded_file.name}) وتحليله بالذكاء الاصطناعي..."):
                    try:
                        raw_text = extract_text_from_file(uploaded_file, uploaded_file.name)
                        parsed_profile = parse_cv_with_ai(
                            raw_text,
                            custom_key=active_key or active_openai,
                            llm_type=st.session_state.get("preferred_llm", "gemini")
                        )
                        st.session_state["master_profile"] = parsed_profile
                        st.session_state["search_results"] = []
                        st.session_state["session_generated_pdfs"] = []
                        master_profile = parsed_profile
                        st.success(f"تم تحليل السيرة الذاتية ({uploaded_file.name}) بنجاح!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ حدث خطأ أثناء التحليل: {e}")

    if master_profile:
        st.markdown("---")
        st.subheader("📋 البيانات المستخرجة من سيرتك الذاتية:")
        
        # Responsive 2-column layout
        col1, col2 = st.columns([1, 1])
        with col1:
            st.metric("👤 الاسم", master_profile.get("name", "غير محدد"))
            st.metric("🎓 التخصص المكتشف", master_profile.get("target_major", "عام"))
            st.write(f"📧 **البريد:** {master_profile.get('email', 'غير محدد')}")
            st.write(f"📞 **الهاتف:** {master_profile.get('phone', 'غير محدد')}")
        with col2:
            st.metric("📊 المستوى التقريبي", master_profile.get("experience_level", "متوسط"))
            st.write("🎯 **المسميات المقترحة تلقائياً للبحث:**")
            suggested = master_profile.get("suggested_job_titles", [])
            for title in suggested:
                st.markdown(f"- **{title}**")
        
        st.write("🛠️ **أبرز المهارات المستخرجة:**")
        skills_str = " • ".join(master_profile.get("skills", []))
        st.info(skills_str if skills_str else "لم يتم العثور على مهارات محددة.")
        
        with st.expander("📝 عرض النبذة المهنية المستخرجة (Summary)"):
            st.write(master_profile.get("summary", "لا يوجد"))

        # ----------------- STRICT ATS AUDIT SECTION -----------------
        ats_audit = master_profile.get("ats_audit")
        if ats_audit:
            st.markdown("---")
            st.subheader("🛡️ تقرير فحص وتوافق الـ ATS الصارم (Strict ATS Audit)")
            
            score = ats_audit.get("overall_score", 70)
            badge = ats_audit.get("verdict_badge", "🟡 تقييم جيد")
            summary_txt = ats_audit.get("summary_verdict", "")
            
            c_score1, c_score2 = st.columns([1, 2])
            with c_score1:
                st.metric("🎯 درجة الـ ATS الإجمالية", f"{score} / 100")
                st.markdown(f"**الحالة:** {badge}")
                st.progress(min(1.0, score / 100.0))
            with c_score2:
                st.markdown("**التقييم العام وخوارزميات الفرز:**")
                st.info(summary_txt if summary_txt else "تم فحص السيرة طبقاً لأحدث معايير أنظمة الـ ATS العالمية.")
            
            # Responsive 2-column sub-scores
            sub_scores = ats_audit.get("sub_scores", {})
            if sub_scores:
                st.markdown("##### 📊 معايير الفحص والتقييم الصارمة:")
                c_sub1, c_sub2 = st.columns(2)
                with c_sub1:
                    s1 = sub_scores.get("structure_parsability", 75)
                    st.metric("بنية السيرة والهيكلية", f"{s1}%")
                    st.progress(s1 / 100.0)
                    
                    s2 = sub_scores.get("action_verbs_impact", 70)
                    st.metric("قوة أفعال الإنجاز", f"{s2}%")
                    st.progress(s2 / 100.0)

                    s3 = sub_scores.get("quantifiable_metrics", 60)
                    st.metric("الأرقام والقياسات", f"{s3}%")
                    st.progress(s3 / 100.0)
                with c_sub2:
                    s4 = sub_scores.get("keyword_density", 75)
                    st.metric("كثافة الكلمات المفتاحية", f"{s4}%")
                    st.progress(s4 / 100.0)

                    s5 = sub_scores.get("contact_completeness", 85)
                    st.metric("اكتمال وسائل التواصل", f"{s5}%")
                    st.progress(s5 / 100.0)

            # Strengths vs Weaknesses
            col_str, col_weak = st.columns(2)
            with col_str:
                st.markdown("##### ✅ أبرز نقاط القوة المعتمدة في الـ ATS:")
                for st_item in ats_audit.get("strengths", []):
                    st.markdown(f"- 🟢 **{st_item}**")
            with col_weak:
                st.markdown("##### ⚠️ نقاط الضعف والمخاطر التي قد تستبعد السيرة:")
                for wk_item in ats_audit.get("critical_weaknesses", []):
                    st.markdown(f"- 🔴 **{wk_item}**")
            
            # Actionable steps
            with st.expander("💡 خارطة طريق وتوصيات عملية للارتقاء بالسيرة إلى 95%+", expanded=True):
                for act_item in ats_audit.get("actionable_recommendations", []):
                    st.markdown(f"• {act_item}")
                
                certs = ats_audit.get("suggested_certifications", [])
                if certs:
                    st.markdown("---")
                    st.markdown("🎓 **شهادات مهنية مقترحة ترفع من قوة السيرة وتفضيلها في خوارزميات الـ ATS:**")
                    st.markdown(" • ".join([f"`{c}`" for c in certs]))

        col_reset, col_reaudit = st.columns(2)
        with col_reset:
            if st.button("🔄 مسح السيرة والبدء من جديد (Reset)"):
                st.session_state["master_profile"] = None
                st.session_state["search_results"] = []
                st.session_state["session_generated_pdfs"] = []
                st.rerun()
        with col_reaudit:
            if st.button("🔬 إعادة تدقيق الـ ATS بتحليل معمق"):
                active_key = st.session_state.get("gemini_api_key", "").strip() or st.session_state.get("openai_api_key", "").strip()
                if not active_key:
                    prompt_api_key_dialog()
                else:
                    with st.spinner("جاري إجراء تدقيق ATS شامل ومعمق بالذكاء الاصطناعي..."):
                        try:
                            fresh_audit = audit_master_cv_ats(
                                master_profile.get("raw_text", ""),
                                custom_key=active_key,
                                llm_type=st.session_state.get("preferred_llm", "gemini")
                            )
                            master_profile["ats_audit"] = fresh_audit
                            st.session_state["master_profile"] = master_profile
                            st.success("تم تحديث تقرير الـ ATS بنجاح!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"حدث خطأ أثناء تدقيق الـ ATS: {e}")
    else:
        st.info("💡 لم يتم رفع سيرة ذاتية بعد. يرجى رفع ملفك بصيغة PDF أو DOCX للبدء.")

# ----------------- TAB 2: CITY SELECTION & SEARCH -----------------
with tabs[1]:
    st.subheader("📍 تحديد المدينة المستهدفة وإعدادات البحث")
    st.caption("حدد المدينة ومسميات البحث للعثور على أحدث وظائف LinkedIn المتاحة:")
    
    if not master_profile:
        st.warning("⚠️ يرجى رفع وتحليل سيرتك الذاتية في الخطوة 1 أولاً ليعرف النظام تخصصك والمسميات المناسبة.")
    else:
        st.success(f"✅ التخصص المكتشف من الـ CV: **{master_profile.get('target_major', 'عام')}**")
        
        col_city1, col_city2 = st.columns(2)
        with col_city1:
            city_options = [
                "الرياض", "جدة", "الدمام", "الخبر", "الظهران", "مكة", "المدينة المنورة",
                "الجبيل", "ينبع", "تبوك", "القصيم", "حائل", "أبها", "دبي", "أبوظبي",
                "الدوحة", "الكويت", "المنامة", "مسقط", "عن بعد (Remote)", "مدينة أخرى..."
            ]
            selected_city = st.selectbox(
                "🏙️ اختر المدينة المستهدفة:",
                options=city_options,
                index=0
            )
            
            custom_city = ""
            if selected_city == "مدينة أخرى...":
                custom_city = st.text_input("اكتب اسم المدينة بالإنجليزية أو العربية:")

            target_city_final = custom_city.strip() if selected_city == "مدينة أخرى..." else selected_city

        with col_city2:
            st.write("🎯 **المسميات الوظيفية للبحث (مستخرجة من الـ CV):**")
            default_keywords = ", ".join(master_profile.get("suggested_job_titles", ["Specialist"]))
            job_keywords_input = st.text_area(
                "يمكنك تعديل أو إضافة مسميات للبحث (مفصولة بفاصلة):",
                value=default_keywords,
                height=90
            )

        st.markdown("##### 🌐 منصات ومحركات البحث المستهدفة:")
        col_src1, col_src2, col_src3 = st.columns(3)
        with col_src1:
            use_linkedin = st.checkbox("🔵 LinkedIn (لينكدين)", value=True)
        with col_src2:
            use_tanqeeb = st.checkbox("🟢 منصة تنقيب (السعودية والخليج)", value=True)
        with col_src3:
            use_remote = st.checkbox("🌍 منصات العمل عن بعد (Remote)", value=True)

        selected_sources = []
        if use_linkedin:
            selected_sources.append("linkedin")
        if use_tanqeeb:
            selected_sources.append("tanqeeb")
        if use_remote:
            selected_sources.append("remote")
        if not selected_sources:
            selected_sources = ["linkedin", "tanqeeb"]

        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            technician_only = st.checkbox("🎯 وظائف الفنيين والتقنيين فقط", value=False)
        with col_opt2:
            exclude_managers = st.checkbox("🚫 استبعاد وظائف المدراء (Manager)", value=True)
        with col_opt3:
            easy_apply_only = st.checkbox("⚡ التقديم السهل فقط (Easy Apply)", value=False)

        st.caption("⚡ **البحث الشامل وغير المحدود:** يبحث النظام في عدة منصات دفعة واحدة ويجلب كافة الوظائف المتاحة بدون تحديد حد أقصى، ويرتبها تلقائياً لتظهر **الوظائف الأكثر تطابقاً مع سيرتك الذاتية في البداية أولاً**.")

        if st.button("🔎 ابدأ البحث الشامل في جميع المنصات", type="primary"):
            keywords_list = [k.strip() for k in job_keywords_input.split(",") if k.strip()]
            with st.spinner(f"جاري البحث في جميع المنصات عن الوظائف في '{target_city_final}' وترتيبها حسب التوافق مع سيرتك..."):
                jobs = search_multi_source_jobs(
                    keywords_list=keywords_list,
                    target_city=target_city_final,
                    master_profile=master_profile,
                    sources=selected_sources,
                    easy_apply_only=easy_apply_only,
                    technician_only=technician_only,
                    exclude_managers=exclude_managers,
                    max_results=None
                )
                if jobs:
                    st.session_state["search_results"] = jobs
                    st.session_state["searched_city"] = target_city_final
                    st.success(f"تم العثور على {len(jobs)} وظيفة ورُتّبت حسب الأكثر تطابقاً مع سيرتك الذاتية! انتقل إلى التبويب التالي لعرضها.")
                else:
                    st.warning("لم يتم العثور على نتائج مباشرة بهذه الكلمات في هذه المدينة. جرب توسيع المسميات أو تفعيل جميع المنصات.")

# ----------------- TAB 3: JOBS & AI TAILORING -----------------
with tabs[2]:
    st.subheader("💼 الوظائف المكتشفة وتخصيص الـ CV بنقرة زر")
    st.caption("اختر أي وظيفة ليقوم الذكاء الاصطناعي بتخصيص السيرة الذاتية لها وتجهيز ملف PDF احترافي:")
    
    search_results = st.session_state.get("search_results", [])
    if not search_results:
        st.info("🔍 لم يتم تنفيذ بحث بعد. اختر المدينة واضغط 'ابدأ البحث' من الخطوة 2.")
    else:
        st.write(f"عرض **{len(search_results)}** وظيفة تم العثور عليها مرتبة من **الأعلى تطابقاً مع سيرتك الذاتية** إلى الأقل:")
        
        for idx, job in enumerate(search_results):
            analysis = analyze_job_qualification(job['title'], job.get('description', ''))
            
            # Match badge
            match_score = job.get("match_score", 70)
            if match_score >= 85:
                match_chip = f'<span class="chip chip-emerald">🔥 تطابق ممتاز {match_score}% مع الـ CV</span>'
            elif match_score >= 70:
                match_chip = f'<span class="chip chip-cyan">⭐ تطابق جيد {match_score}% مع الـ CV</span>'
            elif match_score >= 50:
                match_chip = f'<span class="chip chip-amber">🔹 تطابق متوسط {match_score}%</span>'
            else:
                match_chip = f'<span class="chip chip-purple">تطابق عام {match_score}%</span>'

            source_name = job.get("source", "LinkedIn")
            source_chip = f'<span class="chip chip-purple">🌐 {source_name}</span>'
            
            with st.container():
                desc_snippet = job.get("description", "")
                has_desc = bool(desc_snippet and len(desc_snippet.strip()) > 30)
                clean_snippet = desc_snippet[:220].strip() if has_desc else ""

                st.markdown(f"""
                <div class="job-card-dark">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px;">
                        <h3 style="margin: 0 0 8px 0; color: #F8FAFC; font-size: 1.15rem; font-weight: 800;">{job['title']}</h3>
                        <div>{match_chip} {source_chip}</div>
                    </div>
                    <p style="margin: 0 0 12px 0; color: #94A3B8; font-weight: 600; font-size: 0.9rem;">
                        🏢 {job['company']} &nbsp; • &nbsp; 📍 {job['location']} &nbsp; • &nbsp; 🕒 {job['posted_time']}
                    </p>
                    <div style="margin-bottom: 12px;">
                        <span class="chip chip-cyan">👨‍🔧 {analysis['role_type']}</span>
                        <span class="chip chip-emerald">🎓 {analysis['degree_match']}</span>
                        <span class="chip chip-amber">⏳ {analysis['experience_level']}</span>
                    </div>
                    {f'<p style="color: #CBD5E1; font-size: 0.88rem; margin-bottom: 10px; line-height: 1.5;">{clean_snippet}...</p>' if has_desc else ''}
                    <p style="margin: 4px 0;"><a href="{job['link']}" target="_blank" style="color: #38BDF8; text-decoration: none; font-weight: 700;">🔗 فتح إعلان الوظيفة على {source_name} ↗</a></p>
                </div>
                """, unsafe_allow_html=True)
                
                col_btn1, col_btn2 = st.columns([1, 2])
                with col_btn1:
                    tailor_btn = st.button(
                        f"🎯 تخصيص الـ CV لهذه الوظيفة",
                        key=f"tailor_btn_{idx}",
                        type="primary"
                    )
                
                tailored_key = f"tailored_{job['id']}"

                if tailor_btn:
                    active_key = st.session_state.get("gemini_api_key", "").strip()
                    active_openai = st.session_state.get("openai_api_key", "").strip()
                    if not active_key and not active_openai:
                        prompt_api_key_dialog()
                    else:
                        with st.spinner("جاري جلب تفاصيل الوظيفة الكاملة وتحليل التوافق وتخصيص الـ CV..."):
                            if not job.get("description") or len(job.get("description", "")) < 80:
                                job["description"] = fetch_job_description(job['id'], job)
                            
                            tailored_res = evaluate_and_tailor_cv(
                                master_profile=master_profile,
                                job_data=job,
                                custom_key=active_key or active_openai,
                                llm_type=st.session_state.get("preferred_llm", "gemini")
                            )
                            # Generate tailored PDF
                            pdf_path = generate_pdf_resume(
                                master_profile=master_profile,
                                tailored_data=tailored_res,
                                job_title=job['title'],
                                company=job['company']
                            )
                            tailored_res["pdf_path"] = pdf_path
                            st.session_state[tailored_key] = tailored_res
                            if pdf_path and pdf_path not in st.session_state["session_generated_pdfs"]:
                                st.session_state["session_generated_pdfs"].append(pdf_path)

                if tailored_key in st.session_state:
                    res = st.session_state[tailored_key]
                    match_score = res.get("match_score", 0)
                    tailored_ats = res.get("tailored_ats_score", max(85, match_score + 10))
                    ats_verdict = res.get("ats_verdict", "🟢 جاهز للتقديم بنسبة عالية")
                    interview_prob = res.get("interview_likelihood", "مرتفعة جداً")
                    
                    st.markdown("#### 🎯 تقييم توافق الـ CV المخصص ومعايير الـ ATS الصارمة:")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        st.metric("📊 نسبة التوافق مع متطلبات الوظيفة", f"{match_score}%")
                        st.progress(min(1.0, match_score / 100.0))
                    with col_m2:
                        st.metric("🛡️ درجة الـ ATS بعد التخصيص", f"{tailored_ats}%")
                        st.progress(min(1.0, tailored_ats / 100.0))
                    with col_m3:
                        st.markdown(f"**حكم الـ ATS:** {ats_verdict}")
                        st.markdown(f"**فرصة المقابلة المتوقعة:** `{interview_prob}`")

                    # Sub-scores breakdown
                    ats_sub = res.get("ats_sub_scores", {})
                    if ats_sub:
                        c_s1, c_s2, c_s3, c_s4 = st.columns(4)
                        with c_s1:
                            st.caption("تغطية كلمات الوظيفة")
                            st.progress(ats_sub.get("keyword_coverage", 85) / 100.0)
                        with c_s2:
                            st.caption("ملاءمة صياغة الخبرات")
                            st.progress(ats_sub.get("experience_relevance", 80) / 100.0)
                        with c_s3:
                            st.caption("تطابق المهارات التقنية")
                            st.progress(ats_sub.get("hard_skills_fit", 85) / 100.0)
                        with c_s4:
                            st.caption("سلامة التنسيق للروبوتات")
                            st.progress(ats_sub.get("formatting_safety", 98) / 100.0)

                    # Injected ATS keywords
                    injected_kw = res.get("injected_ats_keywords", [])
                    if injected_kw:
                        st.markdown("🔑 **الكلمات المفتاحية التنافسية المدمجة في الـ CV لاجتياز الفرز التلقائي:**")
                        st.markdown(" • ".join([f"`{kw}`" for kw in injected_kw]))

                    if res.get("match_rationale"):
                        st.info(f"💡 **تحليل التوافق:** {res.get('match_rationale')}")

                    c1, c2 = st.columns(2)
                    with c1:
                        st.write("✅ **المهارات المتطابقة المعتمدة:**")
                        st.write(", ".join(res.get("matching_skills", [])))
                    with c2:
                        st.write("⚠️ **مهارات إضافية تطلبها الوظيفة:**")
                        st.write(", ".join(res.get("missing_skills", [])) if res.get("missing_skills") else "تمت تغطية كافة المتطلبات الأساسية بنجاح.")

                    with st.expander("📝 الملخص المهني المخصص للـ ATS"):
                        st.write(res.get("tailored_summary", ""))

                    with st.expander("✉️ خطاب التغطية المخصص (Cover Letter)"):
                        st.text_area("نص الخطاب:", value=res.get("cover_letter", ""), height=140, key=f"cl_{idx}")

                    pdf_file_path = res.get("pdf_path")
                    if pdf_file_path and os.path.exists(pdf_file_path):
                        with open(pdf_file_path, "rb") as f:
                            pdf_bytes = f.read()
                        
                        st.download_button(
                            label=f"📥 تحميل الـ CV المخصص لهذه الوظيفة فوراً (PDF)",
                            data=pdf_bytes,
                            file_name=os.path.basename(pdf_file_path),
                            mime="application/pdf",
                            key=f"dl_pdf_{idx}",
                            type="primary"
                        )

                        with st.expander("👁️ معاينة السيرة الذاتية داخل الصفحة (PDF Preview)", expanded=True):
                            render_pdf_preview(pdf_bytes, height=520)

                        if st.button(f"🚀 التقديم السريع على الوظيفة (على الكمبيوتر)", key=f"apply_{idx}"):
                            with st.spinner("جاري فتح المتصفح للتقديم التلقائي..."):
                                applier = LinkedInApplier(headless=False)
                                apply_res = applier.apply_to_job(
                                    job_url=job['link'],
                                    tailored_cv_pdf_path=pdf_file_path,
                                    user_profile=master_profile
                                )
                                if apply_res.get("success"):
                                    st.success(apply_res.get("message"))
                                else:
                                    st.warning(apply_res.get("message"))

                st.markdown("---")

# ----------------- TAB 4: GENERATED FILES -----------------
with tabs[3]:
    st.subheader("📁 السير الذاتية التي قمت بتخصيصها في هذه الجلسة")
    session_pdfs = st.session_state.get("session_generated_pdfs", [])
    valid_pdfs = [p for p in session_pdfs if os.path.exists(p)]
    
    if not valid_pdfs:
        st.info("💡 لم تقم بتوليد أي سيرة ذاتية في جلستك الحالية بعد. اختر وظيفة من الخطوة 3 واضغط 'تخصيص الـ CV' لتظهر وتُحفظ هنا.")
    else:
        for p in valid_pdfs:
            p_path = Path(p)
            with st.container():
                st.markdown(f"#### 📄 {p_path.name}")
                with open(p_path, "rb") as f:
                    f_bytes = f.read()
                
                st.download_button(
                    label=f"📥 تحميل الملف (PDF)",
                    data=f_bytes,
                    file_name=p_path.name,
                    mime="application/pdf",
                    key=f"file_dl_{p_path.name}",
                    type="primary"
                )
                with st.expander("👁️ معاينة سريعة للملف"):
                    render_pdf_preview(f_bytes, height=480)
                st.markdown("---")
