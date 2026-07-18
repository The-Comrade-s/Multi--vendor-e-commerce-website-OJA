from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import (
    Product, Category, OrderItem, Order, ProductVariant, ProductImage, Coupon,
    Review, ReviewReply, ReturnRequest, DeliveryUpdate,
)
from app.utils import slugify
from app.services.uploads import save_upload
from app.services.notifications import notify
from app.api.decorators import get_current_api_user, api_role_required, error_response
from app.api.serializers import (
    serialize_product_card, serialize_product_detail, serialize_order_summary,
    serialize_order_detail, serialize_review, serialize_vendor_full,
)

vendor_api_bp = Blueprint("vendor_api", __name__, url_prefix="/vendor")


def _vendor_or_403(user):
    profile = user.vendor_profile
    if not profile:
        return None
    return profile


@vendor_api_bp.route("/dashboard", methods=["GET"])
@api_role_required("vendor")
def dashboard():
    user = get_current_api_user()
    profile = _vendor_or_403(user)
    if not profile:
        return error_response("No store profile found.", 404)

    order_items = OrderItem.query.filter_by(vendor_id=profile.id).all()
    total_sales = sum(oi.line_total for oi in order_items)
    order_count = len({oi.order_id for oi in order_items})
    pending_returns = (
        ReturnRequest.query.join(OrderItem)
        .filter(OrderItem.vendor_id == profile.id, ReturnRequest.status == "requested")
        .count()
    )

    return jsonify({
        "store": serialize_vendor_full(profile),
        "total_sales": total_sales,
        "order_count": order_count,
        "product_count": profile.products.count(),
        "pending_returns": pending_returns,
        "low_stock": [serialize_product_card(p) for p in profile.products.filter(Product.stock <= 10, Product.stock > 0).limit(10)],
    })


@vendor_api_bp.route("/products", methods=["GET"])
@api_role_required("vendor")
def list_products():
    profile = _vendor_or_403(get_current_api_user())
    products = profile.products.order_by(Product.created_at.desc()).all()
    return jsonify([serialize_product_detail(p) for p in products])


@vendor_api_bp.route("/products", methods=["POST"])
@api_role_required("vendor")
def add_product():
    user = get_current_api_user()
    profile = _vendor_or_403(user)
    if not profile:
        return error_response("No store profile found.", 404)
    if profile.status != "verified":
        return error_response("Your store is still awaiting admin verification.", 403)

    # Supports multipart/form-data (with image files) or plain JSON (no images).
    is_multipart = request.content_type and "multipart/form-data" in request.content_type
    data = request.form if is_multipart else (request.get_json(silent=True) or {})

    name = (data.get("name") or "").strip()
    category_id = data.get("category_id", type=int) if is_multipart else data.get("category_id")
    price = data.get("price", type=float) if is_multipart else data.get("price")

    if not name or not category_id or not price:
        return error_response("name, category_id, and price are required.")

    base_slug = slugify(name)
    slug, counter = base_slug, 1
    while Product.query.filter_by(slug=slug).first():
        counter += 1
        slug = f"{base_slug}-{counter}"

    stock_raw = data.get("stock", type=int) if is_multipart else data.get("stock")
    product = Product(
        vendor_id=profile.id,
        category_id=int(category_id),
        name=name,
        slug=slug,
        description=(data.get("description") or "").strip(),
        sku=(data.get("sku") or "").strip(),
        price=float(price),
        compare_at_price=(data.get("compare_at_price", type=float) if is_multipart else data.get("compare_at_price")) or None,
        stock=int(stock_raw) if stock_raw not in (None, "") else 0,
        icon=(data.get("icon") or "bi-box-seam").strip(),
        status="active",
    )
    db.session.add(product)
    db.session.flush()

    if is_multipart:
        for i, file in enumerate(request.files.getlist("images")):
            filename = save_upload(file, subfolder="products")
            if filename:
                db.session.add(ProductImage(product_id=product.id, filename=filename, position=i))

    db.session.commit()
    return jsonify(serialize_product_detail(product)), 201


