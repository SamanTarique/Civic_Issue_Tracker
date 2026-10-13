import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.models import Issue, IssuePhoto, User
from app.services.firebase_auth import TokenError
from tests.conftest import app_config, register, submit_report


@patch("app.blueprints.auth.verify_id_token")
def test_valid_token_creates_citizen(mock_verify, client, app):
    mock_verify.return_value = {
        "uid": "uid-new",
        "email": "new.google@example.com",
        "auth_time": 1,
    }
    response = client.post("/auth/google", data={"id_token": "ok-token"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(firebase_uid="uid-new").one()
        assert user.email == "new.google@example.com"
        assert user.role == "citizen"
        assert user.auth_provider == "google"
        assert user.password_hash is None
        assert user.created_at is not None


@patch("app.blueprints.auth.verify_id_token", side_effect=TokenError("Google sign-in failed."))
def test_invalid_token_rejected(mock_verify, client, app):
    response = client.post("/auth/google", data={"id_token": "bad"}, follow_redirects=True)
    assert b"Google sign-in failed." in response.data
    with app.app_context():
        assert User.query.filter_by(auth_provider="google").count() == 0


@patch("app.services.firebase_auth.init_firebase_admin")
def test_verify_rejects_expired_and_wrong_audience(mock_init, app):
    from app.services import firebase_auth as fa

    with app.app_context():
        with patch("firebase_admin.auth.verify_id_token", side_effect=Exception("expired")):
            try:
                fa.verify_id_token("expired-token")
                raise AssertionError("should reject")
            except TokenError:
                pass
        with patch(
            "firebase_admin.auth.verify_id_token",
            return_value={
                "uid": "x",
                "email": "a@example.com",
                "email_verified": True,
                "aud": "other-project",
            },
        ):
            try:
                fa.verify_id_token("wrong-aud")
                raise AssertionError("should reject")
            except TokenError:
                pass


@patch("app.services.firebase_auth.init_firebase_admin")
def test_unverified_email_rejected(mock_init, app):
    from app.services import firebase_auth as fa

    with app.app_context():
        with patch(
            "firebase_admin.auth.verify_id_token",
            return_value={
                "uid": "x",
                "email": "a@example.com",
                "email_verified": False,
                "aud": "demo-project",
            },
        ):
            try:
                fa.verify_id_token("unverified")
                raise AssertionError("should reject")
            except TokenError:
                pass


@patch("app.blueprints.auth.verify_id_token")
def test_google_user_cannot_be_staff(mock_verify, client, app):
    mock_verify.return_value = {
        "uid": "staff-attempt",
        "email": "staff@example.com",
        "auth_time": 1,
    }
    response = client.post("/auth/google", data={"id_token": "tok"}, follow_redirects=True)
    assert b"password account" in response.data
    with app.app_context():
        staff = User.query.filter_by(email="staff@example.com").one()
        assert staff.is_staff
        assert staff.firebase_uid is None
    mock_verify.return_value = {
        "uid": "citizen-g",
        "email": "g.citizen@example.com",
        "auth_time": 1,
    }
    client.post("/auth/google", data={"id_token": "tok2"}, follow_redirects=True)
    with app.app_context():
        user = User.query.filter_by(email="g.citizen@example.com").one()
        assert user.role == "citizen"
        assert not user.is_staff


@patch("app.blueprints.auth.verify_id_token")
def test_existing_email_conflict_message(mock_verify, client):
    register(client, "taken.google@example.com")
    client.post("/logout")
    mock_verify.return_value = {
        "uid": "uid-conflict",
        "email": "taken.google@example.com",
        "auth_time": 1,
    }
    response = client.post("/auth/google", data={"id_token": "tok"}, follow_redirects=True)
    assert b"already has a password account" in response.data


def test_firebase_uid_unique(app):
    with app.app_context():
        first = User(
            email="one@example.com",
            firebase_uid="same-uid",
            auth_provider="google",
            role="citizen",
        )
        db.session.add(first)
        db.session.commit()
        second = User(
            email="two@example.com",
            firebase_uid="same-uid",
            auth_provider="google",
            role="citizen",
        )
        db.session.add(second)
        try:
            db.session.commit()
            raise AssertionError("expected unique uid")
        except IntegrityError:
            db.session.rollback()


def test_remember_cookie_flags(client):
    response = client.post(
        "/login",
        data={"email": "staff@example.com", "password": "staff-pass-123"},
        follow_redirects=False,
    )
    cookies = response.headers.getlist("Set-Cookie")
    remember = [item for item in cookies if "remember_token" in item.lower()]
    assert remember
    header = remember[0].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


@patch("app.blueprints.auth.verify_id_token")
def test_logout_keeps_issues_and_relogin_shows_them(mock_verify, client, app):
    mock_verify.return_value = {
        "uid": "uid-keep",
        "email": "keep@example.com",
        "auth_time": 1,
    }
    client.post("/auth/google", data={"id_token": "tok"}, follow_redirects=True)
    submit_report(client)
    with app.app_context():
        issue = Issue.query.one()
        public_id = issue.public_id
        photo_name = issue.before_photo().filename
        photo_id = issue.before_photo().id
    listed = client.get("/reports")
    assert public_id.encode() in listed.data
    assert client.get("/logout").status_code == 405
    logged_out = client.post("/logout", follow_redirects=False)
    assert logged_out.status_code in (302, 303)
    with app.app_context():
        assert Issue.query.filter_by(public_id=public_id).one()
        assert IssuePhoto.query.filter_by(id=photo_id).one()
    anon = client.get("/reports")
    assert anon.status_code in (302, 401)
    client.post("/auth/google", data={"id_token": "tok"}, follow_redirects=True)
    again = client.get("/reports")
    assert public_id.encode() in again.data
    photo = client.get(f"/reports/photos/{photo_id}")
    assert photo.status_code == 200
    with app.app_context():
        stored = Issue.query.filter_by(public_id=public_id).one()
        assert stored.before_photo().filename == photo_name


def test_logout_requires_csrf(tmp_path):
    application = create_app(app_config(tmp_path, CSRF_ENABLED=True))
    with application.app_context():
        db.create_all()
        staff = User(email="staff@example.com", role="staff")
        staff.set_password("staff-pass-123")
        db.session.add(staff)
        db.session.commit()
    csrf_client = application.test_client()
    login_page = csrf_client.get("/login")
    html = login_page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    token = html.split(marker, 1)[1].split('"', 1)[0]
    csrf_client.post(
        "/login",
        data={"email": "staff@example.com", "password": "staff-pass-123", "csrf_token": token},
    )
    blocked = csrf_client.post("/logout")
    assert blocked.status_code == 400
    queue = csrf_client.get("/staff")
    html = queue.get_data(as_text=True)
    token = html.split(marker, 1)[1].split('"', 1)[0]
    ok = csrf_client.post("/logout", data={"csrf_token": token})
    assert ok.status_code in (302, 303)


@patch("app.blueprints.auth.delete_firebase_user")
@patch("app.blueprints.auth.verify_id_token")
def test_delete_account_reauth_enforced(mock_verify, mock_delete_fb, client, app):
    mock_verify.return_value = {
        "uid": "uid-del",
        "email": "delme@example.com",
        "auth_time": 1,
    }
    client.post("/auth/google", data={"id_token": "tok"}, follow_redirects=True)
    submit_report(client)
    mock_verify.side_effect = TokenError("Google sign-in failed.")
    denied = client.post(
        "/account",
        data={"action": "delete", "id_token": "stale"},
        follow_redirects=True,
    )
    assert b"Sign in again" in denied.data
    with app.app_context():
        assert User.query.filter_by(email="delme@example.com").one()
        assert Issue.query.count() == 1
    mock_verify.side_effect = None
    mock_verify.return_value = {
        "uid": "uid-del",
        "email": "delme@example.com",
        "auth_time": 1,
    }
    mock_delete_fb.return_value = None
    gone = client.post(
        "/account",
        data={"action": "delete", "id_token": "fresh"},
        follow_redirects=True,
    )
    assert gone.status_code == 200
    mock_delete_fb.assert_called_once_with("uid-del")
    with app.app_context():
        assert User.query.filter_by(email="delme@example.com").first() is None
        assert Issue.query.count() == 0


@patch("app.blueprints.auth.verify_id_token")
def test_no_token_or_email_in_logs(mock_verify, client, caplog):
    mock_verify.side_effect = TokenError("Google sign-in failed.")
    with caplog.at_level(logging.DEBUG):
        client.post(
            "/auth/google",
            data={"id_token": "super-secret-id-token", "unused": "secret-user@example.com"},
            follow_redirects=True,
        )
        mock_verify.side_effect = None
        mock_verify.return_value = {
            "uid": "uid-keep",
            "email": "secret-user@example.com",
            "auth_time": 1,
        }
        client.post(
            "/auth/google",
            data={"id_token": "super-secret-id-token"},
            follow_redirects=True,
        )
    text = caplog.text
    assert "super-secret-id-token" not in text
    assert "secret-user@example.com" not in text
    assert "uid-keep" not in text


def test_firebase_scripts_only_on_login(client):
    login = client.get("/login")
    assert b"vendor/firebase/firebase-app-compat.js" in login.data
    assert b"Continue with Google" in login.data
    privacy = client.get("/privacy")
    assert b"vendor/firebase" not in privacy.data
    register_page = client.get("/register")
    assert b"vendor/firebase" not in register_page.data
    assert "accounts.google.com" not in privacy.headers.get("Content-Security-Policy", "")
    csp = login.headers.get("Content-Security-Policy", "")
    assert "accounts.google.com" in csp
    assert "identitytoolkit.googleapis.com" in csp
    assert login.headers.get("Cross-Origin-Opener-Policy") == "same-origin-allow-popups"
    register(client, "scripts@example.com")
    home = client.get("/")
    assert b"vendor/firebase" not in home.data
    reports = client.get("/reports")
    assert b"vendor/firebase" not in reports.data
    assert "accounts.google.com" not in home.headers.get("Content-Security-Policy", "")
    account = client.get("/account")
    assert b"vendor/firebase" not in account.data
    assert "accounts.google.com" not in account.headers.get("Content-Security-Policy", "")
    assert "127.0.0.1" not in account.headers.get("Content-Security-Policy", "")
    assert "localhost" not in login.headers.get("Content-Security-Policy", "")


@patch("app.blueprints.auth.verify_id_token")
def test_firebase_scripts_on_account_only_for_google(mock_verify, client):
    mock_verify.return_value = {
        "uid": "uid-scripts",
        "email": "gscripts@example.com",
        "auth_time": 1,
    }
    client.post("/auth/google", data={"id_token": "ok"}, follow_redirects=True)
    account = client.get("/account")
    assert b"vendor/firebase/firebase-app-compat.js" in account.data
    assert "accounts.google.com" in account.headers.get("Content-Security-Policy", "")
    assert account.headers.get("Cross-Origin-Opener-Policy") == "same-origin-allow-popups"


def test_csp_localhost_only_in_development(tmp_path):
    prod = create_app(app_config(tmp_path, APP_ENV="production", TESTING=False))
    with prod.app_context():
        db.create_all()
    prod_client = prod.test_client()
    csp = prod_client.get("/login").headers.get("Content-Security-Policy", "")
    assert "127.0.0.1" not in csp
    assert "localhost" not in csp
    assert "identitytoolkit.googleapis.com" in csp

    dev_root = tmp_path / "dev"
    dev_root.mkdir()
    dev = create_app(app_config(dev_root, APP_ENV="development"))
    with dev.app_context():
        db.create_all()
    dev_csp = dev.test_client().get("/login").headers.get("Content-Security-Policy", "")
    assert "http://127.0.0.1:*" in dev_csp
    assert "http://localhost:*" in dev_csp


@patch("app.services.firebase_auth.init_firebase_admin")
def test_require_recent_auth_time(mock_init, app):
    from app.services import firebase_auth as fa

    old = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
    with app.app_context():
        with patch(
            "firebase_admin.auth.verify_id_token",
            return_value={
                "uid": "x",
                "email": "a@example.com",
                "email_verified": True,
                "aud": "demo-project",
                "auth_time": old,
            },
        ):
            try:
                fa.verify_id_token("old", require_recent=True)
                raise AssertionError("should reject")
            except TokenError:
                pass


def test_refuse_emulator_in_production(tmp_path):
    try:
        create_app(
            app_config(
                tmp_path,
                APP_ENV="production",
                TESTING=False,
                FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099",
            )
        )
    except RuntimeError as exc:
        assert "FIREBASE_AUTH_EMULATOR_HOST" in str(exc)
        assert "production" in str(exc)
    else:
        raise AssertionError("should refuse to start")


def test_refuse_example_secret_in_production(tmp_path):
    try:
        create_app(
            app_config(
                tmp_path,
                APP_ENV="production",
                TESTING=False,
                SECRET_KEY="replace-with-a-long-random-string",
            )
        )
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
        assert "production" in str(exc)
    else:
        raise AssertionError("should refuse to start")


def test_refuse_testing_flag_in_production(tmp_path):
    try:
        create_app(app_config(tmp_path, APP_ENV="production", TESTING=True))
    except RuntimeError as exc:
        assert "TESTING" in str(exc)
        assert "production" in str(exc)
    else:
        raise AssertionError("should refuse to start")


def test_production_password_hash_is_strong(tmp_path):
    application = create_app(app_config(tmp_path, APP_ENV="production", TESTING=False))
    with application.app_context():
        db.create_all()
        user = User(email="hashcheck@example.com", role="citizen")
        user.set_password("password1")
        assert user.password_hash.startswith("pbkdf2:sha256:260000$")
        assert application.config["PASSWORD_HASH_METHOD"] == "pbkdf2:sha256:260000"


def test_fast_password_hash_only_when_testing(app):
    assert app.config["TESTING"] is True
    assert app.config["PASSWORD_HASH_METHOD"] == "pbkdf2:sha256:1"
    with app.app_context():
        user = User(email="fast-hash@example.com", role="citizen")
        user.set_password("password1")
        assert user.password_hash.startswith("pbkdf2:sha256:1$")
