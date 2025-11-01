# dining/checkout.py
import json, io, qrcode, stripe
from decimal import Decimal
from urllib.parse import unquote
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.db import transaction
from .models import Cart, CartItem, Order
from .views import get_guest_token

stripe.api_key = settings.STRIPE_SECRET_KEY

def _get_or_create_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart, ''
    guest_token = get_guest_token(request)
    cart, _ = Cart.objects.get_or_create(user=None, guest_token=guest_token)
    return cart, guest_token

@ensure_csrf_cookie
def cart_page(request):
    cart, guest_token = _get_or_create_cart(request)
    items = CartItem.objects.filter(cart=cart).select_related('menu_item')
    subtotal = sum((it.qty * it.menu_item.price for it in items), Decimal('0.00'))
    tax = (subtotal * Decimal('0.08')).quantize(Decimal('0.01'))
    total = (subtotal + tax).quantize(Decimal('0.01'))
    resp = render(request, 'dining/checkout.html', {
        'items': items, 'subtotal': subtotal, 'tax': tax, 'total': total,
        'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY
    })
    if guest_token and not request.COOKIES.get('guest_token'):
        resp.set_cookie('guest_token', guest_token, max_age=60*60*24*365)
    return resp

@require_POST
def remove_cart_item(request, item_id: int):
    cart, _ = _get_or_create_cart(request)
    CartItem.objects.filter(cart=cart, id=item_id).delete()
    return JsonResponse({"ok": True})

@require_POST
def set_cart_qty(request, item_id: int):
    cart, _ = _get_or_create_cart(request)
    try:
        payload = json.loads(request.body or '{}')
        qty = int(payload.get('qty', 1))
    except Exception:
        return HttpResponseBadRequest("bad qty")
    try:
        it = CartItem.objects.get(cart=cart, id=item_id)
    except CartItem.DoesNotExist:
        return HttpResponseBadRequest("not found")
    if qty <= 0:
        it.delete()
        return JsonResponse({"ok": True, "deleted": True})
    it.qty = qty
    it.save()
    return JsonResponse({"ok": True, "qty": it.qty})

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Cart, CartItem, Order

@require_POST
def create_checkout_session(request):
    # 1) Guard: Stripe configured?
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        return JsonResponse({"error": "Stripe not configured. Set STRIPE_SECRET_KEY in settings/.env"}, status=500)

    cart, guest_token = _get_or_create_cart(request)
    items = CartItem.objects.filter(cart=cart).select_related('menu_item')
    if not items:
        return HttpResponseBadRequest("Cart is empty")

    # 2) Parse payload safely
    try:
        payload = json.loads(request.body or "{}")
    except Exception:
        payload = {}
    fulfillment = payload.get("fulfillment", "pickup")
    address = payload.get("address") or {}
    notes = (payload.get("notes") or "")[:200]

    if fulfillment == "delivery":
        required = ["name","phone","line1","city","state","postal_code"]
        if any(not address.get(k) for k in required):
            return HttpResponseBadRequest("Missing delivery address")

    # 3) Build line items
    currency = "usd"
    line_items = []
    from decimal import Decimal
    amount_total = Decimal("0.00")
    for it in items:
        unit_amount = int((it.menu_item.price * 100).quantize(Decimal("1")))
        amount_total += it.menu_item.price * it.qty
        line_items.append({
            "quantity": it.qty,
            "price_data": {
                "currency": currency,
                "unit_amount": unit_amount,
                "product_data": {
                    "name": it.menu_item.name,
                    "description": (it.menu_item.description or "")[:200],
                }
            }
        })

    # Optional delivery fee
    delivery_fee = Decimal("3.50") if fulfillment == "delivery" else Decimal("0.00")
    if delivery_fee > 0:
        line_items.append({
            "quantity": 1,
            "price_data": {
                "currency": currency,
                "unit_amount": int(delivery_fee * 100),
                "product_data": {"name": "Delivery fee"}
            }
        })
        amount_total += delivery_fee

    # 4) Create Order + Stripe session with robust error handling
    import traceback
    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                guest_token="" if request.user.is_authenticated else guest_token,
                status="pending",
                total=amount_total,
            )
            meta = {
                "order_id": str(order.id),
                "fulfillment": fulfillment,
                "name": address.get("name",""),
                "phone": address.get("phone",""),
                "addr_line1": address.get("line1",""),
                "addr_line2": address.get("line2",""),
                "city": address.get("city",""),
                "state": address.get("state",""),
                "postal_code": address.get("postal_code",""),
                "notes": notes,
            }

            stripe.api_key = settings.STRIPE_SECRET_KEY
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],   # Apple Pay appears automatically in Checkout
                line_items=line_items,
                success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=settings.STRIPE_CANCEL_URL,
                metadata=meta,
                allow_promotion_codes=True,
            )
            order.payment_ref = session.id
            order.save()
        return JsonResponse({"checkout_url": session.url, "session_id": session.id})
    except stripe.error.AuthenticationError:
        # Most common: missing/invalid STRIPE_SECRET_KEY
        return JsonResponse({"error": "Stripe authentication failed. Check STRIPE_SECRET_KEY."}, status=500)
    except Exception as e:
        print("Stripe session error:\n", traceback.format_exc())
        return JsonResponse({"error": f"Checkout error: {e}"}, status=500)

def qr_for_url(request):
    data = request.GET.get('u')
    if not data:
        return HttpResponseBadRequest("missing u")
    img = qrcode.make(unquote(data))
    buf = io.BytesIO(); img.save(buf, format='PNG')
    return HttpResponse(buf.getvalue(), content_type='image/png')