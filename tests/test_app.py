from app.models import Issue, StatusEvent, User

from tests.conftest import jpeg_bytes, register, submit_report


def test_privacy_page(client):
    response = client.get("/privacy")
    assert response.status_code == 200
    assert b"Privacy Policy" in response.data
    assert b"does not request GPS until" in response.data
    assert b"Google sign-in is optional" in response.data


def test_home_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Report your issue" in response.data
    assert b"Nearby reports" in response.data
    assert b"Log in to report" in response.data
    assert b"step-link" in response.data
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert b"data-password-toggle" in login_page.data
    assert login_page.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_register_requires_privacy_consent(client):
    blocked = client.post("/register", data={"email":"nopolicy@example.com","password":"password1","confirm":"password1"}, follow_redirects=True)
    assert b"Confirm that you have read" in blocked.data


def test_register_rejects_bad_emails_and_repeat_login(client, app):
    for bad in ("not-an-email", "missingtld@com", "a@", "@x.com", ""):
        assert b"Enter a valid email address." in register(client, bad).data
    register(client, "Owner.Real@Example.com", password="password1")
    client.post("/logout")
    response = client.post("/login", data={"email":"  owner.real@example.com ","password":"password1"}, follow_redirects=True)
    assert b"Report your issue" in response.data
    client.post("/logout")
    wrong = client.post("/login", data={"email":"owner.real@example.com","password":"wrong-password"}, follow_redirects=True)
    assert b"Email or password is incorrect." in wrong.data
    unknown = client.post("/login", data={"email":"unknown@example.com","password":"password1"}, follow_redirects=True)
    assert b"Email or password is incorrect." in unknown.data
    with app.app_context():
        user = User.query.filter_by(email="owner.real@example.com").one()
        assert user.password_hash != "password1"


def test_home_card_destinations(client):
    response = client.get("/")
    assert b"next=/reports/new" in response.data
    assert b"next=/reports" in response.data


def test_home_page_after_login(client):
    register(client, "homeuser@example.com")
    response = client.get("/")
    assert response.status_code == 200
    assert b"New report" in response.data


def test_report_requires_login(client):
    response = client.get("/reports/new")
    assert response.status_code in (302, 401)


def test_register_and_report_flow(client, app):
    assert register(client, "citizen@example.com").status_code == 200
    response = submit_report(client, public_map_consent="on")
    assert response.status_code == 200
    with app.app_context():
        issue = Issue.query.filter_by(category="pothole").one()
        assert issue.status == "reported"
        assert issue.public_id.startswith("CIV-")
        filename = issue.before_photo().filename
    pins = client.get("/api/pins").get_json()
    assert pins and "public_id" not in pins[0] and "email" not in pins[0]
    client.post("/logout")
    assert client.get("/static/media/" + filename).status_code == 404
