from app.models import Issue, StatusEvent, User

from tests.conftest import jpeg_bytes, register, submit_report


def test_privacy_page(client):
    response = client.get("/privacy")
    assert response.status_code == 200
    assert b"Privacy Policy" in response.data
    assert b"Google Fonts" in response.data
    assert b"does not request GPS until" in response.data
    assert b"leaflet.js" not in response.data
    assert b"Google sign-in is optional" in response.data
    assert b"firebase_uid, email, and created_at" in response.data
    assert b"Google sees that sign-in event and your visitor IP" in response.data
    assert b"Firebase JavaScript files load on the login page" in response.data
    assert b"account page only if you signed in with Google" in response.data
    assert b"opt-in pins only" in response.data
    assert b"Demo project, not connected to any real authority." in response.data
    assert b'<main id="main" class="container">' in response.data
    assert b"sign-in is within five minutes" in response.data


def test_home_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b">Home</a>" in response.data
    assert b"Report your issue" in response.data
    assert b"Nearby reports" in response.data
    assert b"Approximate locations only." in response.data
    assert b"Opt-in pins only" not in response.data
    assert b"What you can report" not in response.data
    assert b"Recently fixed" not in response.data
    assert b"Log in to report" in response.data
    assert b">Register</a>" not in response.data
    assert b"Demo project, not connected to any real authority." in response.data
    assert b'<main id="main" class="container">' in response.data
    assert b"vendor/leaflet/leaflet.js" in response.data
    assert b"unpkg" not in response.data
    assert b"firebasejs" not in response.data
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert b"data-password-toggle" in login_page.data
    assert b"Privacy Policy" in login_page.data
    assert "no-referrer" in login_page.headers.get("Referrer-Policy", "")
    assert "Content-Security-Policy" in login_page.headers
    assert login_page.headers.get("Cache-Control") == "no-store"
    assert "geolocation=()" in login_page.headers.get("Permissions-Policy", "")
    assert b"unpkg" not in login_page.data
    assert b"leaflet.js" not in login_page.data


def test_register_requires_privacy_consent(client):
    blocked = client.post(
        "/register",
        data={
            "email": "nopolicy@example.com",
            "password": "password1",
            "confirm": "password1",
        },
        follow_redirects=True,
    )
    assert b"Privacy Policy" in blocked.data
    assert b"Confirm that you have read" in blocked.data


def test_register_rejects_bad_emails_and_unknown_login(client, app):
    for bad in ("not-an-email", "missingtld@com", "a@", "@x.com", ""):
        response = register(client, bad)
        assert b"Enter a valid email address." in response.data
    with app.app_context():
        assert User.query.filter(User.email.like("%not-an-email%")).first() is None
    unknown = client.post(
        "/login",
        data={"email": "someone-else@example.com", "password": "password1"},
        follow_redirects=True,
    )
    assert b"Email or password is incorrect." in unknown.data
    register(client, "owner.real@example.com")
    client.post("/logout")
    stolen = client.post(
        "/login",
        data={"email": "owner.real@example.com", "password": "not-the-password"},
        follow_redirects=True,
    )
    assert b"Email or password is incorrect." in stolen.data


def test_home_page_after_login(client):
    register(client, "homeuser@example.com")
    response = client.get("/")
    assert response.status_code == 200
    assert b"New report" in response.data
    assert b"vendor/leaflet/leaflet.js" in response.data
    assert b"unpkg" not in response.data
    form = client.get("/reports/new")
    assert "geolocation=(self)" in form.headers.get("Permissions-Policy", "")


def test_report_requires_login(client):
    response = client.get("/reports/new")
    assert response.status_code in (302, 401)


