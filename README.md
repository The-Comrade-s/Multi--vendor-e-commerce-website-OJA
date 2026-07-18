# OJÀ — Multi-Vendor E-Commerce Marketplace

A working Flask + PostgreSQL multi-vendor marketplace with role-based flows for
customers, vendors, and admins. Built for the "A Web-Based Multi-Vendor
E-Commerce Web Application" HND final-year project.

## Feature coverage

**Customer**
Registration/login, email verification, password reset, browse/search with
price filters, product variants (size/colour), wishlist, cart, coupon codes,
saved addresses, checkout, card/bank-transfer/pay-on-delivery/USSD payment
options, order tracking with a delivery timeline, printable receipts,
returns/refunds requests, product reviews, in-app notifications, live chat
with vendors.

**Vendor**
Dashboard with sales stats, product CRUD with multiple photos and variants,
order management with status updates, flash-sale scheduling, coupon
creation, review replies, return/refund resolution, store profile (logo,
banner, description), sales reports with charts, customer chat inbox.

**Admin**
Platform dashboard, vendor verification, user suspension, product
moderation, category management, platform-wide coupons, return/refund
oversight, reports & analytics (revenue, top vendors, category breakdown).

**Platform-wide**
Role-based access control, CSRF protection on every form, rate limiting on
auth endpoints, structured logging, Paystack/Flutterwave payment
integration (falls back to a safe demo mode if no keys are configured).

## Mobile API (for the OJÀ Flutter app)

The website's business logic — pricing, checkout, stock, coupons — was
factored into shared services (`app/services/cart_pricing.py`,
`app/services/checkout.py`) so the mobile API and the website call the
*exact same code*, not parallel copies. The API layer under `app/api/`
just exposes that logic over JSON with JWT auth instead of cookie sessions.

- Base URL: `/api/v1/...`
- Auth: `Authorization: Bearer <access_token>` header (JWT, 30 min access /
  30 day refresh — see `POST /api/v1/auth/refresh`)
- Full endpoint groups: `auth`, `products`/`categories`/`vendors` (catalog,
  public), `cart`, `checkout`/`orders`/`returns`, `wishlist`, `addresses`,
  `vendor/*` (vendor-role only), `chat`, `notifications`, `payments`
- The website keeps using Flask-Login cookie sessions untouched — the two
  auth systems are independent but point at the same `User` table, so the
  same email/password logs into either one.
- CORS is enabled for `/api/*` only (native Flutter doesn't need it, but
  Flutter Web builds and browser-based testing do).
- Chat now supports optional image attachments (`Message.image_filename`)
  on both the website and the API, per the mobile spec's "image sharing if
  the backend supports it" requirement.

See `oja_mobile/README.md` (in the Flutter project) for the full endpoint
reference the app consumes.

## What still needs your input before a real launch

- **Payment gateway keys** — card payments run in demo mode (instantly
  marked paid) until you add real `PAYSTACK_SECRET_KEY` /
  `FLUTTERWAVE_SECRET_KEY` values. Get these from your Paystack/Flutterwave
  dashboard (test keys first, then live keys when ready for real money).
- **Email/SMTP credentials** — without `MAIL_USERNAME`/`MAIL_PASSWORD`,
  verification and password-reset emails are logged to the console instead
  of sent. Any SMTP provider works (Gmail app password, SendGrid, etc.).
