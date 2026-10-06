import os
import json
import re
from config import load_settings

GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-flash-latest"
]

def get_active_keys(custom_key: str = None, llm_type: str = None):
    settings = load_settings()
    llm_type = llm_type or settings.get("preferred_llm", "gemini")
    
    gemini_key = ""
    openai_key = ""
    
    if custom_key:
        if llm_type == "openai":
            openai_key = custom_key
        else:
            gemini_key = custom_key
            
    if not gemini_key and not openai_key:
        gemini_key = settings.get("gemini_api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "")
        openai_key = settings.get("openai_api_key", "").strip() or os.environ.get("OPENAI_API_KEY", "")
        
    return llm_type, gemini_key, openai_key

def get_llm_client(custom_key: str = None, llm_type: str = None):
    """Backward compatibility helper for retrieving configured LLM client."""
    chosen_type, gemini_key, openai_key = get_active_keys(custom_key=custom_key, llm_type=llm_type)
    if chosen_type == "openai" and openai_key:
        from openai import OpenAI
        return "openai", OpenAI(api_key=openai_key)
    elif gemini_key:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        return "gemini", genai
    elif openai_key:
        from openai import OpenAI
        return "openai", OpenAI(api_key=openai_key)
    return "none", None

def ask_gemini(prompt: str, system_prompt: str, gemini_key: str, is_json: bool = False) -> str:
    import google.generativeai as genai
    genai.configure(api_key=gemini_key)
    
    gen_config = {"temperature": 0.1}
    if is_json:
        gen_config["response_mime_type"] = "application/json"
    
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt if system_prompt else None,
                generation_config=gen_config
            )
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            err_msg = str(e)
            last_error = e
            # If model is 404 / unsupported, try the next model
            if "404" in err_msg or "NotFound" in err_msg or "not found" in err_msg.lower() or "unsupported" in err_msg.lower():
                continue
            # If invalid API key, fail fast with a friendly message
            if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg or "400" in err_msg:
                raise ValueError("مفتاح Google Gemini API غير صالح. يرجى التأكد من نسخه بدقة من Google AI Studio.")
            # If quota exceeded
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                raise ValueError("تم تجاوز حد الاستخدام المسموح لمفتاح Gemini (Quota Exceeded). يرجى استخدام مفتاح آخر أو المحاولة لاحقاً.")
            raise e

    raise ValueError(f"تعذر الاتصال بنماذج Google Gemini المتاحة. آخر خطأ: {last_error}")

def ask_openai(prompt: str, system_prompt: str, openai_key: str, is_json: bool = False) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    kwargs = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.1,
    }
    if is_json:
        kwargs["response_format"] = {"type": "json_object"}
        
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()

def ask_llm(prompt: str, system_prompt: str = "", custom_key: str = None, llm_type: str = None, is_json: bool = False) -> str:
    """Sends a prompt to the configured LLM and returns the text output."""
    chosen_type, gemini_key, openai_key = get_active_keys(custom_key=custom_key, llm_type=llm_type)
    
    if chosen_type == "openai" and openai_key:
        return ask_openai(prompt, system_prompt, openai_key, is_json=is_json)
    elif gemini_key:
        return ask_gemini(prompt, system_prompt, gemini_key, is_json=is_json)
    elif openai_key:
        return ask_openai(prompt, system_prompt, openai_key, is_json=is_json)
    else:
        raise ValueError("لم يتم إدخال مفتاح الذكاء الاصطناعي (Google Gemini أو OpenAI). يرجى إدخال المفتاح للبدء.")

def ask_llm_json(prompt: str, system_prompt: str = "", custom_key: str = None, llm_type: str = None) -> dict:
    """Forces the LLM to return valid JSON using native JSON output mode where supported."""
    json_instructions = "\nهام جداً: يجب أن تكون إجابتك بصيغة JSON صالحة فقط بدون أي شروحات خارج الـ JSON."
    full_prompt = prompt + json_instructions
    response_text = ask_llm(full_prompt, system_prompt=system_prompt, custom_key=custom_key, llm_type=llm_type, is_json=True)
    
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
