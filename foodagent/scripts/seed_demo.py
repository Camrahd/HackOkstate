# scripts/seed_demo.py
from decimal import Decimal
from dining.models import Restaurant, Tag, MenuItem

def T(kind, name):
    t, _ = Tag.objects.get_or_create(kind=kind, name=name)
    return t

def R(name, slug):
    r, _ = Restaurant.objects.get_or_create(name=name, slug=slug)
    return r

def upsert_item(restaurant, name, price, desc, popularity, tag_tuples, is_available=True):
    mi, created = MenuItem.objects.get_or_create(
        restaurant=restaurant,
        name=name,
        defaults={
            "price": Decimal(str(price)),
            "description": desc,
            "is_available": is_available,
            "popularity": popularity,
        },
    )
    # If it already existed, update mutable fields
    if not created:
        mi.price = Decimal(str(price))
        mi.description = desc
        mi.is_available = is_available
        mi.popularity = popularity
        mi.save()

    tags = [Tag.objects.get_or_create(kind=k, name=n)[0] for (k, n) in tag_tuples]
    mi.tags.set(tags)
    return mi, created

# ---- Restaurants ----
demo   = R("Demo Kitchen", "demo-kitchen")
green  = R("Green Bowl Co.", "green-bowl")
spice  = R("Spice Route", "spice-route")
bella  = R("Bella Pasta", "bella-pasta")
sushi  = R("Sushi Bird", "sushi-bird")

# ---- Ensure core tags exist (cuisine / diet / feature) ----
cuisines = ["thai","indian","mexican","italian","japanese","chinese","korean","mediterranean","american"]
diets = ["vegan","vegetarian","halal","gluten-free","keto","low-carb","high-protein"]
features = ["spicy","mild","dessert","salad","bowl","grilled","noodles","soup","burger","pizza","wrap","seafood","rice","dairy-free","nut-free"]

for c in cuisines: T("cuisine", c)
for d in diets: T("diet", d)
for f in features: T("feature", f)

# ---- Menu Items ----
items = [
    # Demo Kitchen (mixed)
    (demo, "Spicy Vegan Pad Thai", 12.50, "Rice noodles, tofu, chili, peanuts", 90,
        [("cuisine","thai"),("diet","vegan"),("feature","spicy"),("feature","noodles")]),
    (demo, "Chili Miso Ramen", 13.00, "Rich miso broth, chili oil", 80,
        [("cuisine","japanese"),("feature","spicy"),("feature","soup")]),
    (demo, "Margherita Pizza", 11.00, "Tomato, mozzarella, basil", 75,
        [("cuisine","italian"),("diet","vegetarian"),("feature","pizza")]),
    (demo, "Grilled Chicken Bowl", 14.50, "Chicken, brown rice, veggies", 70,
        [("cuisine","american"),("diet","high-protein"),("diet","gluten-free"),("feature","bowl"),("feature","grilled")]),
    (demo, "Mediterranean Falafel Wrap", 10.50, "Falafel, hummus, pickles", 65,
        [("cuisine","mediterranean"),("diet","vegetarian"),("feature","wrap"),("feature","dairy-free")]),
    (demo, "Classic Caesar Salad", 9.50, "Romaine, parmesan, croutons", 50,
        [("cuisine","american"),("feature","salad")]),

    # Green Bowl Co. (healthy)
    (green, "Keto Power Bowl", 14.00, "Steak, greens, avocado", 60,
        [("cuisine","american"),("diet","keto"),("diet","low-carb"),("diet","high-protein"),("diet","gluten-free"),("feature","bowl")]),
    (green, "Quinoa Veggie Bowl", 12.00, "Quinoa, roasted veg, tahini", 55,
        [("diet","vegetarian"),("diet","gluten-free"),("feature","bowl")]),
    (green, "Spicy Tofu Buddha Bowl", 12.75, "Tofu, chili crunch, veggies", 58,
        [("diet","vegan"),("feature","spicy"),("feature","bowl"),("feature","dairy-free")]),
    (green, "Chicken Avocado Salad", 12.25, "Greens, chicken, avocado", 52,
        [("diet","gluten-free"),("diet","high-protein"),("feature","salad")]),
    (green, "Berry Chia Pudding", 6.50, "Almond milk, chia, berries", 35,
        [("diet","vegan"),("feature","dessert"),("feature","dairy-free"),("feature","nut-free")]),

    # Spice Route (Indian/Mex/Mixed)
    (spice, "Butter Chicken", 13.75, "Creamy tomato gravy, rice", 85,
        [("cuisine","indian"),("feature","mild"),("feature","rice")]),
    (spice, "Paneer Tikka Wrap", 11.25, "Marinated paneer, peppers", 62,
        [("cuisine","indian"),("diet","vegetarian"),("feature","wrap")]),
    (spice, "Chana Masala", 10.75, "Chickpeas in spicy sauce", 68,
        [("cuisine","indian"),("diet","vegan"),("feature","spicy"),("feature","rice")]),
    (spice, "Tandoori Chicken", 14.25, "Yogurt-spiced, grilled", 66,
        [("cuisine","indian"),("feature","grilled"),("diet","high-protein"),("feature","spicy")]),
    (spice, "Lamb Biryani", 15.00, "Fragrant rice, spices", 64,
        [("cuisine","indian"),("feature","spicy"),("feature","rice")]),
    (spice, "Chicken Tacos", 9.75, "Soft tortillas, salsa", 60,
        [("cuisine","mexican"),("feature","wrap"),("feature","mild")]),
    (spice, "Veggie Quesadilla", 9.25, "Cheese, peppers, onions", 48,
        [("cuisine","mexican"),("diet","vegetarian")]),
    (spice, "Chipotle Bowl", 11.95, "Chicken, beans, chipotle", 72,
        [("cuisine","mexican"),("feature","spicy"),("feature","bowl"),("diet","high-protein")]),

    # Bella Pasta (Italian)
    (bella, "Fettuccine Alfredo", 12.50, "Creamy parmesan sauce", 74,
        [("cuisine","italian"),("diet","vegetarian")]),
    (bella, "Penne al Pesto", 12.25, "Basil pesto, parmesan", 63,
        [("cuisine","italian"),("diet","vegetarian")]),
    (bella, "Spicy Arrabbiata", 11.50, "Tomato chili sauce", 59,
        [("cuisine","italian"),("feature","spicy"),("feature","noodles")]),
    (bella, "Gluten-Free Lasagna", 13.95, "Layered veggies, ricotta", 57,
        [("cuisine","italian"),("diet","gluten-free"),("diet","vegetarian")]),

    # Sushi Bird (Japanese)
    (sushi, "Salmon Nigiri Set", 16.50, "8 pcs nigiri, wasabi", 77,
        [("cuisine","japanese"),("feature","seafood"),("diet","high-protein"),("diet","gluten-free"),("feature","rice")]),
    (sushi, "Spicy Tuna Roll", 12.25, "Tuna, chili mayo", 73,
        [("cuisine","japanese"),("feature","seafood"),("feature","spicy"),("feature","rice")]),
    (sushi, "Veggie Uramaki", 10.95, "Avocado, cucumber, carrot", 61,
        [("cuisine","japanese"),("diet","vegetarian"),("feature","dairy-free")]),
    (sushi, "Miso Soup", 3.95, "Classic comfort broth", 40,
        [("cuisine","japanese"),("feature","soup"),("diet","vegetarian")]),
]

created_count = 0
for args in items:
    _, created = upsert_item(*args)
    created_count += 1 if created else 0

print(f"Seed complete. Items created: {created_count}, total MenuItem: {MenuItem.objects.count()}")