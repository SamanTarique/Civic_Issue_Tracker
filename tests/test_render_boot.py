from flask import request
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.config import database_url, listen_address
from tests.conftest import app_config


def test_listen_address_local_is_loopback(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert listen_address() == ("127.0.0.1", 5000)


def test_listen_address_uses_render_port(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert listen_address() == ("0.0.0.0", 10000)


def test_render_postgres_scheme_is_rewritten(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://user:pass@dpg-abc/civic?sslmode=require",
    )
    assert database_url() == "postgresql://user:pass@dpg-abc/civic?sslmode=require"


def test_blank_database_url_stays_on_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "  ")
    assert database_url().startswith("sqlite:///")


def test_production_trusts_one_proxy_hop(tmp_path):
    application = create_app(
        app_config(tmp_path, APP_ENV="production", TESTING=False, SECRET_KEY="unique-prod-secret")
    )
    assert isinstance(application.wsgi_app, ProxyFix)
    assert application.wsgi_app.x_for == 1
    assert application.wsgi_app.x_proto == 1
    seen = {}

    @application.before_request
    def capture():
        seen["ip"] = request.remote_addr
        seen["scheme"] = request.scheme

    response = application.test_client().get(
        "/",
        headers={"X-Forwarded-For": "203.0.113.8", "X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    assert seen["ip"] == "203.0.113.8"
    assert seen["scheme"] == "https"


def test_development_ignores_forwarded_client(tmp_path):
    application = create_app(app_config(tmp_path, APP_ENV="development"))
    assert not isinstance(application.wsgi_app, ProxyFix)
    seen = {}

    @application.before_request
    def capture():
        seen["ip"] = request.remote_addr

    application.test_client().get("/", headers={"X-Forwarded-For": "203.0.113.8"})
    assert seen["ip"] == "127.0.0.1"
