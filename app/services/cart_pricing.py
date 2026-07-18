"""Cart pricing calculations shared between the web app and the mobile API.

This is the single source of truth for subtotal/discount/delivery/total
math so the website and the Flutter app can never compute different totals
for the same cart.
"""
from app.models import Coupon


def resolve_coupon(code):
    """Look up a coupon by code and return it only if currently valid."""
    if not code:
        return None
    coupon = Coupon.query.filter_by(code=code.strip().upper()).first()
    return coupon if coupon and coupon.is_valid else None


def compute_cart_totals(items, coupon, free_delivery_threshold, flat_delivery_fee):
    """Pure pricing calculation — no Flask session/request access, so it's
    safe to call from both cookie-session web requests and stateless JWT
    API requests.

    Returns (subtotal, discount, delivery_fee, total).
    """
    subtotal = sum(item.line_total for item in items)
    discount = round(subtotal * coupon.discount_percent / 100) if coupon else 0
    payable = max(0, subtotal - discount)
    delivery_fee = 0 if (payable >= free_delivery_threshold or subtotal == 0) else flat_delivery_fee
    total = payable + delivery_fee
    return subtotal, discount, delivery_fee, total
