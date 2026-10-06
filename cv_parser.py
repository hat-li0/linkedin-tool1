# Safe resilient imports for document readers
try:
    from pypdf import PdfReader
except Exception:
    try:
        from PyPDF2 import PdfReader
    except Exception:
        PdfReader = None

try:
    from docx import Document
except Exception:
    Document = None

from ai_engine import ask_llm_json

def extract_text_from_file(file_path_or_bytes, filename: str) -> str:
    """Extracts raw text from PDF, DOCX, or TXT."""
    filename_lower = filename.lower()
    text = ""
    
    if hasattr(file_path_or_bytes, "seek"):
        file_path_or_bytes.seek(0)
    
    if filename_lower.endswith(".pdf"):
        if PdfReader is None:
            raise ImportError("مكتبة قراءة الـ PDF (pypdf) غير متوفرة على الخادم. يرجى رفع الملف بصيغة TXT أو تثبيت pypdf.")
        reader = PdfReader(file_path_or_bytes)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    elif filename_lower.endswith(".docx"):
        if Document is None:
            raise ImportError("مكتبة قراءة ملفات Word (python-docx) غير متوفرة على الخادم. يرجى رفع الملف بصيغة PDF أو TXT.")
        doc = Document(file_path_or_bytes)
        for p in doc.paragraphs:
            if p.text:
                text += p.text + "\n"
    elif filename_lower.endswith(".txt"):
        if isinstance(file_path_or_bytes, (str, Path)):
            with open(file_path_or_bytes, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        else:
            text = file_path_or_bytes.getvalue().decode("utf-8", errors="ignore")
    else:
        raise ValueError("صيغة الملف غير مدعومة. يرجى رفع ملف PDF أو DOCX أو TXT.")
        
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("الملف المرفوع فارغ أو لا يحتوي على نصوص قابلة للقراءة (قد يكون صورة ممسوحة ضوئياً). يرجى التأكد من رفع ملف يحتوي على نصوص واضحة.")
    return cleaned

def heuristic_extract_profile(raw_text: str) -> dict:
    """Generic fallback extractor if no LLM is available."""
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
    phone_match = re.search(r"(\+?\d{1,4}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}", raw_text)
    
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    name = lines[0] if lines else "الباحث عن عمل"
    potential_title = lines[1] if len(lines) > 1 and len(lines[1]) < 60 else "عام"
    
    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "target_major": potential_title,
        "experience_level": "متوسط",
        "summary": raw_text[:300] + "..." if len(raw_text) > 300 else raw_text,
        "skills": ["مهارات مهنية عامة"],
        "suggested_job_titles": [potential_title] if potential_title != "عام" else ["Specialist", "Officer"],
        "search_keywords": [potential_title] if potential_title != "عام" else ["Specialist"],
        "work_experience": [],
        "education": [],
        "raw_text": raw_text,
        "ats_audit": {
            "overall_score": 65,
            "verdict_badge": "🟠 متوسط يحتاج إعادة صياغة واكتمال",
            "summary_verdict": "تم استخراج البيانات عبر التحليل الأولي. يُنصح برفع السيرة مع مفتاح الذكاء الاصطناعي لفحص دقيق ومعمق.",
            "sub_scores": {
                "structure_parsability": 70,
                "action_verbs_impact": 60,
                "quantifiable_metrics": 50,
                "keyword_density": 65,
                "contact_completeness": 80
            },
            "strengths": ["البيانات الأساسية موجودة وواضحة"],
            "critical_weaknesses": ["غياب القياسات والأرقام التي تثبت الإنجازات"],
            "actionable_recommendations": ["إضافة أرقام وإحصائيات للإنجازات السابقة"],
            "suggested_certifications": ["شهادة تخصصية معتمدة في المجال"]
        }
    }

