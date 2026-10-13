from unittest.mock import patch

from app import create_app, db
from app.models import Issue
from tests.conftest import app_config, register, submit_report


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
