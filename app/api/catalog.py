from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Product, Category, Review
from app.api.decorators import get_current_api_user, error_response
from app.api.serializers import serialize_category, serialize_product_card, serialize_product_detail, serialize_review

catalog_api_bp = Blueprint("catalog_api", __name__)


@catalog_api_bp.route("/categories", methods=["GET"])
def categories():
    return jsonify([serialize_category(c) for c in Category.query.all()])


@catalog_api_bp.route("/products", methods=["GET"])
def products():
    """Listing endpoint powering Home, Category, and Search screens.

    Query params: category (slug), q (search), min_price, max_price,
    flash_sale=1, sort=newest|price_low|price_high, page, per_page.
    """
    query = Product.query.filter_by(status="active")

    category_slug = request.args.get("category")
    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first()
        if not cat:
            return error_response("Unknown category.", 404)
        query = query.filter_by(category_id=cat.id)

    q = request.args.get("q", "").strip()
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))

    min_price = request.args.get("min_price", type=float)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    max_price = request.args.get("max_price", type=float)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if request.args.get("flash_sale") == "1":
        query = query.filter_by(is_flash_sale=True)

    sort = request.args.get("sort", "newest")
    if sort == "price_low":
        query = query.order_by(Product.price.asc())
    elif sort == "price_high":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 50)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [serialize_product_card(p) for p in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    })


@catalog_api_bp.route("/products/<slug>", methods=["GET"])
def product_detail(slug):
    product = Product.query.filter_by(slug=slug).first()
    if not product:
        return error_response("Product not found.", 404)
    return jsonify(serialize_product_detail(product))


@catalog_api_bp.route("/products/<slug>/related", methods=["GET"])
def product_related(slug):
    product = Product.query.filter_by(slug=slug).first()
    if not product:
        return error_response("Product not found.", 404)
    related = (
        Product.query.filter(Product.category_id == product.category_id, Product.id != product.id, Product.status == "active")
        .limit(8).all()
    )
    return jsonify([serialize_product_card(p) for p in related])


@catalog_api_bp.route("/products/<slug>/reviews", methods=["GET"])
def list_reviews(slug):
    product = Product.query.filter_by(slug=slug).first()
    if not product:
        return error_response("Product not found.", 404)
    page = request.args.get("page", 1, type=int)
    pagination = product.reviews.order_by(Review.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return jsonify({
        "items": [serialize_review(r) for r in pagination.items],
        "page": pagination.page, "pages": pagination.pages, "total": pagination.total,
    })


@catalog_api_bp.route("/products/<slug>/reviews", methods=["POST"])
@jwt_required()
def add_review(slug):
    user = get_current_api_user()
    if not user.is_customer:
        return error_response("Only customers can leave reviews.", 403)

    product = Product.query.filter_by(slug=slug).first()
    if not product:
        return error_response("Product not found.", 404)

    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    comment = (data.get("comment") or "").strip()
    if not rating or not (1 <= int(rating) <= 5):
        return error_response("rating must be between 1 and 5.")

    review = Review(product_id=product.id, user_id=user.id, rating=int(rating), comment=comment)
    db.session.add(review)
    db.session.commit()
    return jsonify(serialize_review(review)), 201


@catalog_api_bp.route("/vendors/<slug>", methods=["GET"])
def vendor_store(slug):
    from app.models import VendorProfile
    from app.api.serializers import serialize_vendor_full

    vendor = VendorProfile.query.filter_by(store_slug=slug).first()
    if not vendor:
        return error_response("Store not found.", 404)

    page = request.args.get("page", 1, type=int)
    pagination = vendor.products.filter_by(status="active").order_by(Product.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    data = serialize_vendor_full(vendor)
    data["products"] = {
        "items": [serialize_product_card(p) for p in pagination.items],
        "page": pagination.page, "pages": pagination.pages, "total": pagination.total,
    }
    return jsonify(data)
