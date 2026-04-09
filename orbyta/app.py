import os

from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

APP_DIR = os.path.dirname(os.path.abspath(__file__))

from core.config import env_bool
from core.constants import JSON_FILES
from core.json_db import iniciar_banco_json
from services.reminder_service import start_reminder_worker

from routes.publicas import publicas_bp
from routes.auth_routes import auth_bp
from routes.cliente_routes import cliente_bp
from routes.funcionario_routes import funcionario_bp
from routes.dono_routes import dono_bp
from routes.admin_routes import admin_bp
from routes.api_routes import api_bp
from routes.pagamento_routes import pagamento_bp


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(APP_DIR, "templates"),
        static_folder=os.path.join(APP_DIR, "static"),
        root_path=APP_DIR,
    )
    app.secret_key = os.getenv("SECRET_KEY", "dev-trocar-secret-key")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = env_bool("SESSION_COOKIE_SECURE", False)
    app.config["PREFERRED_URL_SCHEME"] = os.getenv("PREFERRED_URL_SCHEME", "https" if app.config["SESSION_COOKIE_SECURE"] else "http")
    app.config["SESSION_COOKIE_NAME"] = os.getenv("SESSION_COOKIE_NAME", "orbyta_session")

    if env_bool("TRUST_PROXY", True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": "orbyta"}), 200

    iniciar_banco_json(JSON_FILES)

    app.register_blueprint(publicas_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cliente_bp)
    app.register_blueprint(funcionario_bp)
    app.register_blueprint(dono_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(pagamento_bp)

    if env_bool("ENABLE_REMINDER_WORKER", True):
        should_start_worker = (not env_bool("FLASK_DEBUG", False)) or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        if should_start_worker:
            start_reminder_worker(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=env_bool("FLASK_DEBUG", False),
    )