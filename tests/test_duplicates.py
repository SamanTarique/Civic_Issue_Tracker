import multiprocessing

from app import db
from app.models import Issue, IssueSupporter, User
from tests.conftest import jpeg_bytes, register, submit_report


def _mp_submit(payload):
    uri, upload, email, password = payload
    from app import create_app
    from tests.conftest import jpeg_bytes as _jpeg

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": uri,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "UPLOAD_FOLDER": upload,
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
            "CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
            "THUMB_MAX_EDGE": 320,
            "APP_ENV": "testing",
            "DUPLICATE_RADIUS_M": 40,
            "DUPLICATE_DAYS": 30,
            "PHOTO_MIN_EDGE": 16,
            "PHOTO_BLUR_MIN_VARIANCE": 0.0,
            "PHOTO_DARK_MEAN": 2.0,
            "PHOTO_BRIGHT_MEAN": 253.0,
            "PHOTO_DHASH_MAX_DISTANCE": 10,
            "STAFF_EMAIL": "",
            "STAFF_PASSWORD": "",
        }
    )
    client = application.test_client()
    client.post("/login", data={"email": email, "password": password})
    return client.post(
        "/reports/new",
        data={
            "category": "pothole",
            "description": "Race condition pothole at the same painted corner.",
            "lat": "33.684400",
            "lng": "73.047900",
            "photo_consent": "on",
            "location_consent": "on",
            "photo": (_jpeg(), "race.jpg"),
        },
        content_type="multipart/form-data",
    ).status_code


def test_duplicate_within_and_outside_radius(client, app):
    register(client, "dup-a@example.com")
    first = submit_report(client)
    assert b"Tracking ID" in first.data
    with app.app_context():
        public_id = Issue.query.one().public_id
        count = Issue.query.count()
    nearby = submit_report(client)
    assert nearby.status_code == 200
    assert b"A similar report already exists nearby" in nearby.data
    assert b"Pothole" in nearby.data
    html = nearby.get_data(as_text=True)
    assert public_id not in html
    assert "dup-a@example.com" not in html
    card = html.split("A similar report already exists nearby", 1)[1].split("<form method=\"post\" enctype", 1)[0]
    assert "33." not in card
    assert "73." not in card
    assert "CIV-" not in card
    assert "reporter" not in card.lower()
    assert " m " not in card
    assert "very close" in card or "within 100 m" in card
    assert "distance_m" not in html
    with app.app_context():
        assert Issue.query.count() == count
    far = submit_report(client, lat="33.900000", lng="73.300000")
    assert b"Tracking ID" in far.data
    with app.app_context():
        assert Issue.query.count() == count + 1


def test_different_category_same_place_allowed(client, app):
    register(client, "dup-cat@example.com")
    submit_report(client)
    other = submit_report(
        client,
        category="garbage",
        description="Bags piled beside the same corner drain.",
        photo=(jpeg_bytes((10, 90, 10)), "bag.jpg"),
    )
    assert b"Tracking ID" in other.data
    with app.app_context():
        assert Issue.query.count() == 2


def test_missing_duplicate_session_returns_to_form(client):
    register(client, "dup-expired@example.com")
    missing = client.post(
        "/reports/new",
        data={"duplicate_action": "support"},
        follow_redirects=True,
    )
    assert missing.status_code == 200
    assert b"no longer available" in missing.data
    assert b"New report" in missing.data
    assert b"Traceback" not in missing.data


def test_own_issue_support_rejected(client, app):
    register(client, "dup-own@example.com")
    submit_report(client)
    submit_report(client)
    denied = client.post(
        "/reports/new",
        data={"duplicate_action": "support"},
        follow_redirects=True,
    )
    assert b"You already opened this report." in denied.data
    with app.app_context():
        assert IssueSupporter.query.count() == 0


def test_support_flow_no_new_ticket_and_no_double_support(client, app):
    register(client, "dup-owner@example.com")
    submit_report(client)
    client.post("/logout")
    register(client, "dup-helper@example.com")
    match_page = submit_report(client)
    assert b"A similar report already exists nearby" in match_page.data
    with app.app_context():
        tickets = Issue.query.count()
    supported = client.post(
        "/reports/new",
        data={"duplicate_action": "support"},
        follow_redirects=True,
    )
    assert b"No new ticket was opened." in supported.data
    with app.app_context():
        assert Issue.query.count() == tickets
        assert IssueSupporter.query.count() == 1
    again = client.post(
        "/reports/new",
        data={"duplicate_action": "support"},
        follow_redirects=True,
    )
    assert b"already listed as affected" in again.data
    with app.app_context():
        assert IssueSupporter.query.count() == 1
        assert Issue.query.count() == tickets


def test_different_issue_sets_possible_duplicate(client, app):
    register(client, "dup-force@example.com")
    submit_report(client)
    submit_report(client)
    created = client.post(
        "/reports/new",
        data={
            "duplicate_action": "different",
            "category": "pothole",
            "description": "This hole is on the opposite curb from the other one.",
            "lat": "33.684400",
            "lng": "73.047900",
            "photo_consent": "on",
            "location_consent": "on",
            "photo": (jpeg_bytes(), "other.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Tracking ID" in created.data
    with app.app_context():
        flagged = Issue.query.filter_by(possible_duplicate=True).one()
        assert flagged.category == "pothole"


def test_staff_queue_shows_supporters_and_duplicate_badge(client, app):
    register(client, "dup-staff-owner@example.com")
    submit_report(client)
    client.post("/logout")
    register(client, "dup-staff-help@example.com")
    submit_report(client)
    client.post("/reports/new", data={"duplicate_action": "support"}, follow_redirects=True)
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    queue = client.get("/staff")
    assert b"1 affected" in queue.data
    client.post("/logout")
    register(client, "dup-staff-force@example.com")
    submit_report(
        client,
        lat="33.700000",
        lng="73.060000",
        description="A second pothole used to flag a possible duplicate.",
    )
    client.post(
        "/reports/new",
        data={
            "duplicate_action": "different",
            "category": "pothole",
            "description": "Not the same break, different slab on this block.",
            "lat": "33.700000",
            "lng": "73.060000",
            "photo_consent": "on",
            "location_consent": "on",
            "photo": (jpeg_bytes((90, 40, 40)), "force.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    queue = client.get("/staff")
    assert b"Possible duplicate" in queue.data


def test_new_report_rate_limited(tmp_path):
    from app import create_app
    from tests.conftest import app_config, register, submit_report as _submit

    application = create_app(app_config(tmp_path, RATELIMIT_ENABLED=True))
    with application.app_context():
        db.create_all()
    limited = application.test_client()
    register(limited, "rate-dup@example.com")
    last = None
    for index in range(11):
        last = _submit(limited, lat=str(33.1 + index * 0.01), lng=str(73.1 + index * 0.01))
    assert last.status_code == 429


def test_two_simultaneous_submits_create_at_most_one_ticket(app):
    with app.app_context():
        for email in ("race-a@example.com", "race-b@example.com"):
            user = User(email=email, role="citizen")
            user.set_password("password1")
            db.session.add(user)
        db.session.commit()
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        upload = app.config["UPLOAD_FOLDER"]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(2) as pool:
        pool.map(
            _mp_submit,
            [
                (uri, upload, "race-a@example.com", "password1"),
                (uri, upload, "race-b@example.com", "password1"),
            ],
        )
    with app.app_context():
        assert Issue.query.count() <= 1
