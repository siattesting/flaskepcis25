from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from werkzeug.exceptions import HTTPException

# Import extensions and config
from .models import User, db, alembic
from .config import config_by_name

# Initialize standalone extensions
jwt = JWTManager()
login_manager = LoginManager() # <--- Initialize

def create_app(config_name=None):
    """
    Application Factory Pattern.
    Creates and configures the Flask application.
    """
    if config_name is None:
        import os
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # 2. Register Global Error Handlers
    register_error_handlers(app)

    # 3. Initialize Extensions
    # This reads app.config['SQLALCHEMY_ENGINES'] and sets up the connection
    db.init_app(app)
    alembic.init_app(app)

    jwt.init_app(app)

    # --- Setup Flask-Login ---
    login_manager.init_app(app)
    login_manager.login_view = "ui.login" # Redirect here if unauthorized
    login_manager.login_message_category = "danger" # Bootstrap class for errors

    # 4. Register Blueprints
    from .routes.auth import auth_bp
    from .routes.events import events_bp
    from .routes.products import products_bp
    from .routes.ui import ui_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(events_bp, url_prefix="/events")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(ui_bp, url_prefix="/")


    @app.route('/')
    def index():
        return "<h2>Flask app. it works!</h2>"
    
    @app.route("/health")
    def health_check():
        """Simple health check for Docker/Load Balancers."""
        return jsonify({"status": "healthy", "env": config_name}), 200

    return app

# Error handlers
def register_error_handlers(app):
    """Standardize JSON error responses."""
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Return JSON instead of HTML for HTTP errors."""
        response = e.get_response()
        response.data = jsonify({
            "code": e.code,
            "name": e.name,
            "description": e.description,
        }).data
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def handle_generic_exception(e):
        """Catch-all for 500 errors."""
        # In production, log this error to a file or monitoring service
        app.logger.error(f"Unhandled Exception: {e}", exc_info=True)
        return jsonify({
            "code": 500,
            "name": "Internal Server Error",
            "description": "An unexpected error occurred."
        }), 500
    
# --- Helper to Load User from Session ---
@login_manager.user_loader
def load_user(user_id):
    """Refreshes the user object from the DB using the ID in the cookie."""
    # Note: flask-sqlalchemy-lite syntax
    return db.session.get(User, user_id)