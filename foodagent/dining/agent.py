# dining/agent.py
from django.db.models import Q
from .recommender import blended_recommendations, content_based_from_tags
from .models import MenuItem
import re


def parse_message(msg: str):
    msg = msg.lower()
    intents = []
    prefs = {"cuisine": [], "diet": [], "features": [], "price_cap": None, "allergens": []}

    cuisines = {"thai","indian","mexican","italian","japanese","chinese","korean","mediterranean"}
    diets = {"vegan","vegetarian","halal","gluten-free","keto","low-carb","high-protein"}
    features = {"spicy","mild","dessert","salad","bowl","grilled","noodles","soup","burger","pizza","wrap"}
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
    if re.search(r"add\s+#?(\d+)\s*(?:qty\s*(\d+))?", msg):
        intents.append("add_to_cart")
    if "checkout" in msg:
        intents.append("checkout")
    if "show cart" in msg or "view cart" in msg:
        intents.append("show_cart")
    if "remove" in msg:
        intents.append("remove_item")
    if not intents:
        intents.append("discover")

    return intents, prefs

def search_candidates(prefs):
    qs = MenuItem.objects.filter(is_available=True)
    if prefs.get("price_cap"):
        qs = qs.filter(price__lte=prefs["price_cap"])

    names = set([*prefs.get("cuisine", []), *prefs.get("diet", []), *prefs.get("features", [])])
    if names:
        q = Q()
        for n in names:
            q |= Q(tags__name__iexact=n)  # case-insensitive
        qs = qs.filter(q)

    # optional: exclude known allergens if you use tags for them
    for a in prefs.get("allergens", []):
        qs = qs.exclude(tags__name__iexact=a)

    return list(qs.distinct())

def rank(items, prefs):
    # If nothing matched, fall back gracefully
    if not items:
        names = prefs.get("cuisine", []) + prefs.get("diet", []) + prefs.get("features", [])
        if names:
            return content_based_from_tags(names, n=8)  # ignore price cap for fallback
        return blended_recommendations(n=8)

    # If no explicit prefs, just blended
    if not (prefs["cuisine"] or prefs["diet"] or prefs["features"] or prefs["price_cap"]):
        return blended_recommendations(n=8)

    # Otherwise: popularity sort
    return sorted(items, key=lambda x: x.popularity, reverse=True)[:8]

ORDER_WORDS = ("order", "add", "buy", "checkout", "place", "purchase", "get", "i'll take", "i will take")
def is_order_intent(msg: str) -> bool:
    m = msg.lower()
    return any(w in m for w in ORDER_WORDS)