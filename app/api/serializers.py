"""Converts SQLAlchemy model instances into JSON-safe dicts for the API.

Deliberately kept outside models.py: these are presentation-layer concerns
(what shape the mobile app wants) and shouldn't mix with the business logic
the website already relies on.
"""


def serialize_category(c):
    return {"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon}


def serialize_vendor_summary(v):
    return {
        "id": v.id,
        "store_name": v.store_name,
        "store_slug": v.store_slug,
        "city": v.city,
        "state": v.state,
        "is_verified": v.is_verified,
        "logo_url": _upload_url(v.logo_filename),
        "banner_url": _upload_url(v.banner_filename),
    }


def serialize_vendor_full(v):
    data = serialize_vendor_summary(v)
    data.update({"description": v.description, "status": v.status})
    return data


def serialize_product_image(img):
    return {"id": img.id, "url": _upload_url(img.filename), "position": img.position}


def serialize_variant(variant):
    return {
        "id": variant.id,
        "name": variant.name,
        "value": variant.value,
        "sku": variant.sku,
        "price": float(variant.effective_price),
        "stock": variant.stock,
    }


def serialize_product_card(p):
    """Compact shape for listing/grid screens."""
    first_image = p.images.first()
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "price": float(p.price),
        "compare_at_price": float(p.compare_at_price) if p.compare_at_price else None,
        "discount_percent": p.discount_percent,
        "rating": p.avg_rating,
        "review_count": p.review_count,
        "stock_label": p.stock_label,
        "in_stock": p.total_stock > 0,
        "icon": p.icon,
        "image_url": _upload_url(first_image.filename) if first_image else None,
        "is_flash_sale": p.is_flash_sale_active,
        "flash_sale_ends_at": p.flash_sale_ends_at.isoformat() if p.flash_sale_ends_at else None,
        "vendor": {
            "id": p.vendor.id,
            "store_name": p.vendor.store_name,
            "store_slug": p.vendor.store_slug,
            "is_verified": p.vendor.is_verified,
        },
    }


def serialize_product_detail(p):
    data = serialize_product_card(p)
    data.update({
        "description": p.description,
        "sku": p.sku,
        "stock": p.stock,
        "category": serialize_category(p.category),
        "images": [serialize_product_image(i) for i in p.images],
        "variants": [serialize_variant(v) for v in p.variants],
    })
    return data


def serialize_review(r, reply=None):
    data = {
        "id": r.id,
        "rating": r.rating,
        "comment": r.comment,
        "created_at": r.created_at.isoformat(),
        "user_name": r.user.name,
    }
    reply_obj = reply or r.reply
    if reply_obj:
        data["vendor_reply"] = {"message": reply_obj.message, "created_at": reply_obj.created_at.isoformat()}
    return data


def serialize_cart_item(item):
    return {
        "id": item.id,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
        "available_stock": item.available_stock,
        "product": {
            "id": item.product.id,
            "name": item.product.name,
            "slug": item.product.slug,
            "icon": item.product.icon,
            "image_url": _upload_url(item.product.images.first().filename) if item.product.images.first() else None,
        },
        "variant": {"id": item.variant.id, "name": item.variant.name, "value": item.variant.value} if item.variant else None,
    }


def serialize_address(a):
    return {
        "id": a.id, "label": a.label, "full_name": a.full_name, "phone": a.phone,
        "address_line": a.address_line, "city": a.city, "state": a.state, "is_default": a.is_default,
    }


def serialize_order_summary(o):
    return {
        "id": o.id,
        "order_number": o.order_number,
        "status": o.status,
        "payment_status": o.payment_status,
        "payment_method": o.payment_method,
        "total": float(o.total),
        "created_at": o.created_at.isoformat(),
        "item_count": o.items.count(),
    }


def serialize_order_detail(o):
    data = serialize_order_summary(o)
    data.update({
        "subtotal": float(o.subtotal),
        "delivery_fee": float(o.delivery_fee),
        "discount_amount": float(o.discount_amount or 0),
        "coupon_code": o.coupon_code,
        "full_name": o.full_name,
        "phone": o.phone,
        "address": o.address,
        "city": o.city,
        "state": o.state,
        "items": [
            {
                "id": item.id, "product_id": item.product_id, "product_name": item.product_name,
                "quantity": item.quantity, "price": float(item.price), "line_total": item.line_total,
                "vendor_name": item.vendor.store_name,
            }
            for item in o.items
        ],
        "timeline": [
            {"status": t.status, "note": t.note, "created_at": t.created_at.isoformat()}
            for t in o.delivery_updates
        ],
    })
    return data


def serialize_notification(n):
    return {
        "id": n.id, "title": n.title, "body": n.body, "url": n.url,
        "icon": n.icon, "is_read": n.is_read, "created_at": n.created_at.isoformat(),
    }


def serialize_conversation(c, viewer_role):
    return {
        "id": c.id,
        "peer_name": c.vendor.store_name if viewer_role == "customer" else c.customer.name,
        "vendor_id": c.vendor_id,
        "customer_id": c.customer_id,
        "updated_at": c.updated_at.isoformat(),
        "last_message": c.last_message.body if c.last_message else None,
    }


def serialize_message(m, viewer_role):
    return {
        "id": m.id,
        "body": m.body,
        "image_url": _upload_url(m.image_filename),
        "sender_role": m.sender_role,
        "is_mine": m.sender_role == viewer_role,
        "created_at": m.created_at.isoformat(),
    }


def serialize_user(u):
    return {
        "id": u.id, "name": u.name, "email": u.email, "phone": u.phone,
        "role": u.role, "is_email_verified": u.is_email_verified,
        "created_at": u.created_at.isoformat(),
        "vendor_profile": serialize_vendor_full(u.vendor_profile) if u.vendor_profile else None,
    }


def _upload_url(filename):
    if not filename:
        return None
    from flask import url_for
    return url_for("static", filename=f"uploads/{filename}", _external=True)
