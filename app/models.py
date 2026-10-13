import secrets
from datetime import datetime, timezone

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(32), nullable=False, default="citizen")
    department = db.Column(db.String(32), nullable=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=True, index=True)
    auth_provider = db.Column(db.String(32), nullable=False, default="password")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    issues = db.relationship("Issue", back_populates="reporter", foreign_keys="Issue.reporter_id")

    def set_password(self, password):
        method = "pbkdf2:sha256:260000"
        try:
            method = current_app.config.get("PASSWORD_HASH_METHOD") or method
        except RuntimeError:
            pass
        self.password_hash = generate_password_hash(password, method=method)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_staff(self):
        return self.role in ("staff", "admin")

    @property
    def is_admin(self):
        return self.role == "admin"


class Issue(db.Model):
    __tablename__ = "issues"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=False)
    lat = db.Column(db.Float, nullable=False, index=True)
    lng = db.Column(db.Float, nullable=False, index=True)
    location_consent = db.Column(db.Boolean, nullable=False, default=False)
    public_map_consent = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32), nullable=False, default="reported", index=True)
    parent_issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=True)
    possible_duplicate = db.Column(db.Boolean, nullable=False, default=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    needs_review = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    reporter = db.relationship("User", back_populates="issues", foreign_keys=[reporter_id])
    photos = db.relationship(
        "IssuePhoto",
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="IssuePhoto.created_at",
    )
    events = db.relationship(
        "StatusEvent",
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="StatusEvent.created_at",
    )
    parent = db.relationship("Issue", remote_side=[id], uselist=False)
    supporters = db.relationship("IssueSupporter", back_populates="issue", cascade="all, delete-orphan")

    def supporter_count(self):
        return len(self.supporters)

    def before_photos(self):
        return [photo for photo in self.photos if photo.kind == "before"]

    def before_photo(self):
        photos = self.before_photos()
        return photos[0] if photos else None

    def extra_before_photos(self):
        return self.before_photos()[1:]

    def after_photos(self):
        return [photo for photo in self.photos if photo.kind == "after"]

    def latest_after_photo(self):
        after = self.after_photos()
        return after[-1] if after else None

    def has_after_photo(self):
        return any(photo.kind == "after" for photo in self.photos)


class IssuePhoto(db.Model):
    __tablename__ = "issue_photos"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False, index=True)
    kind = db.Column(db.String(16), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    dhash = db.Column(db.String(16), nullable=True, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    issue = db.relationship("Issue", back_populates="photos")
    uploader = db.relationship("User")


class IssueSupporter(db.Model):
    __tablename__ = "issue_supporters"
    __table_args__ = (db.UniqueConstraint("issue_id", "user_id", name="uq_issue_supporter"),)

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    issue = db.relationship("Issue", back_populates="supporters")
    user = db.relationship("User")


class StatusEvent(db.Model):
    __tablename__ = "status_events"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    from_status = db.Column(db.String(32), nullable=True)
    to_status = db.Column(db.String(32), nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    issue = db.relationship("Issue", back_populates="events")
    actor = db.relationship("User")


def new_public_id():
    for _ in range(8):
        candidate = "CIV-" + secrets.token_hex(3).upper()
        if not Issue.query.filter_by(public_id=candidate).first():
            return candidate
    raise RuntimeError("Could not allocate a tracking ID.")


def record_status(issue, actor, to_status, note=None, initial=False):
    event = StatusEvent(
        issue_id=issue.id,
        actor_id=actor.id,
        from_status=None if initial else issue.status,
        to_status=to_status,
        note=note,
    )
    issue.status = to_status
    issue.updated_at = utcnow()
    db.session.add(event)


def ensure_staff_user():
    email = (current_app.config.get("STAFF_EMAIL") or "").strip().lower()
    password = current_app.config.get("STAFF_PASSWORD")
    if not email or not password:
        return
    user = User.query.filter_by(email=email).first()
    if user:
        if user.role != "staff":
            user.role = "staff"
            db.session.commit()
        return
    user = User(
        email=email,
        role="staff",
        department=current_app.config.get("STAFF_DEPARTMENT") or "Other",
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
