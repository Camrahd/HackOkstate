# dining/webhooks.py
import stripe
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Order, Cart, CartItem

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        order_id = sess.get("metadata", {}).get("order_id")
        cart_id  = sess.get("metadata", {}).get("cart_id")

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                if order.status != "paid":
                    order.status = "paid"
                    order.payment_ref = sess.get("id") or order.payment_ref
                    order.save(update_fields=["status", "payment_ref"])
            except Order.DoesNotExist:
                pass

        if cart_id:
            try:
                c = Cart.objects.get(id=cart_id)
                CartItem.objects.filter(cart=c).delete()
            except Cart.DoesNotExist:
                pass

    return HttpResponse(status=200)