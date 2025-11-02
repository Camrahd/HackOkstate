# dining/tavily.py
import os
import requests
from django.conf import settings

TAVILY_URL = "https://api.tavily.com/search"

def tavily_enrich(place_name: str, city: str = ""):
    """
    Returns {"menus": [links...], "highlights": "..."} using Tavily.
    Best-effort; safe to ignore on failure.
    """
    key = getattr(settings, "TAVILY_API_KEY", "")
    if not key:
        return {}

    q = f"{place_name} {city} menu nutrition calories"
    try:
        r = requests.post(TAVILY_URL, json={
            "api_key": key,
            "query": q,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": True
        }, timeout=10)
        j = r.json()
    except Exception:
        return {}

    res = j.get("results", []) or []
    menus = []
    for it in res:
        url = it.get("url","")
        title = (it.get("title") or "")[:80]
        if any(s in url for s in ["menu","nutrit","pdf","eat","order","takeout","doordash","ubereats","grubhub"]):
            menus.append({"title": title, "url": url})
    return {
        "menus": menus[:3],
        "highlights": (j.get("answer") or "")[:400]
    }