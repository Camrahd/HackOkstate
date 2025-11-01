# dining/checkout.py
import json
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
import stripe

from .models import Cart, CartItem, Order
from .views import get_guest_token  # your helper to manage guest carts

stripe.api_key = settings.STRIPE_SECRET_KEY


@require_POST
def set_cart_qty(request, item_id: int):
    """Update quantity for a CartItem by its id."""
    cart, _ = _get_or_create_cart(request)
    try:
        payload = json.loads(request.body or "{}")
        qty = int(payload.get("qty", 1))
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

@require_POST
def remove_cart_item(request, item_id: int):
    """Delete a CartItem row."""
    cart, _ = _get_or_create_cart(request)
    CartItem.objects.filter(cart=cart, id=item_id).delete()
    return JsonResponse({"ok": True})


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
    resp = render(request, "dining/checkout.html", {
        "items": items, "subtotal": subtotal, "tax": tax, "total": total,
        "STRIPE_PUBLISHABLE_KEY": getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
    })
    if guest_token and not request.COOKIES.get("guest_token"):
        resp.set_cookie("guest_token", guest_token, max_age=60*60*24*365)
    return resp


def create_checkout_session_for_cart(request, *, fulfillment="pickup"):
    """
    Return (checkout_url, session_id) for the CURRENT USER'S cart.
    Enforces login. Raises PermissionError if not authenticated.
    """
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        raise RuntimeError("Stripe not configured")

    if not request.user.is_authenticated:
        raise PermissionError("Login required to pay")

    # Only authenticated users can reach here
    cart, _ = _get_or_create_cart(request)
    items = CartItem.objects.filter(cart=cart).select_related("menu_item")
    if not items:
        raise ValueError("Cart is empty")

    currency = "usd"
    line_items = []
    subtotal = Decimal("0.00")

    for it in items:
        unit_amount = int((it.menu_item.price * 100).quantize(Decimal("1")))
        subtotal += it.menu_item.price * it.qty
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

    # Example delivery fee:
    # if fulfillment == "delivery":
    #     line_items.append({
    #         "quantity": 1,
    #         "price_data": {
    #             "currency": currency,
    #             "unit_amount": 350,
    #             "product_data": {"name": "Delivery fee"}
    #         }
    #     })

    with transaction.atomic():
        order = Order.objects.create(
            user=request.user,
            guest_token="",
            status="pending",
            total=subtotal,
        )
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],  # Apple Pay appears automatically
            line_items=line_items,
            success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=settings.STRIPE_CANCEL_URL,
            metadata={"order_id": str(order.id)},
            allow_promotion_codes=True,
        )
        order.payment_ref = session.id
        order.save()

    return session.url, session.id


@require_POST
def create_checkout_session(request):
    """Thin view for FE: requires login and returns Stripe Checkout URL."""
    try:
        url, sid = create_checkout_session_for_cart(request)
        return JsonResponse({"checkout_url": url, "session_id": sid})
    except PermissionError:
        return JsonResponse({"error": "login required"}, status=401)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def checkout_success(request):
    session_id = request.GET.get("session_id")
    order = Order.objects.filter(payment_ref=session_id).first() if session_id else None
    return render(request, "dining/checkout_success.html", {"session_id": session_id, "order": order})


def checkout_cancel(request):
    return render(request, "dining/checkout_cancel.html")


def qr_for_url(request):
    return HttpResponse("QR disabled", status=404)