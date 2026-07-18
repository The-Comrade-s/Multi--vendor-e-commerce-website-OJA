from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Conversation, Message, VendorProfile
from app.services.notifications import notify

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/")
@login_required
def inbox():
    if current_user.is_customer:
        conversations = Conversation.query.filter_by(customer_id=current_user.id).order_by(Conversation.updated_at.desc()).all()
    elif current_user.is_vendor:
        conversations = Conversation.query.filter_by(vendor_id=current_user.vendor_profile.id).order_by(Conversation.updated_at.desc()).all()
    else:
        abort(403)
    return render_template("chat/inbox.html", conversations=conversations)


@chat_bp.route("/start/<int:vendor_id>", methods=["POST"])
@login_required
def start(vendor_id):
    if not current_user.is_customer:
        abort(403)
    vendor = VendorProfile.query.get_or_404(vendor_id)

    convo = Conversation.query.filter_by(customer_id=current_user.id, vendor_id=vendor.id).first()
    if not convo:
        convo = Conversation(customer_id=current_user.id, vendor_id=vendor.id)
        db.session.add(convo)
        db.session.commit()

    return redirect(url_for("chat.thread", conversation_id=convo.id))


@chat_bp.route("/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def thread(conversation_id):
    convo = Conversation.query.get_or_404(conversation_id)

    is_customer_party = current_user.is_customer and convo.customer_id == current_user.id
    is_vendor_party = current_user.is_vendor and current_user.vendor_profile and convo.vendor_id == current_user.vendor_profile.id
    if not (is_customer_party or is_vendor_party):
        abort(403)

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        image_filename = None
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            from app.services.uploads import save_upload
            image_filename = save_upload(image_file, subfolder="chat")

        if body or image_filename:
            sender_role = "customer" if is_customer_party else "vendor"
            db.session.add(Message(conversation_id=convo.id, sender_role=sender_role, body=body, image_filename=image_filename))
            from datetime import datetime
            convo.updated_at = datetime.utcnow()
            db.session.commit()

            # Notify the other party
            if sender_role == "customer":
                notify(convo.vendor.user_id, "New message", f"{current_user.name} sent you a message.", url_for("chat.thread", conversation_id=convo.id), "bi-chat-dots")
            else:
                notify(convo.customer_id, "New message", f"{convo.vendor.store_name} replied to you.", url_for("chat.thread", conversation_id=convo.id), "bi-chat-dots")

        return redirect(url_for("chat.thread", conversation_id=convo.id))

    messages = convo.messages.all()
    # Mark incoming messages as read
    other_role = "vendor" if is_customer_party else "customer"
    Message.query.filter_by(conversation_id=convo.id, sender_role=other_role, is_read=False).update({"is_read": True})
    db.session.commit()

    return render_template("chat/thread.html", convo=convo, messages=messages, is_vendor_party=is_vendor_party)
