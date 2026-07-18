import pytest

from app import create_app
from app.config import Config
from app.extensions import db as _db
from app.models import User, VendorProfile, Category, Product


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # simplifies posting from the test client
    SECRET_KEY = "test-secret-key"
    MAIL_USERNAME = None  # forces console-mode email (no real sending in tests)
    RATELIMIT_ENABLED = False


@pytest.fixture
def app():
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def sample_category(db):
    cat = Category(name="Electronics", slug="electronics", icon="bi-phone")
    db.session.add(cat)
    db.session.commit()
    return cat


@pytest.fixture
def sample_vendor(db):
    user = User(name="Test Vendor", email="vendor@test.com", role="vendor", is_email_verified=True)
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()

    profile = VendorProfile(user_id=user.id, store_name="Test Store", store_slug="test-store", status="verified")
    db.session.add(profile)
    db.session.commit()
    return profile


@pytest.fixture
def sample_customer(db):
    user = User(name="Test Customer", email="customer@test.com", role="customer", is_email_verified=True)
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_product(db, sample_vendor, sample_category):
    product = Product(
        vendor_id=sample_vendor.id,
        category_id=sample_category.id,
        name="Test Wireless Earbuds",
        slug="test-wireless-earbuds",
        price=15000,
        compare_at_price=20000,
        stock=25,
        icon="bi-headphones",
        status="active",
    )
    db.session.add(product)
    db.session.commit()
    return product


def login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)