def audit_master_cv_ats(raw_text: str, custom_key: str = None, llm_type: str = None) -> dict:
    """
    Performs a strict, uncompromising ATS audit assessing format, verbs, metrics,
    keyword density, completeness, weaknesses, and certification gaps.
    """
    system_prompt = (
        "You are an Elite Executive Talent Partner & Certified ATS Algorithm Auditor (Taleo, Workday, Greenhouse, Lever). "
        "Your task is to conduct a strict, objective, and unflinching ATS audit of a candidate's resume text. "
        "Apply the highest industry hiring benchmarks. Do not inflate scores. Give honest, constructive, and actionable feedback in Arabic."
    )
    
    prompt = f"""
قم بإجراء تقييم وفحص صارم وشامل للسيرة الذاتية التالية وفقاً لأحدث معايير أنظمة تتبع المتقدمين (ATS):

أجب بصيغة JSON تطابق هذا الهيكل تماماً:
{{
  "overall_score": <درجة رقمية صحيحة من 100 تعبر بدقة عن قوة وجاهزية الـ CV لأنظمة الـ ATS>,
  "verdict_badge": "<حكم التقييم: '🟢 استثنائي وجاهز بنسبة عالية' (90-100) أو '🟡 تنافسي جيد ويحتاج تحسينات' (75-89) أو '🟠 متوسط يحتاج إعادة صياغة' (60-74) أو '🔴 ضعيف ومعرض للاستبعاد التلقائي' (أقل من 60)>",
  "summary_verdict": "<فقرة من 2-3 جمل باللغة العربية تشرح التقييم العام والصورة الانطباعية لمدراء التوظيف والـ ATS>",
  "sub_scores": {{
    "structure_parsability": <درجة من 100: وضوح الهيكلية، وضوح الأقسام القياسية، سهولة قراءة الروبوتات للنص وتجاوز الجداول>,
    "action_verbs_impact": <درجة من 100: قوة الأفعال الحركية في بداية النقاط وتجنب العبارات الروتينية الضعيفة>,
    "quantifiable_metrics": <درجة من 100: استخدام الأرقام والنسب المئوية والنتائج القابلة للقياس المالي أو الإجرائي>,
    "keyword_density": <درجة من 100: كثافة وجودة المصطلحات والمهارات التقنية التخصصية المعيارية>,
    "contact_completeness": <درجة من 100: اكتمال بيانات الاتصال، الروابط المهنية كالـ LinkedIn، والنبذة المهنية>
  }},
  "strengths": [
    "3 إلى 4 نقاط قوة واضحة وبارزة في السيرة الذاتية"
  ],
  "critical_weaknesses": [
    "3 إلى 4 نقاط ضعف ومخاطر حقيقية قد تتسبب في استبعاد السيرة أو خفض ترتيبها في خوارزميات الفرز التلقائي"
  ],
  "actionable_recommendations": [
    "4 إلى 5 نصائح وخطوات عملية محددة لتحويل السيرة إلى مستوى 95%+"
  ],
  "suggested_certifications": [
    "2 إلى 3 شهادات مهنية أو اعتمادات دولية مطلوبة في سوق العمل لرفع قيمة هذا التخصص"
  ]
}}

نص السيرة الذاتية:
\"\"\"
{raw_text[:12000]}
\"\"\"
"""
    return ask_llm_json(prompt, system_prompt=system_prompt, custom_key=custom_key, llm_type=llm_type)

