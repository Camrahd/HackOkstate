# dining/billing.py
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.conf import settings
import stripe

from .models import Cart, CartItem, Order
from .checkout import _get_or_create_cart  # reuse your helper

stripe.api_key = settings.STRIPE_SECRET_KEY

def _get_customer_id(user):
    # Adjust to your app: user.profile.stripe_customer_id, or user.stripe_customer_id, etc.
    return getattr(getattr(user, "profile", None), "stripe_customer_id", None) or getattr(user, "stripe_customer_id", None)

@require_GET
@login_required
def has_card(request):
    cid = _get_customer_id(request.user)
    if not cid:
        return JsonResponse({"has_card": False})
    try:
        cust = stripe.Customer.retrieve(cid, expand=["invoice_settings.default_payment_method"])
        pm = cust.invoice_settings.default_payment_method
        return JsonResponse({"has_card": bool(pm), "payment_method_id": pm["id"] if pm else None})
    except Exception:
        return JsonResponse({"has_card": False})

@require_POST
@login_required
def pay_now(request):
    """Charge immediately using the user's default saved card (no redirect)."""
    cid = _get_customer_id(request.user)
    if not cid:
        return JsonResponse({"error": "no_customer"}, status=400)

    # Ensure there is a default PM
    cust = stripe.Customer.retrieve(cid, expand=["invoice_settings.default_payment_method"])
    pm = cust.invoice_settings.default_payment_method
    if not pm:
        return JsonResponse({"error": "no_card_on_file"}, status=400)

    cart, _ = _get_or_create_cart(request)
    items = CartItem.objects.filter(cart=cart).select_related("menu_item")
    if not items:
        return JsonResponse({"error": "empty_cart"}, status=400)

    # Build total (same tax as checkout.py if you want parity)
    subtotal = sum((it.qty * it.menu_item.price for it in items), Decimal("0.00"))
    tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
    total = (subtotal + tax).quantize(Decimal("0.01"))
    amount_cents = int((total * 100).quantize(Decimal("1")))

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user, guest_token="", status="pending", total=total
            )
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                customer=cid,
                payment_method=pm["id"],
                confirm=True,
                off_session=True,
                description=f"OSU Dining Order #{order.id}",
                automatic_payment_methods={"enabled": False},
            )
            # If we got here, payment is captured/authorized and no extra action required
            order.payment_ref = intent.id
            order.status = "paid"
            order.save()

            # Clear the cart
            CartItem.objects.filter(cart=cart).delete()

        receipt_url = ""
        try:
            charge = intent.charges.data[0] if intent.charges and intent.charges.data else None
            receipt_url = (charge.get("receipt_url") if charge else "") or ""
        except Exception:
            pass

        return JsonResponse({"ok": True, "order_id": order.id, "receipt_url": receipt_url})

    except stripe.error.CardError as e:
        # Requires authentication or declined: let frontend fall back to Checkout
        return JsonResponse({
            "requires_action": True,
            "message": str(e)
        }, status=400)
    except Exception as e:
        return JsonResponse({"error": "payment_failed", "message": str(e)}, status=400)