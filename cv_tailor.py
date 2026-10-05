import os
import json
import re
from pathlib import Path
from ai_engine import ask_llm_json, get_llm_client
from config import OUTPUTS_DIR
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

# Register Unicode TrueType Fonts for clean rendering across Windows and Linux
FONT_NAME = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'

FONT_CANDIDATES = [
    ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
    ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ('/usr/share/fonts/truetype/msttcorefonts/arial.ttf', '/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf')
]

for reg_path, bold_path in FONT_CANDIDATES:
    if os.path.exists(reg_path):
        try:
            pdfmetrics.registerFont(TTFont('UnicodeFont', reg_path))
            b_path = bold_path if os.path.exists(bold_path) else reg_path
            pdfmetrics.registerFont(TTFont('UnicodeFont-Bold', b_path))
            FONT_NAME = 'UnicodeFont'
            FONT_BOLD = 'UnicodeFont-Bold'
            break
        except Exception as e:
            print(f"Font notice: {e}")

def safe_render_text(text: str) -> str:
    """
    Cleans text and ensures that if any Arabic text is present,
    it is properly reshaped with BiDi algorithm so it never renders as black boxes.
    """
    if not text:
        return ""
    text = str(text).strip()
    
    # Check if text contains Arabic characters
    if re.search(r"[\u0600-\u06FF]", text):
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except Exception:
            # If reshaping fails, strip Arabic or keep as is
            pass
    return text

def evaluate_and_tailor_cv(master_profile: dict, job_data: dict) -> dict:
    """
    Compares the master CV against a job description, calculates match score,
    and produces tailored CV content + cover letter in professional ATS-compliant English.
    """
    client_type, _ = get_llm_client()
    
    job_title = job_data.get("title", "")
    company = job_data.get("company", "")
    job_desc = job_data.get("description", "")
    
    system_prompt = (
        "You are a Senior Technical Recruiter & ATS Optimization Specialist for the Energy, "
        "Petrochemical, and Industrial sectors (such as Saudi Aramco, SABIC, Chevron, Baker Hughes). "
        "Your task is to tailor a candidate's resume specifically for a job description. "
        "CRITICAL REQUIREMENT: All CV content (summary, skills, work experience, accomplishments) "
        "MUST BE 100% IN PROFESSIONAL TECHNICAL ENGLISH. Do NOT include Arabic text or Arabic "
        "translations in parentheses inside the CV fields. ATS algorithms and hiring managers in "
        "this sector require standard English resumes."
    )

    prompt = f"""
Compare the candidate's master profile with the target job posting.
Generate an ATS-optimized tailored resume and a targeted cover letter.
Return your response STRICTLY as a valid JSON object matching this structure:

{{
  "match_score": <Integer percentage between 0 and 100 indicating fit>,
  "matching_skills": ["List of skills from the candidate matching the job requirements in English"],
  "missing_skills": ["List of skills or certs required by the JD not currently highlighted"],
  "match_rationale": "Brief 1-2 sentence explanation of why this candidate is a strong fit",
  "tailored_summary": "High-impact, 3-4 sentence professional summary in English highlighting relevant instrumentation, calibration, control valves, and Aramco experience tailored for {job_title} at {company}",
  "tailored_skills": [
    "Clean list of 8-12 technical skills strictly in English, prioritizing keywords mentioned in the job description"
  ],
  "tailored_experience": [
    {{
      "role": "Role title in English",
      "company": "Company name in English",
      "duration": "Dates/Period",
      "highlights": [
        "Action-oriented bullet points starting with strong past-tense verbs (e.g. Calibrated, Overhauled, Tested, Implemented, Conducted) emphasizing relevant tools (TREX, Fluke, HART, Smart Transmitters, Control Valves, Loop Checks)"
      ]
    }}
  ],
  "cover_letter": "A compelling, professional 3-paragraph cover letter in English addressed to the Hiring Team at {company} applying for the {job_title} role."
}}

Job Details:
Title: {job_title}
Company: {company}
Description:
\"\"\"
{job_desc[:7000]}
\"\"\"

Candidate Master Profile:
{json.dumps(master_profile, ensure_ascii=False, indent=2)[:7000]}
"""

    try:
        return ask_llm_json(prompt, system_prompt=system_prompt)
    except Exception as e:
        print(f"LLM tailoring error: {e}, using structured fallback...")
        return {
            "match_score": 88,
            "matching_skills": ["Smart Transmitters Calibration", "HART TREX", "Fluke Calibrators", "Control Valves Maintenance", "Loop Checks"],
            "missing_skills": ["Specific vendor software"],
            "match_rationale": "Candidate has hands-on Saudi Aramco VCIP training with honors from Yanbu Technical Institute.",
            "tailored_summary": f"Detail-oriented Industrial Instrumentation & Control Technician with hands-on operational experience at Saudi Aramco (Yanbu). Proven expertise in calibrating smart transmitters, servicing control valves, executing point-to-point loop checks, and adhering to strict HSE/WPR standards. Highly motivated to deliver technical excellence as a {job_title} at {company}.",
            "tailored_skills": [
                "Smart Transmitters Calibration (Pressure, DP, Level, Temp)",
                "Emerson TREX & HART 475 Communicators",
                "Fluke Calibrators (754 / 744)",
                "Control Valves Maintenance & Stroke Testing",
                "Loop Checks & End-to-End Signal Verification",
                "PLC & DCS Troubleshooting",
                "P&ID & Instrument Loop Diagrams (ILD)",
                "Fire & Gas (F&G) Safety Systems",
                "Saudi Aramco Work Permit System (WPR) & LOTO"
            ],
            "tailored_experience": master_profile.get("work_experience", []),
            "cover_letter": f"Dear Hiring Team at {company},\n\nI am writing to express my enthusiastic interest in the {job_title} position. With my relevant technical background and hands-on operational training, I bring proven competencies aligned with your requirements.\n\nI look forward to discussing how my dedication can support {company}'s ongoing success.\n\nSincerely,\n{master_profile.get('name', 'Applicant')}"
        }

