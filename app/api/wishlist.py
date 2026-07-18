from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import WishlistItem, Product
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_product_card

wishlist_api_bp = Blueprint("wishlist_api", __name__, url_prefix="/wishlist")


@wishlist_api_bp.route("", methods=["GET"])
@jwt_required()
def list_wishlist():
    user = get_current_api_user()
    items = WishlistItem.query.filter_by(user_id=user.id).all()
    return jsonify([{"id": i.id, "product": serialize_product_card(i.product)} for i in items])


@wishlist_api_bp.route("/toggle/<int:product_id>", methods=["POST"])
@jwt_required()
def toggle(product_id):
    user = get_current_api_user()
    product = db.session.get(Product, product_id)
    if not product:
        return error_response("Product not found.", 404)

    existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify(in_wishlist=False)

    db.session.add(WishlistItem(user_id=user.id, product_id=product_id))
    db.session.commit()
    return jsonify(in_wishlist=True)
