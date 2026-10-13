from sqlalchemy import event

from app import db
from app.models import Issue, IssuePhoto, User, new_public_id, record_status
from tests.conftest import register


def _count_sql(app, callback):
    statements = []

    def before(_conn, _cursor, statement, _parameters, _context, _executemany):
        sql = statement.strip().upper()
        if sql.startswith("PRAGMA") or sql.startswith("BEGIN"):
            return
        statements.append(statement)

    engine = db.engine
    event.listen(engine, "before_cursor_execute", before)
    try:
        callback()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return statements


def _seed_issues(app, reporter, count):
    categories = ("pothole", "garbage", "streetlight", "water", "other")
    with app.app_context():
        user = User.query.filter_by(email=reporter).one()
        for index in range(count):
            category = categories[index % 5]
            issue = Issue(
                public_id=new_public_id(),
                reporter_id=user.id,
                category=category,
                description="Seeded list row " + str(index + 1) + " for query counting.",
                lat=33.68,
                lng=73.04,
                location_consent=True,
                public_map_consent=False,
                status="reported",
                is_demo=True,
            )
            db.session.add(issue)
            db.session.flush()
            db.session.add(
                IssuePhoto(
                    issue_id=issue.id,
                    kind="before",
                    filename="demo-" + category + ".jpg",
                    uploaded_by=user.id,
                )
            )
            record_status(issue, user, "reported", note="query seed", initial=True)
        db.session.commit()


def test_my_reports_query_count_independent_of_rows(client, app):
    register(client, "list-owner@example.com")
    _seed_issues(app, "list-owner@example.com", 52)
    with app.app_context():
        first = _count_sql(app, lambda: client.get("/reports"))
    _seed_issues(app, "list-owner@example.com", 20)
    with app.app_context():
        second = _count_sql(app, lambda: client.get("/reports"))
    assert len(first) <= 15
    assert len(second) <= 15
    assert len(second) == len(first)


def test_staff_queue_query_count_independent_of_rows(client, app):
    register(client, "queue-owner@example.com")
    _seed_issues(app, "queue-owner@example.com", 52)
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    with app.app_context():
        first = _count_sql(app, lambda: client.get("/staff"))
    _seed_issues(app, "queue-owner@example.com", 20)
    with app.app_context():
        second = _count_sql(app, lambda: client.get("/staff"))
    assert len(first) <= 15
    assert len(second) <= 15
    assert len(second) == len(first)
