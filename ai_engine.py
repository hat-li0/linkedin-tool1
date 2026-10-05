import os
import json
import re
from config import load_settings

def get_llm_client(custom_key: str = None, llm_type: str = None):
    settings = load_settings()
    llm_type = llm_type or settings.get("preferred_llm", "gemini")
    
    gemini_key = custom_key if (llm_type == "gemini" and custom_key) else ""
    openai_key = custom_key if (llm_type == "openai" and custom_key) else ""

    if not gemini_key and not openai_key:
        gemini_key = settings.get("gemini_api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "")
        openai_key = settings.get("openai_api_key", "").strip() or os.environ.get("OPENAI_API_KEY", "")

    if llm_type == "openai" and openai_key:
        from openai import OpenAI
        return "openai", OpenAI(api_key=openai_key)
    elif gemini_key:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        for model_name in ['gemini-3.8-flash', 'gemini-3.5-flash', 'gemini-3.7-flash', 'gemini-3.6-flash', 'gemini-flash-latest']:
            try:
                model = genai.GenerativeModel(model_name)
                return "gemini", model
            except Exception:
                continue
    elif openai_key:
        from openai import OpenAI
        return "openai", OpenAI(api_key=openai_key)
    
    return "none", None

def ask_llm(prompt: str, system_prompt: str = "", custom_key: str = None, llm_type: str = None) -> str:
    """Sends a prompt to the configured LLM and returns the text output."""
    client_type, client = get_llm_client(custom_key=custom_key, llm_type=llm_type)
    if client_type == "gemini":
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = client.generate_content(full_prompt)
        return response.text.strip()
    elif client_type == "openai":
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    else:
        raise ValueError("لم يتم ضبط مفتاح الذكاء الاصطناعي (Gemini أو OpenAI). يرجى إدخال المفتاح للبدء.")

def ask_llm_json(prompt: str, system_prompt: str = "", custom_key: str = None, llm_type: str = None) -> dict:
    """Forces the LLM to return valid JSON."""
    json_instructions = "\nهام جداً: يجب أن تكون إجابتك بصيغة JSON صالحة فقط بدون أي شروحات خارج الـ JSON code block."
    full_prompt = prompt + json_instructions
    response_text = ask_llm(full_prompt, system_prompt=system_prompt, custom_key=custom_key, llm_type=llm_type)
    
    cleaned = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.rstrip("`").strip()
    
    try:
        return json.loads(cleaned)
    except Exception as e:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"فشل تحليل الـ JSON المستلم من الذكاء الاصطناعي: {e}\nالنص:\n{response_text[:300]}")
