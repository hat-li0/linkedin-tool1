import streamlit as st
import os
import json
import base64
from pathlib import Path
from config import OUTPUTS_DIR
from cv_parser import extract_text_from_file, parse_cv_with_ai
from job_searcher import search_linkedin_jobs, fetch_job_description, analyze_job_qualification, CITY_MAP
from cv_tailor import evaluate_and_tailor_cv, generate_pdf_resume
from auto_apply import LinkedInApplier

st.set_page_config(
    page_title="مساعد التوظيف الذكي و مخصص الـ CV",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
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

# Custom Styling (RTL and sleek cards)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    
    html, body, [class*="css"], .stMarkdown, .stButton, .stTextInput, .stSelectbox {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    .metric-card {
        background: linear-gradient(135deg, #1E293B, #0F172A);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
        color: white;
        margin-bottom: 12px;
    }
    .job-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 14px;
        transition: transform 0.2s ease;
    }
    .job-card:hover {
        border-color: #0284C7;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .stDownloadButton button, .stButton button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

def render_pdf_preview(pdf_bytes: bytes, height: int = 580):
    """Renders an interactive PDF preview within the browser."""
    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_html = f'''
    <div style="margin: 12px 0; border: 1px solid #CBD5E1; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
        <iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="{height}px" type="application/pdf" style="border: none;"></iframe>
    </div>
    '''
    st.markdown(pdf_html, unsafe_allow_html=True)

@st.dialog("🔑 مطلوب إدخال مفتاح Google Gemini للبدء")
def prompt_api_key_dialog():
    st.markdown("""
    **مرحباً بك!** 👋  
    لقراءة سيرتك الذاتية وتحديد تخصصك ومؤهلاتك بدقة وتخصيص الـ CV لكل وظيفة، تحتاج إلى إدخال مفتاح **Google Gemini**.
    
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
        "مزود الذكاء الاصطناعي المفضل:",
        options=["gemini", "openai"],
        format_func=lambda x: "Google Gemini (موصى به - متوفر مجاناً)" if x == "gemini" else "OpenAI GPT-4o-mini",
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

    if st.button("💾 حفظ الإعدادات للجلسة"):
        st.session_state["gemini_api_key"] = gemini_key.strip()
        st.session_state["openai_api_key"] = openai_key.strip()
        st.success("تم حفظ الإعدادات بنجاح!")

    st.markdown("---")
    st.subheader("🌐 جلسة لينكدين للتقديم")
    st.caption("سجّل دخولك لمرة واحدة ليتمكن البوت من التقديم التلقائي على الوظائف:")
    
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

# ----------------- MAIN CONTENT -----------------
st.title("🎯 أداة البحث عن الوظائف وتخصيص الـ CV والتقديم الذكي")
st.caption("أداة متكاملة: ترفع سيرتك الذاتية الأساسية، تختار المدينة، وتبحث لك عن الوظائف المناسبة لتخصصك وتخصص لك الـ CV لكل وظيفة على حدة!")

master_profile = st.session_state.get("master_profile", None)

tabs = st.tabs([
    "1️⃣ السيرة الذاتية الأساسية",
    "2️⃣ اختيار المدينة والبحث",
    "3️⃣ الوظائف والـ CV المخصص",
    "📁 السير الذاتية المجهزة للتقديم"
])

# ----------------- TAB 1: MASTER CV -----------------
with tabs[0]:
    st.subheader("📄 رفع وتحليل السيرة الذاتية الأساسية (Master CV)")
    st.write("ارفع سيرتك الذاتية ليقوم الذكاء الاصطناعي باستخراج تخصصك ومهاراتك واقتراح الوظائف المناسبة لك تلقائياً:")
    
    uploaded_file = st.file_uploader(
        "اختر ملف السيرة الذاتية (PDF أو Word أو TXT):",
        type=["pdf", "docx", "txt"],
        key="master_cv_uploader"
    )
    
    if uploaded_file is not None:
        analyze_clicked = st.button("🚀 تحليل السيرة الذاتية واستخراج التخصص والمهارات")
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
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👤 الاسم", master_profile.get("name", "غير محدد"))
            st.write(f"📧 **البريد:** {master_profile.get('email', 'غير محدد')}")
            st.write(f"📞 **الهاتف:** {master_profile.get('phone', 'غير محدد')}")
        with col2:
            st.metric("🎓 التخصص الأساسي المستخرج", master_profile.get("target_major", "عام"))
            st.metric("📊 المستوى التقريبي", master_profile.get("experience_level", "متوسط"))
        with col3:
            st.write("🎯 **المسميات الوظيفية المقترحة تلقائياً للبحث:**")
            suggested = master_profile.get("suggested_job_titles", [])
            for title in suggested:
                st.markdown(f"- **{title}**")
        
        st.write("🛠️ **أبرز المهارات المستخرجة:**")
        skills_str = " • ".join(master_profile.get("skills", []))
        st.info(skills_str if skills_str else "لم يتم العثور على مهارات محددة.")
        
        with st.expander("📝 عرض النبذة المهنية المستخرجة (Summary)"):
            st.write(master_profile.get("summary", "لا يوجد"))

        if st.button("🔄 مسح السيرة والبدء من جديد (Reset)"):
            st.session_state["master_profile"] = None
            st.session_state["search_results"] = []
            st.session_state["session_generated_pdfs"] = []
            st.rerun()
    else:
        st.info("💡 لم يتم رفع سيرة ذاتية بعد. يرجى رفع ملفك بصيغة PDF أو DOCX للبدء.")

# ----------------- TAB 2: CITY SELECTION & SEARCH -----------------
with tabs[1]:
    st.subheader("📍 تحديد المدينة المستهدفة وإعدادات البحث")
    
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
            default_keywords = ", ".join(master_profile.get("suggested_job_titles", ["Software Engineer"]))
            job_keywords_input = st.text_area(
                "يمكنك تعديل أو إضافة مسميات للبحث (مفصولة بفاصلة):",
                value=default_keywords,
                height=100
            )

        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            technician_only = st.checkbox("🎯 وظائف الفنيين والتقنيين فقط (Technician)", value=False, help="حصر النتائج في الوظائف الفنية والتقنية والمهارات التطبيقية")
        with col_opt2:
            exclude_managers = st.checkbox("🚫 استبعاد وظائف المدراء (Manager/Lead)", value=True)
        with col_opt3:
            easy_apply_only = st.checkbox("⚡ التقديم السهل فقط (Easy Apply)", value=False)

        max_jobs = st.slider("عدد الوظائف المطلوبة للبحث:", min_value=5, max_value=30, value=15)

        if st.button("🔎 ابدأ البحث عن الوظائف في هذه المدينة"):
            keywords_list = [k.strip() for k in job_keywords_input.split(",") if k.strip()]
            with st.spinner(f"جاري البحث في لينكدين وتطبيق فلاتر المسمى والشهادة في '{target_city_final}'..."):
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
    st.subheader("💼 الوظائف المكتشفة وتخصيص السيرة الذاتية (AI Customizer)")
    
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
                    <h3 style="margin: 0; color: #0F172A;">{job['title']}</h3>
                    <p style="margin: 4px 0; color: #475569; font-weight: 600;">🏢 {job['company']} &nbsp; | &nbsp; 📍 {job['location']} &nbsp; | &nbsp; 🕒 {job['posted_time']}</p>
                    <div style="margin: 8px 0; display: flex; gap: 8px; flex-wrap: wrap;">
                        <span style="background: #E0F2FE; color: #0369A1; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 700;">👨‍🔧 {analysis['role_type']}</span>
                        <span style="background: #DCFCE7; color: #15803D; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 700;">🎓 {analysis['degree_match']}</span>
                        <span style="background: #FEF3C7; color: #B45309; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 700;">⏳ {analysis['experience_level']}</span>
                    </div>
                    <p style="margin: 6px 0;"><a href="{job['link']}" target="_blank" style="color: #0284C7; text-decoration: none; font-weight: 600;">🔗 رابط الوظيفة في LinkedIn</a></p>
                </div>
                """, unsafe_allow_html=True)
                
                col_btn1, col_btn2 = st.columns([1, 3])
                with col_btn1:
                    tailor_btn = st.button(
                        f"🎯 تخصيص الـ CV لهذه الوظيفة",
                        key=f"tailor_btn_{idx}"
                    )
                
                job_desc_key = f"job_desc_{job['id']}"
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
                    score = res.get("match_score", 0)
                    
                    st.markdown(f"#### 📊 نسبة التوافق مع مؤهلاتك: **{score}%**")
                    st.progress(min(1.0, score / 100.0))
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write("✅ **المهارات المتطابقة:**")
                        st.write(", ".join(res.get("matching_skills", [])))
                    with c2:
                        st.write("⚠️ **مهارات إضافية تطلبها الوظيفة:**")
                        st.write(", ".join(res.get("missing_skills", [])))

                    with st.expander("📝 الملخص المهني المخصص للـ ATS"):
                        st.write(res.get("tailored_summary", ""))

                    with st.expander("✉️ خطاب التغطية المخصص (Cover Letter)"):
                        st.text_area("نص الخطاب:", value=res.get("cover_letter", ""), height=150, key=f"cl_{idx}")

                    pdf_file_path = res.get("pdf_path")
                    if pdf_file_path and os.path.exists(pdf_file_path):
                        with open(pdf_file_path, "rb") as f:
                            pdf_bytes = f.read()
                        
                        with st.expander("👁️ معاينة السيرة الذاتية المخصصة قبل التحميل (PDF Preview)", expanded=True):
                            render_pdf_preview(pdf_bytes, height=580)

                        col_dl, col_apply = st.columns([1, 1])
                        with col_dl:
                            st.download_button(
                                label=f"📥 تحميل الـ CV المخصص لهذه الوظيفة (PDF)",
                                data=pdf_bytes,
                                file_name=os.path.basename(pdf_file_path),
                                mime="application/pdf",
                                key=f"dl_pdf_{idx}"
                            )
                        
                        with col_apply:
                            if st.button(f"🚀 التقديم السريع على الوظيفة بالـ CV المخصص", key=f"apply_{idx}"):
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
            with st.expander(f"📄 {p_path.name}", expanded=True):
                with open(p_path, "rb") as f:
                    f_bytes = f.read()
                render_pdf_preview(f_bytes, height=520)
                st.download_button(
                    label=f"📥 تحميل {p_path.name} (PDF)",
                    data=f_bytes,
                    file_name=p_path.name,
                    mime="application/pdf",
                    key=f"file_dl_{p_path.name}"
                )
