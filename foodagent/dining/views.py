from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import render
from django.db.models import F

from .websearch import search_places
from .agent import parse_message, search_candidates, rank
from .models import MenuItem, Cart, CartItem, EventLog
from .serializers import MenuItemSerializer, CartSerializer, CartItemCreateSerializer
from .recommender import blended_recommendations, content_based_from_tags
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie


def get_guest_token(request):
    tok = request.COOKIES.get('guest_token','')
    if not tok:
        import secrets
        tok = secrets.token_hex(16)
    return tok
@ensure_csrf_cookie
def landing(request):
    return render(request, 'landing.html')


@ensure_csrf_cookie
def agent_page(request):
    return render(request, 'agent.html')

@ensure_csrf_cookie
def websearch_page(request):
    return render(request, "websearch.html")

class RecommendationAPI(APIView):
    def get(self, request):
        guest_token = get_guest_token(request)
        items = blended_recommendations(request.user if request.user.is_authenticated else None,
                                        guest_token=guest_token, n=8)
        data = MenuItemSerializer(items, many=True).data
        resp = Response({'results': data})
        resp.set_cookie('guest_token', guest_token, max_age=60*60*24*365)
        return resp

class MenuAPI(viewsets.ReadOnlyModelViewSet):
    queryset = MenuItem.objects.filter(is_available=True).select_related('restaurant').prefetch_related('tags')
    serializer_class = MenuItemSerializer

class CartAPI(APIView):
    def get(self, request):
        guest_token = get_guest_token(request)
        cart, _ = Cart.objects.get_or_create(user=request.user if request.user.is_authenticated else None,
                                             guest_token='' if request.user.is_authenticated else guest_token)
        resp = Response(CartSerializer(cart).data)
        resp.set_cookie('guest_token', guest_token, max_age=60*60*24*365)
        return resp

    def post(self, request):
        guest_token = get_guest_token(request)
        cart, _ = Cart.objects.get_or_create(user=request.user if request.user.is_authenticated else None,
                                             guest_token='' if request.user.is_authenticated else guest_token)
        ser = CartItemCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        mi = ser.validated_data['menu_item']
        qty = ser.validated_data['qty']
        item, created = CartItem.objects.get_or_create(cart=cart, menu_item=mi, defaults={'qty': qty})
        if not created:
            item.qty = F('qty') + qty
            item.save()
        EventLog.objects.create(user=request.user if request.user.is_authenticated else None,
                                guest_token='' if request.user.is_authenticated else guest_token,
                                menu_item=mi, event_type='add')
        return Response({'ok': True}, status=201)


@method_decorator(csrf_exempt, name="dispatch")
class AgentAPI(APIView):
    def post(self, request):
        msg = (request.data.get("message") or "").strip()
        intents, prefs = parse_message(msg)

        # discovery/refine
        items = search_candidates(prefs)
        items = rank(items, prefs) or blended_recommendations(n=8)
        data = MenuItemSerializer(items, many=True).data

        follow_up = "Want to add one to your cart or refine (e.g., less spicy, under $12)?"
        return Response({"detected_prefs": prefs, "suggestions": data, "follow_up": follow_up})
    
from rest_framework.views import APIView
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .agent_runner import run_order_agent


def add_items(cart, items, default_qty=1):
    added = []
    for x in items:
        ci, created = CartItem.objects.get_or_create(cart=cart, menu_item=x, defaults={"qty": default_qty})
        if not created:
            ci.qty += default_qty
            ci.save()
        added.append(x)
    return added

from .checkout import create_checkout_session_for_cart
from django.urls import reverse
from urllib.parse import urlencode

@method_decorator(csrf_exempt, name="dispatch")  # keep for dev; remove in prod when CSRF wired
class AgentOrderAPI(APIView):
    def post(self, request):
        msg = (request.data.get("message") or "").strip()
        if not msg:
            return Response({"error":"message required"}, status=400)

        # Your agent decides items AND/OR we fallback to recommender inside run_order_agent
        out = run_order_agent(request, msg)  # should add items to cart internally or return which to add

        # If not logged in: DO NOT create Stripe session; guide to login
        if not request.user.is_authenticated:
            login_url  = reverse("account_login") + "?" + urlencode({"next": "/cart/"})
            google_url = "/accounts/google/login/?" + urlencode({"process": "login", "next": "/cart/"})
            out.update({
                "follow_up": out.get("follow_up") or "I added items to your cart. Please sign in to continue to payment.",
                "require_login": True,
                "login_url": login_url,
                "google_login_url": google_url,
            })
            return Response(out, status=401)

        # Logged in: prepare checkout now
        try:
            checkout_url, sid = create_checkout_session_for_cart(request, fulfillment="pickup")
            out.update({"checkout_url": checkout_url, "session_id": sid})
        except Exception as e:
            # Don’t break the chat; cart is updated already, user can pay from cart
            out.update({"error": str(e)})

        return Response(out)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .websearch import search_places

class WebSearchAPI(APIView):
    permission_classes = [AllowAny]  # allow anonymous discovery

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        prompt = (data.get("prompt") or "").strip()

        # required lat/lng
        try:
            lat = float(data.get("lat"))
            lng = float(data.get("lng"))
        except (TypeError, ValueError):
            return Response({"error": "lat and lng are required floats"}, status=400)

        # optional filters
        radius = int(data.get("radius") or 2000)
        budget = data.get("budget")
        try:
            budget = int(budget) if str(budget).strip() != "" and budget is not None else None
        except (TypeError, ValueError):
            budget = None

        open_now = bool(data.get("open_now")) if "open_now" in data else None
        healthy  = bool(data.get("healthy"))  if "healthy"  in data else None

        # call your search helper
        from .websearch import search_places

        try:
            # Preferred signature: (query, lat, lng, radius=..., open_now=..., budget=..., healthy=...)
            results = search_places(
    prompt=prompt,
    lat=lat,
    lng=lng,
    open_now=open_now,
    budget=budget,
    radius=radius,
)
        except TypeError:
            # If your local function is older and doesn’t accept healthy
            results = search_places(prompt, lat, lng,
                                    radius=radius, open_now=open_now,
                                    budget=budget)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

        return Response(results)