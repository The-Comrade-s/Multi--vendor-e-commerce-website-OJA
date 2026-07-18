"""
Seed the OJÀ database with sample categories, vendors, and products.
Run once after your database is created:

    python seed.py
"""
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import User, VendorProfile, Category, Product, ProductVariant, Coupon, Address
from app.utils import slugify

app = create_app()

CATEGORIES = [
    ("Electronics", "bi-phone"),
    ("Fashion", "bi-bag-heart"),
    ("Home & Living", "bi-house-heart"),
    ("Beauty", "bi-stars"),
    ("Computers", "bi-laptop"),
    ("Sports", "bi-bicycle"),
    ("Baby & Kids", "bi-balloon"),
    ("Automotive", "bi-car-front"),
]

VENDORS = [
    dict(name="Chuka Eze", email="techhub@oja.ng", store="TechHub Lagos", city="Lagos", state="Lagos"),
    dict(name="Ada Nwosu", email="ada@oja.ng", store="Ada's Fashion House", city="Abuja", state="FCT"),
    dict(name="Musa Bello", email="fitlife@oja.ng", store="FitLife Store", city="Kano", state="Kano"),
    dict(name="Grace Udo", email="littleones@oja.ng", store="LittleOnes NG", city="Port Harcourt", state="Rivers"),
]

PRODUCTS = [
    ("AirPulse X2 Wireless Earbuds", "Electronics", "TechHub Lagos", 24500, 38000, 42, "bi-headphones", True,
     "Active noise cancellation, 30hrs battery life, Bluetooth 5.3, IPX5 water resistant."),
    ("SmartFit Pro Watch Series 5", "Electronics", "TechHub Lagos", 45000, 60000, 30, "bi-smartwatch", True,
     "Heart-rate monitoring, GPS tracking, 7-day battery life."),
    ("14\" UltraBook Pro i7 16GB", "Computers", "TechHub Lagos", 612000, 705000, 6, "bi-laptop", False,
     "Intel Core i7, 16GB RAM, 512GB SSD, full-HD display."),
    ("Ankara Print Wrap Dress", "Fashion", "Ada's Fashion House", 15800, 21000, 25, "bi-bag-heart", True,
     "Handmade Ankara fabric, true-to-size fit, machine washable."),
    ("Men's Leather Sneakers", "Fashion", "Ada's Fashion House", 22500, 30000, 18, "bi-bag-heart", False,
     "Genuine leather upper, cushioned sole, available in 3 colours."),
    ("Adjustable Dumbbell Set 20kg", "Sports", "FitLife Store", 32000, 39000, 15, "bi-bicycle", False,
     "Space-saving adjustable dumbbells, non-slip grip."),
    ("Yoga Mat Premium 6mm", "Sports", "FitLife Store", 8500, 12000, 60, "bi-bicycle", False,
     "Non-slip texture, extra cushioning, carry strap included."),
    ("Baby Convertible Car Seat", "Baby & Kids", "LittleOnes NG", 68000, 82000, 9, "bi-balloon", True,
     "Rear and forward-facing, 5-point harness, machine-washable cover."),
]

ADMIN_EMAIL = "admin@oja.ng"


