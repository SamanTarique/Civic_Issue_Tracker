import re
import secrets
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, limiter
from app.models import User
from app.services.firebase_auth import TokenError, delete_firebase_user, verify_id_token
from app.services.issues import ReportError, delete_citizen_account

auth_bp = Blueprint("auth", __name__)
_GOOGLE_FAIL = "Google sign-in failed."


def _dummy_hash():
    cached = current_app.config.get("_DUMMY_PASSWORD_HASH")
    if cached:
        return cached
    method = current_app.config.get("PASSWORD_HASH_METHOD") or "pbkdf2:sha256:260000"
    value = generate_password_hash("civic-tracker-dummy-hash", method=method)
    current_app.config["_DUMMY_PASSWORD_HASH"] = value
    return value
_EMAIL_CONFLICT = "This email already has a password account. Log in with email and password."
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _safe_next(target):
    if not target:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    if "\\" in target or ":" in target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def _rotate_session():
    session.clear()
    session["csrf_token"] = secrets.token_hex(16)


def _normalize_email(email):
    return User.normalize_email(email)


def _users_by_email(email):
    normalized = _normalize_email(email)
    if not normalized:
        return []
    return (
        User.query.filter(func.lower(func.trim(User.email)) == normalized)
        .order_by(User.id.asc())
        .limit(2)
        .all()
    )


def _single_user_by_email(email):
    users = _users_by_email(email)
    if len(users) != 1:
        return None
    return users[0]


def _firebase_web_config():
    project_id = current_app.config.get("FIREBASE_PROJECT_ID") or ""
    api_key = current_app.config.get("FIREBASE_WEB_API_KEY") or ""
    auth_domain = current_app.config.get("FIREBASE_AUTH_DOMAIN") or ""
    if not (project_id and api_key and auth_domain):
        return None
    return {
        "apiKey": api_key,
        "authDomain": auth_domain,
        "projectId": project_id,
        "emulatorHost": current_app.config.get("FIREBASE_AUTH_EMULATOR_HOST") or "",
    }


def _finish_login(user, nxt=None):
    _rotate_session()
    login_user(user, remember=True)
    if nxt:
        return redirect(nxt)
    if user.is_staff:
        return redirect(url_for("staff.queue"))
    return redirect(url_for("public.home"))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        if current_user.is_staff:
            return redirect(url_for("staff.queue"))
        return redirect(url_for("public.home"))
    if request.method == "POST":
        email = _normalize_email(request.form.get("email"))
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if not email or not _EMAIL_RE.match(email):
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Use a password of at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif request.form.get("privacy_consent") != "on":
            flash("Confirm that you have read the Privacy Policy.", "error")
        elif _users_by_email(email):
            flash("Could not create that account. Try logging in.", "error")
        else:
            user = User(email=email, role="citizen", auth_provider="password")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return _finish_login(user)
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_staff:
            return redirect(url_for("staff.queue"))
        return redirect(url_for("public.home"))
    nxt = _safe_next(request.form.get("next") or request.args.get("next"))
    if request.method == "POST":
        email = _normalize_email(request.form.get("email"))
        password = request.form.get("password") or ""
        user = _single_user_by_email(email)
        if user:
            valid = user.check_password(password)
        else:
            check_password_hash(_dummy_hash(), password)
            valid = False
        if valid:
            return _finish_login(user, nxt)
        flash("Email or password is incorrect.", "error")
    return render_template(
        "auth/login.html",
        next_url=nxt or "",
        firebase_web_config=_firebase_web_config(),
    )


@auth_bp.route("/auth/google", methods=["POST"])
@limiter.limit("5 per minute", methods=["POST"])
def google_login():
    nxt = _safe_next(request.form.get("next") or request.args.get("next"))
    try:
        claims = verify_id_token(request.form.get("id_token"))
    except TokenError:
        flash(_GOOGLE_FAIL, "error")
        return redirect(url_for("auth.login"))

    uid = claims["uid"]
    email = _normalize_email(claims["email"])
    existing_uid = User.query.filter_by(firebase_uid=uid).first()
    if existing_uid:
        if existing_uid.is_staff or existing_uid.role != "citizen":
            flash(_GOOGLE_FAIL, "error")
            return redirect(url_for("auth.login"))
        return _finish_login(existing_uid, nxt)

    existing_email = _users_by_email(email)
    if existing_email:
        flash(_EMAIL_CONFLICT, "error")
        return redirect(url_for("auth.login"))

    user = User(
        email=email,
        role="citizen",
        firebase_uid=uid,
        auth_provider="google",
        password_hash=None,
    )
    db.session.add(user)
    db.session.commit()
    return _finish_login(user, nxt)


def _clear_session_keep_logout_flags():
    remember = session.get("_remember")
    session.clear()
    if remember == "clear":
        session["_remember"] = "clear"


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    _clear_session_keep_logout_flags()
    return redirect(url_for("auth.login"))


@auth_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if current_user.is_staff:
        flash("Staff accounts cannot be deleted from this page.", "error")
        return redirect(url_for("staff.queue"))
    if request.method == "POST" and request.form.get("action") == "delete":
        user = current_user._get_current_object()
        try:
            if user.auth_provider == "google":
                claims = verify_id_token(request.form.get("id_token"), require_recent=True)
                if claims["uid"] != user.firebase_uid:
                    raise TokenError("Google sign-in failed.")
                if user.firebase_uid:
                    delete_firebase_user(user.firebase_uid)
                logout_user()
                _clear_session_keep_logout_flags()
                delete_citizen_account(user, skip_password=True)
            else:
                password = request.form.get("password") or ""
                if not user.check_password(password):
                    flash("Password is incorrect.", "error")
                    return render_template(
                        "auth/account.html",
                        firebase_web_config=_firebase_web_config(),
                    )
                logout_user()
                _clear_session_keep_logout_flags()
                delete_citizen_account(user, skip_password=True)
        except TokenError:
            flash("Sign in again to delete your account.", "error")
            return render_template(
                "auth/account.html",
                firebase_web_config=_firebase_web_config(),
            )
        except ReportError as exc:
            flash(str(exc), "error")
            return redirect(url_for("auth.login"))
        flash("Your account and reports have been deleted.", "success")
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/account.html",
        firebase_web_config=_firebase_web_config(),
    )