@vendor_api_bp.route("/products/<int:product_id>", methods=["PATCH"])
@api_role_required("vendor")
def update_product(product_id):
    profile = _vendor_or_403(get_current_api_user())
    product = db.session.get(Product, product_id)
    if not product or product.vendor_id != profile.id:
        return error_response("Product not found.", 404)

    is_multipart = request.content_type and "multipart/form-data" in request.content_type
    data = request.form if is_multipart else (request.get_json(silent=True) or {})

    for field in ["name", "description", "sku", "status", "icon"]:
        if data.get(field) is not None:
            setattr(product, field, data.get(field))
    if data.get("category_id"):
        product.category_id = int(data.get("category_id"))
    if data.get("price"):
        product.price = float(data.get("price"))
    if data.get("compare_at_price"):
        product.compare_at_price = float(data.get("compare_at_price"))
    if data.get("stock") is not None:
        product.stock = int(data.get("stock"))

    if is_multipart:
        existing_count = product.images.count()
        for i, file in enumerate(request.files.getlist("images")):
            filename = save_upload(file, subfolder="products")
            if filename:
                db.session.add(ProductImage(product_id=product.id, filename=filename, position=existing_count + i))

    db.session.commit()
    return jsonify(serialize_product_detail(product))


@vendor_api_bp.route("/products/<int:product_id>", methods=["DELETE"])
@api_role_required("vendor")
def delete_product(product_id):
    profile = _vendor_or_403(get_current_api_user())
    product = db.session.get(Product, product_id)
    if not product or product.vendor_id != profile.id:
        return error_response("Product not found.", 404)

    db.session.delete(product)
    db.session.commit()
    return jsonify(message="Product deleted.")


@vendor_api_bp.route("/products/<int:product_id>/images/<int:image_id>", methods=["DELETE"])
@api_role_required("vendor")
def delete_product_image(product_id, image_id):
    profile = _vendor_or_403(get_current_api_user())
    image = db.session.get(ProductImage, image_id)
    if not image or image.product_id != product_id or image.product.vendor_id != profile.id:
        return error_response("Image not found.", 404)

    db.session.delete(image)
    db.session.commit()
    return jsonify(message="Image removed.")


@vendor_api_bp.route("/orders", methods=["GET"])
@api_role_required("vendor")
def vendor_orders():
    profile = _vendor_or_403(get_current_api_user())
    order_ids = sorted({oi.order_id for oi in OrderItem.query.filter_by(vendor_id=profile.id).all()}, reverse=True)
    orders = Order.query.filter(Order.id.in_(order_ids)).all() if order_ids else []
    return jsonify([serialize_order_summary(o) for o in orders])


@vendor_api_bp.route("/orders/<order_number>/status", methods=["POST"])
@api_role_required("vendor")
def update_order_status(order_number):
    profile = _vendor_or_403(get_current_api_user())
    order = Order.query.filter_by(order_number=order_number).first()
    if not order or not OrderItem.query.filter_by(order_id=order.id, vendor_id=profile.id).first():
        return error_response("Order not found.", 404)

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in Order.STATUS_STEPS + ["cancelled"]:
        return error_response("Invalid status.")

    order.status = new_status
    db.session.add(DeliveryUpdate(order_id=order.id, status=new_status, note=(data.get("note") or "").strip() or None))
    db.session.commit()
    notify(order.user_id, "Order update", f"Order #{order.order_number} is now {new_status}.", f"/orders/{order.order_number}", "bi-truck")
    return jsonify(serialize_order_detail(order))


@vendor_api_bp.route("/coupons", methods=["GET"])
@api_role_required("vendor")
def list_coupons():
    profile = _vendor_or_403(get_current_api_user())
    coupons = Coupon.query.filter_by(vendor_id=profile.id).order_by(Coupon.created_at.desc()).all()
    return jsonify([
        {"id": c.id, "code": c.code, "discount_percent": c.discount_percent, "active": c.active,
         "is_valid": c.is_valid, "usage_limit": c.usage_limit, "times_used": c.times_used,
         "expires_at": c.expires_at.isoformat() if c.expires_at else None}
        for c in coupons
    ])


