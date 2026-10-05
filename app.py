import streamlit as st
import os
import json
from pathlib import Path
from config import (
    load_settings, save_settings,
    load_master_profile, save_master_profile,
    OUTPUTS_DIR
)
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

# ----------------- SIDEBAR SETTINGS -----------------
settings = load_settings()

with st.sidebar:
    st.header("⚙️ إعدادات الذكاء الاصطناعي")
    
    llm_choice = st.selectbox(
        "مزود الذكاء الاصطناعي المفضل:",
        options=["gemini", "openai"],
        format_func=lambda x: "Google Gemini (موصى به - متوفر مجاناً)" if x == "gemini" else "OpenAI GPT-4o-mini",
        index=0 if settings.get("preferred_llm") == "gemini" else 1
    )
    
    gemini_key = st.text_input(
        "Google Gemini API Key:",
        value=settings.get("gemini_api_key", ""),
        type="password",
        help="احصل على مفتاح مجاني فوري من: https://aistudio.google.com/app/apikey"
    )
    
    openai_key = st.text_input(
        "OpenAI API Key (اختياري):",
        value=settings.get("openai_api_key", ""),
        type="password"
    )
    
    if st.button("💾 حفظ الإعدادات"):
        settings["preferred_llm"] = llm_choice
        settings["gemini_api_key"] = gemini_key
        settings["openai_api_key"] = openai_key
        save_settings(settings)
        st.success("تم حفظ الإعدادات بنجاح!")

    st.markdown("---")
    st.subheader("🌐 جلسة لينكدين للتقديم")
    st.caption("سجّل دخولك لمرة واحدة فقط ليقوم البوت بحفظ الجلسة والتقديم بسهولة:")
    if st.button("🔑 تسجيل الدخول إلى لينكدين"):
        with st.spinner("جاري فتح المتصفح لتسجيل الدخول..."):
            try:
                applier = LinkedInApplier(headless=False)
                applier.launch_browser_for_login()
                st.success("تم إنهاء جلسة المتصفح بنجاح!")
            except Exception as e:
                st.error(f"حدث خطأ: {e}")

# ----------------- MAIN CONTENT -----------------
st.title("🎯 أداة البحث عن الوظائف وتخصيص الـ CV والتقديم الذكي")
st.caption("أداة متكاملة: ترفع سيرتك الذاتية الأساسية، تختار المدينة، وتبحث لك عن الوظائف المناسبة لتخصصك وتخصص لك الـ CV لكل وظيفة على حدة!")

master_profile = load_master_profile()

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
        if st.button("🚀 تحليل السيرة الذاتية واستخراج التخصص والمهارات"):
            with st.spinner("جاري قراءة الملف وتحليله بالذكاء الاصطناعي..."):
                try:
                    raw_text = extract_text_from_file(uploaded_file, uploaded_file.name)
                    parsed_profile = parse_cv_with_ai(raw_text)
                    save_master_profile(parsed_profile)
                    master_profile = parsed_profile
                    st.success("تم تحليل السيرة الذاتية بنجاح وحفظ الملف الشخصي الأساسي!")
                except Exception as e:
                    st.error(f"حدث خطأ أثناء التحليل: {e}")

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
            technician_only = st.checkbox("🎯 وظائف الفنيين والتقنيين فقط (Technician)", value=True, help="يستبعد الوظائف النظرية وهندسة البرمجيات ويركز على الآلات الدقيقة والتحكم")
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
                    with st.spinner("جاري جلب تفاصيل الوظيفة الكاملة وتحليل التوافق وتخصيص الـ CV..."):
                        if not job.get("description"):
                            job["description"] = fetch_job_description(job['id'])
                        
                        tailored_res = evaluate_and_tailor_cv(master_profile, job)
                        # Generate tailored PDF
                        pdf_path = generate_pdf_resume(
                            master_profile=master_profile,
                            tailored_data=tailored_res,
                            job_title=job['title'],
                            company=job['company']
                        )
                        tailored_res["pdf_path"] = pdf_path
                        st.session_state[tailored_key] = tailored_res

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
                        
                        st.download_button(
                            label=f"📥 تحميل الـ CV المخصص لهذه الوظيفة (PDF)",
                            data=pdf_bytes,
                            file_name=os.path.basename(pdf_file_path),
                            mime="application/pdf",
                            key=f"dl_pdf_{idx}"
                        )
                        
                        # Apply button
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
    st.subheader("📁 جميع ملفات السير الذاتية التي تم تخصيصها وتوليدها")
    generated_pdfs = list(OUTPUTS_DIR.glob("*.pdf"))
    if not generated_pdfs:
        st.info("لم يتم توليد أي ملفات بعد.")
    else:
        for p in generated_pdfs:
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                st.write(f"📄 **{p.name}**")
            with col_f2:
                with open(p, "rb") as f:
                    st.download_button(
                        label="تحميل",
                        data=f.read(),
                        file_name=p.name,
                        mime="application/pdf",
                        key=f"file_dl_{p.name}"
                    )