def run():
    with app.app_context():
        db.create_all()

        # Categories
        cat_map = {}
        for name, icon in CATEGORIES:
            cat = Category.query.filter_by(name=name).first()
            if not cat:
                cat = Category(name=name, slug=slugify(name), icon=icon)
                db.session.add(cat)
                db.session.flush()
            cat_map[name] = cat

        # Admin
        if not User.query.filter_by(email=ADMIN_EMAIL).first():
            admin = User(name="Super Admin", email=ADMIN_EMAIL, role="admin", is_email_verified=True)
            admin.set_password("admin123")
            db.session.add(admin)

        # Customer demo account
        if not User.query.filter_by(email="chidinma@oja.ng").first():
            customer = User(name="Chidinma Okafor", email="chidinma@oja.ng", phone="08034567890", role="customer", is_email_verified=True)
            customer.set_password("customer123")
            db.session.add(customer)

        db.session.commit()

        # Vendors
        vendor_map = {}
        for v in VENDORS:
            user = User.query.filter_by(email=v["email"]).first()
            if not user:
                user = User(name=v["name"], email=v["email"], role="vendor", is_email_verified=True)
                user.set_password("vendor123")
                db.session.add(user)
                db.session.flush()

            profile = VendorProfile.query.filter_by(user_id=user.id).first()
            if not profile:
                profile = VendorProfile(
                    user_id=user.id,
                    store_name=v["store"],
                    store_slug=slugify(v["store"]),
                    city=v["city"],
                    state=v["state"],
                    status="verified",
                )
                db.session.add(profile)
                db.session.flush()
            vendor_map[v["store"]] = profile

        db.session.commit()

        # Products
        product_map = {}
        for name, cat_name, store, price, compare, stock, icon, flash, desc in PRODUCTS:
            existing = Product.query.filter_by(name=name).first()
            if existing:
                product_map[name] = existing
                continue
            slug = slugify(name)
            counter = 1
            base_slug = slug
            while Product.query.filter_by(slug=slug).first():
                counter += 1
                slug = f"{base_slug}-{counter}"

            product = Product(
                vendor_id=vendor_map[store].id,
                category_id=cat_map[cat_name].id,
                name=name,
                slug=slug,
                description=desc,
                price=price,
                compare_at_price=compare,
                stock=stock,
                icon=icon,
                status="active",
                is_flash_sale=flash,
                flash_sale_ends_at=(datetime.utcnow() + timedelta(hours=48)) if flash else None,
            )
            db.session.add(product)
            db.session.flush()
            product_map[name] = product

        db.session.commit()

        # A couple of variant examples (Ankara dress: sizes; sneakers: colours)
        dress = product_map.get("Ankara Print Wrap Dress")
        if dress and not dress.variants.count():
            for size, stock in [("S", 8), ("M", 12), ("L", 5), ("XL", 0)]:
                db.session.add(ProductVariant(product_id=dress.id, name="Size", value=size, stock=stock))

        sneakers = product_map.get("Men's Leather Sneakers")
        if sneakers and not sneakers.variants.count():
            for colour, stock in [("Black", 10), ("Brown", 6), ("Tan", 2)]:
                db.session.add(ProductVariant(product_id=sneakers.id, name="Colour", value=colour, stock=stock))

        db.session.commit()

        # Coupons
        if not Coupon.query.filter_by(code="WELCOME10").first():
            db.session.add(Coupon(code="WELCOME10", discount_percent=10, vendor_id=None, expires_at=datetime.utcnow() + timedelta(days=90)))
        techhub = vendor_map.get("TechHub Lagos")
        if techhub and not Coupon.query.filter_by(code="TECHHUB15").first():
            db.session.add(Coupon(code="TECHHUB15", discount_percent=15, vendor_id=techhub.id, usage_limit=100, expires_at=datetime.utcnow() + timedelta(days=30)))

        # A saved address for the demo customer
        customer_user = User.query.filter_by(email="chidinma@oja.ng").first()
        if customer_user and not Address.query.filter_by(user_id=customer_user.id).first():
            db.session.add(Address(
                user_id=customer_user.id, label="Home", full_name="Chidinma Okafor", phone="08034567890",
                address_line="12 Allen Avenue, Opebi", city="Ikeja", state="Lagos", is_default=True,
            ))

        db.session.commit()
        print("Seed complete.")
        print(f"  Admin login:    {ADMIN_EMAIL} / admin123")
        print("  Vendor login:   techhub@oja.ng / vendor123")
        print("  Customer login: chidinma@oja.ng / customer123")
        print("  Coupons seeded: WELCOME10 (10% platform-wide), TECHHUB15 (15% TechHub Lagos)")


if __name__ == "__main__":
    run()
