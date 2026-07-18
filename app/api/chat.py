from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Conversation, Message, VendorProfile
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_conversation, serialize_message
from app.services.notifications import notify

chat_api_bp = Blueprint("chat_api", __name__, url_prefix="/chat")


@chat_api_bp.route("/conversations", methods=["GET"])
@jwt_required()
def list_conversations():
    user = get_current_api_user()
    if user.is_customer:
        convos = Conversation.query.filter_by(customer_id=user.id).order_by(Conversation.updated_at.desc()).all()
    elif user.is_vendor and user.vendor_profile:
        convos = Conversation.query.filter_by(vendor_id=user.vendor_profile.id).order_by(Conversation.updated_at.desc()).all()
    else:
        return error_response("No conversations for this account type.", 403)

    role = "customer" if user.is_customer else "vendor"
    return jsonify([serialize_conversation(c, role) for c in convos])


@chat_api_bp.route("/conversations/start/<int:vendor_id>", methods=["POST"])
@jwt_required()
def start_conversation(vendor_id):
    user = get_current_api_user()
    if not user.is_customer:
        return error_response("Only customers can start a conversation with a vendor.", 403)

    vendor = db.session.get(VendorProfile, vendor_id)
    if not vendor:
        return error_response("Vendor not found.", 404)

    convo = Conversation.query.filter_by(customer_id=user.id, vendor_id=vendor.id).first()
    if not convo:
        convo = Conversation(customer_id=user.id, vendor_id=vendor.id)
        db.session.add(convo)
        db.session.commit()

    return jsonify(serialize_conversation(convo, "customer")), 201


@chat_api_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(conversation_id):
    user = get_current_api_user()
    convo = db.session.get(Conversation, conversation_id)
    if not convo:
        return error_response("Conversation not found.", 404)

    is_customer_party = user.is_customer and convo.customer_id == user.id
    is_vendor_party = user.is_vendor and user.vendor_profile and convo.vendor_id == user.vendor_profile.id
    if not (is_customer_party or is_vendor_party):
        return error_response("Forbidden.", 403)

    role = "customer" if is_customer_party else "vendor"
    other_role = "vendor" if is_customer_party else "customer"
    Message.query.filter_by(conversation_id=convo.id, sender_role=other_role, is_read=False).update({"is_read": True})
    db.session.commit()

    messages = convo.messages.all()
    return jsonify([serialize_message(m, role) for m in messages])


@chat_api_bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
@jwt_required()
def send_message(conversation_id):
    user = get_current_api_user()
    convo = db.session.get(Conversation, conversation_id)
    if not convo:
        return error_response("Conversation not found.", 404)

    is_customer_party = user.is_customer and convo.customer_id == user.id
    is_vendor_party = user.is_vendor and user.vendor_profile and convo.vendor_id == user.vendor_profile.id
    if not (is_customer_party or is_vendor_party):
        return error_response("Forbidden.", 403)

    if request.content_type and "application/json" in request.content_type:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form
    body = (data.get("body") or "").strip()

    image_filename = None
    if "image" in request.files:
        from app.services.uploads import save_upload
        image_filename = save_upload(request.files.get("image"), subfolder="chat")

    if not body and not image_filename:
        return error_response("body or image is required.")

    role = "customer" if is_customer_party else "vendor"
    message = Message(conversation_id=convo.id, sender_role=role, body=body, image_filename=image_filename)
    db.session.add(message)
    convo.updated_at = datetime.utcnow()
    db.session.commit()

    if role == "customer":
        notify(convo.vendor.user_id, "New message", f"{user.name} sent you a message.", f"/chat/{convo.id}", "bi-chat-dots")
    else:
        notify(convo.customer_id, "New message", f"{convo.vendor.store_name} replied to you.", f"/chat/{convo.id}", "bi-chat-dots")

    return jsonify(serialize_message(message, role)), 201
