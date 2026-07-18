from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Product, ProductVariant, CartItem
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_cart_item
from app.services.cart_pricing import resolve_coupon, compute_cart_totals

cart_api_bp = Blueprint("cart_api", __name__, url_prefix="/cart")


def _cart_payload(user, coupon_code=None):
    items = CartItem.query.filter_by(user_id=user.id).all()
    coupon = resolve_coupon(coupon_code) if coupon_code else None
    subtotal, discount, delivery_fee, total = compute_cart_totals(
        items, coupon, current_app.config["FREE_DELIVERY_THRESHOLD"], current_app.config["FLAT_DELIVERY_FEE"]
    )
    return {
        "items": [serialize_cart_item(i) for i in items],
        "subtotal": subtotal,
        "coupon_code": coupon.code if coupon else None,
        "coupon_valid": bool(coupon) if coupon_code else None,
        "discount": discount,
        "delivery_fee": delivery_fee,
        "total": total,
    }


@cart_api_bp.route("", methods=["GET"])
@jwt_required()
def get_cart():
    user = get_current_api_user()
    coupon_code = request.args.get("coupon_code")
    return jsonify(_cart_payload(user, coupon_code))


@cart_api_bp.route("/items", methods=["POST"])
@jwt_required()
def add_item():
    user = get_current_api_user()
    if not user.is_customer:
        return error_response("Only customer accounts have a cart.", 403)

    data = request.get_json(silent=True) or {}
    product = db.session.get(Product, data.get("product_id"))
    if not product:
        return error_response("Product not found.", 404)

    variant_id = data.get("variant_id")
    variant = db.session.get(ProductVariant, variant_id) if variant_id else None
    available = variant.stock if variant else product.stock
    if available <= 0:
        return error_response("That item is out of stock.", 409)

    qty = max(1, int(data.get("quantity", 1)))
    existing = CartItem.query.filter_by(user_id=user.id, product_id=product.id, variant_id=variant_id).first()
    if existing:
        existing.quantity += qty
    else:
        db.session.add(CartItem(user_id=user.id, product_id=product.id, variant_id=variant_id, quantity=qty))
    db.session.commit()

    return jsonify(_cart_payload(user)), 201


@cart_api_bp.route("/items/<int:item_id>", methods=["PATCH"])
@jwt_required()
def update_item(item_id):
    user = get_current_api_user()
    item = db.session.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        return error_response("Cart item not found.", 404)

    data = request.get_json(silent=True) or {}
    qty = data.get("quantity")
    if not qty or int(qty) < 1:
        return error_response("quantity must be at least 1.")

    item.quantity = int(qty)
    db.session.commit()
    return jsonify(_cart_payload(user))


@cart_api_bp.route("/items/<int:item_id>", methods=["DELETE"])
@jwt_required()
def remove_item(item_id):
    user = get_current_api_user()
    item = db.session.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        return error_response("Cart item not found.", 404)

    db.session.delete(item)
    db.session.commit()
    return jsonify(_cart_payload(user))
