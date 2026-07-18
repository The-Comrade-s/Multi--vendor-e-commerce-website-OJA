"""Order placement — the actual checkout business logic, called by both the
website's checkout form and the mobile API's /checkout endpoint. Neither one
duplicates this: they just collect input differently (HTML form vs JSON)
and hand it to the same function.
"""
from flask import current_app

from app.extensions import db
from app.models import CartItem, Order, OrderItem, DeliveryUpdate, Address
from app.utils import generate_order_number
from app.services.cart_pricing import resolve_coupon, compute_cart_totals
from app.services.notifications import notify
from app.services.email import send_order_confirmation_email


class CheckoutError(Exception):
    """Raised for any checkout validation failure — callers turn this into
    a flash message (web) or a JSON error (API)."""


def place_order(user, *, full_name, phone, address, city, state, payment_method,
                 coupon_code=None, save_address=False):
    if not all([full_name, phone, address, city, state]):
        raise CheckoutError("Please complete your delivery address.")

    items = CartItem.query.filter_by(user_id=user.id).all()
    if not items:
        raise CheckoutError("Your cart is empty.")

    for item in items:
        if item.quantity > item.available_stock:
            raise CheckoutError(f"Sorry, only {item.available_stock} left of {item.product.name}.")

    coupon = resolve_coupon(coupon_code)
    subtotal, discount, delivery_fee, total = compute_cart_totals(
        items, coupon, current_app.config["FREE_DELIVERY_THRESHOLD"], current_app.config["FLAT_DELIVERY_FEE"]
    )

    if save_address:
        has_existing = Address.query.filter_by(user_id=user.id).count() > 0
        db.session.add(Address(
            user_id=user.id, full_name=full_name, phone=phone,
            address_line=address, city=city, state=state, is_default=not has_existing,
        ))

    order = Order(
        order_number=generate_order_number(),
        user_id=user.id,
        full_name=full_name, phone=phone, address=address, city=city, state=state,
        payment_method=payment_method,
        payment_status="pending",
        status="pending",
        coupon_code=coupon.code if coupon else None,
        discount_amount=discount,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        db.session.add(OrderItem(
            order_id=order.id, product_id=item.product.id, vendor_id=item.product.vendor_id,
            product_name=item.product.name, quantity=item.quantity, price=item.unit_price,
        ))
        if item.variant:
            item.variant.stock = max(0, item.variant.stock - item.quantity)
        else:
            item.product.stock = max(0, item.product.stock - item.quantity)
        db.session.delete(item)

    if coupon:
        coupon.times_used = (coupon.times_used or 0) + 1

    db.session.add(DeliveryUpdate(order_id=order.id, status="pending", note="Order placed."))
    db.session.commit()

    notify(user.id, "Order placed", f"Order #{order.order_number} was placed successfully.",
           f"/orders/{order.order_number}", "bi-bag-check")

    if payment_method != "card":
        send_order_confirmation_email(order)

    return order
