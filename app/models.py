from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")  # customer | vendor | admin
    is_active_account = db.Column(db.Boolean, default=True)
    is_email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor_profile = db.relationship("VendorProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    orders = db.relationship("Order", backref="customer", lazy="dynamic", cascade="all, delete-orphan")
    cart_items = db.relationship("CartItem", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    wishlist_items = db.relationship("WishlistItem", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    reviews = db.relationship("Review", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    addresses = db.relationship("Address", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    notifications = db.relationship("Notification", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_vendor(self):
        return self.role == "vendor"

    @property
    def is_customer(self):
        return self.role == "customer"

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class VendorProfile(db.Model):
    __tablename__ = "vendor_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    store_name = db.Column(db.String(150), nullable=False)
    store_slug = db.Column(db.String(160), unique=True, nullable=False)
    description = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    logo_filename = db.Column(db.String(255))
    banner_filename = db.Column(db.String(255))
    status = db.Column(db.String(20), default="pending")  # pending | verified | rejected | suspended
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship("Product", backref="vendor", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def is_verified(self):
        return self.status == "verified"


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    icon = db.Column(db.String(50), default="bi-grid")  # bootstrap-icons class name

    products = db.relationship("Product", backref="category", lazy="dynamic")


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor_profiles.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)

    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    description = db.Column(db.Text)
    sku = db.Column(db.String(60))

    price = db.Column(db.Numeric(12, 2), nullable=False)
    compare_at_price = db.Column(db.Numeric(12, 2))
    stock = db.Column(db.Integer, default=0)

    icon = db.Column(db.String(50), default="bi-box-seam")
    status = db.Column(db.String(20), default="active")  # active | draft | archived
    is_flash_sale = db.Column(db.Boolean, default=False)
    flash_sale_ends_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reviews = db.relationship("Review", backref="product", lazy="dynamic", cascade="all, delete-orphan")
    images = db.relationship("ProductImage", backref="product", lazy="dynamic", cascade="all, delete-orphan", order_by="ProductImage.position")
    variants = db.relationship("ProductVariant", backref="product", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def is_flash_sale_active(self):
        if not self.is_flash_sale:
            return False
        if self.flash_sale_ends_at and self.flash_sale_ends_at < datetime.utcnow():
            return False
        return True

    @property
    def total_stock(self):
        """Stock across variants if any exist, else the base stock field."""
        variant_list = self.variants.all()
        if variant_list:
            return sum(v.stock for v in variant_list)
        return self.stock


class ProductImage(db.Model):
    __tablename__ = "product_images"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProductVariant(db.Model):
    __tablename__ = "product_variants"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)  # e.g. "Size" or "Colour"
    value = db.Column(db.String(80), nullable=False)  # e.g. "Large" or "Red"
    sku = db.Column(db.String(60))
    price_override = db.Column(db.Numeric(12, 2))  # null = use product.price
    stock = db.Column(db.Integer, default=0)

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def discount_percent(self):
        if self.compare_at_price and float(self.compare_at_price) > float(self.price):
            return round((1 - float(self.price) / float(self.compare_at_price)) * 100)
        return 0

    @property
    def avg_rating(self):
        ratings = [r.rating for r in self.reviews]
        return round(sum(ratings) / len(ratings), 1) if ratings else 0

    @property
    def review_count(self):
        return self.reviews.count()

    @property
    def stock_label(self):
        if self.stock <= 0:
            return "Out of Stock"
        if self.stock <= 10:
            return "Low Stock"
        return "In Stock"

    @property
    def in_stock(self):
        return self.stock > 0


class CartItem(db.Model):
    __tablename__ = "cart_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"))
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")

    @property
    def unit_price(self):
        return float(self.variant.effective_price) if self.variant else float(self.product.price)

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def available_stock(self):
        return self.variant.stock if self.variant else self.product.stock


class WishlistItem(db.Model):
    __tablename__ = "wishlist_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    full_name = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))

    payment_method = db.Column(db.String(30), default="pay_on_delivery")
    payment_status = db.Column(db.String(20), default="pending")  # pending | paid | failed
    status = db.Column(db.String(20), default="pending")  # pending|processing|shipped|out_for_delivery|delivered|cancelled

    coupon_code = db.Column(db.String(40))
    discount_amount = db.Column(db.Numeric(12, 2), default=0)

    subtotal = db.Column(db.Numeric(12, 2), default=0)
    delivery_fee = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy="dynamic", cascade="all, delete-orphan")

    STATUS_STEPS = ["pending", "processing", "shipped", "out_for_delivery", "delivered"]


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor_profiles.id"), nullable=False)

    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(12, 2), nullable=False)

    product = db.relationship("Product")
    vendor = db.relationship("VendorProfile")

    @property
    def line_total(self):
        return float(self.price) * self.quantity


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Coupon(db.Model):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    discount_percent = db.Column(db.Integer, nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor_profiles.id"))  # null = platform-wide
    active = db.Column(db.Boolean, default=True)
    usage_limit = db.Column(db.Integer)
    times_used = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("VendorProfile")

    @property
    def is_valid(self):
        if not self.active:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.usage_limit and self.times_used >= self.usage_limit:
            return False
        return True


class Address(db.Model):
    __tablename__ = "addresses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    label = db.Column(db.String(50), default="Home")  # Home, Office, etc.
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address_line = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    gateway = db.Column(db.String(30), nullable=False)  # paystack | flutterwave | pay_on_delivery | bank_transfer
    reference = db.Column(db.String(120), unique=True, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending | success | failed
    raw_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)

    order = db.relationship("Order", backref=db.backref("payments", lazy="dynamic", cascade="all, delete-orphan"))


class DeliveryUpdate(db.Model):
    __tablename__ = "delivery_updates"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False)  # pending|processing|shipped|out_for_delivery|delivered|cancelled
    note = db.Column(db.String(255))
    location = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order", backref=db.backref("delivery_updates", lazy="dynamic", cascade="all, delete-orphan", order_by="DeliveryUpdate.created_at"))


class ReturnRequest(db.Model):
    __tablename__ = "return_requests"

    id = db.Column(db.Integer, primary_key=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_items.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    status = db.Column(db.String(20), default="requested")  # requested|approved|rejected|refunded
    refund_amount = db.Column(db.Numeric(12, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    order_item = db.relationship("OrderItem")
    user = db.relationship("User")


class ReviewReply(db.Model):
    __tablename__ = "review_replies"

    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("reviews.id"), nullable=False, unique=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor_profiles.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    review = db.relationship("Review", backref=db.backref("reply", uselist=False, cascade="all, delete-orphan"))
    vendor = db.relationship("VendorProfile")


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor_profiles.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("User")
    vendor = db.relationship("VendorProfile")
    messages = db.relationship("Message", backref="conversation", lazy="dynamic", cascade="all, delete-orphan", order_by="Message.created_at")

    __table_args__ = (db.UniqueConstraint("customer_id", "vendor_id", name="uq_customer_vendor_thread"),)

    @property
    def last_message(self):
        return self.messages.order_by(Message.created_at.desc()).first()


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    sender_role = db.Column(db.String(20), nullable=False)  # customer | vendor
    body = db.Column(db.Text, nullable=False, default="")
    image_filename = db.Column(db.String(255))  # optional attached photo
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.String(255))
    url = db.Column(db.String(255))
    icon = db.Column(db.String(50), default="bi-bell")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

