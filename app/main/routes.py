from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, session, current_app
from flask_login import login_required, current_user
from datetime import datetime

from app.extensions import db
from app.models import (
    Product, Category, CartItem, WishlistItem, Order, OrderItem, VendorProfile, Review,
    DeliveryUpdate, Address, Coupon, ReviewReply, ReturnRequest, ProductVariant,
)
from app.utils import generate_order_number
from app.services.cart_pricing import resolve_coupon, compute_cart_totals
from app.services.checkout import place_order, CheckoutError

main_bp = Blueprint("main", __name__)

import os


@main_bp.route("/run-seed-once")
def run_seed_once():
    """One-time seed trigger. DELETE THIS ROUTE after you've used it."""
    provided = request.args.get("key", "")
    expected = os.environ.get("SEED_SECRET", "")

    if request.args.get("debug") == "1":
        return {
            "seed_secret_is_set": bool(expected),
            "seed_secret_length": len(expected),
            "provided_key_length": len(provided),
            "match": provided == expected,
        }

    if provided != expected:
        abort(404)

    from seed import run as seed_run
    seed_run()
    return "Seed complete. Check your homepage — then delete this route from routes.py."


def _applied_coupon():
    code = session.get("coupon_code")
    if not code:
        return None
    coupon = resolve_coupon(code)
    if not coupon:
        session.pop("coupon_code", None)
    return coupon


def _cart_totals(items):
    coupon = _applied_coupon()
    subtotal, discount, delivery_fee, total = compute_cart_totals(
        items, coupon, current_app.config["FREE_DELIVERY_THRESHOLD"], current_app.config["FLAT_DELIVERY_FEE"]
    )
    return subtotal, coupon, discount, delivery_fee, total


@main_bp.route("/")
def home():
    categories = Category.query.all()
    flash_deals = Product.query.filter_by(status="active", is_flash_sale=True).limit(4).all()
    trending = Product.query.filter_by(status="active").order_by(Product.created_at.desc()).limit(8).all()
    top_vendors = VendorProfile.query.filter_by(status="verified").limit(4).all()
    return render_template(
        "main/home.html",
        categories=categories,
        flash_deals=flash_deals,
        trending=trending,
        top_vendors=top_vendors,
    )


@main_bp.route("/category/<slug>")
def category(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    page = request.args.get("page", 1, type=int)
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    sort = request.args.get("sort", "newest")

    query = Product.query.filter_by(category_id=cat.id, status="active")
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if sort == "price_low":
        query = query.order_by(Product.price.asc())
    elif sort == "price_high":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    pagination = query.paginate(page=page, per_page=12, error_out=False)
    return render_template("main/category.html", category=cat, pagination=pagination, min_price=min_price, max_price=max_price, sort=sort)


@main_bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    results = []
    if q:
        query = Product.query.filter(Product.status == "active", Product.name.ilike(f"%{q}%"))
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        results = query.limit(40).all()
    return render_template("main/search.html", query=q, results=results, min_price=min_price, max_price=max_price)


@main_bp.route("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    related = (
        Product.query.filter(Product.category_id == product.category_id, Product.id != product.id, Product.status == "active")
        .limit(4)
        .all()
    )
    reviews = product.reviews.order_by(Review.created_at.desc()).limit(10).all()
    variants = product.variants.all()
    images = product.images.all()
    in_wishlist = False
    if current_user.is_authenticated:
        in_wishlist = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product.id).first() is not None
    return render_template("main/product_detail.html", product=product, related=related, reviews=reviews, variants=variants, images=images, in_wishlist=in_wishlist)


