from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    Product, Category, OrderItem, Order, ProductVariant, ProductImage, Coupon,
    Review, ReviewReply, ReturnRequest, DeliveryUpdate,
)
from app.utils import role_required, slugify, vendor_must_be_verified
from app.services.uploads import save_upload
from app.services.notifications import notify

vendor_bp = Blueprint("vendor", __name__)


@vendor_bp.before_request
@login_required
@role_required("vendor")
def require_vendor():
    pass


@vendor_bp.route("/dashboard")
def dashboard():
    profile = current_user.vendor_profile
    products = profile.products
    product_count = products.count()

    order_items = OrderItem.query.filter_by(vendor_id=profile.id).all()
    total_sales = sum(oi.line_total for oi in order_items)
    order_count = len({oi.order_id for oi in order_items})

    low_stock = products.filter(Product.stock <= 10, Product.stock > 0).limit(5).all()
    recent_order_ids = sorted({oi.order_id for oi in order_items}, reverse=True)[:5]
    recent_orders = Order.query.filter(Order.id.in_(recent_order_ids)).all() if recent_order_ids else []

    pending_returns = (
        ReturnRequest.query.join(OrderItem)
        .filter(OrderItem.vendor_id == profile.id, ReturnRequest.status == "requested")
        .count()
    )

    return render_template(
        "vendor/dashboard.html",
        profile=profile,
        product_count=product_count,
        total_sales=total_sales,
        order_count=order_count,
        low_stock=low_stock,
        recent_orders=recent_orders,
        pending_returns=pending_returns,
    )


# ---------------------------------------------------------------- Products

@vendor_bp.route("/products")
def products():
    profile = current_user.vendor_profile
    all_products = profile.products.order_by(Product.created_at.desc()).all()
    return render_template("vendor/products.html", products=all_products, profile=profile)


@vendor_bp.route("/products/add", methods=["GET", "POST"])
@vendor_must_be_verified
def add_product():
    categories = Category.query.all()
    profile = current_user.vendor_profile

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id", type=int)
        price = request.form.get("price", type=float)
        compare_at_price = request.form.get("compare_at_price", type=float)
        stock = request.form.get("stock", type=int) or 0
        sku = request.form.get("sku", "").strip()
        description = request.form.get("description", "").strip()
        icon = request.form.get("icon", "bi-box-seam").strip() or "bi-box-seam"
        is_flash_sale = bool(request.form.get("is_flash_sale"))
        flash_hours = request.form.get("flash_sale_hours", type=int)

        if not name or not category_id or not price:
            flash("Please fill in the required fields.", "error")
            return render_template("vendor/add_product.html", categories=categories)

        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        while Product.query.filter_by(slug=slug).first():
            counter += 1
            slug = f"{base_slug}-{counter}"

        product = Product(
            vendor_id=profile.id,
            category_id=category_id,
            name=name,
            slug=slug,
            description=description,
            sku=sku,
            price=price,
            compare_at_price=compare_at_price,
            stock=stock,
            icon=icon,
            status="active",
            is_flash_sale=is_flash_sale,
            flash_sale_ends_at=(datetime.utcnow() + timedelta(hours=flash_hours)) if is_flash_sale and flash_hours else None,
        )
        db.session.add(product)
        db.session.flush()

        # Multiple image uploads
        for i, file in enumerate(request.files.getlist("images")):
            filename = save_upload(file, subfolder="products")
            if filename:
                db.session.add(ProductImage(product_id=product.id, filename=filename, position=i))

        # Variants (parallel arrays: variant_name[], variant_value[], variant_stock[], variant_price[])
        names = request.form.getlist("variant_name[]")
        values = request.form.getlist("variant_value[]")
        stocks = request.form.getlist("variant_stock[]")
        prices = request.form.getlist("variant_price[]")
        for vn, vv, vs, vp in zip(names, values, stocks, prices):
            if vn.strip() and vv.strip():
                db.session.add(ProductVariant(
                    product_id=product.id, name=vn.strip(), value=vv.strip(),
                    stock=int(vs) if vs.strip().isdigit() else 0,
                    price_override=float(vp) if vp.strip() else None,
                ))

        db.session.commit()
        flash(f"{name} was published to your store.", "success")
        return redirect(url_for("vendor.products"))

    return render_template("vendor/add_product.html", categories=categories)


