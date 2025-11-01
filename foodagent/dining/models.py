from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Restaurant(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

class Tag(models.Model):
    KIND_CHOICES = [
        ('cuisine', 'Cuisine'), ('diet', 'Diet'), ('feature', 'Feature')
    ]
    name = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)

    def __str__(self):
        return f'{self.kind}:{self.name}'

class MenuItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    name = models.CharField(max_length=140)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    is_available = models.BooleanField(default=True)
    popularity = models.PositiveIntegerField(default=0)  # quick signal

    def __str__(self):
        return self.name

class Cart(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    guest_token = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    qty = models.PositiveIntegerField(default=1)

class Order(models.Model):
    STATUS = [('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('canceled', 'Canceled')]
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    guest_token = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS, default='pending')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_ref = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    qty = models.PositiveIntegerField()
    price_each = models.DecimalField(max_digits=8, decimal_places=2)

class EventLog(models.Model):
    EVENT = [('view','view'), ('click','click'), ('add','add_to_cart'), ('buy','purchase')]
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    guest_token = models.CharField(max_length=64, blank=True, db_index=True)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    event_type = models.CharField(max_length=16, choices=EVENT)
    ts = models.DateTimeField(auto_now_add=True)