@main_bp.route("/product/<slug>/review", methods=["POST"])
@login_required
def add_review(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()
    if not rating or rating < 1 or rating > 5:
        flash("Please select a rating between 1 and 5.", "error")
    else:
        db.session.add(Review(product_id=product.id, user_id=current_user.id, rating=rating, comment=comment))
        db.session.commit()
        flash("Thanks for your review!", "success")
    return redirect(url_for("main.product_detail", slug=slug))


# ---------------------------------------------------------------- Wishlist

@main_bp.route("/wishlist")
@login_required
def wishlist():
    items = WishlistItem.query.filter_by(user_id=current_user.id).all()
    return render_template("main/wishlist.html", items=items)


@main_bp.route("/wishlist/toggle/<int:product_id>", methods=["POST"])
@login_required
def wishlist_toggle(product_id):
    existing = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash("Removed from wishlist.", "info")
    else:
        db.session.add(WishlistItem(user_id=current_user.id, product_id=product_id))
        db.session.commit()
        flash("Added to wishlist.", "success")
    return redirect(request.referrer or url_for("main.home"))


# -------------------------------------------------------------------- Cart

@main_bp.route("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    subtotal, coupon, discount, delivery_fee, total = _cart_totals(items)
    return render_template("main/cart.html", items=items, subtotal=subtotal, coupon=coupon, discount=discount, delivery_fee=delivery_fee, total=total)


@main_bp.route("/cart/coupon/apply", methods=["POST"])
@login_required
def coupon_apply():
    code = request.form.get("code", "").strip().upper()
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon or not coupon.is_valid:
        flash("That coupon code is invalid or has expired.", "error")
    else:
        session["coupon_code"] = coupon.code
        flash(f"Coupon '{coupon.code}' applied — {coupon.discount_percent}% off.", "success")
    return redirect(url_for("main.cart"))


@main_bp.route("/cart/coupon/remove", methods=["POST"])
@login_required
def coupon_remove():
    session.pop("coupon_code", None)
    flash("Coupon removed.", "info")
    return redirect(url_for("main.cart"))


@main_bp.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def cart_add(product_id):
    product = Product.query.get_or_404(product_id)
    variant_id = request.form.get("variant_id", type=int)
    variant = ProductVariant.query.get(variant_id) if variant_id else None

    available = variant.stock if variant else product.stock
    if available <= 0:
        flash("That item is currently out of stock.", "error")
        return redirect(request.referrer or url_for("main.home"))

    qty = request.form.get("quantity", 1, type=int) or 1
    existing = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id, variant_id=variant_id).first()
    if existing:
        existing.quantity += qty
    else:
        db.session.add(CartItem(user_id=current_user.id, product_id=product_id, variant_id=variant_id, quantity=qty))
    db.session.commit()
    flash(f"{product.name} added to your cart.", "success")
    return redirect(request.referrer or url_for("main.home"))


@main_bp.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def cart_update(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    qty = request.form.get("quantity", 1, type=int)
    if qty and qty > 0:
        item.quantity = qty
        db.session.commit()
    return redirect(url_for("main.cart"))


@main_bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def cart_remove(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash("Item removed from cart.", "info")
    return redirect(url_for("main.cart"))


# ---------------------------------------------------------------- Checkout

@main_bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("Your cart is empty.", "info")
        return redirect(url_for("main.home"))

    subtotal, coupon, discount, delivery_fee, total = _cart_totals(items)
    saved_addresses = Address.query.filter_by(user_id=current_user.id).order_by(Address.is_default.desc()).all()

    if request.method == "POST":
        try:
            order = place_order(
                current_user,
                full_name=request.form.get("full_name", "").strip(),
                phone=request.form.get("phone", "").strip(),
                address=request.form.get("address", "").strip(),
                city=request.form.get("city", "").strip(),
                state=request.form.get("state", "").strip(),
                payment_method=request.form.get("payment_method", "pay_on_delivery"),
                coupon_code=coupon.code if coupon else None,
                save_address=bool(request.form.get("save_address")),
            )
        except CheckoutError as exc:
            flash(str(exc), "error")
            return render_template("main/checkout.html", items=items, subtotal=subtotal, coupon=coupon, discount=discount, delivery_fee=delivery_fee, total=total, saved_addresses=saved_addresses)

        session.pop("coupon_code", None)

        if order.payment_method == "card":
            return redirect(url_for("payments.pay", order_number=order.order_number))

        flash("Order placed successfully!", "success")
        return redirect(url_for("main.order_detail", order_number=order.order_number))

    return render_template("main/checkout.html", items=items, subtotal=subtotal, coupon=coupon, discount=discount, delivery_fee=delivery_fee, total=total, saved_addresses=saved_addresses)


# ------------------------------------------------------------------ Orders

@main_bp.route("/orders")
@login_required
def orders():
    all_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("main/orders.html", orders=all_orders)


@main_bp.route("/orders/<order_number>")
@login_required
def order_detail(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    timeline = order.delivery_updates.all()
    return render_template("main/order_detail.html", order=order, timeline=timeline)


# --------------------------------------------------------------- Profile

@main_bp.route("/profile")
@login_required
def profile():
    return render_template("main/profile.html")


# --------------------------------------------------------------- Addresses

@main_bp.route("/addresses")
@login_required
def addresses():
    all_addresses = Address.query.filter_by(user_id=current_user.id).order_by(Address.is_default.desc()).all()
    return render_template("main/addresses.html", addresses=all_addresses)


@main_bp.route("/addresses/add", methods=["POST"])
@login_required
def address_add():
    label = request.form.get("label", "Home").strip() or "Home"
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    address_line = request.form.get("address_line", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()

    if not all([full_name, phone, address_line, city, state]):
        flash("Please fill in all address fields.", "error")
        return redirect(url_for("main.addresses"))

    is_first = Address.query.filter_by(user_id=current_user.id).count() == 0
    db.session.add(Address(
        user_id=current_user.id, label=label, full_name=full_name, phone=phone,
        address_line=address_line, city=city, state=state, is_default=is_first,
    ))
    db.session.commit()
    flash("Address saved.", "success")
    return redirect(url_for("main.addresses"))


@main_bp.route("/addresses/<int:address_id>/default", methods=["POST"])
@login_required
def address_set_default(address_id):
    addr = Address.query.get_or_404(address_id)
    if addr.user_id != current_user.id:
        abort(403)
    Address.query.filter_by(user_id=current_user.id).update({"is_default": False})
    addr.is_default = True
    db.session.commit()
    return redirect(url_for("main.addresses"))


@main_bp.route("/addresses/<int:address_id>/delete", methods=["POST"])
@login_required
def address_delete(address_id):
    addr = Address.query.get_or_404(address_id)
    if addr.user_id != current_user.id:
        abort(403)
    db.session.delete(addr)
    db.session.commit()
    flash("Address removed.", "info")
    return redirect(url_for("main.addresses"))


# --------------------------------------------------------- Returns/Refunds

@main_bp.route("/orders/item/<int:order_item_id>/return", methods=["POST"])
@login_required
def request_return(order_item_id):
    item = OrderItem.query.get_or_404(order_item_id)
    if item.order.user_id != current_user.id:
        abort(403)
    if item.order.status != "delivered":
        flash("Returns can only be requested after an order is delivered.", "error")
        return redirect(url_for("main.order_detail", order_number=item.order.order_number))

    existing = ReturnRequest.query.filter_by(order_item_id=item.id).first()
    if existing:
        flash("A return request already exists for this item.", "info")
        return redirect(url_for("main.order_detail", order_number=item.order.order_number))

    reason = request.form.get("reason", "").strip()
    details = request.form.get("details", "").strip()
    if not reason:
        flash("Please select a reason for the return.", "error")
        return redirect(url_for("main.order_detail", order_number=item.order.order_number))

    db.session.add(ReturnRequest(order_item_id=item.id, user_id=current_user.id, reason=reason, details=details))
    db.session.commit()
    flash("Return request submitted — the vendor will review it shortly.", "success")
    return redirect(url_for("main.order_detail", order_number=item.order.order_number))


@main_bp.route("/returns")
@login_required
def my_returns():
    returns = ReturnRequest.query.filter_by(user_id=current_user.id).order_by(ReturnRequest.created_at.desc()).all()
    return render_template("main/returns.html", returns=returns)


# ----------------------------------------------------------- Notifications

@main_bp.route("/notifications")
@login_required
def notifications():
    from app.models import Notification
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("main/notifications.html", items=items)
    
