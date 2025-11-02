from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecommendationAPI, MenuAPI, CartAPI, AgentAPI, landing, AgentOrderAPI
from .checkout import cart_page, create_checkout_session, qr_for_url, remove_cart_item, set_cart_qty, checkout_success, checkout_cancel
from . import billing, views
from .webhooks import stripe_webhook
from . import views_account
# urls.py
from django.urls import path
from .views_account import profile_settings, order_history, billing_cards
router = DefaultRouter()
router.register('menu', MenuAPI, basename='menu')

urlpatterns = [
   path('', landing, name='landing'),
    path('cart/', cart_page, name='cart'),
    path('agent/', views.agent_page, name='agent'),
    path('api/cart/item/<int:item_id>/delete/', remove_cart_item, name='cart_item_delete'),
    path('api/cart/item/<int:item_id>/set-qty/', set_cart_qty, name='cart_item_set_qty'),
    path('api/create-checkout-session/', create_checkout_session, name='create_checkout_session'),
    path('qr/', qr_for_url, name='qr_for_url'),
    path("checkout/success/", checkout_success, name="checkout_success"),
    path("checkout/cancel/", checkout_cancel, name="checkout_cancel"),

    path('api/recommendations/', RecommendationAPI.as_view()),
    path('api/cart/', CartAPI.as_view()),
    path('api/agent/', AgentAPI.as_view(), name='agent'),
    path('api/', include(router.urls)),
    path("api/agent/order/", AgentOrderAPI.as_view(), name="agent_order"),
    path("account/profile/", views_account.profile_settings, name="profile_settings"),
    path("orders/history/", views_account.order_history, name="order_history"),
    path("billing/cards/", views_account.billing_cards, name="billing_cards"),
    path("orders/<int:order_id>/receipt/", views_account.order_receipt, name="order_receipt"),  # optional

    path("account/profile/", profile_settings, name="profile_settings"),
    path("orders/history/", order_history, name="order_history"),
    path("billing/cards/", billing_cards, name="billing_cards"),

   
    # ... your other api routes ...
    path("api/billing/has-card/", billing.has_card, name="billing-has-card"),
    path("api/pay-now/",           billing.pay_now,  name="billing-pay-now"),
    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),

]