from app import create_app, db
from app.models import Issue, IssuePhoto, User, new_public_id, record_status
from app.services.seed_demo import seed_demo
from tests.conftest import jpeg_bytes, register, submit_report


def _make_staff(app, email, department, role="staff"):
    with app.app_context():
        user = User(email=email, role=role, department=department)
        user.set_password("password1")
        db.session.add(user)
        db.session.commit()


def test_department_isolation_and_admin(client, app):
    register(client, "road-user@example.com")
    submit_report(client)
    client.post("/logout")
    register(client, "trash-user@example.com")
    submit_report(
        client,
        category="garbage",
        description="Overflowing bins along the market street edge.",
        photo=(jpeg_bytes((20, 80, 20)), "bin.jpg"),
    )
    with app.app_context():
        pothole = Issue.query.filter_by(category="pothole").one()
        garbage = Issue.query.filter_by(category="garbage").one()
        pothole_id = pothole.public_id
        garbage_id = garbage.public_id
    client.post("/logout")
    _make_staff(app, "sanitation@example.com", "Sanitation")
    client.post("/login", data={"email": "sanitation@example.com", "password": "password1"})
    queue = client.get("/staff")
    assert garbage_id.encode() in queue.data
    assert pothole_id.encode() not in queue.data
    assert client.get("/staff/" + pothole_id).status_code == 404
    assert client.get("/staff/" + garbage_id).status_code == 200
    client.post("/logout")
    _make_staff(app, "admin@example.com", None, role="admin")
    client.post("/login", data={"email": "admin@example.com", "password": "password1"})
    admin_queue = client.get("/staff")
    assert pothole_id.encode() in admin_queue.data
    assert garbage_id.encode() in admin_queue.data
    assert client.get("/staff/" + pothole_id).status_code == 200


def test_roads_staff_cannot_fetch_water_photo(client, app):
    register(client, "water-owner@example.com")
    submit_report(
        client,
        category="water",
        description="Broken main flooding the street corner drain.",
        photo=(jpeg_bytes((20, 40, 160)), "water.jpg"),
    )
    with app.app_context():
        photo = IssuePhoto.query.one()
        photo_id = photo.id
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    assert client.get("/reports/photos/" + str(photo_id)).status_code == 404
    assert client.get("/reports/photos/" + str(photo_id) + "/thumb").status_code == 404
    client.post("/logout")
    _make_staff(app, "water-staff@example.com", "Water")
    client.post("/login", data={"email": "water-staff@example.com", "password": "password1"})
    assert client.get("/reports/photos/" + str(photo_id)).status_code == 200
    assert client.get("/reports/photos/" + str(photo_id) + "/thumb").status_code == 200


def test_seed_demo_refuses_outside_development(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo"])
    assert result.exit_code != 0
    assert "APP_ENV=development" in (result.output or "") + str(result.exception)


def test_seed_demo_runs_when_demo_mode(tmp_path):
    from tests.conftest import app_config

    application = create_app(
        app_config(tmp_path, APP_ENV="testing", TESTING=True, DEMO_MODE=True)
    )
    with application.app_context():
        db.create_all()
        count = seed_demo()
        assert count >= 50


def test_seed_demo_runs_in_development(tmp_path):
    from tests.conftest import app_config

    application = create_app(app_config(tmp_path, APP_ENV="development", TESTING=True))
    with application.app_context():
        db.create_all()
        count = seed_demo()
        assert count >= 50
        assert Issue.query.count() >= 50
        assert User.query.filter(User.email.like("%@example.test")).count() >= 7
        pages = Issue.query.count() / 20
        assert pages > 1
        names = {row[0] for row in IssuePhoto.query.with_entities(IssuePhoto.filename)}
        assert names <= {
            "demo-pothole.jpg",
            "demo-garbage.jpg",
            "demo-streetlight.jpg",
            "demo-water.jpg",
            "demo-other.jpg",
            "demo-after.jpg",
        }


def test_recently_fixed_uses_demo_images_only(client, app):
    register(client, "fixed@example.com")
    submit_report(client)
    with app.app_context():
        live = Issue.query.one()
        live.status = "confirmed"
        live.is_demo = False
        db.session.commit()
        live_id = live.public_id
        citizen = User.query.filter_by(email="fixed@example.com").one()
        demo = Issue(
            public_id=new_public_id(),
            reporter_id=citizen.id,
            category="pothole",
            description="Demo confirmed repair used on the home page.",
            lat=33.6844,
            lng=73.0479,
            location_consent=True,
            public_map_consent=True,
            status="reported",
            is_demo=True,
        )
        db.session.add(demo)
        db.session.flush()
        db.session.add(
            IssuePhoto(issue_id=demo.id, kind="after", filename="demo-after.jpg", uploaded_by=citizen.id)
        )
        record_status(demo, citizen, "confirmed", note="demo")
        db.session.commit()
    home = client.get("/")
    assert b"Recently fixed" in home.data
    assert b"DEMO" in home.data
    assert b"static/demo/demo-after.jpg" in home.data
    assert live_id.encode() not in home.data