@vendor_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def edit_product(product_id):
    profile = current_user.vendor_profile
    product = Product.query.get_or_404(product_id)
    if product.vendor_id != profile.id:
        abort(403)
    categories = Category.query.all()

    if request.method == "POST":
        product.name = request.form.get("name", product.name).strip()
        product.category_id = request.form.get("category_id", product.category_id, type=int)
        product.price = request.form.get("price", product.price, type=float)
        product.compare_at_price = request.form.get("compare_at_price", type=float)
        product.stock = request.form.get("stock", product.stock, type=int)
        product.description = request.form.get("description", product.description)
        product.status = request.form.get("status", product.status)

        for i, file in enumerate(request.files.getlist("images")):
            filename = save_upload(file, subfolder="products")
            if filename:
                existing_count = product.images.count()
                db.session.add(ProductImage(product_id=product.id, filename=filename, position=existing_count + i))

        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for("vendor.products"))

    return render_template("vendor/edit_product.html", product=product, categories=categories)


@vendor_bp.route("/products/<int:product_id>/delete", methods=["POST"])
def delete_product(product_id):
    profile = current_user.vendor_profile
    product = Product.query.get_or_404(product_id)
    if product.vendor_id != profile.id:
        abort(403)
    db.session.delete(product)
    db.session.commit()
    flash("Product removed from your store.", "info")
    return redirect(url_for("vendor.products"))


@vendor_bp.route("/products/image/<int:image_id>/delete", methods=["POST"])
def delete_product_image(image_id):
    image = ProductImage.query.get_or_404(image_id)
    if image.product.vendor_id != current_user.vendor_profile.id:
        abort(403)
    product_id = image.product_id
    db.session.delete(image)
    db.session.commit()
    flash("Image removed.", "info")
    return redirect(url_for("vendor.edit_product", product_id=product_id))


# ------------------------------------------------------------------ Orders

@vendor_bp.route("/orders")
def orders():
    profile = current_user.vendor_profile
    order_items = OrderItem.query.filter_by(vendor_id=profile.id).all()
    order_ids = sorted({oi.order_id for oi in order_items}, reverse=True)
    vendor_orders = Order.query.filter(Order.id.in_(order_ids)).all() if order_ids else []
    return render_template("vendor/orders.html", orders=vendor_orders, profile=profile)


@vendor_bp.route("/orders/<order_number>/status", methods=["POST"])
def update_order_status(order_number):
    profile = current_user.vendor_profile
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    has_items = OrderItem.query.filter_by(order_id=order.id, vendor_id=profile.id).first()
    if not has_items:
        abort(403)

    new_status = request.form.get("status")
    if new_status in Order.STATUS_STEPS + ["cancelled"]:
        order.status = new_status
        db.session.add(DeliveryUpdate(order_id=order.id, status=new_status, note=request.form.get("note", "").strip() or None))
        db.session.commit()
        notify(order.user_id, "Order update", f"Order #{order.order_number} is now {new_status}.", url_for("main.order_detail", order_number=order.order_number), "bi-truck")
        flash(f"Order #{order.order_number} marked as {new_status}.", "success")
    return redirect(url_for("vendor.orders"))


# --------------------------------------------------------------- Returns

@vendor_bp.route("/returns")
def returns():
    profile = current_user.vendor_profile
    requests_ = (
        ReturnRequest.query.join(OrderItem)
        .filter(OrderItem.vendor_id == profile.id)
        .order_by(ReturnRequest.created_at.desc())
        .all()
    )
    return render_template("vendor/returns.html", returns=requests_)


@vendor_bp.route("/returns/<int:return_id>/resolve", methods=["POST"])
def resolve_return(return_id):
    profile = current_user.vendor_profile
    ret = ReturnRequest.query.get_or_404(return_id)
    if ret.order_item.vendor_id != profile.id:
        abort(403)

    decision = request.form.get("decision")
    if decision == "approve":
        ret.status = "approved"
        ret.refund_amount = ret.order_item.line_total
    elif decision == "reject":
        ret.status = "rejected"
    elif decision == "refunded":
        ret.status = "refunded"

    ret.resolved_at = datetime.utcnow()
    db.session.commit()
    notify(ret.user_id, "Return update", f"Your return request is now {ret.status}.", url_for("main.my_returns"), "bi-arrow-return-left")
    flash(f"Return request marked as {ret.status}.", "success")
    return redirect(url_for("vendor.returns"))


# --------------------------------------------------------------- Coupons

@vendor_bp.route("/coupons", methods=["GET", "POST"])
@vendor_must_be_verified
def coupons():
    profile = current_user.vendor_profile

    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        discount = request.form.get("discount_percent", type=int)
        usage_limit = request.form.get("usage_limit", type=int)
        expires_days = request.form.get("expires_days", type=int)

        if not code or not discount:
            flash("Please provide a code and discount percentage.", "error")
        elif Coupon.query.filter_by(code=code).first():
            flash("That coupon code is already in use.", "error")
        else:
            db.session.add(Coupon(
                code=code, discount_percent=discount, vendor_id=profile.id,
                usage_limit=usage_limit,
                expires_at=(datetime.utcnow() + timedelta(days=expires_days)) if expires_days else None,
            ))
            db.session.commit()
            flash(f"Coupon '{code}' created.", "success")
        return redirect(url_for("vendor.coupons"))

    all_coupons = Coupon.query.filter_by(vendor_id=profile.id).order_by(Coupon.created_at.desc()).all()
    return render_template("vendor/coupons.html", coupons=all_coupons)


