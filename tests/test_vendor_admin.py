from tests.conftest import login
from app.models import Product, VendorProfile


def test_unverified_vendor_cannot_add_product(client, db, sample_category):
    from app.models import User
    user = User(name="Pending Vendor", email="pending@test.com", role="vendor", is_email_verified=True)
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    profile = VendorProfile(user_id=user.id, store_name="Pending Store", store_slug="pending-store", status="pending")
    db.session.add(profile)
    db.session.commit()

    login(client, "pending@test.com", "password123")
    resp = client.get("/vendor/products/add", follow_redirects=True)
    assert b"awaiting admin verification" in resp.data.lower()


def test_verified_vendor_can_add_product(client, db, sample_vendor, sample_category):
    login(client, "vendor@test.com", "password123")
    resp = client.post("/vendor/products/add", data={
        "name": "New Gadget", "category_id": sample_category.id,
        "price": "9999", "stock": "10", "icon": "bi-box-seam",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.filter_by(name="New Gadget").first() is not None


def test_vendor_cannot_edit_other_vendors_product(client, db, sample_vendor, sample_product, sample_category):
    from app.models import User
    other = User(name="Other Vendor", email="other@test.com", role="vendor", is_email_verified=True)
    other.set_password("password123")
    db.session.add(other)
    db.session.flush()
    other_profile = VendorProfile(user_id=other.id, store_name="Other Store", store_slug="other-store", status="verified")
    db.session.add(other_profile)
    db.session.commit()

    login(client, "other@test.com", "password123")
    resp = client.get(f"/vendor/products/{sample_product.id}/edit")
    assert resp.status_code == 403


def test_admin_can_verify_pending_vendor(client, db, sample_category):
    from app.models import User
    admin = User(name="Admin", email="admin@test.com", role="admin", is_email_verified=True)
    admin.set_password("password123")
    db.session.add(admin)

    vendor_user = User(name="Vendor", email="v2@test.com", role="vendor", is_email_verified=True)
    vendor_user.set_password("password123")
    db.session.add(vendor_user)
    db.session.flush()
    profile = VendorProfile(user_id=vendor_user.id, store_name="V2 Store", store_slug="v2-store", status="pending")
    db.session.add(profile)
    db.session.commit()

    login(client, "admin@test.com", "password123")
    resp = client.post(f"/admin/vendors/{profile.id}/status", data={"status": "verified"}, follow_redirects=True)
    assert resp.status_code == 200

    db.session.refresh(profile)
    assert profile.status == "verified"


def test_non_admin_cannot_access_admin_dashboard(client, sample_customer):
    login(client, sample_customer.email, "password123")
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 403
