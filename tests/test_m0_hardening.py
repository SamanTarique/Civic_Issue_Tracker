from datetime import timedelta

from sqlalchemy import text

from app import create_app, db
from app.models import Issue, User, utcnow
from app.services.issues import auto_confirm_stale
from tests.conftest import app_config, jpeg_bytes, register, submit_report


def test_open_redirect_blocked(client):
    register(client, "redir@example.com")
    client.post("/logout")
    response = client.post(
        "/login",
        data={
            "email": "redir@example.com",
            "password": "password1",
            "next": "https://evil.example/phish",
        },
        follow_redirects=False,
    )
    location = response.headers.get("Location", "")
    assert "evil.example" not in location


def test_login_unknown_and_wrong_password_same_message(client):
    register(client, "known@example.com")
    client.post("/logout")
    unknown = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "password1"},
        follow_redirects=True,
    )
    wrong = client.post(
        "/login",
        data={"email": "known@example.com", "password": "not-the-password"},
        follow_redirects=True,
    )
    assert b"Email or password is incorrect." in unknown.data
    assert b"Email or password is incorrect." in wrong.data


def test_photo_is_jpeg_stream_with_thumb(client, app):
    register(client, "thumbs@example.com")
    submit_report(client)
    with app.app_context():
        from pathlib import Path
        from app.models import IssuePhoto
        from app.services.images import thumb_name

        photo = IssuePhoto.query.one()
        photo_id = photo.id
        thumb = Path(app.config["UPLOAD_FOLDER"]) / thumb_name(photo.filename)
        assert thumb.is_file()
    full = client.get(f"/reports/photos/{photo_id}")
    assert full.status_code == 200
    assert full.headers.get("Content-Type", "").startswith("image/jpeg")
    assert full.headers.get("Cache-Control") == "private, no-store"
    thumb_resp = client.get(f"/reports/photos/{photo_id}/thumb")
    assert thumb_resp.status_code == 200
    assert b"loading=\"lazy\"" in client.get("/reports").data


def test_thumb_placeholder_when_missing(client, app):
    register(client, "nothumb@example.com")
    submit_report(client)
    with app.app_context():
        from pathlib import Path

        from app.models import IssuePhoto
        from app.services.images import thumb_name

        photo = IssuePhoto.query.one()
        photo_id = photo.id
        full = Path(app.config["UPLOAD_FOLDER"]) / photo.filename
        thumb = Path(app.config["UPLOAD_FOLDER"]) / thumb_name(photo.filename)
        thumb.unlink()
        full.unlink()
    missing = client.get(f"/reports/photos/{photo_id}/thumb")
    assert missing.status_code == 200
    assert missing.headers.get("Content-Type", "").startswith("image/svg+xml")
    assert b"<svg" in missing.data


def test_backfill_thumbnails(client, app):
    register(client, "backfill@example.com")
    submit_report(client)
    with app.app_context():
        from pathlib import Path

        from app.models import IssuePhoto
        from app.services.images import backfill_thumbnails, thumb_name

        photo = IssuePhoto.query.one()
        thumb = Path(app.config["UPLOAD_FOLDER"]) / thumb_name(photo.filename)
        assert thumb.is_file()
        thumb.unlink()
        assert not thumb.is_file()
        assert backfill_thumbnails() == 1
        assert thumb.is_file()


def test_auto_confirm_stale_marked_resolved(client, app):
    register(client, "stale@example.com")
    submit_report(client)
    with app.app_context():
        issue = Issue.query.one()
        public_id = issue.public_id
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    client.post(f"/staff/{public_id}", data={"status": "in_progress"})
    client.post(
        f"/staff/{public_id}",
        data={"status": "marked_resolved", "photo": (jpeg_bytes((10, 140, 40)), "after.jpg")},
        content_type="multipart/form-data",
    )
    with app.app_context():
        issue = Issue.query.filter_by(public_id=public_id).one()
        issue.updated_at = utcnow() - timedelta(days=8)
        db.session.commit()
        count = auto_confirm_stale()
        assert count == 1
        assert Issue.query.filter_by(public_id=public_id).one().status == "confirmed"


def test_rate_limit_login(tmp_path):
    application = create_app(app_config(tmp_path, RATELIMIT_ENABLED=True))
    with application.app_context():
        db.create_all()
        staff = User(email="staff@example.com", role="staff")
        staff.set_password("staff-pass-123")
        db.session.add(staff)
        db.session.commit()
    limited = application.test_client()
    last = None
    for _ in range(6):
        last = limited.post(
            "/login",
            data={"email": "nope@example.com", "password": "wrongpass"},
        )
    assert last.status_code == 429
    assert b"Too many attempts" in last.data


def test_sqlite_pragmas(app):
    with app.app_context():
        rows = db.session.execute(text("PRAGMA foreign_keys")).fetchone()
        assert rows[0] == 1
        mode = db.session.execute(text("PRAGMA journal_mode")).fetchone()
        assert str(mode[0]).lower() == "wal"