@vendor_bp.route("/coupons/<int:coupon_id>/toggle", methods=["POST"])
def toggle_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    if coupon.vendor_id != current_user.vendor_profile.id:
        abort(403)
    coupon.active = not coupon.active
    db.session.commit()
    return redirect(url_for("vendor.coupons"))


# ------------------------------------------------------------- Flash sales

@vendor_bp.route("/flash-sales", methods=["GET", "POST"])
@vendor_must_be_verified
def flash_sales():
    profile = current_user.vendor_profile

    if request.method == "POST":
        product_id = request.form.get("product_id", type=int)
        hours = request.form.get("hours", type=int) or 24
        product = Product.query.filter_by(id=product_id, vendor_id=profile.id).first()
        if product:
            product.is_flash_sale = True
            product.flash_sale_ends_at = datetime.utcnow() + timedelta(hours=hours)
            db.session.commit()
            flash(f"{product.name} added to flash sale for {hours}h.", "success")
        return redirect(url_for("vendor.flash_sales"))

    all_products = profile.products.filter_by(status="active").all()
    active_flash = profile.products.filter_by(is_flash_sale=True).all()
    return render_template("vendor/flash_sales.html", products=all_products, active_flash=active_flash)


@vendor_bp.route("/flash-sales/<int:product_id>/end", methods=["POST"])
def end_flash_sale(product_id):
    product = Product.query.get_or_404(product_id)
    if product.vendor_id != current_user.vendor_profile.id:
        abort(403)
    product.is_flash_sale = False
    product.flash_sale_ends_at = None
    db.session.commit()
    flash("Flash sale ended.", "info")
    return redirect(url_for("vendor.flash_sales"))


# --------------------------------------------------------------- Reviews

@vendor_bp.route("/reviews")
def reviews():
    profile = current_user.vendor_profile
    product_ids = [p.id for p in profile.products]
    all_reviews = Review.query.filter(Review.product_id.in_(product_ids)).order_by(Review.created_at.desc()).all() if product_ids else []
    return render_template("vendor/reviews.html", reviews=all_reviews)


@vendor_bp.route("/reviews/<int:review_id>/reply", methods=["POST"])
def reply_review(review_id):
    profile = current_user.vendor_profile
    review = Review.query.get_or_404(review_id)
    if review.product.vendor_id != profile.id:
        abort(403)

    message = request.form.get("message", "").strip()
    if not message:
        flash("Reply can't be empty.", "error")
        return redirect(url_for("vendor.reviews"))

    existing = ReviewReply.query.filter_by(review_id=review.id).first()
    if existing:
        existing.message = message
    else:
        db.session.add(ReviewReply(review_id=review.id, vendor_id=profile.id, message=message))
    db.session.commit()
    flash("Reply posted.", "success")
    return redirect(url_for("vendor.reviews"))


# ---------------------------------------------------------------- Store

@vendor_bp.route("/settings", methods=["GET", "POST"])
def settings():
    profile = current_user.vendor_profile

    if request.method == "POST":
        profile.description = request.form.get("description", "").strip()
        profile.city = request.form.get("city", "").strip()
        profile.state = request.form.get("state", "").strip()

        logo_file = request.files.get("logo")
        banner_file = request.files.get("banner")
        logo_filename = save_upload(logo_file, subfolder="stores")
        banner_filename = save_upload(banner_file, subfolder="stores")
        if logo_filename:
            profile.logo_filename = logo_filename
        if banner_filename:
            profile.banner_filename = banner_filename

        db.session.commit()
        flash("Store profile updated.", "success")
        return redirect(url_for("vendor.settings"))

    return render_template("vendor/settings.html", profile=profile)


# --------------------------------------------------------------- Reports

@vendor_bp.route("/reports")
def reports():
    profile = current_user.vendor_profile
    order_items = OrderItem.query.filter_by(vendor_id=profile.id).all()

    total_revenue = sum(oi.line_total for oi in order_items)
    total_units = sum(oi.quantity for oi in order_items)

    by_product = {}
    for oi in order_items:
        by_product.setdefault(oi.product_name, {"units": 0, "revenue": 0})
        by_product[oi.product_name]["units"] += oi.quantity
        by_product[oi.product_name]["revenue"] += oi.line_total
    top_products = sorted(by_product.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:8]

    return render_template("vendor/reports.html", total_revenue=total_revenue, total_units=total_units, top_products=top_products)
