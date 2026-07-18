from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"

mail = Mail()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])

# Used only by the /api/* blueprints (the mobile app). The website continues
# to use Flask-Login's cookie sessions untouched.
jwt = JWTManager()
cors = CORS()