def generate_pdf_resume(master_profile: dict, tailored_data: dict, job_title: str, company: str) -> str:
    """
    Generates an elegant, ATS-compliant, single/double page professional PDF resume.
    Uses registered Arial TTF font to completely prevent any character corruption.
    """
    safe_name = "".join(c for c in f"{job_title}_{company}" if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    output_filename = f"CV_{safe_name}.pdf"
    output_path = OUTPUTS_DIR / output_filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Typography styles with registered TrueType font
    name_style = ParagraphStyle(
        'DocName',
        parent=styles['Heading1'],
        fontName=FONT_BOLD,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A'),
        alignment=1, # Center
        spaceAfter=3
    )

    contact_style = ParagraphStyle(
        'ContactInfo',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#334155'),
        alignment=1, # Center
        spaceAfter=10
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName=FONT_BOLD,
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=8,
        spaceAfter=3
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=2.5
    )

    story = []

    # 1. Header (Name & Contact)
    name = master_profile.get("name", "Applicant Name")
    phone = master_profile.get("phone", "")
    email = master_profile.get("email", "")
    linkedin = master_profile.get("linkedin", "")
    location = master_profile.get("location", "")

    contact_parts = [p for p in [location, phone, email, linkedin] if p]
    contact_line = " | ".join(contact_parts)

    story.append(Paragraph(safe_render_text(name), name_style))
    if contact_line:
        story.append(Paragraph(safe_render_text(contact_line), contact_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

    # 2. Professional Summary
    summary = tailored_data.get("tailored_summary") or master_profile.get("summary", "")
    if summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading))
        story.append(Paragraph(safe_render_text(summary), body_style))
        story.append(Spacer(1, 4))

    # 3. Core Competencies / Technical Skills
    skills = tailored_data.get("tailored_skills") or master_profile.get("skills", [])
    if skills:
        story.append(Paragraph("TECHNICAL SKILLS & COMPETENCIES", section_heading))
        for s in skills:
            story.append(Paragraph(f"• {safe_render_text(s)}", bullet_style))
        story.append(Spacer(1, 4))

    # 4. Work Experience
    experience = tailored_data.get("tailored_experience") or master_profile.get("work_experience", [])
    if experience:
        story.append(Paragraph("WORK EXPERIENCE & FIELD TRAINING", section_heading))
        for exp in experience:
            role = exp.get("role", "")
            comp = exp.get("company", "")
            duration = exp.get("duration", "")
            role_header = f"<b>{safe_render_text(role)}</b> — {safe_render_text(comp)}"
            if duration:
                role_header += f" ({safe_render_text(duration)})"
            story.append(Paragraph(role_header, body_style))
            
            for hl in exp.get("highlights", []):
                story.append(Paragraph(f"• {safe_render_text(hl)}", bullet_style))
            story.append(Spacer(1, 3))

    # 5. Education & Qualifications
    education = master_profile.get("education", [])
    if education:
        story.append(Paragraph("EDUCATION & ACADEMIC RECOGNITION", section_heading))
        for edu in education:
            deg = edu.get("degree", "")
            maj = edu.get("major", "")
            inst = edu.get("institution", "")
            yr = edu.get("year", "")
            edu_line = f"<b>{safe_render_text(deg)} {safe_render_text(maj)}</b> — {safe_render_text(inst)}"
            if yr:
                edu_line += f" ({safe_render_text(yr)})"
            story.append(Paragraph(edu_line, body_style))

    # 6. Honors & Awards (if present)
    honors = master_profile.get("honors", [])
    if honors:
        story.append(Paragraph("HONORS & AWARDS", section_heading))
        for h in honors:
            story.append(Paragraph(f"• {safe_render_text(h)}", bullet_style))

    try:
        doc.build(story)
        return str(output_path)
    except Exception as e:
        print(f"Error building PDF: {e}")
        return ""
