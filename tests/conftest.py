import io

import pytest
from PIL import Image

from app import create_app, db
from app.models import User


def app_config(tmp_path, **overrides):
    upload = tmp_path / "uploads"
    upload.mkdir()
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "test.db").as_posix(),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "UPLOAD_FOLDER": str(upload),
        "MAX_CONTENT_LENGTH": 8 * 1024 * 1024,
        "ALLOWED_IMAGE_MIMES": frozenset({"image/jpeg", "image/png", "image/webp"}),
        "IMAGE_MAX_EDGE": 1280,
        "IMAGE_JPEG_QUALITY": 82,
        "IMAGE_MAX_PIXELS": 20_000_000,
        "CATEGORIES": ("pothole", "garbage", "streetlight", "water", "other"),
        "PAGE_SIZE": 20,
        "MAP_DEFAULT_LAT": 33.6844,
        "MAP_DEFAULT_LNG": 73.0479,
        "COORDINATE_ROUNDING": 3,
        "STAFF_EMAIL": "staff@example.com",
        "STAFF_PASSWORD": "staff-pass-123",
        "CSRF_ENABLED": False,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": False,
        "RATELIMIT_ENABLED": False,
        "AUTO_CONFIRM_DAYS": 7,
        "PUBLIC_PIN_LIMIT": 200,
        "THUMB_MAX_EDGE": 320,
        "APP_ENV": "testing",
        "DEBUG": False,
        "DUPLICATE_RADIUS_M": 40,
        "DUPLICATE_DAYS": 30,
        "PHOTO_MIN_EDGE": 16,
        "PHOTO_BLUR_MIN_VARIANCE": 0.0,
        "PHOTO_DARK_MEAN": 2.0,
        "PHOTO_BRIGHT_MEAN": 253.0,
        "PHOTO_DHASH_MAX_DISTANCE": 10,
        "PHOTO_AI_ENABLED": False,
        "STAFF_DEPARTMENT": "Roads",
        "DEPARTMENTS": ("Roads", "Sanitation", "Water", "Electric", "Other"),
        "CATEGORY_DEPARTMENT": {
            "pothole": "Roads",
            "garbage": "Sanitation",
            "streetlight": "Electric",
            "water": "Water",
            "other": "Other",
        },
    }
    config.update(overrides)
    return config


@pytest.fixture()
def app(tmp_path):
    application = create_app(app_config(tmp_path))
    with application.app_context():
        db.create_all()
        staff = User(email="staff@example.com", role="staff", department="Roads")
        staff.set_password("staff-pass-123")
        db.session.add(staff)
        db.session.commit()
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def jpeg_bytes(color=(180, 40, 40), seed=None):
    buffer = io.BytesIO()
    image = Image.new("RGB", (48, 48), color=color)
    pixels = image.load()
    if seed is None:
        import secrets

        seed = secrets.randbits(32)
    rng = int(seed) | 1
    for y in range(48):
        for x in range(48):
            rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
            delta = rng % 48
            red, green, blue = color
            pixels[x, y] = ((red + delta) % 256, (green + delta // 2) % 256, (blue + delta // 3) % 256)
    image.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


def register(client, email, password="password1"):
    return client.post(
        "/register",
        data={
            "email": email,
            "password": password,
            "confirm": password,
            "privacy_consent": "on",
        },
        follow_redirects=True,
    )


def submit_report(client, **overrides):
    data = {
        "category": "pothole",
        "description": "Deep pothole on the corner near the school gate.",
        "lat": "33.684400",
        "lng": "73.047900",
        "photo_consent": "on",
        "location_consent": "on",
        "photo": (jpeg_bytes(), "hole.jpg"),
    }
    data.update(overrides)
    return client.post(
        "/reports/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