def test_register_and_report_flow(client, app):
    response = register(client, "citizen@example.com")
    assert response.status_code == 200

    response = submit_report(client, public_map_consent="on")
    assert response.status_code == 200
    with app.app_context():
        issue = Issue.query.filter_by(category="pothole").one()
        assert issue.status == "reported"
        assert issue.public_id.startswith("CIV-")
        public_id = issue.public_id
        events = StatusEvent.query.filter_by(issue_id=issue.id).all()
        assert len(events) == 1
        assert events[0].from_status is None
        filename = issue.before_photo().filename

    pins = client.get("/api/pins").get_json()
    assert pins
    assert "public_id" not in pins[0]
    assert "email" not in pins[0]
    assert pins[0]["lat"] == 33.684
    client.post("/logout")
    guest_pins = client.get("/api/pins").get_json()
    assert guest_pins
    assert "email" not in guest_pins[0]
    leaked = client.get("/static/media/" + filename)
    assert leaked.status_code == 404


def test_staff_must_upload_after_photo(client, app):
    register(client, "second@example.com")
    submit_report(
        client,
        category="pothole",
        description="Overflowing bin blocking the sidewalk entirely.",
        lat="33.68",
        lng="73.04",
        photo=(jpeg_bytes(), "bin.jpg"),
    )
    with app.app_context():
        issue = Issue.query.filter_by(category="pothole").one()
        public_id = issue.public_id

    client.post("/logout")
    client.post(
        "/login",
        data={"email": "staff@example.com", "password": "staff-pass-123"},
    )
    advanced = client.post(
        f"/staff/{public_id}",
        data={"status": "in_progress", "note": "Crew assigned"},
        follow_redirects=True,
    )
    assert advanced.status_code == 200
    blocked = client.post(
        f"/staff/{public_id}",
        data={"status": "marked_resolved", "note": "Done"},
        follow_redirects=True,
    )
    assert b"after-repair photo is required" in blocked.data

    resolved = client.post(
        f"/staff/{public_id}",
        data={
            "status": "marked_resolved",
            "note": "Patched",
            "photo": (jpeg_bytes((20, 160, 80)), "after.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resolved.status_code == 200
    with app.app_context():
        issue = Issue.query.filter_by(public_id=public_id).one()
        assert issue.status == "marked_resolved"
        assert issue.has_after_photo()


def test_confirm_and_reopen(client, app):
    register(client, "closer@example.com")
    submit_report(client)
    with app.app_context():
        public_id = Issue.query.one().public_id

    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    client.post(f"/staff/{public_id}", data={"status": "in_progress"})
    client.post(
        f"/staff/{public_id}",
        data={"status": "marked_resolved", "photo": (jpeg_bytes((10, 140, 40)), "after.jpg")},
        content_type="multipart/form-data",
    )
    client.post("/logout")
    client.post("/login", data={"email": "closer@example.com", "password": "password1"})
    reopened = client.post(
        f"/reports/{public_id}/reopen",
        data={"note": "The patch already sank."},
        follow_redirects=True,
    )
    assert reopened.status_code == 200
    with app.app_context():
        assert Issue.query.filter_by(public_id=public_id).one().status == "reopened"

    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    client.post(f"/staff/{public_id}", data={"status": "in_progress"})
    client.post(
        f"/staff/{public_id}",
        data={"status": "marked_resolved", "photo": (jpeg_bytes((10, 140, 40)), "after2.jpg")},
        content_type="multipart/form-data",
    )
    client.post("/logout")
    client.post("/login", data={"email": "closer@example.com", "password": "password1"})
    confirmed = client.post(f"/reports/{public_id}/confirm", follow_redirects=True)
    assert confirmed.status_code == 200
    with app.app_context():
        assert Issue.query.filter_by(public_id=public_id).one().status == "confirmed"


def test_citizen_cannot_open_staff_queue(client):
    register(client, "third@example.com")
    response = client.get("/staff")
    assert response.status_code == 403


def test_staff_user_exists(app):
    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").one()
        assert user.is_staff


def test_duplicate_register_does_not_name_the_email(client):
    register(client, "taken@example.com")
    client.post("/logout")
    response = register(client, "taken@example.com")
    assert b"already registered" not in response.data
    assert b"Could not create that account" in response.data
