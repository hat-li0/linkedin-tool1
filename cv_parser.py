import os
import re
from pathlib import Path
from pypdf import PdfReader
from docx import Document
from ai_engine import ask_llm_json, get_llm_client

def extract_text_from_file(file_path_or_bytes, filename: str) -> str:
    """Extracts raw text from PDF, DOCX, or TXT."""
    filename_lower = filename.lower()
    text = ""
    
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
        
    return text.strip()

def heuristic_extract_profile(raw_text: str) -> dict:
    """Fallback extractor if no LLM key is configured."""
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
    phone_match = re.search(r"(\+?\d{1,4}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}", raw_text)
    
    first_lines = [line.strip() for line in raw_text.split("\n") if line.strip()][:5]
    name = first_lines[0] if first_lines else "الباحث عن عمل"
    
    # Comprehensive skills library across engineering and tech
    instrument_skills = [
        "Instrumentation", "Control Valves", "Transmitters", "HART", "PLC", "DCS", 
        "P&ID", "Calibration", "Fluke", "SCADA", "Automation", "Loop Check", "Fire & Gas", "LOTO"
    ]
    tech_skills = [
        "Python", "JavaScript", "SQL", "Java", "C++", "React", "Data Analysis", "Machine Learning"
    ]
    
    found_instrument = [s for s in instrument_skills if re.search(rf"\b{re.escape(s)}\b", raw_text, re.IGNORECASE)]
    found_tech = [s for s in tech_skills if re.search(rf"\b{re.escape(s)}\b", raw_text, re.IGNORECASE)]
    
    if found_instrument:
        target_major = "آلات دقيقة وتحكم صناعي (Instrumentation & Control)"
        suggested_job_titles = [
            "Instrument Technician",
            "Instrumentation & Control Technician",
            "Instrument Maintenance Technician",
            "Calibration Technician"
        ]
        skills = found_instrument
    elif found_tech:
        target_major = "تقنية معلومات وبرمجيات"
        suggested_job_titles = [
            "Software Engineer",
            "Full Stack Developer",
            "Data Analyst"
        ]
        skills = found_tech
    else:
        target_major = "هندسة وفني صيانة"
        suggested_job_titles = ["Technician", "Maintenance Specialist", "Field Operator"]
        skills = ["صيانة وتشغيل", "التواصل", "حل المشكلات"]
    
    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "target_major": target_major,
        "experience_level": "متوسط",
        "summary": raw_text[:350] + "..." if len(raw_text) > 350 else raw_text,
        "skills": skills,
        "suggested_job_titles": suggested_job_titles,
        "search_keywords": suggested_job_titles[:3],
        "work_experience": [],
        "education": [],
        "raw_text": raw_text
    }

def parse_cv_with_ai(raw_text: str) -> dict:
    """Parses raw CV text into structured profile data and auto-generates target search keywords."""
    client_type, _ = get_llm_client()
    if client_type == "none":
        return heuristic_extract_profile(raw_text)
        
    system_prompt = (
        "أنت خبير محترف في الموارد البشرية (HR) وفحص السير الذاتية لأنظمة الـ ATS والتطظيف على LinkedIn. "
        "مهمتك هي تحليل نص السيرة الذاتية بدقة واستخراج البيانات الأساسية، وتحديد تخصص المرشح بدقة، "
        "واقتراح أفضل المسميات الوظيفية (Job Titles) والكلمات المفتاحية للبحث عن وظائف تناسبه تماماً."
    )
    
    prompt = f"""
قم بتحليل السيرة الذاتية التالية واستخرج بيانتها بصيغة JSON طبقاً للهيكل التالي بدقة:

{{
  "name": "اسم المرشح الكامل",
  "email": "البريد الإلكتروني",
  "phone": "رقم الهاتف",
  "linkedin": "رابط حساب لينكدين إن وجد",
  "target_major": "التخصص الأساسي الدقيق للمرشح (مثلاً: هندسة برمجيات، علم بيانات، أمن سيبراني، إدارة مشاريع، محاسبة، تسويق رقمي)",
  "experience_level": "المستوى الوظيفي التقريبي (حديث تخرج / مبتدئ / متوسط / متقدم / إداري)",
  "summary": "نبذة مهنية احترافية مركزة تلخص خبرات المرشح وأبرز نقاط قوته",
  "skills": ["قائمة بأبرز المهارات التقنية والمهنية الأساسية"],
  "suggested_job_titles": [
    "قائمة بـ 4 إلى 6 مسميات وظيفية دقيقة باللغة الإنجليزية والإنجليزية/العربية هي الأنسب للبحث عنها في لينكدين بناء على تخصص وخبرة المرشح"
  ],
  "search_keywords": ["3 إلى 5 كلمات بحث مفتاحية أساسية للبحث في مواقع التوظيف"],
  "work_experience": [
    {{
      "role": "المسمى الوظيفي",
      "company": "الشركة",
      "duration": "الفترة",
      "highlights": ["أهم الإنجازات والمهام"]
    }}
  ],
  "location": "المدينة والدولة إن وجدت",
  "honors": ["قائمة بالجوائز وشهادات الشكر والتكريم إن وجدت"],
  "education": [
    {{
      "degree": "الدرجة العلمية",
      "major": "التخصص",
      "institution": "الجامعة / الكلية",
      "year": "سنة التخرج أو الفترة"
    }}
  ]
}}

نص السيرة الذاتية:
\"\"\"
{raw_text[:12000]}
\"\"\"
"""
    try:
        data = ask_llm_json(prompt, system_prompt=system_prompt)
        data["raw_text"] = raw_text
        return data
    except Exception as e:
        print(f"Error calling AI parser: {e}, falling back to heuristic...")
        fallback = heuristic_extract_profile(raw_text)
        fallback["error_note"] = str(e)
        return fallback
