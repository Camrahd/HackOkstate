# dining/checkout.py
import json
from decimal import Decimal
from typing import Tuple, Optional

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction

import stripe

from .models import Cart, CartItem, Order
from .views import get_guest_token  # helper for guest carts (used by cart page)

stripe.api_key = settings.STRIPE_SECRET_KEY


# -----------------------------
# Custom errors
# -----------------------------
class EmptyCartError(Exception):
    """Raised when the current cart has no items and a checkout was attempted."""


# -----------------------------
# Helpers
# -----------------------------
def _get_or_create_cart(request) -> Tuple[Cart, str]:
    """
    Returns the current user's cart (or a guest cart) and the guest_token ('' if authed).
    """
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart, ''
    guest_token = get_guest_token(request)
    cart, _ = Cart.objects.get_or_create(user=None, guest_token=guest_token)
    return cart, guest_token


def _clear_cart_by_id(cart_id: int) -> None:
    try:
        c = Cart.objects.get(id=cart_id)
        CartItem.objects.filter(cart=c).delete()
    except Cart.DoesNotExist:
        pass


def _clear_current_cart(request) -> None:
    cart, _ = _get_or_create_cart(request)
    CartItem.objects.filter(cart=cart).delete()


def _mark_order_paid(order: Order) -> None:
    order.status = "paid"
    order.save(update_fields=["status"])


def _is_session_paid(sess) -> bool:
    # For mode="payment", Stripe sets payment_status to "paid" when the payment is complete.
    return (getattr(sess, "payment_status", "") == "paid")


# -----------------------------
# Cart page (HTML)
# -----------------------------
@ensure_csrf_cookie
def cart_page(request):
    """
    Render checkout/cart page with current cart contents and totals.
    Works for guests (view only) and logged-in users.
    """
    cart, guest_token = _get_or_create_cart(request)
    items = CartItem.objects.filter(cart=cart).select_related('menu_item')

    subtotal = sum((it.qty * it.menu_item.price for it in items), Decimal('0.00'))
    tax = (subtotal * Decimal('0.08')).quantize(Decimal('0.01'))
    total = (subtotal + tax).quantize(Decimal('0.01'))

    resp = render(request, "dining/checkout.html", {
        "items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "STRIPE_PUBLISHABLE_KEY": getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
    })
    # persist guest cookie if needed
    if guest_token and not request.COOKIES.get("guest_token"):
        resp.set_cookie("guest_token", guest_token, max_age=60*60*24*365)
    return resp


# -----------------------------
# Cart item mutations (AJAX)
# -----------------------------
@require_POST
def set_cart_qty(request, item_id: int):
    """Update quantity for a CartItem by its id (0 -> delete)."""
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


# -----------------------------
# Stripe Checkout creation
# -----------------------------
def _build_line_items(items_qs) -> Tuple[list, Decimal]:
    """
    Convert CartItem queryset to Stripe line_items and compute subtotal.
    """
    currency = "usd"
    line_items = []
    subtotal = Decimal("0.00")

    for it in items_qs:
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
    return line_items, subtotal


def create_checkout_session_for_cart(request, *, fulfillment: str = "pickup") -> Tuple[str, str]:
    """
    Creates a Stripe Checkout Session for the CURRENT (logged-in) user's cart.
    Enforces login. Returns (checkout_url, session_id).
    Raises PermissionError if unauthenticated, EmptyCartError if cart empty.
    """
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        raise RuntimeError("Stripe not configured")

    if not request.user.is_authenticated:
        raise PermissionError("Login required to pay")

    # Only authenticated users can reach here
    cart, _ = _get_or_create_cart(request)
    items = CartItem.objects.filter(cart=cart).select_related("menu_item")
    if not items.exists():
        raise EmptyCartError("Cart is empty")

    line_items, subtotal = _build_line_items(items)

    with transaction.atomic():
        order = Order.objects.create(
            user=request.user,
            guest_token="",
            status="pending",
            total=subtotal,
        )
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],  # Apple Pay / GPay appear automatically where applicable
            line_items=line_items,
            success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=settings.STRIPE_CANCEL_URL,
            metadata={
                "order_id": str(order.id),
                "cart_id": str(cart.id),
                "user_id": str(request.user.id),
                "fulfillment": fulfillment or "pickup",
            },
            client_reference_id=str(cart.id),
            allow_promotion_codes=True,
        )
        order.payment_ref = session.id  # the Checkout Session id
        order.save(update_fields=["payment_ref"])

    return session.url, session.id


@require_POST
def create_checkout_session(request):
    """
    Thin API for FE:
    - Requires login
    - Returns Stripe Checkout URL and session_id
    - If the cart is empty, returns a clear error payload (400) so UI can say: "Add items to the cart"
    Body may include {"fulfillment": "pickup"|"delivery"} if you want to forward it
    """
    try:
        payload = json.loads(request.body or "{}")
        fulfillment = payload.get("fulfillment", "pickup")
        url, sid = create_checkout_session_for_cart(request, fulfillment=fulfillment)
        return JsonResponse({"checkout_url": url, "session_id": sid})
    except PermissionError:
        return JsonResponse({"error": "login_required", "message": "Please sign in to pay."}, status=401)
    except EmptyCartError:
        return JsonResponse({"error": "empty_cart", "message": "Your cart is empty. Add items to continue."}, status=400)
    except ValueError as e:
        return JsonResponse({"error": "bad_request", "message": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": "server_error", "message": str(e)}, status=500)


# -----------------------------
# Success / Cancel pages
# -----------------------------
def checkout_success(request):
    """
    Success URL handler. Verifies the Checkout Session with Stripe.
    If payment_status == 'paid' and order not yet marked, marks as paid and clears the cart once.
    """
    session_id = request.GET.get("session_id")
    order: Optional[Order] = Order.objects.filter(payment_ref=session_id).first() if session_id else None

    sess = None
    if session_id and getattr(settings, "STRIPE_SECRET_KEY", ""):
        try:
            sess = stripe.checkout.Session.retrieve(
                session_id,
                expand=["payment_intent", "line_items"]
            )
        except Exception:
            sess = None

    if sess and _is_session_paid(sess) and order and order.status != "paid":
        cart_id_str = (getattr(sess, "metadata", {}) or {}).get("cart_id", "")
        if cart_id_str and cart_id_str.isdigit():
            _clear_cart_by_id(int(cart_id_str))
        else:
            _clear_current_cart(request)
        _mark_order_paid(order)

    return render(request, "dining/checkout_success.html", {"session_id": session_id, "order": order})


def checkout_cancel(request):
    return render(request, "dining/checkout_cancel.html")


# Optional QR endpoint (disabled)
def qr_for_url(request):
    return HttpResponse("QR disabled", status=404)