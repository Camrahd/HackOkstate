# dining/admin.py
from django.contrib import admin
from .models import Restaurant, Tag, MenuItem, Cart, CartItem, Order, OrderItem, EventLog
admin.site.register(Restaurant)
admin.site.register(Tag)
admin.site.register(MenuItem)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(EventLog)