import json
import re
import difflib
import wikipedia
import random
import os
import requests
from datetime import datetime
import traceback

# HuggingFace / torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# -------------------- SAFETY / PERFORMANCE TUNING --------------------
# limit CPU threads to avoid saturating laptop
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
torch.set_num_threads(1)

# HTTP session for connection reuse and global timeout usage
SESSION = requests.Session()
DEFAULT_TIMEOUT = 6  # seconds for requests (small enough to avoid hangs)
SESSION.headers.update({"User-Agent": "AerisAI/1.0 (contact: none)"})

# -------------------- FILE PATHS --------------------
BASE_DIR = os.path.dirname(__file__)
KB_FILE = os.path.join(BASE_DIR, "../database/knowledge.json")
USERS_FILE = os.path.join(BASE_DIR, "../database/users.json")

# Ensure database folder exists
db_dir = os.path.dirname(KB_FILE)
os.makedirs(db_dir, exist_ok=True)

# -------------------- LOAD KNOWLEDGE (SAFE) --------------------
knowledge_base = {}
if os.path.exists(KB_FILE):
    try:
        with open(KB_FILE, "r", encoding="utf-8") as f:
            knowledge_base = json.load(f)
            if not isinstance(knowledge_base, dict):
                print("[WARN] knowledge.json not a dict; ignoring and using empty KB.")
                knowledge_base = {}
    except Exception as e:
        print(f"[WARN] Failed to load KB ({KB_FILE}): {e}")
        knowledge_base = {}
else:
    # create empty KB file to avoid file not found later
    with open(KB_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=2)
    knowledge_base = {}

PREBUILT_RESPONSES = {
    "hello": ["Hey there!", "Hi! How’s it going?", "Hello!"],
    "hi": ["Hi!", "Hey!", "Hello!"],
    "how are you": ["I’m doing great, thanks for asking!", "All systems operational 😎", "Feeling chatty!"],
    "thanks": ["Anytime!", "You got it!", "No problem!"],
    "bye": ["Goodbye!", "See you later!", "Take care!"]
}

# -------------------- LOAD FLAN-T5 (GUARDED) --------------------
MODEL_NAME = "google/flan-t5-base"
tokenizer = None
model = None
MODEL_LOADED = False

print("Attempting to load FLAN-T5 model (this can be heavy)...")
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    MODEL_LOADED = True
    print("FLAN-T5 loaded. Running on", device)
except Exception as e:
    print("[WARN] Failed to load FLAN-T5 model. Falling back to KB/Wikipedia-only behavior.")
    print(f"[DEBUG] Model load error: {e}")
    traceback.print_exc()
    tokenizer = None
    model = None
    device = None

# -------------------- HELPERS --------------------
def safe_json_load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def safe_json_save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save JSON to {path}: {e}")

def normalize_query(query):
    if not query:
        return ""
    return re.sub(r"[^\w\s]", "", query.lower().strip())

def fetch_knowledge(query):
    """
    Try close match in knowledge_base. More robust: check substring fallback
    """
    q = normalize_query(query)
    if not q:
        return None
    entries = {}
    for key, entry in (knowledge_base or {}).items():
        term = normalize_query(entry.get("term", key))
        entries[term] = entry
        for alias in entry.get("aliases", []) if isinstance(entry.get("aliases", []), list) else []:
            entries[normalize_query(alias)] = entry

    # exact/close-match
    matches = difflib.get_close_matches(q, entries.keys(), n=1, cutoff=0.6)
    if matches:
        return entries[matches[0]]
    # substring fallback (useful for short queries)
    for k in entries.keys():
        if q in k:
            return entries[k]
    return None

def fetch_wikipedia_summary(query, sentences=3):
    """
    Search and return short summary. Robust to disambiguation / page errors.
    """
    try:
        results = wikipedia.search(query, results=5)
        if not results:
            return None
        # try each result until a non-empty summary is returned
        for title in results:
            try:
                # limit sentences to keep response short
                s = wikipedia.summary(title, sentences=sentences, auto_suggest=False, redirect=True)
                if s and len(s.strip()) > 20:
                    return s
            except wikipedia.DisambiguationError as e:
                # pick first non-empty option from options if possible (very cautious)
                options = e.options[:3]
                for opt in options:
                    try:
                        s = wikipedia.summary(opt, sentences=sentences, auto_suggest=False, redirect=True)
                        if s and len(s.strip()) > 20:
                            return s
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return None

def safe_request_get(url, params=None, timeout=DEFAULT_TIMEOUT):
    """
    Wrapper for requesting with session, timeout, and safe JSON handling.
    Returns (json_obj or None, text or None)
    """
    try:
        resp = SESSION.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return resp.json(), None
        return None, resp.text
    except Exception as e:
        print(f"[WARN] Request failed: {e}  url={url} params={params}")
        return None, None

def get_user_location(username):
    users = safe_json_load(USERS_FILE, [])
    if not users:
        return None, None
    for user in users:
        if user.get("username") == username:
            return user.get("latitude"), user.get("longitude")
    return None, None

