from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Notification
from app.api.decorators import get_current_api_user
from app.api.serializers import serialize_notification

notifications_api_bp = Blueprint("notifications_api", __name__, url_prefix="/notifications")


@notifications_api_bp.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    user = get_current_api_user()
    items = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([serialize_notification(n) for n in items])


@notifications_api_bp.route("/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    user = get_current_api_user()
    count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify(count=count)


@notifications_api_bp.route("/mark-read", methods=["POST"])
@jwt_required()
def mark_read():
    user = get_current_api_user()
    Notification.query.filter_by(user_id=user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify(message="Marked as read.")
