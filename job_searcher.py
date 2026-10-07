import time
import urllib.parse
import re
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple

__all__ = [
    "search_multi_source_jobs",
    "search_linkedin_jobs",
    "fetch_job_description",
    "analyze_job_qualification",
    "CITY_MAP",
    "calculate_cv_match",
    "normalize_city"
]

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

_session = requests.Session()
_session.headers.update(HEADERS)

def calculate_cv_match(job: Dict, master_profile: Dict = None) -> int:
    """
    Calculates a relevance score (20-99%) comparing the job against the candidate's CV profile.
    Considers target major, suggested titles, extracted skills, and experience level.
    """
    if not master_profile:
        return 65

    title = job.get("title", "").lower()
    desc = (job.get("description", "") or "").lower()
    
    cand_major = (master_profile.get("target_major", "") or "").lower()
    cand_titles = [t.lower() for t in master_profile.get("suggested_job_titles", [])]
    cand_skills = [s.lower() for s in master_profile.get("skills", [])]
    cand_exp = master_profile.get("experience_level", "")
    
    score = 45  # baseline score
    
    # 1. Target major matching (+25 if in title, +12 if in description)
    major_tokens = [m for m in re.split(r"[\s,/-]+", cand_major) if len(m) > 2]
    if major_tokens and any(t in title for t in major_tokens):
        score += 25
    elif major_tokens and any(t in desc for t in major_tokens):
        score += 12

    # 2. Suggested job titles matching (+20 for full, +10 for partial)
    for ct in cand_titles:
        ct_tokens = [w for w in re.split(r"[\s,/-]+", ct) if len(w) > 2]
        if ct_tokens and all(w in title for w in ct_tokens):
            score += 20
            break
        elif ct_tokens and any(w in title for w in ct_tokens):
            score += 10
            break

    # 3. Matching skills in title or description (+4 per skill, max +20)
    skills_matched = 0
    for sk in cand_skills:
        if len(sk) > 2 and (sk in title or sk in desc):
            skills_matched += 1
            if skills_matched >= 5:
                break
    score += skills_matched * 4

    # 4. Penalty for mismatched seniority
    if any(m in title for m in ['director', 'vice president', 'vp', 'head of', 'general manager', 'chief']):
        if any(w in str(cand_exp) for w in ['حديث', 'مبتدئ', 'متوسط', 'junior', 'entry', 'fresh']):
            score -= 30

    return max(25, min(99, score))

def _fetch_linkedin_jobs(keyword: str, location_query: str, easy_apply_only: bool, start: int = 0) -> List[Dict]:
    kw_encoded = urllib.parse.quote(f'"{keyword}"' if " " in keyword else keyword)
    loc_encoded = urllib.parse.quote(location_query)
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={kw_encoded}&location={loc_encoded}&start={start}"
    if easy_apply_only:
        url += "&f_AL=true"
    try:
        res = _session.get(url, timeout=10)
        if res.status_code != 200:
            return []
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.find_all("div", class_="base-search-card")
        parsed = []
        for card in cards:
            job_id_elem = card.get("data-entity-urn", "")
            job_id_match = re.search(r"\d+", job_id_elem)
            if not job_id_match:
                continue
            job_id = job_id_match.group(0)

            title_elem = card.find("h3", class_="base-search-card__title")
            title = title_elem.get_text(strip=True) if title_elem else ""

            company_elem = card.find("h4", class_="base-search-card__subtitle")
            location_elem = card.find("span", class_="job-search-card__location")
            time_elem = card.find("time", class_="job-search-card__listdate") or card.find("time", class_="job-search-card__listdate--new")
            link_elem = card.find("a", class_="base-card__full-link")

            company = company_elem.get_text(strip=True) if company_elem else "شركة غير معلنة"
            location = location_elem.get_text(strip=True) if location_elem else location_query
            posted_time = time_elem.get_text(strip=True) if time_elem else "مؤخراً"
            link = link_elem["href"].split("?")[0] if link_elem and "href" in link_elem.attrs else f"https://www.linkedin.com/jobs/view/{job_id}/"

            has_easy_apply = bool(card.find("span", class_="job-result-card__easy-apply") or "Easy Apply" in card.get_text())

            parsed.append({
                "id": f"li_{job_id}",
                "raw_id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "posted_time": posted_time,
                "link": link,
                "easy_apply": has_easy_apply or easy_apply_only,
                "search_keyword": keyword,
                "source": "LinkedIn",
                "description": ""
            })
        return parsed
    except Exception as e:
        print(f"Notice during LinkedIn search for '{keyword}': {e}")
        return []

