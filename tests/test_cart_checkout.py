from tests.conftest import login
from app.models import CartItem, Order


def test_add_to_cart(client, db, sample_customer, sample_product):
    login(client, sample_customer.email, "password123")
    resp = client.post(f"/cart/add/{sample_product.id}", data={"quantity": 2}, follow_redirects=True)
    assert resp.status_code == 200

    item = CartItem.query.filter_by(user_id=sample_customer.id, product_id=sample_product.id).first()
    assert item is not None
    assert item.quantity == 2


def test_cannot_add_out_of_stock_product(client, db, sample_customer, sample_product):
    sample_product.stock = 0
    db.session.commit()

    login(client, sample_customer.email, "password123")
    resp = client.post(f"/cart/add/{sample_product.id}", data={"quantity": 1}, follow_redirects=True)
    assert b"out of stock" in resp.data.lower()


def test_checkout_creates_order_and_clears_cart(client, db, sample_customer, sample_product):
    login(client, sample_customer.email, "password123")
    client.post(f"/cart/add/{sample_product.id}", data={"quantity": 1})

    resp = client.post("/checkout", data={
        "full_name": "Test Customer", "phone": "08011112222",
        "address": "1 Test Street", "city": "Lagos", "state": "Lagos",
        "payment_method": "pay_on_delivery",
    }, follow_redirects=True)

    assert resp.status_code == 200
    order = Order.query.filter_by(user_id=sample_customer.id).first()
    assert order is not None
    assert order.status == "pending"
    assert CartItem.query.filter_by(user_id=sample_customer.id).count() == 0


def test_checkout_decrements_stock(client, db, sample_customer, sample_product):
    starting_stock = sample_product.stock
    login(client, sample_customer.email, "password123")
    client.post(f"/cart/add/{sample_product.id}", data={"quantity": 3})
    client.post("/checkout", data={
        "full_name": "Test Customer", "phone": "08011112222",
        "address": "1 Test Street", "city": "Lagos", "state": "Lagos",
        "payment_method": "pay_on_delivery",
    })

    db.session.refresh(sample_product)
    assert sample_product.stock == starting_stock - 3


def test_empty_cart_checkout_redirects_home(client, sample_customer):
    login(client, sample_customer.email, "password123")
    resp = client.get("/checkout", follow_redirects=True)
    assert b"cart is empty" in resp.data.lower()
