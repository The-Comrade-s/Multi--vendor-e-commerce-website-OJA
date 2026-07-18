from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Address
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_address

addresses_api_bp = Blueprint("addresses_api", __name__, url_prefix="/addresses")


@addresses_api_bp.route("", methods=["GET"])
@jwt_required()
def list_addresses():
    user = get_current_api_user()
    items = Address.query.filter_by(user_id=user.id).order_by(Address.is_default.desc()).all()
    return jsonify([serialize_address(a) for a in items])


@addresses_api_bp.route("", methods=["POST"])
@jwt_required()
def add_address():
    user = get_current_api_user()
    data = request.get_json(silent=True) or {}

    required = ["full_name", "phone", "address_line", "city", "state"]
    if not all((data.get(f) or "").strip() for f in required):
        return error_response("full_name, phone, address_line, city, and state are required.")

    is_first = Address.query.filter_by(user_id=user.id).count() == 0
    address = Address(
        user_id=user.id, label=(data.get("label") or "Home").strip(),
        full_name=data["full_name"].strip(), phone=data["phone"].strip(),
        address_line=data["address_line"].strip(), city=data["city"].strip(), state=data["state"].strip(),
        is_default=is_first,
    )
    db.session.add(address)
    db.session.commit()
    return jsonify(serialize_address(address)), 201


@addresses_api_bp.route("/<int:address_id>/default", methods=["POST"])
@jwt_required()
def set_default(address_id):
    user = get_current_api_user()
    addr = db.session.get(Address, address_id)
    if not addr or addr.user_id != user.id:
        return error_response("Address not found.", 404)

    Address.query.filter_by(user_id=user.id).update({"is_default": False})
    addr.is_default = True
    db.session.commit()
    return jsonify(serialize_address(addr))


@addresses_api_bp.route("/<int:address_id>", methods=["DELETE"])
@jwt_required()
def delete_address(address_id):
    user = get_current_api_user()
    addr = db.session.get(Address, address_id)
    if not addr or addr.user_id != user.id:
        return error_response("Address not found.", 404)

    db.session.delete(addr)
    db.session.commit()
    return jsonify(message="Address deleted.")
