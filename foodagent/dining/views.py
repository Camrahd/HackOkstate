from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import render
from django.db.models import F
from .agent import parse_message, search_candidates, rank
from .models import MenuItem, Cart, CartItem, EventLog
from .serializers import MenuItemSerializer, CartSerializer, CartItemCreateSerializer
from .recommender import blended_recommendations, content_based_from_tags
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

def get_guest_token(request):
    tok = request.COOKIES.get('guest_token','')
    if not tok:
        import secrets
        tok = secrets.token_hex(16)
    return tok

def landing(request):
    return render(request, 'landing.html')

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