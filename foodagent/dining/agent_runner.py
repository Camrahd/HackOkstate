# dining/agent_runner.py
from typing import Dict, Any, List
from django.urls import reverse
from urllib.parse import urlencode

from .models import MenuItem, Cart, CartItem
from .agent import parse_message, search_candidates, rank, is_order_intent
from .checkout import create_checkout_session_for_cart

def _get_or_create_cart_for_request(request):
    # if you already have a helper, you can reuse it; this is inline to avoid circular imports
    from .views import get_guest_token
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, guest_token="")
    else:
        tok = get_guest_token(request)
        cart, _ = Cart.objects.get_or_create(user=None, guest_token=tok)
    return cart

def _add_items(cart, items: List[MenuItem], qty:int=1):
    added = []
    for m in items:
        ci, created = CartItem.objects.get_or_create(cart=cart, menu_item=m, defaults={"qty": qty})
        if not created:
            ci.qty += qty
            ci.save()
        added.append(m)
    return added

def run_order_agent(request, message: str) -> Dict[str, Any]:
    intents, prefs = parse_message(message)
    candidates = search_candidates(prefs)
    picks = rank(candidates, prefs)  # list[MenuItem]

    # If we have no picks yet, fallback (popularity blend)
    if not picks:
        from .recommender import blended_recommendations
        picks = blended_recommendations(user=request.user if request.user.is_authenticated else None, n=5)

    # --- Suggest mode (no order words) ---
    if not is_order_intent(message):
        # Return top suggestions only
        from .serializers import MenuItemSerializer
        data = MenuItemSerializer(picks[:6], many=True).data
        return {
            "detected_prefs": prefs,
            "suggestions": data,
            "follow_up": "Say 'order the first two' or 'order the spicy noodles' to add to cart."
        }

    # --- Order mode ---
    cart = _get_or_create_cart_for_request(request)

    # simple: add top 1–2 items (you can improve by parsing quantities/indices)
    to_add = picks[:2] if len(picks) >= 2 else picks[:1]
    _add_items(cart, to_add, qty=1)

    from .serializers import MenuItemSerializer
    added_data = MenuItemSerializer(to_add, many=True).data

    # If not logged in: do NOT create Checkout; ask to sign in
    if not request.user.is_authenticated:
        login_url  = reverse("account_login") + "?" + urlencode({"next": "/cart/"})
        google_url = "/accounts/google/login/?" + urlencode({"process": "login", "next": "/cart/"})
        return {
            "added": added_data,
            "follow_up": "I’ve added items to your cart. Please sign in to continue to payment.",
            "require_login": True,
            "login_url": login_url,
            "google_login_url": google_url,
        }

    # Logged in: create Stripe Checkout session and return url
    try:
        checkout_url, sid = create_checkout_session_for_cart(request, fulfillment="pickup")
        return {
            "added": added_data,
            "follow_up": "Great choice! Opening checkout…",
            "checkout_url": checkout_url,
            "session_id": sid,
        }
    except Exception as e:
        # Don’t break the chat flow if Stripe fails
        return {
            "added": added_data,
            "error": str(e),
            "follow_up": "Items added. You can review and pay from your cart."
        }