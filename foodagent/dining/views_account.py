# views_account.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch

from dining.models import Order, OrderItem


def _guest_token(request):
    return request.COOKIES.get("guest_token") or request.session.get("guest_token")


@login_required
def profile_settings(request):
    user = request.user
    if request.method == "POST":
        user.first_name = request.POST.get("first_name", user.first_name or "")
        user.last_name  = request.POST.get("last_name", user.last_name or "")
        setattr(user, "profile_phone", request.POST.get("phone", getattr(user, "profile_phone", "")))
        user.save()
        messages.success(request, "Profile updated.")
        return redirect("profile_settings")
    return render(request, "account/profile_settings.html", {"user_obj": user})


def order_history(request):
    # Pick source: user vs guest
    if request.user.is_authenticated:
        qs = Order.objects.filter(user=request.user)
    else:
        gt = _guest_token(request)
        qs = Order.objects.filter(guest_token=gt) if gt else Order.objects.none()

    # Prefetch items efficiently
    qs = qs.prefetch_related(
        Prefetch(
            "items",
            queryset=OrderItem.objects
                .select_related("menu_item")
                .only("id", "qty", "price_each", "menu_item__name"),
            to_attr="_prefetched_items",
        )
    ).order_by("-created_at")

    page_obj = Paginator(qs, 10).get_page(request.GET.get("page") or 1)

    orders = []
    for o in page_obj.object_list:
        # Prefer prefetched, but if it's empty, double-check directly (defensive)
        pref = list(getattr(o, "_prefetched_items", []) or [])
        if not pref:
            pref = list(
                OrderItem.objects.filter(order=o)
                .select_related("menu_item")
                .only("qty", "price_each", "menu_item__name")
            )

        items = []
        for it in pref:
            name = getattr(it.menu_item, "name", "")
            if name:
                items.append({
                    "name": name,
                    "qty": it.qty,
                    "price_each": float(it.price_each),
                })

        orders.append({
            "id": o.id,
            "number": f"ORD-{o.id}",
            "status": o.status,
            "total": float(o.total or 0),
            "created": o.created_at,
            "payment_ref": o.payment_ref,
            "items": items,
        })

    return render(request, "orders/order_history.html", {"orders": orders, "page_obj": page_obj})


@login_required
def billing_cards(request):
    cards = [
        {"id": 1, "brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2030, "is_default": True},
        {"id": 2, "brand": "mastercard", "last4": "4444", "exp_month": 9, "exp_year": 2028, "is_default": False},
    ]
    return render(request, "billing/cards.html", {"cards": cards})


def order_receipt(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    allowed = (request.user.is_authenticated and order.user_id == request.user.id) \
              or (order.guest_token and order.guest_token == _guest_token(request))
    if not allowed:
        return render(request, "orders/receipt.html", {"order": None, "not_allowed": True})

    items = OrderItem.objects.filter(order=order).select_related("menu_item").only("qty", "price_each", "menu_item__name")
    return render(request, "orders/receipt.html", {"order": order, "items": items})
