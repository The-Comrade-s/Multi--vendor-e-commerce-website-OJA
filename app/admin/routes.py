from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, VendorProfile, Product, Order, Category, ReturnRequest, OrderItem, Coupon
from app.utils import role_required, slugify
from app.services.notifications import notify

admin_bp = Blueprint("admin", __name__)


@admin_bp.before_request
@login_required
@role_required("admin")
def require_admin():
    pass


@admin_bp.route("/dashboard")
def dashboard():
    total_users = User.query.filter_by(role="customer").count()
    total_vendors = VendorProfile.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_revenue = sum(float(o.total) for o in Order.query.filter(Order.payment_status == "paid").all())

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(6).all()
    pending_vendors = VendorProfile.query.filter_by(status="pending").limit(5).all()
    pending_returns = ReturnRequest.query.filter_by(status="requested").count()

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_vendors=total_vendors,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue,
        recent_orders=recent_orders,
        pending_vendors=pending_vendors,
        pending_returns=pending_returns,
    )


@admin_bp.route("/vendors")
def vendors():
    status_filter = request.args.get("status")
    query = VendorProfile.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    all_vendors = query.order_by(VendorProfile.created_at.desc()).all()
    return render_template("admin/vendors.html", vendors=all_vendors, status_filter=status_filter)


@admin_bp.route("/vendors/<int:vendor_id>/status", methods=["POST"])
def update_vendor_status(vendor_id):
    profile = VendorProfile.query.get_or_404(vendor_id)
    new_status = request.form.get("status")
    if new_status in ("verified", "rejected", "suspended", "pending"):
        profile.status = new_status
        db.session.commit()
        notify(profile.user_id, "Store status updated", f"{profile.store_name} is now {new_status}.", url_for("vendor.dashboard"), "bi-shop")
        flash(f"{profile.store_name} is now {new_status}.", "success")
    return redirect(url_for("admin.vendors"))


@admin_bp.route("/users")
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You can't suspend your own account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active_account = not user.is_active_account
    db.session.commit()
    flash(f"{user.name}'s account is now {'active' if user.is_active_account else 'suspended'}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/products")
def products():
    all_products = Product.query.order_by(Product.created_at.desc()).limit(200).all()
    return render_template("admin/products.html", products=all_products)


@admin_bp.route("/products/<int:product_id>/delist", methods=["POST"])
def delist_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.status = "archived" if product.status != "archived" else "active"
    db.session.commit()
    flash(f"{product.name} was {'delisted' if product.status == 'archived' else 're-listed'}.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        icon = request.form.get("icon", "bi-grid").strip() or "bi-grid"
        if name and not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name, slug=slugify(name), icon=icon))
            db.session.commit()
            flash(f"Category '{name}' added.", "success")
    all_categories = Category.query.all()
    return render_template("admin/categories.html", categories=all_categories)


# --------------------------------------------------------------- Returns

@admin_bp.route("/returns")
def returns():
    all_returns = ReturnRequest.query.order_by(ReturnRequest.created_at.desc()).all()
    return render_template("admin/returns.html", returns=all_returns)


@admin_bp.route("/returns/<int:return_id>/resolve", methods=["POST"])
def resolve_return(return_id):
    ret = ReturnRequest.query.get_or_404(return_id)
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
    return redirect(url_for("admin.returns"))


# --------------------------------------------------------------- Coupons

@admin_bp.route("/coupons", methods=["GET", "POST"])
def coupons():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        discount = request.form.get("discount_percent", type=int)
        expires_days = request.form.get("expires_days", type=int)
        if code and discount and not Coupon.query.filter_by(code=code).first():
            db.session.add(Coupon(
                code=code, discount_percent=discount, vendor_id=None,  # platform-wide
                expires_at=(datetime.utcnow() + timedelta(days=expires_days)) if expires_days else None,
            ))
            db.session.commit()
            flash(f"Platform-wide coupon '{code}' created.", "success")
    all_coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template("admin/coupons.html", coupons=all_coupons)


@admin_bp.route("/coupons/<int:coupon_id>/toggle", methods=["POST"])
def toggle_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.active = not coupon.active
    db.session.commit()
    return redirect(url_for("admin.coupons"))


# --------------------------------------------------------------- Reports

@admin_bp.route("/reports")
def reports():
    orders = Order.query.filter_by(payment_status="paid").all()
    total_revenue = sum(float(o.total) for o in orders)

    by_vendor = {}
    for oi in OrderItem.query.all():
        by_vendor.setdefault(oi.vendor.store_name, 0)
        by_vendor[oi.vendor.store_name] += oi.line_total
    top_vendors = sorted(by_vendor.items(), key=lambda kv: kv[1], reverse=True)[:8]

    by_category = {}
    for p in Product.query.all():
        by_category.setdefault(p.category.name, 0)
        by_category[p.category.name] += 1

    return render_template("admin/reports.html", total_revenue=total_revenue, top_vendors=top_vendors, by_category=by_category, order_count=len(orders))