def _fetch_tanqeeb_jobs(keyword: str, location_query: str) -> List[Dict]:
    """Fetches real jobs from Tanqeeb (Saudi Arabia aggregator)."""
    try:
        kw_enc = urllib.parse.quote(keyword)
        url = f"https://saudi.tanqeeb.com/ar/jobs/search?keywords={kw_enc}&search_in=jobs"
        res = _session.get(url, timeout=10)
        if res.status_code != 200:
            return []
        soup = BeautifulSoup(res.text, "html.parser")
        h2s = [h for h in soup.find_all("h2") if h.find("a")]
        parsed = []
        for h2 in h2s:
            a = h2.find("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link = a.get("href", "")
            if link.startswith("/"):
                link = f"https://saudi.tanqeeb.com{link}"
            parent = h2.find_parent("div", class_=lambda c: c and ("search-job-card" in c or "card" in c or "item" in c)) or h2.parent

            # Extract location
            loc = location_query
            if parent:
                loc_elem = parent.find("span", class_="search-job-workplace-location")
                if loc_elem:
                    loc = loc_elem.get_text(strip=True).replace("في الموقع - ", "").strip()

            # Extract company / source
            company = "جهة عمل معلنة"
            if parent:
                comp_elem = parent.find("span", class_="search-job-source")
                if comp_elem:
                    company = comp_elem.get_text(strip=True)

            # Extract date
            posted_time = "مؤخراً"
            if parent:
                meta_elem = parent.find("div", class_="search-job-meta-line")
                if meta_elem and "·" in meta_elem.get_text():
                    posted_time = meta_elem.get_text(strip=True).split("·")[-1].strip()

            # Extract snippet
            p = parent.find("p") if parent else None
            desc = p.get_text(strip=True) if p else ""

            job_id_num = re.sub(r"\D", "", link)
            job_id = f"tq_{job_id_num[-8:] if job_id_num else abs(hash(link)) % 10000000}"

            parsed.append({
                "id": job_id,
                "raw_id": job_id,
                "title": title,
                "company": company,
                "location": loc,
                "posted_time": posted_time,
                "link": link,
                "easy_apply": False,
                "search_keyword": keyword,
                "source": "تنقيب (Tanqeeb)",
                "description": desc
            })
        return parsed
    except Exception as e:
        print(f"Notice during Tanqeeb search for '{keyword}': {e}")
        return []

def _fetch_remotive_jobs(keyword: str) -> List[Dict]:
    """Fetches relevant remote jobs from Remotive API."""
    try:
        url = f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(keyword)}&limit=15"
        res = _session.get(url, timeout=8)
        if res.status_code != 200:
            return []
        data = res.json()
        parsed = []
        for j in data.get("jobs", []):
            parsed.append({
                "id": f"rem_{j.get('id', abs(hash(j.get('url', ''))) % 10000000)}",
                "raw_id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "company": j.get("company_name", "Global Company"),
                "location": j.get("candidate_required_location", "عن بعد (Remote)"),
                "posted_time": j.get("publication_date", "مؤخراً")[:10],
                "link": j.get("url", ""),
                "easy_apply": False,
                "search_keyword": keyword,
                "source": "عن بعد (Remotive)",
                "description": j.get("description", "")[:500]
            })
        return parsed
    except Exception as e:
        print(f"Notice during Remotive search for '{keyword}': {e}")
        return []

