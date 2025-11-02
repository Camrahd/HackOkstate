# dining/agent.py
from django.db.models import Q
from .recommender import blended_recommendations, content_based_from_tags
from .models import MenuItem
import re

# --- Helpers to parse add/remove by ID ---------------------------------------
ADD_VERBS = ("order", "add", "buy", "get", "take", "i'll take", "i will take")
REMOVE_VERBS = ("remove", "delete", "drop")

_PRICE_PHRASE = re.compile(r"(?:under|below|less\s*than|<=?)\s*\$?\s*\d+(?:\.\d{1,2})?", re.I)

def _strip_price_phrases(s: str) -> str:
    # Avoid treating prices as IDs (e.g., "order under $12 ramen")
    return _PRICE_PHRASE.sub("", s)

def extract_add_items(msg: str):
    """
    Returns list of (item_id, qty). Supports:
      "add 23", "order 23 and 45", "buy #12, 19", "get item 7 x2", "add 31 qty 3"
    Ignores price phrases like 'under $12'.
    """
    m = re.search(r"\b(?:" + "|".join(ADD_VERBS) + r")\b(.*)$", msg, re.I)
    if not m:
        return []
    tail = _strip_price_phrases(m.group(1))
    pairs = re.findall(r"#?\b(\d{1,6})\b(?:\s*(?:x|qty)\s*(\d{1,3}))?", tail, flags=re.I)
    out = []
    for iid, q in pairs:
        try:
            out.append((int(iid), int(q) if q else 1))
        except ValueError:
            continue
    # De-dup IDs by summing quantities
    merged = {}
    for iid, q in out:
        merged[iid] = merged.get(iid, 0) + q
    return [(iid, merged[iid]) for iid in merged]

def extract_remove_items(msg: str):
    m = re.search(r"\b(?:" + "|".join(REMOVE_VERBS) + r")\b(.*)$", msg, re.I)
    if not m:
        return []
    tail = m.group(1)
    ids = re.findall(r"#?\b(\d{1,6})\b", tail)
    out = []
    for iid in ids:
        try:
            out.append(int(iid))
        except ValueError:
            continue
    return list(dict.fromkeys(out))  # unique, keep order

def is_order_intent(msg: str) -> bool:
    """Only treat as order if we actually see one or more numeric IDs."""
    return bool(extract_add_items(msg))

# --- Main NLU for discovery/recommendations ----------------------------------
def parse_message(msg: str):
    msg = msg.lower()
    intents = []
    prefs = {"cuisine": [], "diet": [], "features": [], "price_cap": None, "allergens": []}

    cuisines = {"thai","indian","mexican","italian","japanese","chinese","korean","mediterranean"}
    diets = {"vegan","vegetarian","halal","gluten-free","keto","low-carb","high-protein"}
    features = {"spicy","mild","dessert","salad","bowl","grilled","noodles","soup","burger","pizza","wrap","sushi","taco","burrito","sandwich","fries"}
    allergens = {"nuts","peanut","dairy","egg","shellfish","gluten"}

    for w in cuisines:
        if w in msg: prefs["cuisine"].append(w)
    for w in diets:
        if w in msg: prefs["diet"].append(w)
    for w in features:
        if w in msg: prefs["features"].append(w)
    for w in allergens:
        if w in msg: prefs["allergens"].append(w)

    # price like: "under 15", "below $12", "<= 10.99"
    m = re.search(r"(?:under|below|<=?)\s*\$?(\d+(?:\.\d{1,2})?)", msg)
    if m:
        prefs["price_cap"] = float(m.group(1))

    # intents
    if extract_add_items(msg):
        intents.append("add_to_cart")
    if "checkout" in msg:
        intents.append("checkout")
    if "show cart" in msg or "view cart" in msg:
        intents.append("show_cart")
    if extract_remove_items(msg):
        intents.append("remove_item")
    if not intents:
        intents.append("discover")

    return intents, prefs

# --- Candidate search and ranking --------------------------------------------
def search_candidates(prefs):
    qs = MenuItem.objects.filter(is_available=True)
    if prefs.get("price_cap"):
        qs = qs.filter(price__lte=prefs["price_cap"])

    names = set([*prefs.get("cuisine", []), *prefs.get("diet", []), *prefs.get("features", [])])
    if names:
        q = Q()
        for n in names:
            q |= Q(tags__name__iexact=n)  # case-insensitive tag match
        qs = qs.filter(q)

    # exclude allergens if your tags include them
    for a in prefs.get("allergens", []):
        qs = qs.exclude(tags__name__iexact=a)

    return list(qs.distinct())

def rank(items, prefs):
    if not items:
        names = prefs.get("cuisine", []) + prefs.get("diet", []) + prefs.get("features", [])
        if names:
            return content_based_from_tags(names, n=8)  # ignore price cap for fallback
        return blended_recommendations(n=8)

    if not (prefs["cuisine"] or prefs["diet"] or prefs["features"] or prefs["price_cap"]):
        return blended_recommendations(n=8)

    return sorted(items, key=lambda x: getattr(x, "popularity", 0), reverse=True)[:8]