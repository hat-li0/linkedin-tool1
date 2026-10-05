import time
import urllib.parse
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

CITY_MAP = {
    "الرياض": "Riyadh, Saudi Arabia",
    "جدة": "Jeddah, Saudi Arabia",
    "ينبع": "Yanbu, Saudi Arabia",
    "الجبيل": "Jubail, Saudi Arabia",
    "الدمام": "Dammam, Saudi Arabia",
    "الخبر": "Khobar, Saudi Arabia",
    "الظهران": "Dhahran, Saudi Arabia",
    "مكة": "Mecca, Saudi Arabia",
    "المدينة المنورة": "Medina, Saudi Arabia",
    "المدينة": "Medina, Saudi Arabia",
    "تبوك": "Tabuk, Saudi Arabia",
    "أبها": "Abha, Saudi Arabia",
    "خميس مشيط": "Khamis Mushait, Saudi Arabia",
    "القصيم": "Al Qassim, Saudi Arabia",
    "بريدة": "Buraidah, Saudi Arabia",
    "حائل": "Hail, Saudi Arabia",
    "جازان": "Jazan, Saudi Arabia",
    "نجران": "Najran, Saudi Arabia",
    "كل السعودية": "Saudi Arabia",
    "السعودية": "Saudi Arabia",
    "دبي": "Dubai, United Arab Emirates",
    "أبوظبي": "Abu Dhabi, United Arab Emirates",
    "عن بعد": "Remote",
    "remote": "Remote"
}

def normalize_city(city_input: str) -> str:
    cleaned = city_input.strip()
    return CITY_MAP.get(cleaned, cleaned)

def clean_query_term(term: str) -> str:
    """Removes slashes, parentheses, and extracts clean search query."""
    cleaned = re.sub(r"[/\\()]", " ", term)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def analyze_job_qualification(job_title: str, job_description: str) -> Dict[str, str]:
    """
    Analyzes title and description to detect degree match, role type, and experience level.
    """
    t_lower = job_title.lower()
    d_lower = job_description.lower() if job_description else ""

    # 1. Role Type Analysis
    if any(w in t_lower for w in ['director', 'vice president', 'vp', 'head of', 'general manager', 'chief']):
        role_type = "إداري / قيادي (غير مناسب)"
        role_badge = "warning"
    elif any(w in t_lower for w in ['technician', 'technologist', 'trainee', 'operator', 'mechanic', 'specialist', 'فني', 'مشغل']):
        role_type = "فني / تقني (مطابق تماماً)"
        role_badge = "success"
    elif 'engineer' in t_lower:
        role_type = "مهندس (قد يقبل فني ذو كفاءة)"
        role_badge = "info"
    else:
        role_type = "عام / تقني"
        role_badge = "default"

    # 2. Degree Analysis
    has_diploma_keywords = any(w in d_lower for w in [
        'diploma', 'associate', 'technical institute', 'vocational', 'high school',
        'دبلوم', 'معهد تقني', 'كلية تقنية', 'ثانوية'
    ])
    has_bachelor_strict = ('bachelor' in d_lower or 'b.sc' in d_lower or 'degree in engineering' in d_lower) and not has_diploma_keywords

    if has_diploma_keywords:
        degree_match = "يقبل الدبلوم / المعاهد التقنية"
        degree_badge = "success"
    elif has_bachelor_strict:
        degree_match = "يشترط بكالوريوس"
        degree_badge = "warning"
    else:
        degree_match = "مؤهل تقني / دبلوم متاح"
        degree_badge = "info"

    # 3. Experience Analysis
    exp_matches = re.findall(r"(\d+)\s*(?:-|to)?\s*(\d+)?\s*(?:years?|yrs?|سنوات|سنة)", d_lower)
    min_exp = 0
    if exp_matches:
        try:
            min_exp = int(exp_matches[0][0])
        except Exception:
            min_exp = 0

    if min_exp == 0 or 'fresh' in d_lower or 'entry' in d_lower or 'trainee' in t_lower or '0-' in d_lower:
        exp_level = "حديث تخرج / 0-2 سنوات"
        exp_badge = "success"
    elif min_exp <= 4:
        exp_level = f"متوسط ({min_exp} سنوات خبرة)"
        exp_badge = "info"
    else:
        exp_level = f"متقدم ({min_exp}+ سنوات خبرة)"
        exp_badge = "warning"

    return {
        "role_type": role_type,
        "role_badge": role_badge,
        "degree_match": degree_match,
        "degree_badge": degree_badge,
        "experience_level": exp_level,
        "exp_badge": exp_badge
    }