@vendor_api_bp.route("/coupons", methods=["POST"])
@api_role_required("vendor")
def create_coupon():
    profile = _vendor_or_403(get_current_api_user())
    if profile.status != "verified":
        return error_response("Your store is still awaiting admin verification.", 403)

    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    discount = data.get("discount_percent")
    if not code or not discount:
        return error_response("code and discount_percent are required.")
    if Coupon.query.filter_by(code=code).first():
        return error_response("That coupon code is already in use.", 409)

    expires_days = data.get("expires_days")
    coupon = Coupon(
        code=code, discount_percent=int(discount), vendor_id=profile.id,
        usage_limit=data.get("usage_limit"),
        expires_at=(datetime.utcnow() + timedelta(days=int(expires_days))) if expires_days else None,
    )
    db.session.add(coupon)
    db.session.commit()
    return jsonify(message="Coupon created.", id=coupon.id), 201


@vendor_api_bp.route("/flash-sales", methods=["POST"])
@api_role_required("vendor")
def start_flash_sale():
    profile = _vendor_or_403(get_current_api_user())
    data = request.get_json(silent=True) or {}
    product = Product.query.filter_by(id=data.get("product_id"), vendor_id=profile.id).first()
    if not product:
        return error_response("Product not found.", 404)

    hours = int(data.get("hours", 24))
    product.is_flash_sale = True
    product.flash_sale_ends_at = datetime.utcnow() + timedelta(hours=hours)
    db.session.commit()
    return jsonify(serialize_product_card(product))


@vendor_api_bp.route("/flash-sales/<int:product_id>", methods=["DELETE"])
@api_role_required("vendor")
def end_flash_sale(product_id):
    profile = _vendor_or_403(get_current_api_user())
    product = db.session.get(Product, product_id)
    if not product or product.vendor_id != profile.id:
        return error_response("Product not found.", 404)

    product.is_flash_sale = False
    product.flash_sale_ends_at = None
    db.session.commit()
    return jsonify(message="Flash sale ended.")


@vendor_api_bp.route("/reviews", methods=["GET"])
@api_role_required("vendor")
def vendor_reviews():
    profile = _vendor_or_403(get_current_api_user())
    product_ids = [p.id for p in profile.products]
    reviews = Review.query.filter(Review.product_id.in_(product_ids)).order_by(Review.created_at.desc()).all() if product_ids else []
    return jsonify([
        {**serialize_review(r), "product_name": r.product.name, "product_id": r.product_id}
        for r in reviews
    ])


@vendor_api_bp.route("/reviews/<int:review_id>/reply", methods=["POST"])
@api_role_required("vendor")
def reply_review(review_id):
    profile = _vendor_or_403(get_current_api_user())
    review = db.session.get(Review, review_id)
    if not review or review.product.vendor_id != profile.id:
        return error_response("Review not found.", 404)

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return error_response("message is required.")

    existing = ReviewReply.query.filter_by(review_id=review.id).first()
    if existing:
        existing.message = message
    else:
        db.session.add(ReviewReply(review_id=review.id, vendor_id=profile.id, message=message))
    db.session.commit()
    return jsonify(message="Reply posted.")


@vendor_api_bp.route("/settings", methods=["PATCH"])
@api_role_required("vendor")
def update_settings():
    profile = _vendor_or_403(get_current_api_user())
    is_multipart = request.content_type and "multipart/form-data" in request.content_type
    data = request.form if is_multipart else (request.get_json(silent=True) or {})

    for field in ["description", "city", "state"]:
        if data.get(field) is not None:
            setattr(profile, field, data.get(field))

    if is_multipart:
        logo_filename = save_upload(request.files.get("logo"), subfolder="stores")
        banner_filename = save_upload(request.files.get("banner"), subfolder="stores")
        if logo_filename:
            profile.logo_filename = logo_filename
        if banner_filename:
            profile.banner_filename = banner_filename

    db.session.commit()
    return jsonify(serialize_vendor_full(profile))


@vendor_api_bp.route("/reports", methods=["GET"])
@api_role_required("vendor")
def reports():
    profile = _vendor_or_403(get_current_api_user())
    order_items = OrderItem.query.filter_by(vendor_id=profile.id).all()

    by_product = {}
    for oi in order_items:
        by_product.setdefault(oi.product_name, {"units": 0, "revenue": 0})
        by_product[oi.product_name]["units"] += oi.quantity
        by_product[oi.product_name]["revenue"] += oi.line_total
    top_products = sorted(by_product.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:8]

    return jsonify({
        "total_revenue": sum(oi.line_total for oi in order_items),
        "total_units": sum(oi.quantity for oi in order_items),
        "top_products": [{"name": name, **data} for name, data in top_products],
    })