def geocode_city(city_name):
    if not city_name:
        return None, None
    try:
        params = {"q": city_name, "format": "json", "limit": 1}
        url = "https://nominatim.openstreetmap.org/search"
        json_resp, _ = safe_request_get(url, params=params)
        if json_resp and isinstance(json_resp, list) and len(json_resp) > 0:
            return float(json_resp[0]["lat"]), float(json_resp[0]["lon"])
    except Exception:
        pass
    return None, None

def fetch_weather(lat, lon):
    if lat is None or lon is None:
        return "Weather info unavailable (no location)."
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": lat, "longitude": lon, "current_weather": True}
        json_resp, _ = safe_request_get(url, params=params)
        if not json_resp:
            return "Weather info unavailable."
        cw = json_resp.get("current_weather", {}) or {}
        temp = cw.get("temperature")
        wind = cw.get("windspeed")
        if temp is None:
            return "Weather info unavailable."
        comment = "Comfortable." if 20 <= temp <= 28 else "Stay hydrated!" if temp > 30 else "Might need a jacket."
        return f"Weather: {temp}°C, Wind: {wind} km/h — {comment}"
    except Exception:
        return "Weather info unavailable."

def fetch_aqi_uv(lat, lon):
    if lat is None or lon is None:
        return "AQI/UV info unavailable (no location)."
    try:
        url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        params = {"latitude": lat, "longitude": lon, "hourly": "pm2_5,pm10,european_aqi", "current_weather": False}
        json_resp, _ = safe_request_get(url, params=params)
        if not json_resp:
            return "AQI/UV info unavailable."
        hourly = json_resp.get("hourly", {}) or {}
        e_aqi = hourly.get("european_aqi", [])
        if not e_aqi:
            return "AQI/UV info unavailable."
        aqi = round(e_aqi[0]) if isinstance(e_aqi, list) and len(e_aqi) > 0 else None
        uv = json_resp.get("current", {}).get("uv_index", 0) or 0
        uv_desc = "Low" if uv <= 2 else "Moderate" if uv <= 5 else "High" if uv <= 7 else "Very High" if uv <= 10 else "Extreme"
        aqi_category = "Good" if aqi <= 50 else "Moderate" if aqi <= 100 else "Unhealthy" if aqi <= 200 else "Very Unhealthy" if aqi <= 300 else "Hazardous"
        advice = "Enjoy your day!" if aqi <= 50 else "Limit prolonged outdoor exertion." if aqi <= 100 else "Avoid outdoor activities, wear a mask."
        return f"AQI: {aqi} ({aqi_category}) — {advice}\nUV index: {uv} ({uv_desc})"
    except Exception:
        return "AQI/UV info unavailable."

# -------------------- MODEL / LLM WRAPPER (SAFE) --------------------
def ask_flan_t5(prompt):
    """
    Generate with T5. If model not available, return None so caller can fallback.
    """
    if not MODEL_LOADED or model is None or tokenizer is None:
        return None

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                num_beams=4,
                early_stopping=True,
                do_sample=False
            )
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return text
    except RuntimeError as e:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        print(f"[WARN] Model generation failed: {e}")
        return None
    except Exception as e:
        print(f"[WARN] Model generation error: {e}")
        return None

def evaluate_answer(question, answer):
    """
    Returns True if answer seems good. If model unavailable, use a simple heuristic.
    """
    if not answer:
        return False

    if MODEL_LOADED:
        prompt = (
            f"Question: {question}\n"
            f"Answer: {answer}\n"
            f"Evaluate: Is this answer complete, factual, and relevant to the question? Respond only with 'Yes' or 'No'."
        )
        resp = ask_flan_t5(prompt)
        if resp:
            return "yes" in resp.strip().lower()

    q_words = set(normalize_query(question).split())
    a_words = set(normalize_query(answer).split())
    if not q_words:
        return True
    overlap = q_words.intersection(a_words)
    return len(overlap) >= 1 or len(a_words) <= 8

# -------------------- INTENT HELPERS (NEW) --------------------
def is_definition_query(query: str) -> bool:
    """Return True if query looks like a definition/explanation request."""
    if not query:
        return False
    q = query.lower().strip()
    return bool(re.search(r'\b(what is|what\'s|define|definition of|meaning of|explain|how is .* calculated|what does .* mean)\b', q))

def is_live_query(query: str) -> bool:
    """
    Return True if query is likely a live-data request that requires a
    location or 'now/current' wording. More strict than just checking for 'aqi'.
    """
    if not query:
        return False
    q = query.lower()

    # If user explicitly includes "in <city>" treat as live
    if re.search(r'\bin\s+[a-z]{2,}(\s+[a-z]{2,})*\b', q):
        return True

    # explicit live/time keywords
    if any(k in q for k in ("current", "now", "today", "tonight", "this hour", "near me", "nearby")):
        return True

    # explicit pattern for live-data (only treat as live if they include location/time)
    if re.search(r'\baqi in\b', q) or re.search(r'\bweather in\b', q) or re.search(r'\btemperature in\b', q):
        return True

    return False

