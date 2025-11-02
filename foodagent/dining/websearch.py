# dining/websearch.py
import os
import requests
from django.conf import settings
from .nlp import parse_intent

# ---------- settings helpers ----------
def _setting(name, default=""):
    return getattr(settings, name, os.getenv(name, default))

# ---------- small geo helpers ----------
def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    import math as m
    p1, p2 = m.radians(lat1), m.radians(lat2)
    dp = p2 - p1
    dl = m.radians(lon2 - lon1)
    a = m.sin(dp/2)**2 + m.cos(p1)*m.cos(p2)*m.sin(dl/2)**2
    return 2 * R * m.asin(m.sqrt(a))

def _google_photo_url(photo_ref, key, maxwidth=400):
    if not photo_ref:
        return ""
    return (
        "https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={maxwidth}&photoreference={photo_ref}&key={key}"
    )

def _maps_place_url(place_id):
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else ""

# ---------- normalizers ----------
def _normalize_google(items, lat, lng, api_key):
    out = []
    for it in items or []:
        loc = (it.get("geometry") or {}).get("location") or {}
        rlat, rlng = loc.get("lat"), loc.get("lng")
        dist = None
        if isinstance(rlat, (int, float)) and isinstance(rlng, (int, float)):
            dist = int(_haversine_m(lat, lng, rlat, rlng))
        photo_ref = (it.get("photos") or [{}])[0].get("photo_reference")
        out.append({
            "name": it.get("name"),
            "rating": it.get("rating"),
            "price_level": it.get("price_level"),
            "address": it.get("formatted_address") or it.get("vicinity") or "",
            "distance_m": dist,
            "maps_url": _maps_place_url(it.get("place_id")),
            "photo_url": _google_photo_url(photo_ref, api_key) if photo_ref else "",
            "highlights": ", ".join((it.get("types") or [])[:3]),
            "menus": [],
        })
    return out

def _normalize_tavily(items):
    out = []
    for it in items or []:
        url = it.get("url") or ""
        title = it.get("title") or (url.split("/")[2] if url else "Result")
        snippet = (it.get("content") or "").strip()
        out.append({
            "name": title,
            "rating": None,
            "price_level": None,
            "address": "",
            "distance_m": None,
            "maps_url": url,
            "photo_url": "",
            "highlights": (snippet[:180] + "…") if len(snippet) > 180 else snippet,
            "menus": [{"title": "Open", "url": url}] if url else [],
        })
    return out

# ---------- providers ----------
def _google_text_search(keyword, lat, lng, radius, open_now, budget, key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    q = keyword
    if "restaurant" not in q.lower():
        q += " restaurant"
    params = {
        "query": q,
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": "restaurant",
        "key": key,
    }
    if open_now:
        params["opennow"] = "true"
    if budget:
        # Google price_level: 0..4; map $..$$$$ to 0..3 or 1..4 depending on region.
        # We'll clamp to 0..4 and center around given budget.
        mn = max(0, budget - 1)
        mx = min(4, budget - 1)
        params["minprice"] = mn
        params["maxprice"] = mx
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    return r.json().get("results", [])

def _tavily_search(keyword, lat, lng, radius, open_now, budget, key):
    payload = {
        "api_key": key,
        "query": f"{keyword} near {lat:.4f},{lng:.4f}",
        "search_depth": "basic",
        "include_answer": False,
        "max_results": 8,
    }
    r = requests.post("https://api.tavily.com/search", json=payload, timeout=12)
    r.raise_for_status()
    return r.json().get("results", [])

# ---------- main entry (now supports dict OR kwargs) ----------
def search_places(payload=None, **kwargs):
    """
    Accepts either:
      search_places({"prompt": "...", "lat": ..., "lng": ..., ...})
    or:
      search_places(prompt="...", lat=..., lng=..., ...)
    Returns: {"results": [], "intent": {...}, "keyword": "...", "error": optional}
    """
    # Merge forms
    if payload is None:
        payload = {}
    if kwargs:
        payload = {**payload, **kwargs}

    prompt = (payload.get("prompt") or "").strip()
    try:
        lat = float(payload.get("lat") if payload.get("lat") is not None else 36.1270)
    except Exception:
        lat = 36.1270
    try:
        lng = float(payload.get("lng") if payload.get("lng") is not None else -97.0737)
    except Exception:
        lng = -97.0737

    open_now = bool(payload.get("open_now") or False)
    budget = payload.get("budget")
    try:
        budget = int(budget) if budget is not None else None
    except Exception:
        budget = None

    radius = payload.get("radius", 2000)
    try:
        radius = int(radius)
    except Exception:
        radius = 2000
    radius = max(250, min(radius, 15000))

    # Intent parsing (Gemini with fallback is handled inside parse_intent)
    intent = parse_intent(prompt)
    keyword = intent.get("keyword") or (prompt or "restaurant")

    g_key = _setting("GOOGLE_PLACES_API_KEY", "")
    t_key = _setting("TAVILY_API_KEY", "")
    provider = (_setting("WEBSEARCH_PROVIDER", "") or "").lower().strip()  # "", "google", "tavily"

    try:
        if (provider == "google" and g_key) or (not provider and g_key):
            gres = _google_text_search(keyword, lat, lng, radius, open_now, budget, g_key)
            out = _normalize_google(gres, lat, lng, g_key)
            out.sort(key=lambda x: (-(x.get("rating") or 0), x.get("distance_m") or 10**9))
            return {"results": out, "intent": intent, "keyword": keyword}
        elif (provider == "tavily" and t_key) or (not provider and t_key):
            tres = _tavily_search(keyword, lat, lng, radius, open_now, budget, t_key)
            out = _normalize_tavily(tres)
            return {"results": out, "intent": intent, "keyword": keyword}
        else:
            return {"results": [], "intent": intent, "keyword": keyword, "error": "no provider configured"}
    except requests.HTTPError as e:
        return {"results": [], "intent": intent, "keyword": keyword, "error": f"provider error: {e}"}
    except Exception:
        return {"results": [], "intent": intent, "keyword": keyword, "error": "search exception"}