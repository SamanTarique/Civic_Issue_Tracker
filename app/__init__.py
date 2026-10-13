import secrets
from pathlib import Path

from flask import Flask, abort, render_template, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "error"
limiter = Limiter(key_func=get_remote_address)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    module = getattr(dbapi_connection, "__class__", type(dbapi_connection)).__module__
    if "sqlite" not in module:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    if test_config:
        app.config.from_mapping(test_config)
        app.config.setdefault("RATELIMIT_ENABLED", False)
        app.config.setdefault("DEBUG", False)
        app.config.setdefault("AUTO_CONFIRM_DAYS", 7)
        app.config.setdefault("PUBLIC_PIN_LIMIT", 200)
        app.config.setdefault("THUMB_MAX_EDGE", 320)
        app.config.setdefault("PAGE_SIZE", 20)
        app.config.setdefault("APP_ENV", "testing")
        app.config.setdefault("SESSION_COOKIE_SECURE", False)
        app.config.setdefault("REMEMBER_COOKIE_DURATION_DAYS", 30)
        from datetime import timedelta

        app.config.setdefault("REMEMBER_COOKIE_DURATION", timedelta(days=30))
        app.config.setdefault("REMEMBER_COOKIE_HTTPONLY", True)
        app.config.setdefault("REMEMBER_COOKIE_SAMESITE", "Lax")
        app.config.setdefault("REMEMBER_COOKIE_SECURE", False)
        app.config.setdefault("FIREBASE_PROJECT_ID", "demo-project")
        app.config.setdefault("FIREBASE_WEB_API_KEY", "test-web-key")
        app.config.setdefault("FIREBASE_AUTH_DOMAIN", "demo-project.firebaseapp.com")
        app.config.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "")
        app.config.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "")
    else:
        from app.config import Config

        app.config.from_object(Config())
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError("Set SECRET_KEY in your .env file (see .env.example).")
    env = (app.config.get("APP_ENV") or "")
    if env == "production":
        secret = (app.config.get("SECRET_KEY") or "").strip()
        example_secrets = {
            "",
            "replace-with-a-long-random-string",
            "changeme",
            "secret",
        }
        if secret in example_secrets:
            raise RuntimeError("SECRET_KEY must be set to a unique value in production.")
        if app.config.get("TESTING"):
            raise RuntimeError("TESTING must not be true when APP_ENV=production.")
        if (app.config.get("FIREBASE_AUTH_EMULATOR_HOST") or "").strip():
            raise RuntimeError(
                "FIREBASE_AUTH_EMULATOR_HOST must not be set when APP_ENV=production."
            )
    if app.config.get("TESTING"):
        app.config["PASSWORD_HASH_METHOD"] = "pbkdf2:sha256:1"
    else:
        app.config["PASSWORD_HASH_METHOD"] = "pbkdf2:sha256:260000"
    app.config.setdefault("DUPLICATE_RADIUS_M", 40)
    app.config.setdefault("DUPLICATE_DAYS", 30)
    app.config.setdefault("PHOTO_MIN_EDGE", 64)
    app.config.setdefault("PHOTO_BLUR_MIN_VARIANCE", 12.0)
    app.config.setdefault("PHOTO_DARK_MEAN", 18.0)
    app.config.setdefault("PHOTO_BRIGHT_MEAN", 237.0)
    app.config.setdefault("PHOTO_DHASH_MAX_DISTANCE", 10)
    app.config.setdefault("PHOTO_AI_ENABLED", False)
    app.config.setdefault("EMAIL_BACKEND", "console")
    app.config.setdefault("EMAIL_FOR_DEMO", False)
    app.config.setdefault("EMAIL_TIMEOUT", 8)
    app.config.setdefault("DEMO_MODE", False)
    app.config.setdefault("DEPT_EMAIL_ROADS", "")
    app.config.setdefault("DEPT_EMAIL_SANITATION", "")
    app.config.setdefault("DEPT_EMAIL_WATER", "")
    app.config.setdefault("DEPT_EMAIL_ELECTRIC", "")
    app.config.setdefault("DEPT_EMAIL_OTHER", "")
    app.config.setdefault(
        "CATEGORY_DEPARTMENT",
        {
            "pothole": "Roads",
            "garbage": "Sanitation",
            "streetlight": "Electric",
            "water": "Water",
            "other": "Other",
        },
    )

    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    uri = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "")
    if uri.startswith("sqlite"):
        app.config.setdefault(
            "SQLALCHEMY_ENGINE_OPTIONS",
            {"connect_args": {"check_same_thread": False, "timeout": 30}},
        )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from app.blueprints.auth import auth_bp
    from app.blueprints.citizen import citizen_bp
    from app.blueprints.public import public_bp
    from app.blueprints.staff import staff_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(citizen_bp)
    app.register_blueprint(staff_bp)

    @app.context_processor
    def inject_globals():
        from app.config import category_label
        from app.services.status_machine import status_label

        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return {
            "csrf_token": session["csrf_token"],
            "status_label": status_label,
            "category_label": category_label,
            "categories": app.config["CATEGORIES"],
        }

    @app.before_request
    def validate_csrf():
        csrf_on = app.config.get("CSRF_ENABLED")
        if csrf_on is None:
            csrf_on = not app.config.get("TESTING")
        if not csrf_on:
            return
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            abort(400)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-DNS-Prefetch-Control"] = "off"
        from flask_login import current_user

        google_account = (
            request.endpoint == "auth.account"
            and current_user.is_authenticated
            and getattr(current_user, "auth_provider", None) == "google"
        )
        firebase_page = request.endpoint == "auth.login" or google_account
        if firebase_page:
            connect = (
                "connect-src 'self' https://identitytoolkit.googleapis.com "
                "https://securetoken.googleapis.com https://www.googleapis.com"
            )
            if (app.config.get("APP_ENV") or "") == "development":
                connect += " http://127.0.0.1:* http://localhost:*"
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
                "style-src 'self'; "
                "script-src 'self'; "
                + connect
                + "; "
                "frame-src https://accounts.google.com https://*.firebaseapp.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
                "style-src 'self'; "
                "script-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        if request.endpoint == "citizen.new_report":
            response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        else:
            response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        if request.endpoint in {"auth.login", "auth.register", "auth.account"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def too_many(_error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("errors/500.html"), 500

    _register_cli(app)

    with app.app_context():
        db.create_all()
        _ensure_sqlite_user_auth_columns()
        if not app.config.get("TESTING"):
            from app.models import ensure_staff_user

            ensure_staff_user()

    return app


def _ensure_sqlite_user_auth_columns():
    uri = str(db.engine.url)
    if not uri.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import IntegrityError

    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "firebase_uid" not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(128)"))
    if "auth_provider" not in cols:
        db.session.execute(
            text("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(32) NOT NULL DEFAULT 'password'")
        )
    db.session.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_firebase_uid ON users (firebase_uid)")
    )
    if "department" not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN department VARCHAR(32)"))
    unique_index_ready = True
    try:
        with db.session.begin_nested():
            db.session.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_ci_unique "
                    "ON users (lower(trim(email)))"
                )
            )
    except IntegrityError:
        unique_index_ready = False
    if not unique_index_ready:
        db.session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_users_email_ci_lookup ON users (lower(trim(email)))")
        )
    issue_cols = {c["name"] for c in inspector.get_columns("issues")} if "issues" in inspector.get_table_names() else set()
    if issue_cols and "possible_duplicate" not in issue_cols:
        db.session.execute(
            text("ALTER TABLE issues ADD COLUMN possible_duplicate BOOLEAN NOT NULL DEFAULT 0")
        )
    if issue_cols and "is_demo" not in issue_cols:
        db.session.execute(text("ALTER TABLE issues ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT 0"))
    if issue_cols and "needs_review" not in issue_cols:
        db.session.execute(text("ALTER TABLE issues ADD COLUMN needs_review BOOLEAN NOT NULL DEFAULT 0"))
    photo_cols = (
        {c["name"] for c in inspector.get_columns("issue_photos")}
        if "issue_photos" in inspector.get_table_names()
        else set()
    )
    if photo_cols and "dhash" not in photo_cols:
        db.session.execute(text("ALTER TABLE issue_photos ADD COLUMN dhash VARCHAR(16)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_issue_photos_dhash ON issue_photos (dhash)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_issues_lat ON issues (lat)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_issues_lng ON issues (lng)"))
    db.session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS issue_supporters ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "issue_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, "
            "created_at DATETIME NOT NULL, "
            "FOREIGN KEY(issue_id) REFERENCES issues (id), "
            "FOREIGN KEY(user_id) REFERENCES users (id), "
            "UNIQUE (issue_id, user_id)"
            ")"
        )
    )
    db.session.commit()


def _register_cli(app):
    @app.cli.command("auto-confirm")
    def auto_confirm_command():
        from app.services.issues import auto_confirm_stale

        count = auto_confirm_stale()
        print("Auto-confirmed " + str(count) + " issue(s).")

    @app.cli.command("find-orphan-uploads")
    def find_orphan_uploads_command():
        from app.services.images import find_orphan_uploads

        orphans = find_orphan_uploads()
        if not orphans:
            print("No orphan upload files.")
            return
        print("Orphan files:")
        for name in orphans:
            print(name)

    @app.cli.command("backfill-thumbnails")
    def backfill_thumbnails_command():
        from app.services.images import backfill_thumbnails

        count = backfill_thumbnails()
        print("Wrote " + str(count) + " thumbnail(s).")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        from app.services.seed_demo import seed_demo

        try:
            seed_demo()
        except RuntimeError as exc:
            print(str(exc))
            raise SystemExit(1) from exc
