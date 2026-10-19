from django.db import migrations

# (name, lucide icon). More can be added any time in the Django admin.
CATEGORIES = [
    ("Agriculture & Farming", "sprout"),
    ("Art & Crafts", "palette"),
    ("Auto & Mechanics", "wrench"),
    ("Bakery & Cakes", "cake"),
    ("Beauty & Cosmetics", "sparkles"),
    ("Books & Stationery", "book-open"),
    ("Cleaning Services", "spray-can"),
    ("Clothing & Fashion", "shirt"),
    ("Construction & Hardware", "hammer"),
    ("Delivery & Logistics", "truck"),
    ("Education & Tutoring", "graduation-cap"),
    ("Electronics & Phones", "smartphone"),
    ("Events & Weddings", "party-popper"),
    ("Fitness & Gym", "dumbbell"),
    ("Food & Restaurants", "utensils"),
    ("Furniture & Home Decor", "sofa"),
    ("Groceries & Supermarkets", "shopping-cart"),
    ("Hair & Barbershop", "scissors"),
    ("Health & Pharmacy", "pill"),
    ("Hotels & Lodging", "bed"),
    ("Jewelry & Accessories", "gem"),
    ("Media & Entertainment", "clapperboard"),
    ("Mobile Money & Finance", "wallet"),
    ("Music & DJ", "music"),
    ("Photography & Video", "camera"),
    ("Real Estate", "house"),
    ("Shoes & Bags", "shopping-bag"),
    ("Tech & IT Services", "laptop"),
    ("Tours & Safari", "mountain"),
    ("Transport & Car Hire", "car"),
    ("Other", "store"),
]


def seed(apps, schema_editor):
    BusinessCategory = apps.get_model("business", "BusinessCategory")
    for name, icon in CATEGORIES:
        BusinessCategory.objects.get_or_create(name=name, defaults={"icon": icon})


class Migration(migrations.Migration):

    dependencies = [
        ("business", "0001_initial"),
    ]

    # Reversing leaves the rows: businesses may already point at them.
    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
