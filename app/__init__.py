from flask import Flask
from app.config import Config
from app.database.db import DatabaseManager
from app.utils.decorators import get_csrf_token
from app.utils.security import SecurityService
from app.controllers.auth_controller import auth_bp
from app.controllers.admin_controller import admin_bp


def create_app(config_class=Config, init_db: bool = True) -> Flask:
    app = Flask(
        __name__,
        template_folder="views/templates",
        static_folder="views/static",
    )
    app.config.from_object(config_class)

    db = DatabaseManager(app.config["DATABASE_PATH"])
    app.extensions["db"] = db

    if init_db:
        db.init_schema()
        db.seed_default_admin(SecurityService.hash_password("Admin123"))

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_globals():
        return {"csrf_token": get_csrf_token}

    @app.after_request
    def add_security_headers(response):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    return app
