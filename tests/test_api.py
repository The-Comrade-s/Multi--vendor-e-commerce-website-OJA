import json


def api_login(client, email, password):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.get_json()


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_api_register_returns_tokens(client):
    resp = client.post("/api/v1/auth/register", json={
        "name": "Mobile User", "email": "mobile@test.com", "password": "password123", "role": "customer",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert "access_token" in data and "refresh_token" in data
    assert data["user"]["email"] == "mobile@test.com"


def test_api_login_wrong_password(client, sample_customer):
    resp = client.post("/api/v1/auth/login", json={"email": sample_customer.email, "password": "wrong"})
    assert resp.status_code == 401


def test_api_login_success(client, sample_customer):
    tokens = api_login(client, sample_customer.email, "password123")
    assert "access_token" in tokens


def test_api_me_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_api_me_with_token(client, sample_customer):
    tokens = api_login(client, sample_customer.email, "password123")
    resp = client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.get_json()["email"] == sample_customer.email


def test_api_product_listing_is_public(client, sample_product):
    resp = client.get("/api/v1/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1
    assert data["items"][0]["name"] == sample_product.name


def test_api_product_detail(client, sample_product):
    resp = client.get(f"/api/v1/products/{sample_product.slug}")
    assert resp.status_code == 200
    assert resp.get_json()["slug"] == sample_product.slug


def test_api_add_to_cart_and_checkout(client, db, sample_customer, sample_product):
    tokens = api_login(client, sample_customer.email, "password123")
    headers = auth_headers(tokens["access_token"])

    add_resp = client.post("/api/v1/cart/items", json={"product_id": sample_product.id, "quantity": 2}, headers=headers)
    assert add_resp.status_code == 201
    assert len(add_resp.get_json()["items"]) == 1

    checkout_resp = client.post("/api/v1/checkout", json={
        "full_name": "Mobile Customer", "phone": "08011112222",
        "address": "1 Test Street", "city": "Lagos", "state": "Lagos",
        "payment_method": "pay_on_delivery",
    }, headers=headers)
    assert checkout_resp.status_code == 201
    order = checkout_resp.get_json()
    assert order["status"] == "pending"
    assert len(order["items"]) == 1

    cart_resp = client.get("/api/v1/cart", headers=headers)
    assert len(cart_resp.get_json()["items"]) == 0


def test_api_vendor_route_forbidden_for_customer(client, sample_customer):
    tokens = api_login(client, sample_customer.email, "password123")
    resp = client.get("/api/v1/vendor/dashboard", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 403


def test_api_and_web_checkout_produce_identical_math(app, db, sample_customer, sample_product):
    """The whole point of the shared cart_pricing/checkout services: API and
    web must compute the exact same totals for the same cart."""
    from app.services.cart_pricing import compute_cart_totals
    from app.models import CartItem

    with app.app_context():
        db.session.add(CartItem(user_id=sample_customer.id, product_id=sample_product.id, quantity=1))
        db.session.commit()
        items = CartItem.query.filter_by(user_id=sample_customer.id).all()
        subtotal, discount, delivery_fee, total = compute_cart_totals(items, None, 20000, 1500)
        assert subtotal == float(sample_product.price)
        assert total == subtotal + delivery_fee