def search_multi_source_jobs(
    keywords_list: List[str],
    target_city: str,
    master_profile: Dict = None,
    sources: List[str] = None,
    easy_apply_only: bool = False,
    technician_only: bool = False,
    exclude_managers: bool = True,
    max_results: int = None
) -> List[Dict]:
    """
    Searches across multiple platforms (LinkedIn, Tanqeeb, Remotive) without artificial limits.
    Calculates CV match scores for all posts, and returns results sorted by highest CV match first.
    """
    location_query = normalize_city(target_city)
    sources = sources or ["linkedin", "tanqeeb", "remote"]
    jobs = []
    seen_keys = set()

    clean_keywords = []
    for raw_kw in keywords_list:
        parts = re.split(r"[/,]", raw_kw)
        for p in parts:
            c = clean_query_term(p)
            if c and len(c) > 2 and c not in clean_keywords:
                clean_keywords.append(c)

    if not clean_keywords:
        return []

    # Parallel asynchronous multi-source fetching
    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for kw in clean_keywords[:6]:
            if "linkedin" in sources:
                tasks.append(executor.submit(_fetch_linkedin_jobs, kw, location_query, easy_apply_only, 0))
                # Also fetch page 2 for deeper results
                tasks.append(executor.submit(_fetch_linkedin_jobs, kw, location_query, easy_apply_only, 25))
            if "tanqeeb" in sources:
                tasks.append(executor.submit(_fetch_tanqeeb_jobs, kw, location_query))
            if "remote" in sources:
                tasks.append(executor.submit(_fetch_remotive_jobs, kw))

        for future in concurrent.futures.as_completed(tasks):
            try:
                batch = future.result()
                for job in batch:
                    title = job.get("title", "").strip()
                    if not title or not is_title_relevant(title, clean_keywords):
                        continue

                    t_lower = title.lower()
                    if exclude_managers and any(m in t_lower for m in ['director', 'vice president', 'head of', 'manager', 'lead engineer']):
                        continue

                    if technician_only:
                        is_tech = any(tk in t_lower for tk in [
                            'technician', 'instrument', 'analyzer', 'calibration', 'i&c', 'control',
                            'operator', 'trainee', 'mechanic', 'فني', 'أجهزة', 'آلات'
                        ])
                        if not is_tech:
                            continue

                    dedup_key = f"{title.lower()}_{job.get('company', '').lower()}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    # Calculate CV match score for this job
                    job["match_score"] = calculate_cv_match(job, master_profile)
                    jobs.append(job)
            except Exception as e:
                print(f"Error collecting search results: {e}")

    # SORT BY HIGHEST CV MATCH RELEVANCE FIRST
    jobs.sort(key=lambda j: j.get("match_score", 0), reverse=True)

    if max_results and len(jobs) > max_results:
        return jobs[:max_results]

    return jobs

def search_linkedin_jobs(
    keywords_list: List[str],
    target_city: str,
    easy_apply_only: bool = False,
    technician_only: bool = True,
    exclude_managers: bool = True,
    max_results: int = None
) -> List[Dict]:
    """Compatibility wrapper calling the multi-source search engine."""
    return search_multi_source_jobs(
        keywords_list=keywords_list,
        target_city=target_city,
        sources=["linkedin", "tanqeeb", "remote"],
        easy_apply_only=easy_apply_only,
        technician_only=technician_only,
        exclude_managers=exclude_managers,
        max_results=max_results
    )

def fetch_job_description(job_id: str, job_dict: Dict = None) -> str:
    """Fetches the full description text for a job."""
    if job_dict and job_dict.get("description") and len(job_dict["description"]) > 100:
        return job_dict["description"]

    clean_id = str(job_id).replace("li_", "").replace("tq_", "").replace("rem_", "")
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{clean_id}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            desc_elem = soup.find("div", class_="show-more-less-html__markup")
            if desc_elem:
                return desc_elem.get_text(separator="\n", strip=True)
            article = soup.find("section", class_="description")
            if article:
                return article.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"Error fetching job description for {clean_id}: {e}")

    if job_dict and job_dict.get("description"):
        return job_dict["description"]

    return "الوظيفة معلنة عبر منصات التوظيف المعتمدة. يمكنك الضغط على رابط الوظيفة للاطلاع على تفاصيل التقديم والشروط بالكامل."