# -------------------- KNOWLEDGE-FIRST FLOW --------------------
def generate_answer_knowledge_first(query, username=None):
    q_norm = normalize_query(query)
    # prebuilt greetings
    for key in PREBUILT_RESPONSES:
        if key in q_norm:
            return random.choice(PREBUILT_RESPONSES[key])

    # 1) Knowledge base
    kb_entry = fetch_knowledge(query)
    if kb_entry:
        kb_answer = kb_entry.get("definition", "")
        if kb_answer:
            prompt = f"Question: {query}\nKnowledge: {kb_answer}\nAnswer concisely:"
            llm_ans = ask_flan_t5(prompt)
            if llm_ans:
                return llm_ans
            return kb_answer

    # 2) Wikipedia fallback
    wiki_summary = fetch_wikipedia_summary(query, sentences=3)
    if wiki_summary:
        prompt = f"Question: {query}\nWikipedia: {wiki_summary}\nAnswer concisely:"
        llm_ans = ask_flan_t5(prompt)
        if llm_ans and evaluate_answer(query, llm_ans):
            return llm_ans
        q_words = set(normalize_query(query).split())
        summary_words = set(normalize_query(wiki_summary).split())
        if q_words.intersection(summary_words):
            return wiki_summary

    # 3) DuckDuckGo Instant Answer fallback
    try:
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        url = "https://api.duckduckgo.com/"
        json_resp, text_resp = safe_request_get(url, params=params)
        abstract = None
        if json_resp:
            abstract = json_resp.get("AbstractText") or json_resp.get("Definition")
        if abstract:
            prompt = f"Question: {query}\nInfo: {abstract}\nAnswer concisely:"
            llm_ans = ask_flan_t5(prompt)
            if llm_ans and evaluate_answer(query, llm_ans):
                return llm_ans
            q_words = set(normalize_query(query).split())
            abs_words = set(normalize_query(abstract).split())
            if q_words.intersection(abs_words):
                return abstract
    except Exception:
        pass

    # 4) Give up politely
    return "I don't know offhand. Try rephrasing the question or provide more detail — I checked my KB, Wikipedia, and DuckDuckGo."

# -------------------- LIVE DATA HANDLING --------------------
def handle_live_data(query, username=None):
    lat = lon = None
    if username:
        lat, lon = get_user_location(username)
    # check for "in <city>" pattern
    city_match = re.search(r"in ([a-z\s]+)", query.lower())
    if city_match:
        city = city_match.group(1).strip()
        lat2, lon2 = geocode_city(city)
        if lat2 is None:
            return "I couldn't find that city. Please type the city name more exactly."
        lat, lon = lat2, lon2

    if lat is None or lon is None:
        return "Please provide your location first (either set your profile location or include 'in <city>')."

    if "aqi" in query.lower():
        return fetch_aqi_uv(lat, lon)
    if "weather" in query.lower() or "temperature" in query.lower():
        return fetch_weather(lat, lon)

    return "Live-data request not recognized."

# -------------------- PUBLIC ENTRYPOINT (IMPROVED ROUTING) --------------------
def generate_response(query, username=None):
    """
    Routing policy:
     - If query looks like a definition/explain request -> knowledge-first flow
     - Else if query looks like a strict live query (contains 'in <city>' or explicit live/time words) -> live flow
     - Else -> knowledge-first flow
    """
    if not query or not query.strip():
        return "Please ask a question."

    # Prefer explicit definition requests first
    if is_definition_query(query):
        try:
            return generate_answer_knowledge_first(query, username)
        except Exception as e:
            print(f"[ERROR] definition flow failed: {e}")
            return "Sorry, I hit a snag while trying to answer that."

    # Strict live-data detection
    if is_live_query(query):
        try:
            return handle_live_data(query, username)
        except Exception as e:
            print(f"[ERROR] live data flow failed: {e}")
            return "Live data currently unavailable."

    # Default to knowledge-first
    try:
        return generate_answer_knowledge_first(query, username)
    except Exception as e:
        print(f"[ERROR] knowledge-first flow crashed: {e}")
        traceback.print_exc()
        return "Something went wrong while answering. Try again or ask a different question."

# -------------------- CLI (safe) --------------------
if __name__ == "__main__":
    print("Aeris AI (safe mode). Type 'exit' or 'quit' to stop.")
    try:
        username = input("Enter your username (optional): ").strip() or None
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        raise SystemExit(0)

    try:
        while True:
            try:
                q = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break
            if not q:
                continue
            if q.lower() in ("exit", "quit"):
                print("Goodbye!")
                break
            resp = generate_response(q, username=username)
            print("Aeris AI:", resp, "\n")
    except KeyboardInterrupt:
        print("\nExiting. Bye.")
