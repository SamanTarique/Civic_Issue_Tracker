import secrets

from flask import current_app

from app import db
from app.config import CATEGORY_DEPARTMENT
from app.models import Issue, IssuePhoto, User, new_public_id, record_status, utcnow
from app.services.status_machine import STATUS_ORDER

_DEMO_DOMAIN = "@example.test"
_ISSUE_COUNT = 52


def seed_demo():
    env = current_app.config.get("APP_ENV") or ""
    demo_mode = bool(current_app.config.get("DEMO_MODE"))
    if env != "development" and not demo_mode:
        raise RuntimeError(
            "flask seed-demo only runs when APP_ENV=development or DEMO_MODE=true."
        )

    mapping = current_app.config.get("CATEGORY_DEPARTMENT") or CATEGORY_DEPARTMENT
    categories = list(current_app.config["CATEGORIES"])
    lat0 = float(current_app.config["MAP_DEFAULT_LAT"])
    lng0 = float(current_app.config["MAP_DEFAULT_LNG"])

    credentials = []

    def _user(email, role, department=None):
        existing = User.query.filter_by(email=email).first()
        password = "demo-" + secrets.token_urlsafe(6)
        if existing:
            existing.role = role
            existing.department = department
            existing.set_password(password)
            credentials.append((email, password, role, department or ""))
            return existing
        user = User(email=email, role=role, department=department, auth_provider="password")
        user.set_password(password)
        db.session.add(user)
        credentials.append((email, password, role, department or ""))
        return user

    citizen = _user("citizen" + _DEMO_DOMAIN, "citizen")
    extra_citizens = [_user("citizen" + str(i) + _DEMO_DOMAIN, "citizen") for i in range(2, 6)]
    reporters = [citizen] + extra_citizens
    for dept in current_app.config.get("DEPARTMENTS") or (
        "Roads",
        "Sanitation",
        "Water",
        "Electric",
        "Other",
    ):
        slug = dept.lower()
        _user(slug + _DEMO_DOMAIN, "staff", dept)
    _user("admin" + _DEMO_DOMAIN, "admin")
    db.session.flush()

    created = 0
    for index in range(_ISSUE_COUNT):
        category = categories[index % len(categories)]
        status = STATUS_ORDER[index % len(STATUS_ORDER)]
        reporter = reporters[index % len(reporters)]
        before = "demo-" + category + ".jpg"
        issue = Issue(
            public_id=new_public_id(),
            reporter_id=reporter.id,
            category=category,
            description="Demo " + category + " report number " + str(index + 1) + " for pagination.",
            lat=lat0 + (index % 9) * 0.002,
            lng=lng0 + (index // 9) * 0.002,
            location_consent=True,
            public_map_consent=True,
            status="reported",
            is_demo=True,
        )
        db.session.add(issue)
        db.session.flush()
        db.session.add(
            IssuePhoto(
                issue_id=issue.id,
                kind="before",
                filename=before,
                uploaded_by=reporter.id,
            )
        )
        record_status(issue, reporter, "reported", note="Demo seed.", initial=True)
        if status != "reported":
            actor = reporter
            if status in ("acknowledged", "in_progress", "marked_resolved"):
                dept = mapping.get(category)
                actor = User.query.filter_by(role="staff", department=dept).first() or reporter
            if status == "marked_resolved" or status == "confirmed":
                after = "demo-after.jpg"
                db.session.add(
                    IssuePhoto(
                        issue_id=issue.id,
                        kind="after",
                        filename=after,
                        uploaded_by=actor.id,
                    )
                )
            record_status(issue, actor, status, note="Demo seed status.")
        created += 1

    db.session.commit()
    print("Seeded " + str(created) + " demo issues. Demo logins (@example.test only):")
    for email, password, role, dept in credentials:
        extra = " " + dept if dept else ""
        print(email + "  " + password + "  (" + role + extra + ")")
    return created
