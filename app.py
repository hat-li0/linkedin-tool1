import streamlit as st
import os
import json
import base64
from pathlib import Path
from config import OUTPUTS_DIR
from cv_parser import extract_text_from_file, parse_cv_with_ai, audit_master_cv_ats
from job_searcher import search_linkedin_jobs, fetch_job_description, analyze_job_qualification, CITY_MAP
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

# Modern, Mobile-First Arabic Responsive Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap');
    
    * {
        font-family: 'Cairo', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    
    html, body, [data-testid="stAppViewContainer"], .stApp {
        direction: rtl;
        text-align: right;
        background-color: #F8FAFC;
    }

    /* Container Spacing & Mobile Responsive Padding */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1100px !important;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
            padding-top: 1rem !important;
        }
    }

    /* Hero Header */
    .hero-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 22px 24px;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
    }
    .hero-title {
        font-size: clamp(1.3rem, 4vw, 1.8rem);
        font-weight: 800;
        margin: 0 0 6px 0;
        color: #FFFFFF;
    }
    .hero-subtitle {
        font-size: clamp(0.85rem, 2.5vw, 1rem);
        color: #94A3B8;
        margin: 0;
        line-height: 1.6;
    }

    /* Modern Card Styles */
    .ui-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
    }

    .job-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
        transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .job-card:hover {
        border-color: #0284C7;
        box-shadow: 0 6px 16px rgba(2, 132, 199, 0.08);
    }

    /* Badges & Chips */
    .chip {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 700;
        margin: 3px 4px 3px 0;
    }
    .chip-blue { background: #E0F2FE; color: #0369A1; }
    .chip-green { background: #DCFCE7; color: #15803D; }
    .chip-amber { background: #FEF3C7; color: #B45309; }
    .chip-purple { background: #F3E8FF; color: #7E22CE; }
    .chip-slate { background: #F1F5F9; color: #475569; }

    /* Touch-friendly Buttons */
    .stButton > button, .stDownloadButton > button {
        border-radius: 10px !important;
        font-weight: 700 !important;
        padding: 0.55rem 1.2rem !important;
        transition: all 0.2s ease !important;
    }
    @media (max-width: 768px) {
        .stButton > button, .stDownloadButton > button {
            width: 100% !important;
            min-height: 48px !important;
            font-size: 15px !important;
            margin-top: 4px !important;
            margin-bottom: 4px !important;
        }
    }

    /* Horizontal Smooth Tabs for Mobile */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        overflow-x: auto;
        flex-wrap: nowrap;
        padding-bottom: 6px;
        scrollbar-width: none;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 8px 14px;
        font-weight: 700;
        font-size: 14px;
        white-space: nowrap;
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        color: #475569;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0284C7 !important;
        color: #FFFFFF !important;
        border-color: #0284C7 !important;
    }

    /* Metrics Cards */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 14px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.02);
    }
    [data-testid="stMetricLabel"] {
        font-weight: 700;
        color: #64748B;
        font-size: 13px !important;
    }
    [data-testid="stMetricValue"] {
        font-weight: 800;
        color: #0F172A;
        font-size: 20px !important;
    }
</style>
""", unsafe_allow_html=True)

def render_pdf_preview(pdf_bytes: bytes, height: int = 540):
    """Renders a responsive PDF preview with fallback for mobile devices."""
    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_html = f'''
    <div style="margin: 12px 0; border: 1px solid #CBD5E1; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.05); background: white;">
        <iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="{height}px" type="application/pdf" style="border: none;">
            <p style="padding: 16px; text-align: center; color: #64748B;">
                📱 جهازك لا يدعم المعاينة المباشرة داخل المتصفح. يمكنك تحميل الملف فوراً عبر زر التحميل أدناه.
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
    
    new_key = st.text_input("ألصق مفتاح Google Gemini API هنا:", type="password", placeholder="AIzaSy...")
    
    if st.button("💾 حفظ المفتاح ومتابعة التحليل", type="primary"):
        clean_key = new_key.strip()
        if clean_key:
            if not clean_key.startswith("AIzaSy"):
                st.warning("⚠️ تنبيه: مفتاح Google Gemini يبدأ عادة بـ `AIzaSy...`. يرجى التأكد من نسخه بدقة من الرابط أعلاه.")
            st.session_state["gemini_api_key"] = clean_key
            st.session_state["preferred_llm"] = "gemini"
            st.session_state["auto_trigger_analysis"] = True
            st.success("تم حفظ المفتاح بنجاح! جاري المتابعة...")
            st.rerun()
        else:
            st.error("يرجى إدخال المفتاح أولاً للمتابعة.")

# ----------------- SIDEBAR SETTINGS -----------------
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

# ----------------- MAIN HERO HEADER -----------------
st.markdown("""
<div class="hero-banner">
    <h1 class="hero-title">💼 مساعد التوظيف الذكي و مخصص الـ CV</h1>
    <p class="hero-subtitle">ارفع سيرتك الذاتية، افحص توافق الـ ATS الصارم، واستكشف وظائف LinkedIn المتاحة مع تخصيص الـ CV بنقرة زر واحدة!</p>
</div>
""", unsafe_allow_html=True)

# Quick Key Check for Mobile Users
has_key = bool(st.session_state.get("gemini_api_key", "").strip() or st.session_state.get("openai_api_key", "").strip())
if not has_key:
    c_banner1, c_banner2 = st.columns([3, 1])
    with c_banner1:
        st.info("💡 للبدء بتحليل السيرة وفحص الـ ATS وتخصيص الـ CV، يلزم إدخال مفتاح Google Gemini (مجاني وفوري 100%).")
    with c_banner2:
        if st.button("🔑 إدخال المفتاح المجاني الآن"):
            prompt_api_key_dialog()

master_profile = st.session_state.get("master_profile", None)

tabs = st.tabs([
    "1️⃣ السيرة الأساسية وفحص الـ ATS",
    "2️⃣ اختيار المدينة والبحث",
    "3️⃣ الوظائف والـ CV المخصص",
    "📁 ملفات الـ CV المجهزة"
])

# ----------------- TAB 1: MASTER CV & ATS AUDIT -----------------
with tabs[0]:
    st.subheader("📄 رفع السيرة الذاتية وفحص الـ ATS (Master CV)")
    st.caption("ارفع سيرتك الذاتية ليقوم الذكاء الاصطناعي باستخراج تخصصك بدقة وتقييم جاهزيتها لأنظمة الـ ATS:")
    
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
        
        # Responsive 2-column on mobile / 3 on desktop
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
            
            # Mobile-friendly 2-row sub-scores
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

        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            technician_only = st.checkbox("🎯 وظائف الفنيين والتقنيين فقط", value=False)
        with col_opt2:
            exclude_managers = st.checkbox("🚫 استبعاد وظائف المدراء (Manager)", value=True)
        with col_opt3:
            easy_apply_only = st.checkbox("⚡ التقديم السهل فقط (Easy Apply)", value=False)

        max_jobs = st.slider("عدد الوظائف المطلوبة للبحث:", min_value=5, max_value=30, value=15)

        if st.button("🔎 ابدأ البحث عن الوظائف في هذه المدينة", type="primary"):
            keywords_list = [k.strip() for k in job_keywords_input.split(",") if k.strip()]
            with st.spinner(f"جاري البحث في لينكدين عن الوظائف في '{target_city_final}'..."):
                jobs = search_linkedin_jobs(
                    keywords_list=keywords_list,
                    target_city=target_city_final,
                    easy_apply_only=easy_apply_only,
                    technician_only=technician_only,
                    exclude_managers=exclude_managers,
                    max_results=max_jobs
                )
                if jobs:
                    st.session_state["search_results"] = jobs
                    st.session_state["searched_city"] = target_city_final
                    st.success(f"تم العثور على {len(jobs)} وظيفة مطابقة في {target_city_final}! انتقل إلى الخطوة 3 لعرضها وتخصيص الـ CV.")
                else:
                    st.warning("لم يتم العثور على نتائج مباشرة بهذه الكلمات المفتاحية في هذه المدينة. جرب توسيع المسميات.")

# ----------------- TAB 3: JOBS & AI TAILORING -----------------
with tabs[2]:
    st.subheader("💼 الوظائف المكتشفة وتخصيص الـ CV بنقرة زر")
    st.caption("اختر أي وظيفة ليقوم الذكاء الاصطناعي بتخصيص السيرة الذاتية لها وتجهيز ملف PDF احترافي:")
    
    search_results = st.session_state.get("search_results", [])
    if not search_results:
        st.info("🔍 لم يتم تنفيذ بحث بعد. اختر المدينة واضغط 'ابدأ البحث' من الخطوة 2.")
    else:
        st.write(f"عرض **{len(search_results)}** وظيفة تم العثور عليها في **{st.session_state.get('searched_city', '')}**:")
        
        for idx, job in enumerate(search_results):
            analysis = analyze_job_qualification(job['title'], job.get('description', ''))
            
            with st.container():
                st.markdown(f"""
                <div class="job-card">
                    <h3 style="margin: 0 0 6px 0; color: #0F172A; font-size: 1.15rem;">{job['title']}</h3>
                    <p style="margin: 0 0 10px 0; color: #475569; font-weight: 600; font-size: 0.9rem;">
                        🏢 {job['company']} &nbsp; | &nbsp; 📍 {job['location']} &nbsp; | &nbsp; 🕒 {job['posted_time']}
                    </p>
                    <div style="margin-bottom: 10px;">
                        <span class="chip chip-blue">👨‍🔧 {analysis['role_type']}</span>
                        <span class="chip chip-green">🎓 {analysis['degree_match']}</span>
                        <span class="chip chip-amber">⏳ {analysis['experience_level']}</span>
                    </div>
                    <p style="margin: 4px 0;"><a href="{job['link']}" target="_blank" style="color: #0284C7; text-decoration: none; font-weight: 700;">🔗 فتح رابط الوظيفة في LinkedIn</a></p>
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
                            if not job.get("description"):
                                job["description"] = fetch_job_description(job['id'])
                            
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