def parse_cv_with_ai(raw_text: str, custom_key: str = None, llm_type: str = None) -> dict:
    """
    Parses raw CV text into structured profile data, generates target search keywords,
    and conducts a strict ATS quality audit all in one structured AI pass.
    """
    system_prompt = (
        "أنت خبير محترف في الموارد البشرية (HR) وفحص السير الذاتية لأنظمة الـ ATS والتوظيف على LinkedIn. "
        "مهمتك هي تحليل نص السيرة الذاتية المرفقة بدقة شديدة واستخراج بيانات المرشح الخاصة بهذا الملف حصراً، "
        "وتحديد تخصصه الدقيق، واقتراح أفضل المسميات الوظيفية باللغة الإنجليزية للبحث عنها في لينكدين، "
        "مع تقديم تقييم صارم ودقيق لمدى توافق السيرة مع معايير الـ ATS العالمية."
    )
    
    prompt = f"""
قم بتحليل نص السيرة الذاتية التالي واستخرج بيانتها مع تقييم ATS صارم بصيغة JSON طبقاً للهيكل التالي بدقة:

{{
  "name": "اسم المرشح الكامل كما هو وارد في الـ CV",
  "email": "البريد الإلكتروني",
  "phone": "رقم الهاتف",
  "linkedin": "رابط حساب لينكدين إن وجد",
  "target_major": "التخصص الأساسي الدقيق للمرشح المذكور في هذا الـ CV (مثلاً: Software Engineering, Mechanical Engineering, Data Science, Accounting, Instrumentation, etc.)",
  "experience_level": "المستوى الوظيفي التقريبي (حديث تخرج / مبتدئ / متوسط / متقدم / إداري)",
  "summary": "نبذة مهنية احترافية تلخص خبرات هذا المرشح بالذات",
  "skills": ["قائمة بأبرز المهارات التقنية والمهنية الأساسية الواردة في السيرة"],
  "suggested_job_titles": [
    "قائمة بـ 4 إلى 6 مسميات وظيفية دقيقة باللغة الإنجليزية مستخرجة من تخصص وخبرة هذا المرشح للبحث عنها في لينكدين"
  ],
  "search_keywords": ["3 إلى 5 كلمات بحث مفتاحية أساسية بالإنجليزية تناسب تخصص هذا المرشح"],
  "work_experience": [
    {{
      "role": "المسمى الوظيفي",
      "company": "الشركة",
      "duration": "الفترة",
      "highlights": ["أهم الإنجازات والمهام"]
    }}
  ],
  "location": "المدينة والدولة إن وجدت",
  "education": [
    {{
      "degree": "الدرجة العلمية",
      "major": "التخصص",
      "institution": "الجامعة / الكلية",
      "year": "سنة التخرج أو الفترة"
    }}
  ],
  "ats_audit": {{
    "overall_score": <درجة رقمية من 100 تعبر عن قوة الـ CV وصعوبة تجاوزه لفلاتر الـ ATS>,
    "verdict_badge": "<حكم الجاهزية: '🟢 استثنائي وجاهز بنسبة عالية' أو '🟡 تنافسي جيد ويحتاج تحسينات' أو '🟠 متوسط يحتاج إعادة صياغة' أو '🔴 ضعيف ومعرض للاستبعاد'>",
    "summary_verdict": "<شرح من جملتين عن وضع السيرة الحالي في السوق والـ ATS>",
    "sub_scores": {{
      "structure_parsability": <درجة من 100: وضوح الهيكلية وعناوين الأقسام>,
      "action_verbs_impact": <درجة من 100: قوة الأفعال والإنجازات في نقاط الخبرة>,
      "quantifiable_metrics": <درجة من 100: توظيف الأرقام والنسب والنتائج الملموسة>,
      "keyword_density": <درجة من 100: ثراء الكلمات المفتاحية التخصصية>,
      "contact_completeness": <درجة من 100: اكتمال بيانات الاتصال وروابط الملف المهني>
    }},
    "strengths": [
      "3 إلى 4 نقاط قوة رئيسية في السيرة"
    ],
    "critical_weaknesses": [
      "3 إلى 4 ملاحظات قد تؤدي لاستبعاد السيرة أو تأخرها في الترتيب"
    ],
    "actionable_recommendations": [
      "4 نصائح عملية للارتقاء بالسيرة الذاتية فوراً"
    ],
    "suggested_certifications": [
      "2 إلى 3 شهادات مهنية موصى بها في هذا التخصص"
    ]
  }}
}}

نص السيرة الذاتية للمرشح:
\"\"\"
{raw_text[:12000]}
\"\"\"
"""
    data = ask_llm_json(prompt, system_prompt=system_prompt, custom_key=custom_key, llm_type=llm_type)
    data["raw_text"] = raw_text
    return data
