import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def _normalize_database_url(raw_url: str) -> str:
    """Normalizes a Postgres connection string for SQLAlchemy + Supabase.

    - Supabase (and some other providers) hand out URLs starting with
      "postgres://", but SQLAlchemy 1.4+/2.x requires the "postgresql://"
      scheme, so we rewrite it here.
    - Supabase's connection pooler requires SSL for external connections.
      We append sslmode=require if the caller hasn't already specified one
      (e.g. for a local Postgres instance without SSL, just set DATABASE_URL
      with your own sslmode= param, or use the sqlite default for local dev).
    """
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    if raw_url.startswith("postgresql://") and "sslmode=" not in raw_url:
        separator = "&" if "?" in raw_url else "?"
        raw_url = f"{raw_url}{separator}sslmode=require"

    return raw_url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # DATABASE_URL is provided by Supabase (Project Settings -> Database ->
    # Connection string -> URI). Set it as a Railway environment variable.
    # Falls back to local SQLite when unset, for local development without
    # a Postgres instance on hand.
    _db_url = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(basedir, "oja.db"))
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(_db_url)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Recycle/pre-ping connections so long-idle Railway workers don't hand out
    # dead connections after Supabase's pooler times them out.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "pool_recycle": 280}
        if SQLALCHEMY_DATABASE_URI.startswith("postgresql://")
        else {}
    )

    ITEMS_PER_PAGE = 12
    PLATFORM_NAME = "OJÀ"
    CURRENCY_SYMBOL = "\u20A6"

    FREE_DELIVERY_THRESHOLD = 20000
    FLAT_DELIVERY_FEE = 1500

    # --- File uploads (product images, store logos/banners) ---
    # NOTE: Railway's default filesystem is ephemeral per-deploy — uploaded
    # files are wiped on every redeploy/restart unless you attach a Railway
    # Volume mounted at this path (Railway dashboard -> service -> Volumes).
    # For a real production launch, prefer a persistent object store such as
    # Cloudinary or AWS S3 over local disk regardless.
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB per upload
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

    # --- Email (Flask-Mail) ---
    # Leave MAIL_USERNAME unset to run in "console mode": emails are printed
    # to the server log instead of actually sent, which is fine for testing.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@oja.ng")

    # --- Payment gateways ---
    # These are unset (demo mode) by default. Add TEST/SANDBOX keys first,
    # then live keys only once you're ready to accept real money.
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    FLUTTERWAVE_SECRET_KEY = os.environ.get("FLUTTERWAVE_SECRET_KEY", "")
    FLUTTERWAVE_PUBLIC_KEY = os.environ.get("FLUTTERWAVE_PUBLIC_KEY", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True

    # Railway sets RAILWAY_ENVIRONMENT automatically (e.g. "production") on
    # every deploy. FLASK_ENV is kept as a manual override for local testing
    # against a production-like config. Either one flips on secure cookies.
    SESSION_COOKIE_SECURE = bool(os.environ.get("RAILWAY_ENVIRONMENT")) or os.environ.get("FLASK_ENV") == "production"

    # --- Mobile API (JWT) ---
    # Separate secret from SECRET_KEY on purpose: rotating the web session
    # secret shouldn't silently invalidate every mobile app's login, and
    # vice versa. Defaults to SECRET_KEY if not set, for convenience in dev.
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_TYPE = "Bearer"
    JWT_ERROR_MESSAGE_KEY = "error"

    # CORS for the /api/* blueprints. Flutter apps run natively (no browser
    # CORS restriction), but this covers Flutter Web builds and lets the
    # existing OJÀ web frontend call /api/* too if it ever needs to.
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
