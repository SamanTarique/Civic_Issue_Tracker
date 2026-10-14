import logging
from unittest.mock import patch

from app import create_app, db
from app.models import Issue, User
from tests.conftest import app_config, jpeg_bytes, register, submit_report


def _mail_app(tmp_path, **overrides):
    options = {
        "EMAIL_BACKEND": "memory",
        "DEPT_EMAIL_ROADS": "roads@example.test",
        "DEPT_EMAIL_WATER": "water@example.test",
    }
    options.update(overrides)
    cfg = app_config(tmp_path, **options)
    application = create_app(cfg)
    with application.app_context():
        db.create_all()
    return application


def test_email_goes_to_mapped_department(tmp_path):
    application = _mail_app(tmp_path)
    client = application.test_client()
    register(client, "mail-citizen@example.com")
    submit_report(client)
    with application.app_context():
        issue = Issue.query.one()
        box = application.config.get("_EMAIL_OUTBOX") or []
        assert len(box) == 1
        assert box[0]["to"] == "roads@example.test"
        body = box[0]["body"]
        assert issue.public_id in body
        assert "Pothole" in body
        assert "openstreetmap.org" in body
        assert "/login" in body
        assert "mail-citizen@example.com" not in body
        assert "uid" not in body.lower()
        assert "reporter" not in body.lower()
        assert "photo" not in body.lower()


def test_no_email_when_department_address_missing(tmp_path):
    application = _mail_app(tmp_path, DEPT_EMAIL_ROADS="")
    client = application.test_client()
    register(client, "mail-none@example.com")
    submit_report(client)
    with application.app_context():
        assert Issue.query.count() == 1
        assert application.config.get("_EMAIL_OUTBOX", []) == []


def _resolve(application, email):
    with application.app_context():
        staff = User(email="staff@example.com", role="staff", department="Roads")
        staff.set_password("staff-pass-123")
        db.session.add(staff)
        db.session.commit()
    client = application.test_client()
    register(client, email)
    submit_report(client)
    with application.app_context():
        public_id = Issue.query.filter_by(reporter_id=User.query.filter_by(email=email).one().id).one().public_id
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    client.post("/staff/" + public_id, data={"status": "in_progress"})
    response = client.post(
        "/staff/" + public_id,
        data={"status": "marked_resolved", "photo": (jpeg_bytes((10, 140, 40), seed=7), "after.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    return response, public_id


def test_resolve_emails_the_resident(tmp_path):
    application = _mail_app(tmp_path)
    response, public_id = _resolve(application, "resident@example.com")
    assert response.status_code == 200
    with application.app_context():
        issue = Issue.query.filter_by(public_id=public_id).one()
        assert issue.status == "marked_resolved"
        box = application.config.get("_EMAIL_OUTBOX") or []
        resident = [item for item in box if item["to"] == "resident@example.com"]
        assert len(resident) == 1
        body = resident[0]["body"]
        assert public_id in body
        assert public_id in resident[0]["subject"]
        assert "Marked resolved" in body
        assert "/reports/" + public_id in body
        assert "resident@example.com" not in body


def test_resolve_email_failure_keeps_status(tmp_path):
    application = _mail_app(
        tmp_path,
        EMAIL_BACKEND="smtp",
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=9,
        SMTP_FROM="app@example.test",
    )
    with patch("app.services.notifications.smtplib.SMTP", side_effect=OSError("down")):
        response, public_id = _resolve(application, "smtp-resident@example.com")
    assert response.status_code == 200
    with application.app_context():
        assert Issue.query.filter_by(public_id=public_id).one().status == "marked_resolved"


def test_console_resolve_logs_and_commits(tmp_path, caplog):
    application = _mail_app(tmp_path, EMAIL_BACKEND="console")
    with caplog.at_level(logging.WARNING, logger="civic.notifications"):
        response, public_id = _resolve(application, "console-resident@example.com")
    assert response.status_code == 200
    with application.app_context():
        assert Issue.query.filter_by(public_id=public_id).one().status == "marked_resolved"
    assert "console-resident@example.com" not in caplog.text
    assert "was not sent" in caplog.text


def test_unconfigured_smtp_logs_and_commits(tmp_path, caplog):
    application = _mail_app(
        tmp_path,
        EMAIL_BACKEND="smtp",
        SMTP_HOST="",
        DEPT_EMAIL_ROADS="",
    )
    with patch("app.services.notifications.smtplib.SMTP") as smtp:
        with caplog.at_level(logging.WARNING, logger="civic.notifications"):
            response, public_id = _resolve(application, "nosmtp@example.com")
    smtp.assert_not_called()
    assert response.status_code == 200
    with application.app_context():
        assert Issue.query.filter_by(public_id=public_id).one().status == "marked_resolved"
    assert "nosmtp@example.com" not in caplog.text
    assert "was not sent" in caplog.text


def test_smtp_failure_does_not_break_create(tmp_path):
    application = _mail_app(
        tmp_path,
        EMAIL_BACKEND="smtp",
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=9,
        SMTP_FROM="app@example.test",
    )
    client = application.test_client()
    register(client, "mail-smtp@example.com")
    with patch("app.services.notifications.smtplib.SMTP", side_effect=OSError("down")):
        response = submit_report(client)
    assert b"Tracking ID" in response.data
    with application.app_context():
        assert Issue.query.count() == 1