def is_title_relevant(title: str, query_keywords: List[str] = None) -> bool:
    """Checks if the title matches what the candidate is actually searching for."""
    if not query_keywords:
        return True
    t = title.lower()
    words = [w.lower() for kw in query_keywords for w in re.split(r"[\s,]+", kw) if len(w) > 2]
    if not words:
        return True
    return any(w in t for w in words)

def search_linkedin_jobs(
    keywords_list: List[str],
    target_city: str,
    easy_apply_only: bool = False,
    technician_only: bool = True,
    exclude_managers: bool = True,
    max_results: int = 15
) -> List[Dict]:
    """
    Searches LinkedIn for jobs with strict title and degree filtering.
    """
    location_query = normalize_city(target_city)
    jobs = []
    seen_ids = set()

    # Expand keywords into clean single queries
    clean_keywords = []
    for raw_kw in keywords_list:
        # Split on slashes or commas
        parts = re.split(r"[/,]", raw_kw)
        for p in parts:
            c = clean_query_term(p)
            if c and len(c) > 2 and c not in clean_keywords:
                clean_keywords.append(c)

    for keyword in clean_keywords:
        if len(jobs) >= max_results:
            break
            
        kw_encoded = urllib.parse.quote(f'"{keyword}"' if " " in keyword else keyword)
        loc_encoded = urllib.parse.quote(location_query)
        
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={kw_encoded}&location={loc_encoded}&start=0"
        if easy_apply_only:
            url += "&f_AL=true"
            
        try:
            res = requests.get(url, headers=HEADERS, timeout=12)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.find_all("div", class_="base-search-card")

            for card in cards:
                if len(jobs) >= max_results:
                    break

                job_id_elem = card.get("data-entity-urn", "")
                job_id_match = re.search(r"\d+", job_id_elem)
                if not job_id_match:
                    continue
                job_id = job_id_match.group(0)

                if job_id in seen_ids:
                    continue

                title_elem = card.find("h3", class_="base-search-card__title")
                title = title_elem.get_text(strip=True) if title_elem else ""

                # 1. Relevance check
                if not is_title_relevant(title):
                    continue

                t_lower = title.lower()

                # 2. Exclude managers if requested
                if exclude_managers and any(m in t_lower for m in ['director', 'vice president', 'head of', 'manager', 'lead engineer']):
                    continue

                # 3. Technician-only filter if requested
                if technician_only:
                    is_tech = any(tk in t_lower for tk in [
                        'technician', 'instrument', 'analyzer', 'calibration', 'i&c', 'control',
                        'operator', 'trainee', 'mechanic', 'فني', 'أجهزة', 'آلات'
                    ])
                    if not is_tech:
                        continue

                seen_ids.add(job_id)

                company_elem = card.find("h4", class_="base-search-card__subtitle")
                location_elem = card.find("span", class_="job-search-card__location")
                time_elem = card.find("time", class_="job-search-card__listdate") or card.find("time", class_="job-search-card__listdate--new")
                link_elem = card.find("a", class_="base-card__full-link")

                company = company_elem.get_text(strip=True) if company_elem else "شركة غير معلنة"
                location = location_elem.get_text(strip=True) if location_elem else location_query
                posted_time = time_elem.get_text(strip=True) if time_elem else "مؤخراً"
                link = link_elem["href"].split("?")[0] if link_elem and "href" in link_elem.attrs else f"https://www.linkedin.com/jobs/view/{job_id}/"

                has_easy_apply = bool(card.find("span", class_="job-result-card__easy-apply") or "Easy Apply" in card.get_text())

                jobs.append({
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "posted_time": posted_time,
                    "link": link,
                    "easy_apply": has_easy_apply or easy_apply_only,
                    "search_keyword": keyword,
                    "description": ""
                })
        except Exception as e:
            print(f"Error searching for {keyword} in {location_query}: {e}")

        time.sleep(0.5)

    return jobs

def fetch_job_description(job_id: str) -> str:
    """Fetches the full description text for a specific LinkedIn job ID."""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            desc_elem = soup.find("div", class_="show-more-less-html__markup")
            if desc_elem:
                return desc_elem.get_text(separator="\n", strip=True)
            article = soup.find("section", class_="description")
            if article:
                return article.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"Error fetching job description for {job_id}: {e}")
    return "لا يتوفر وصف تفصيلي لهذه الوظيفة حالياً."
