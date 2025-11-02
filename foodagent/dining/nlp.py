# dining/nlp.py
import os, re, json

# Optional Django settings (works even if Django not loaded in early scripts)
try:
    from django.conf import settings
    _HAS_DJANGO = True
except Exception:
    _HAS_DJANGO = False

# ---------- Local rule-based intent (fallback) ----------
CUISINE_WORDS = [
    "thai","mexican","indian","japanese","korean","chinese","italian","pizza",
    "ramen","sushi","mediterranean","greek","vietnamese","bbq","burger","vegan",
    "vegetarian","salad","tacos","noodles","pho","halal","dessert","sandwich",
    "seafood","breakfast",
]

def parse_intent_rules(prompt: str):
    p = (prompt or "").lower().strip()
    healthy = bool(re.search(r"\b(healthy|light|low[- ]cal|keto|low[- ]carb|salad)\b", p))
    mood = None
    for m in ["comfort","spicy","cozy","quick","date","study","quiet","trendy"]:
        if re.search(rf"\b{re.escape(m)}\b", p):
            mood = m
            break
    cuisines = [w for w in CUISINE_WORDS if re.search(rf"\b{re.escape(w)}\b", p)]
    m = re.search(r"(\${1,4})", p)
    budget = len(m.group(1)) if m else None

    parts = []
    if healthy: parts.append("healthy")
    parts.extend(cuisines or [])
    if not cuisines:
        parts.append("restaurant")
    if "open now" in p or "open" in p:
        parts.append("open now")
    keyword = " ".join(parts) if parts else (p or "restaurant")
    return {"healthy": healthy, "mood": mood, "cuisines": cuisines, "budget": budget, "keyword": keyword}


# ---------- Gemini (optional) ----------
def _get_setting(name, default=""):
    if _HAS_DJANGO and hasattr(settings, name):
        return getattr(settings, name, default)
    return os.getenv(name, default)

_GEMINI_API_KEY = _get_setting("GEMINI_API_KEY", "")
_GEMINI_MODEL   = _get_setting("GEMINI_MODEL_NAME", "gemini-1.5-flash")  # safe default

try:
    import google.generativeai as genai
    _GENAI_OK = True
except Exception:
    _GENAI_OK = False

def parse_intent_with_gemini(prompt: str):
    """
    Best effort: returns a dict. Falls back to rules if anything goes wrong.
    """
    base = parse_intent_rules(prompt)

    if not _GENAI_OK or not _GEMINI_API_KEY:
        return base

    try:
        genai.configure(api_key=_GEMINI_API_KEY)

        # Force JSON out (requires google-generativeai >= 0.7.x)
        model = genai.GenerativeModel(
            _GEMINI_MODEL,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        )

        sys = (
            "Extract user dining intent as strict JSON with keys:\n"
            "{healthy: boolean, mood: string|null, cuisines: string[], budget: integer|null, keyword: string}.\n"
            "budget is number of $ (1..4) if present, else null. Only output JSON."
        )
        resp = model.generate_content([sys, prompt], request_options={"timeout": 10})

        raw = getattr(resp, "text", "") or ""
        # Some older client versions wrap JSON in code fences — strip safely:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            i = raw.find("{")
            j = raw.rfind("}")
            if i >= 0 and j >= 0:
                raw = raw[i:j+1]

        data = json.loads(raw or "{}")
        # Merge with base so we always have all fields
        out = {
            "healthy": bool(data.get("healthy", base["healthy"])),
            "mood": (data.get("mood") if data.get("mood") not in ("", "null", None) else base["mood"]),
            "cuisines": data.get("cuisines") or base["cuisines"],
            "budget": (int(data["budget"]) if str(data.get("budget","")).isdigit() else base["budget"]),
            "keyword": data.get("keyword") or base["keyword"],
        }
        return out
    except Exception:
        # Any Gemini issue -> safe fallback
        return base


def parse_intent(prompt: str):
    """Public entry: try Gemini then fallback to rules."""
    return parse_intent_with_gemini(prompt)