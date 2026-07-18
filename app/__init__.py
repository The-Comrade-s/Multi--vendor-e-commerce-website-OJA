import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, jsonify, request

from app.config import Config
from app.extensions import db, login_manager, migrate, mail, csrf, limiter, jwt, cors


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    _configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Website blueprints (cookie-session auth via Flask-Login) ---
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.vendor.routes import vendor_bp
    from app.admin.routes import admin_bp
    from app.payments.routes import payments_bp
    from app.chat.routes import chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(vendor_bp, url_prefix="/vendor")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(chat_bp, url_prefix="/chat")

    # Payment webhooks accept raw provider POSTs — exempt from CSRF
    csrf.exempt(payments_bp)

    # --- Mobile API blueprints (stateless JWT auth — shared backend/DB with
    # the website above; same models, same services, no duplicated logic) ---
    from app.api.auth import auth_api_bp
    from app.api.catalog import catalog_api_bp
    from app.api.cart import cart_api_bp
    from app.api.orders import orders_api_bp
    from app.api.wishlist import wishlist_api_bp
    from app.api.addresses import addresses_api_bp
    from app.api.vendor import vendor_api_bp
    from app.api.chat import chat_api_bp
    from app.api.notifications import notifications_api_bp
    from app.api.payments import payments_api_bp

    api_blueprints = [
        auth_api_bp, catalog_api_bp, cart_api_bp, orders_api_bp, wishlist_api_bp,
        addresses_api_bp, vendor_api_bp, chat_api_bp, notifications_api_bp, payments_api_bp,
    ]
    for bp in api_blueprints:
        app.register_blueprint(bp, url_prefix="/api/v1" + bp.url_prefix if bp.url_prefix else "/api/v1")
        # JWT-authenticated JSON API — CSRF tokens don't apply (no cookies
        # involved in auth), so these routes are exempt like the payment
        # webhooks above.
        csrf.exempt(bp)

    @app.route("/healthz")
    def healthz():
        """Lightweight liveness/readiness check for Railway's healthcheck probe."""
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "ok"}, 200
        except Exception as exc:
            app.logger.error("Healthcheck DB probe failed: %s", exc)
            return {"status": "error", "detail": "database unreachable"}, 503

    def _wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify(error="Forbidden"), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify(error="Not found"), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def too_many_requests(e):
        if _wants_json():
            return jsonify(error="Too many requests — please slow down."), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        if _wants_json():
            return jsonify(error="Internal server error"), 500
        return render_template("errors/500.html"), 500

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from app.models import CartItem, Notification

        cart_count = 0
        unread_notifications = 0
        if current_user.is_authenticated:
            if current_user.is_customer:
                cart_count = sum(
                    item.quantity for item in CartItem.query.filter_by(user_id=current_user.id).all()
                )
            unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()

        return {
            "platform_name": app.config["PLATFORM_NAME"],
            "currency": app.config["CURRENCY_SYMBOL"],
            "cart_count": cart_count,
            "unread_notifications": unread_notifications,
        }

    @app.template_filter("naira")
    def naira_filter(value):
        try:
            return f"{app.config['CURRENCY_SYMBOL']}{float(value):,.0f}"
        except (TypeError, ValueError):
            return value
    with app.app_context():
    db.create_all()

    return app


def _configure_logging(app):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(os.path.join(log_dir, "oja.log"), maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s [in %(pathname)s:%(lineno)d]"
    ))
    handler.setLevel(logging.INFO)

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
