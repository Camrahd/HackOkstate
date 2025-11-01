from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecommendationAPI, MenuAPI, CartAPI, AgentAPI, landing, AgentOrderAPI
from .checkout import cart_page, create_checkout_session, qr_for_url, remove_cart_item, set_cart_qty, checkout_success, checkout_cancel


router = DefaultRouter()
router.register('menu', MenuAPI, basename='menu')

urlpatterns = [
   path('', landing, name='landing'),
    path('cart/', cart_page, name='cart'),
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
]