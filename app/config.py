import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from app.services.status_machine import (
    CITIZEN_TRANSITIONS,
    STAFF_TRANSITIONS,
    STATUS_ORDER,
    status_label,
)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

CATEGORY_LABELS = {
    "pothole": "Pothole",
    "garbage": "Garbage",
    "streetlight": "Street light",
    "water": "Water",
    "other": "Other",
}

CATEGORY_DEPARTMENT = {
    "pothole": "Roads",
    "garbage": "Sanitation",
    "streetlight": "Electric",
    "water": "Water",
    "other": "Other",
}


def category_label(code):
    if not code:
        return ""
    return CATEGORY_LABELS.get(code, str(code).replace("_", " ").title())


def department_for_category(category, mapping=None):
    mapping = mapping or CATEGORY_DEPARTMENT
    return mapping.get(category) or "Other"


def categories_for_department(department, mapping=None):
    mapping = mapping or CATEGORY_DEPARTMENT
    return tuple(code for code, dept in mapping.items() if dept == department)


def _csv_tuple(value, fallback):
    raw = os.environ.get(value, fallback)
    items = tuple(part.strip() for part in raw.split(",") if part.strip())
    return items or tuple(part.strip() for part in fallback.split(",") if part.strip())


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or ""
    APP_ENV = os.environ.get("APP_ENV", "development")
    DEBUG = _env_bool("FLASK_DEBUG", False) or _env_bool("DEBUG", False)
    TEMPLATES_AUTO_RELOAD = APP_ENV != "production"

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + str(BASE_DIR / "instance" / "civic.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        str(BASE_DIR / "instance" / "uploads"),
    )
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
    IMAGE_MAX_EDGE = 1280
    IMAGE_JPEG_QUALITY = 88
    IMAGE_MAX_PIXELS = 20_000_000
    THUMB_MAX_EDGE = 320

    CATEGORIES = _csv_tuple(
        "ISSUE_CATEGORIES",
        "pothole,garbage,streetlight,water,other",
    )
    DEPARTMENTS = ("Roads", "Sanitation", "Water", "Electric", "Other")
    CATEGORY_DEPARTMENT = CATEGORY_DEPARTMENT
    STAFF_DEPARTMENT = os.environ.get("STAFF_DEPARTMENT", "Other")
    DUPLICATE_RADIUS_M = int(os.environ.get("DUPLICATE_RADIUS_M", "40"))
    DUPLICATE_DAYS = int(os.environ.get("DUPLICATE_DAYS", "30"))
    PHOTO_MIN_EDGE = int(os.environ.get("PHOTO_MIN_EDGE", "64"))
    PHOTO_BLUR_MIN_VARIANCE = float(os.environ.get("PHOTO_BLUR_MIN_VARIANCE", "12"))
    PHOTO_DARK_MEAN = float(os.environ.get("PHOTO_DARK_MEAN", "18"))
    PHOTO_BRIGHT_MEAN = float(os.environ.get("PHOTO_BRIGHT_MEAN", "237"))
    PHOTO_DHASH_MAX_DISTANCE = int(os.environ.get("PHOTO_DHASH_MAX_DISTANCE", "10"))
    PHOTO_AI_ENABLED = _env_bool("PHOTO_AI_ENABLED", False)
    PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "20"))
    PUBLIC_PIN_LIMIT = int(os.environ.get("PUBLIC_PIN_LIMIT", "200"))
    AUTO_CONFIRM_DAYS = int(os.environ.get("AUTO_CONFIRM_DAYS", "7"))
    MAP_DEFAULT_LAT = float(os.environ.get("MAP_DEFAULT_LAT", "33.6844"))
    MAP_DEFAULT_LNG = float(os.environ.get("MAP_DEFAULT_LNG", "73.0479"))
    COORDINATE_ROUNDING = int(os.environ.get("COORDINATE_ROUNDING", "3"))

    STAFF_EMAIL = os.environ.get("STAFF_EMAIL")
    STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD")

    DEPT_EMAIL_ROADS = os.environ.get("DEPT_EMAIL_ROADS", "")
    DEPT_EMAIL_SANITATION = os.environ.get("DEPT_EMAIL_SANITATION", "")
    DEPT_EMAIL_WATER = os.environ.get("DEPT_EMAIL_WATER", "")
    DEPT_EMAIL_ELECTRIC = os.environ.get("DEPT_EMAIL_ELECTRIC", "")
    DEPT_EMAIL_OTHER = os.environ.get("DEPT_EMAIL_OTHER", "")
    EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND") or (
        "console" if APP_ENV != "production" else "smtp"
    )
    EMAIL_FOR_DEMO = _env_bool("EMAIL_FOR_DEMO", False)
    EMAIL_TIMEOUT = float(os.environ.get("EMAIL_TIMEOUT", "8"))
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    SMTP_TLS = _env_bool("SMTP_TLS", True)
    DEMO_MODE = _env_bool("DEMO_MODE", False)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    SEND_FILE_MAX_AGE_DEFAULT = 0 if APP_ENV != "production" else 43200
    CSRF_ENABLED = True
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"

    REMEMBER_COOKIE_DURATION_DAYS = int(os.environ.get("REMEMBER_COOKIE_DURATION_DAYS", "30"))
    REMEMBER_COOKIE_DURATION = timedelta(days=REMEMBER_COOKIE_DURATION_DAYS)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = APP_ENV == "production"

    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
    FIREBASE_WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "")
    FIREBASE_AUTH_DOMAIN = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    FIREBASE_AUTH_EMULATOR_HOST = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "")
