import io
from pathlib import Path

from PIL import Image

from app import create_app, db
from app.models import Issue, IssuePhoto, IssueSupporter, User
from app.privacy import save_issue_photo
from tests.conftest import app_config, register, submit_report


def _jpeg_with_exif():
    buffer = io.BytesIO()
    image = Image.new("RGB", (60, 60), color=(30, 80, 120))
    exif = image.getexif()
    exif[271] = "PrivacyCam"
    image.save(buffer, format="JPEG", exif=exif)
    buffer.seek(0)
    return buffer


def test_exif_is_stripped(app):
    from werkzeug.datastructures import FileStorage

    payload = _jpeg_with_exif()
    storage = FileStorage(stream=payload, filename="cam.jpg", content_type="image/jpeg")
    with app.app_context():
        filename = save_issue_photo(storage)
        stored = Image.open(Path(app.config["UPLOAD_FOLDER"]) / filename)
        stored.load()
        leftover = dict(stored.getexif())
        assert 271 not in leftover
        assert 34853 not in leftover


def test_photo_idor_and_account_delete(client, app):
    register(client, "owner@example.com")
    submit_report(client)
    with app.app_context():
        photo = IssuePhoto.query.one()
        photo_id = photo.id
        stored = Path(app.config["UPLOAD_FOLDER"]) / photo.filename
        assert stored.is_file()

    owner_ok = client.get(f"/reports/photos/{photo_id}")
    assert owner_ok.status_code == 200
    assert owner_ok.headers.get("Cache-Control") == "private, no-store"
    owner_ok.close()

    client.post("/logout")
    register(client, "other@example.com")
    hidden = client.get(f"/reports/photos/{photo_id}")
    assert hidden.status_code == 404
    with app.app_context():
        public_id = Issue.query.one().public_id
    missing = client.get(f"/reports/{public_id}")
    assert missing.status_code == 404

    client.post("/logout")
    client.post("/login", data={"email": "owner@example.com", "password": "password1"})
    deleted = client.post(
        "/account",
        data={"action": "delete", "password": "password1"},
        follow_redirects=True,
    )
    assert deleted.status_code == 200
    with app.app_context():
        assert User.query.filter_by(email="owner@example.com").first() is None
        assert Issue.query.count() == 0
    assert not stored.exists()


def test_account_delete_removes_supporters(client, app):
    register(client, "keep-owner@example.com")
    submit_report(client)
    with app.app_context():
        remaining = Issue.query.one().id
    client.post("/logout")
    register(client, "helper-del@example.com")
    submit_report(client)
    client.post("/reports/new", data={"duplicate_action": "support"}, follow_redirects=True)
    with app.app_context():
        assert IssueSupporter.query.filter_by(issue_id=remaining).count() == 1
    deleted = client.post(
        "/account",
        data={"action": "delete", "password": "password1"},
        follow_redirects=True,
    )
    assert deleted.status_code == 200
    with app.app_context():
        assert User.query.filter_by(email="helper-del@example.com").first() is None
        assert Issue.query.filter_by(id=remaining).one().reporter.email == "keep-owner@example.com"
        assert IssueSupporter.query.filter_by(issue_id=remaining).count() == 0


def test_secret_files_are_not_served(client, app):
    sentinel = "SENTINEL_ENV_FILE_CONTENTS_9f3a"
    static_root = Path(app.root_path) / "static"
    planted = (
        static_root / ".env",
        static_root / "firebase-service-account.json",
    )
    try:
        for path in planted:
            path.write_text(sentinel + "\nSECRET_KEY=super-secret\n", encoding="utf-8")
        for url in (
            "/.env",
            "/instance/.env",
            "/firebase-service-account.json",
            "/static/.env",
            "/static/firebase-service-account.json",
            "/instance/civic.db",
        ):
            response = client.get(url)
            assert response.status_code == 404, url
            body = response.get_data(as_text=True)
            assert sentinel not in body
            assert "super-secret" not in body
            assert "BEGIN PRIVATE" not in body
    finally:
        for path in planted:
            path.unlink(missing_ok=True)


def test_login_page_hides_server_secrets(client):
    page = client.get("/login")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "test-web-key" in text
    assert "demo-project" in text
    assert "test-secret" not in text
    assert "staff-pass-123" not in text
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in text
    assert "SMTP_PASSWORD" not in text
    assert "BEGIN PRIVATE" not in text
    privacy = client.get("/privacy")
    privacy_text = privacy.get_data(as_text=True)
    assert "test-secret" not in privacy_text
    assert "staff-pass-123" not in privacy_text
    assert "authorized domains" in privacy_text
    assert "Department staff" in privacy_text


def test_csrf_rejects_post_without_token(tmp_path):
    application = create_app(app_config(tmp_path, CSRF_ENABLED=True))
    with application.app_context():
        db.create_all()
    csrf_client = application.test_client()
    blocked = csrf_client.post(
        "/login",
        data={"email": "staff@example.com", "password": "staff-pass-123"},
    )
    assert blocked.status_code == 400
