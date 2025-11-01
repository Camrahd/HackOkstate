from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import render
from django.db.models import F
from .models import MenuItem, Cart, CartItem, EventLog
from .serializers import MenuItemSerializer, CartSerializer, CartItemCreateSerializer
from .recommender import blended_recommendations, content_based_from_tags

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

class AgentAPI(APIView):
    """
    Very simple rule-based conversational agent:
    - Extracts tag-like keywords from 'message' (e.g., 'spicy', 'vegan', 'thai')
    - Returns recommended items and suggested next action
    """
    TAG_KEYWORDS = {'vegan','vegetarian','gluten-free','spicy','mild','thai','indian','mexican','dessert','salad','low-carb','halal'}

    def post(self, request):
        msg = (request.data.get('message') or '').lower()
        guest_token = get_guest_token(request)
        prefs = [w for w in self.TAG_KEYWORDS if w in msg]
        items = content_based_from_tags(prefs, n=5) if prefs else blended_recommendations(
            request.user if request.user.is_authenticated else None, guest_token, n=5)
        data = MenuItemSerializer(items, many=True).data
        return Response({
            'detected_prefs': prefs,
            'suggestions': data,
            'hint': "Reply with 'add #ID qty 2' to add, or say more preferences (e.g., 'vegan spicy')."
        })