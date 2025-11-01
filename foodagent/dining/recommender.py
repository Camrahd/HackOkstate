from collections import Counter
from .models import MenuItem, Tag, EventLog

def popularity_top_n(n=8):
    return list(MenuItem.objects.filter(is_available=True).order_by('-popularity')[:n])

def content_based_from_tags(preferred_tags: list[str], n=8):
    if not preferred_tags:
        return popularity_top_n(n)
    qs = MenuItem.objects.filter(is_available=True, tags__name__in=preferred_tags).distinct()
    items = list(qs.order_by('-popularity')[:n])
    # If not enough, pad with popular
    if len(items) < n:
        pad = [x for x in popularity_top_n(n*2) if x not in items][: (n - len(items))]
        items += pad
    return items

def infer_user_taste(user=None, guest_token:str=''):
    events = EventLog.objects.all()
    if user and user.is_authenticated:
        events = events.filter(user=user)
    elif guest_token:
        events = events.filter(guest_token=guest_token)
    else:
        return []

    tag_counts = Counter()
    for e in events.select_related('menu_item'):
        if e.menu_item:
            tag_counts.update([t.name for t in e.menu_item.tags.all()])
    return [name for (name, _) in tag_counts.most_common(5)]

def blended_recommendations(user=None, guest_token:str='', n=8):
    prefs = infer_user_taste(user, guest_token)
    if prefs:
        return content_based_from_tags(prefs, n)
    return popularity_top_n(n)