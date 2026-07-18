from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Order, OrderItem, ReturnRequest
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_order_summary, serialize_order_detail
from app.services.checkout import place_order, CheckoutError

orders_api_bp = Blueprint("orders_api", __name__)


@orders_api_bp.route("/checkout", methods=["POST"])
@jwt_required()
def checkout():
    user = get_current_api_user()
    if not user.is_customer:
        return error_response("Only customer accounts can check out.", 403)

    data = request.get_json(silent=True) or {}
    try:
        order = place_order(
            user,
            full_name=(data.get("full_name") or "").strip(),
            phone=(data.get("phone") or "").strip(),
            address=(data.get("address") or "").strip(),
            city=(data.get("city") or "").strip(),
            state=(data.get("state") or "").strip(),
            payment_method=data.get("payment_method", "pay_on_delivery"),
            coupon_code=data.get("coupon_code"),
            save_address=bool(data.get("save_address")),
        )
    except CheckoutError as exc:
        return error_response(str(exc), 400)

    response = serialize_order_detail(order)

    if order.payment_method == "card":
        # Client should follow up with POST /api/v1/payments/initiate
        # to get a gateway checkout URL to open in a WebView.
        response["requires_payment"] = True

    return jsonify(response), 201


@orders_api_bp.route("/orders", methods=["GET"])
@jwt_required()
def list_orders():
    user = get_current_api_user()
    page = request.args.get("page", 1, type=int)
    pagination = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return jsonify({
        "items": [serialize_order_summary(o) for o in pagination.items],
        "page": pagination.page, "pages": pagination.pages, "total": pagination.total,
    })


@orders_api_bp.route("/orders/<order_number>", methods=["GET"])
@jwt_required()
def order_detail(order_number):
    user = get_current_api_user()
    order = Order.query.filter_by(order_number=order_number).first()
    if not order or (order.user_id != user.id and not user.is_admin):
        return error_response("Order not found.", 404)
    return jsonify(serialize_order_detail(order))


@orders_api_bp.route("/orders/item/<int:order_item_id>/return", methods=["POST"])
@jwt_required()
def request_return(order_item_id):
    user = get_current_api_user()
    item = db.session.get(OrderItem, order_item_id)
    if not item or item.order.user_id != user.id:
        return error_response("Order item not found.", 404)
    if item.order.status != "delivered":
        return error_response("Returns can only be requested after delivery.", 400)
    if ReturnRequest.query.filter_by(order_item_id=item.id).first():
        return error_response("A return request already exists for this item.", 409)

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return error_response("reason is required.")

    ret = ReturnRequest(order_item_id=item.id, user_id=user.id, reason=reason, details=(data.get("details") or "").strip())
    db.session.add(ret)
    db.session.commit()
    return jsonify(message="Return request submitted.", id=ret.id), 201


@orders_api_bp.route("/returns", methods=["GET"])
@jwt_required()
def list_returns():
    user = get_current_api_user()
    returns = ReturnRequest.query.filter_by(user_id=user.id).order_by(ReturnRequest.created_at.desc()).all()
    return jsonify([
        {
            "id": r.id, "product_name": r.order_item.product_name, "reason": r.reason,
            "details": r.details, "status": r.status,
            "refund_amount": float(r.refund_amount) if r.refund_amount else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in returns
    ])
