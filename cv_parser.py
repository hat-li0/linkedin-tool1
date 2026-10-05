import os
import re
from pathlib import Path
from pypdf import PdfReader
from docx import Document
from ai_engine import ask_llm_json

def extract_text_from_file(file_path_or_bytes, filename: str) -> str:
    """Extracts raw text from PDF, DOCX, or TXT."""
    filename_lower = filename.lower()
    text = ""
    
    if hasattr(file_path_or_bytes, "seek"):
        file_path_or_bytes.seek(0)
    
    if filename_lower.endswith(".pdf"):
        reader = PdfReader(file_path_or_bytes)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    elif filename_lower.endswith(".docx"):
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
    
    # Extract candidate title / major from top lines if available
    potential_title = lines[1] if len(lines) > 1 and len(lines[1]) < 60 else "عام"
    
    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "target_major": potential_title,
        "experience_level": "متوسط",
        "summary": raw_text[:300] + "..." if len(raw_text) > 300 else raw_text,
        "skills": ["مهارات عامة"],
        "suggested_job_titles": [potential_title] if potential_title != "عام" else ["Specialist", "Officer"],
        "search_keywords": [potential_title] if potential_title != "عام" else ["Specialist"],
        "work_experience": [],
        "education": [],
        "raw_text": raw_text
    }

def parse_cv_with_ai(raw_text: str, custom_key: str = None, llm_type: str = None) -> dict:
    """Parses raw CV text into structured profile data and auto-generates target search keywords."""
    system_prompt = (
        "أنت خبير محترف في الموارد البشرية (HR) وفحص السير الذاتية لأنظمة الـ ATS والتوظيف على LinkedIn. "
        "مهمتك هي تحليل نص السيرة الذاتية المرفقة بدقة شديدة واستخراج بيانات المرشح الخاصة بهذا الملف حصراً، "
        "وتحديد تخصصه الدقيق، واقتراح أفضل المسميات الوظيفية باللغة الإنجليزية للبحث عنها في لينكدين."
    )
    
    prompt = f"""
قم بتحليل نص السيرة الذاتية التالي واستخرج بيانتها بصيغة JSON طبقاً للهيكل التالي بدقة:

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
  ]
}}

نص السيرة الذاتية للمرشح:
\"\"\"
{raw_text[:12000]}
\"\"\"
"""
    data = ask_llm_json(prompt, system_prompt=system_prompt, custom_key=custom_key, llm_type=llm_type)
    data["raw_text"] = raw_text
    return data
