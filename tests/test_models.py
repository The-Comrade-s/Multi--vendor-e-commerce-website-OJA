from app.models import Product, Order


def test_password_hashing(sample_customer):
    assert sample_customer.check_password("password123")
    assert not sample_customer.check_password("wrong-password")


def test_product_discount_percent(sample_product):
    assert sample_product.discount_percent == 25  # (20000-15000)/20000


def test_product_stock_labels(db, sample_product):
    assert sample_product.stock_label == "In Stock"
    sample_product.stock = 5
    assert sample_product.stock_label == "Low Stock"
    sample_product.stock = 0
    assert sample_product.stock_label == "Out of Stock"


def test_product_avg_rating_with_no_reviews(sample_product):
    assert sample_product.avg_rating == 0
    assert sample_product.review_count == 0


def test_order_status_steps_include_out_for_delivery():
    assert "out_for_delivery" in Order.STATUS_STEPS
    assert Order.STATUS_STEPS.index("shipped") < Order.STATUS_STEPS.index("delivered")