- **Persistent file storage** — product photos and store logos currently
  save to local disk (`app/static/uploads`). Railway's default filesystem is
  **ephemeral** — files vanish on every redeploy/restart, unless you attach
  a [Railway Volume](https://docs.railway.app/reference/volumes) mounted at
  that path. Fine for testing, but swap in Cloudinary or AWS S3 (a few
  lines in `app/services/uploads.py`) before a real launch either way.
- **Database migrations** — `seed.py` calls `db.create_all()`, which is
  enough to stand up a fresh database. If you change `models.py` after
  going live, run migrations against Railway via the Railway CLI:
  `railway run flask db init` (once), then `railway run flask db migrate`
  and `railway run flask db upgrade` for each schema change, instead of
  dropping data.

## Run locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # edit SECRET_KEY, and add mail/payment keys if you have them
python seed.py                  # creates tables + demo data (SQLite by default)
python wsgi.py                  # runs on http://127.0.0.1:5000
```

### Run the test suite

```bash
pip install -r requirements-dev.txt
pytest
```

Covers: password hashing, product pricing/stock logic, registration,
login/RBAC gating, cart & checkout (including stock decrement), vendor
verification gating, and admin vendor approval.

### Demo logins (created by seed.py)

| Role     | Email               | Password    |
|----------|----------------------|-------------|
| Admin    | admin@oja.ng         | admin123    |
| Vendor   | techhub@oja.ng       | vendor123   |
| Customer | chidinma@oja.ng      | customer123 |

Seeded coupons: `WELCOME10` (10% off, platform-wide) and `TECHHUB15` (15%
off, TechHub Lagos products only). New customer/vendor accounts can also
register through the sign-up page — new vendors start as "pending" and need
admin approval (log in as admin → Vendors → Approve) before they can
publish products.

## Deploy to Railway + Supabase (for testing with multiple people)

The app runs on **Railway** (hosting) with **Supabase** as the managed
Postgres database. Railway builds with Nixpacks automatically — no
Dockerfile needed — and reads `railway.json` for the start command and
healthcheck.

### 1. Set up the database on Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → Database → Connection string → URI**.
3. Copy the **connection pooling** URI (port `6543`, not the direct `5432`
   one) — Railway's workers are short-lived and benefit from Supabase's
   pgbouncer pool.
4. Keep this handy for step 3 below; you'll set it as `DATABASE_URL`.

### 2. Deploy the app on Railway

1. Push this project to a GitHub repo.
2. In Railway, choose **New Project → Deploy from GitHub repo** and select it.
3. Railway detects `railway.json` and Nixpacks builds it automatically using
   `requirements.txt` — no build command needed from you.
4. Go to the service's **Variables** tab and add:
   - `SECRET_KEY` — any long random string (Railway can generate one)
   - `DATABASE_URL` — the Supabase connection-pooling URI from step 1
   - Optionally: `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`,
     `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`,
     `FLUTTERWAVE_SECRET_KEY`, `FLUTTERWAVE_PUBLIC_KEY`.
     Everything works without these — they just unlock real email/payments.
   - Railway automatically sets `PORT` and `RAILWAY_ENVIRONMENT` — you don't
     need to add those yourself; the app reads them directly.
5. Deploy. Railway assigns a public URL under **Settings → Networking →
   Generate Domain** if one isn't already attached.
6. Once live, open the Railway service's **Shell** (or run locally with
   `railway run python seed.py` after `railway link`) and run:
   ```bash
   python seed.py
   ```
   to create the tables (via `db.create_all()`) and load demo data on
   the Supabase database.

### Notes

- The `/healthz` endpoint (checked by `railway.json`) pings the database
  with `SELECT 1` — if Railway shows the deploy as unhealthy, check that
  `DATABASE_URL` is set correctly first.
- Free Railway usage sleeps/limits after a monthly credit runs out, not
  after inactivity like some other platforms — check your current plan's
  limits in the Railway dashboard.
- **CI/CD:** Railway auto-deploys on every push to your connected branch
  by default — no separate CD config is required. A GitHub Actions
  workflow at `.github/workflows/tests.yml` runs the pytest suite on every
  push/PR to `main` so broken code is caught before it reaches the branch
  Railway watches; it doesn't deploy anything itself, Railway's own GitHub
  integration handles that.

## Project structure

```
oja/
  app/
    auth/        registration, login, logout, email verification, password reset
    main/        customer storefront (home, product, cart, checkout, orders, addresses, returns, notifications)
    vendor/      vendor dashboard, products, coupons, flash sales, reviews, returns, reports, settings
    admin/       admin dashboard, vendor verification, users, products, categories, coupons, returns, reports
    payments/    Paystack/Flutterwave initiation, callbacks, receipts
    chat/        customer <-> vendor messaging
    services/    email, tokens (verify/reset), notifications, payment gateways, file uploads
    templates/   Jinja templates (Tailwind CDN + Bootstrap Icons, OJÀ palette)
    models.py    SQLAlchemy models
    config.py    reads all settings from environment variables
  tests/         pytest suite
  seed.py        sample Nigerian marketplace data (products, variants, coupons)
  wsgi.py        gunicorn entry point
  railway.json   Railway build/deploy config (Nixpacks, start command, healthcheck)
  Procfile       fallback start command (also read by Railway/Nixpacks)
  requirements.txt / requirements-dev.txt
```

## Honest limitations

- Product images are stored on local disk — see the file-storage note above
  before a real production launch.
- Chat is polling-based (refresh to see new messages), not real-time
  websockets — fine for a class demo, worth upgrading with Flask-SocketIO
  for production.
- Payment gateways are integrated against their real REST APIs but only
  verified by static code review in this environment (no internet access
  was available to actually run `pip install` and hit Paystack/Flutterwave's
  live endpoints during development) — test with real sandbox keys before
  trusting it with real transactions.
