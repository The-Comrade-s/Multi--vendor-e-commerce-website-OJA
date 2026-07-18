from tests.conftest import login


def test_customer_can_register(client):
    resp = client.post("/auth/register", data={
        "name": "New Customer", "email": "new@test.com", "phone": "08011112222",
        "password": "password123", "role": "customer",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"OJ" in resp.data  # rendered home page


def test_vendor_registration_requires_store_name(client):
    resp = client.post("/auth/register", data={
        "name": "New Vendor", "email": "vendor2@test.com",
        "password": "password123", "role": "vendor", "store_name": "",
    })
    assert resp.status_code == 200
    assert b"store name" in resp.data.lower()


def test_duplicate_email_rejected(client, sample_customer):
    resp = client.post("/auth/register", data={
        "name": "Dupe", "email": sample_customer.email,
        "password": "password123", "role": "customer",
    })
    assert b"already exists" in resp.data.lower()


def test_login_with_wrong_password_fails(client, sample_customer):
    resp = login(client, sample_customer.email, "wrong-password")
    assert b"incorrect" in resp.data.lower()


def test_login_success_redirects_home(client, sample_customer):
    resp = login(client, sample_customer.email, "password123")
    assert resp.status_code == 200


def test_customer_cannot_access_vendor_dashboard(client, sample_customer):
    login(client, sample_customer.email, "password123")
    resp = client.get("/vendor/dashboard")
    assert resp.status_code == 403


def test_anonymous_redirected_from_cart(client):
    resp = client.get("/cart", follow_redirects=False)
    assert resp.status_code in (302, 401)
