import math
from datetime import timedelta

from flask import current_app, session
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import db
from app.config import categories_for_department, department_for_category
from app.models import (
    Issue,
    IssuePhoto,
    IssueSupporter,
    User,
    new_public_id,
    record_status,
    utcnow,
)
from app.services.images import UploadError, delete_photo_file, save_issue_photo
from app.services.photo_check import (
    REJECT,
    WARN,
    _bit_chars,
    _high_pair_chars,
    _low_pair_chars,
    evaluate_path,
    hamming_hex,
    hex_slice_spans,
)
from app.services.status_machine import citizen_allowed, staff_allowed, status_label
from pathlib import Path


class ReportError(ValueError):
    pass


class TransitionError(ValueError):
    pass


class DuplicateFound(ReportError):
    def __init__(self, payload):
        self.payload = payload
        super().__init__("A similar report already exists nearby")


class SupportAccepted(Exception):
    pass


def _begin_immediate():
    db.session.rollback()
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name == "sqlite":
        db.session.execute(text("BEGIN IMMEDIATE"))


def paginate_query(query, page):
    page = page or 1
    return query.paginate(
        page=page,
        per_page=current_app.config["PAGE_SIZE"],
        error_out=False,
    )


def citizen_issue_query(user_id):
    return (
        Issue.query.options(selectinload(Issue.photos))
        .filter_by(reporter_id=user_id)
        .order_by(Issue.created_at.desc())
    )


def staff_queue_query(actor, status_filter=None):
    query = (
        Issue.query.options(selectinload(Issue.photos), selectinload(Issue.supporters))
        .order_by(Issue.updated_at.desc())
    )
    if not actor.is_admin:
        cats = categories_for_department(
            actor.department, current_app.config.get("CATEGORY_DEPARTMENT")
        )
        query = query.filter(Issue.category.in_(cats or ("__none__",)))
    if status_filter:
        query = query.filter_by(status=status_filter)
    return query


def staff_can_access(actor, issue):
    if not actor.is_staff:
        return False
    if actor.is_admin:
        return True
    return department_for_category(
        issue.category, current_app.config.get("CATEGORY_DEPARTMENT")
    ) == actor.department


def haversine_m(lat1, lng1, lat2, lng2):
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def find_nearby_duplicate(category, lat, lng, exclude_id=None):
    radius_m = float(current_app.config.get("DUPLICATE_RADIUS_M") or 40)
    days = int(current_app.config.get("DUPLICATE_DAYS") or 30)
    cutoff = utcnow() - timedelta(days=days)
    lat = float(lat)
    lng = float(lng)
    dlat = radius_m / 111320.0
    cos_lat = math.cos(math.radians(lat)) or 1e-6
    dlng = radius_m / (111320.0 * abs(cos_lat))
    query = (
        Issue.query.filter(Issue.category == category)
        .filter(Issue.status != "confirmed")
        .filter(Issue.created_at >= cutoff)
        .filter(Issue.lat >= lat - dlat, Issue.lat <= lat + dlat)
        .filter(Issue.lng >= lng - dlng, Issue.lng <= lng + dlng)
    )
    if exclude_id is not None:
        query = query.filter(Issue.id != exclude_id)
    best = None
    best_dist = None
    for issue in query.all():
        dist = haversine_m(lat, lng, issue.lat, issue.lng)
        if dist <= radius_m and (best_dist is None or dist < best_dist):
            best = issue
            best_dist = dist
    if best is None:
        return None
    return {"issue": best, "distance_m": int(round(best_dist))}


def distance_bucket(metres):
    if metres <= 40:
        return "very close"
    return "within 100 m"


def duplicate_public_payload(match):
    from app.config import category_label

    return {
        "category": category_label(match["issue"].category),
        "status": status_label(match["issue"].status),
        "distance": distance_bucket(match["distance_m"]),
    }


def recently_fixed_demo(limit=6):
    issues = (
        Issue.query.options(selectinload(Issue.photos))
        .filter_by(is_demo=True, status="confirmed")
        .order_by(Issue.updated_at.desc())
        .limit(limit)
        .all()
    )
    rows = []
    for issue in issues:
        photo = issue.latest_after_photo() or issue.before_photo()
        if not photo:
            continue
        rows.append(
            {
                "filename": photo.filename,
                "category": issue.category,
            }
        )
    return rows


def _dhash_narrow_clause(digest, max_distance):
    """SQL predicate that cannot drop a hash within max_distance.

    ``substr`` and ``lower`` are the same on SQLite and PostgreSQL. For the
    default distance the hash is split into distance+1 slices: a hit must
    share one slice. Wider distances use 2-bit, then 1-bit, groups.
    """
    if max_distance >= 64:
        return None
    folded = func.lower(IssuePhoto.dhash)
    if max_distance <= 0:
        return folded == digest
    if max_distance <= 15:
        parts = []
        for start, length in hex_slice_spans(16, max_distance + 1):
            piece = digest[start : start + length]
            parts.append(func.substr(folded, start + 1, length) == piece)
        return or_(*parts)
    if max_distance <= 31:
        parts = []
        for index, nibble in enumerate(digest):
            char = func.substr(folded, index + 1, 1)
            parts.append(char.in_(tuple(_high_pair_chars(nibble))))
            parts.append(char.in_(tuple(_low_pair_chars(nibble))))
        return or_(*parts)
    parts = []
    for index, nibble in enumerate(digest):
        char = func.substr(folded, index + 1, 1)
        for bit in range(4):
            parts.append(char.in_(tuple(_bit_chars(nibble, bit))))
    return or_(*parts)


def similar_photo_candidates(digest, max_distance):
    """Rows the database still allows, lowest id first.

    Python then applies the same Hamming cut as the old full-table scan.
    """
    digest = (digest or "").strip().lower()
    if len(digest) != 16 or any(char not in "0123456789abcdef" for char in digest):
        return []
    max_distance = int(max_distance)
    query = IssuePhoto.query.with_entities(IssuePhoto.dhash, IssuePhoto.uploaded_by).filter(
        IssuePhoto.dhash.isnot(None)
    )
    clause = _dhash_narrow_clause(digest, max_distance)
    if clause is not None:
        query = query.filter(clause)
    return query.order_by(IssuePhoto.id.asc()).all()


def _photo_quality(user, filename, error_cls=None):
    error_cls = error_cls or ReportError
    path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    check = evaluate_path(path)
    if check.decision == REJECT:
        delete_photo_file(filename)
        raise error_cls(check.message)
    max_d = int(current_app.config.get("PHOTO_DHASH_MAX_DISTANCE") or 10)
    if check.dhash:
        for digest, uploader in similar_photo_candidates(check.dhash, max_d):
            if hamming_hex(check.dhash, digest) > max_d:
                continue
            if uploader == user.id:
                delete_photo_file(filename)
                raise error_cls("You already uploaded a nearly identical photo.")
            check.decision = WARN
            check.reasons.append("A similar photo already exists; staff will review it.")
            break
    return check


def _support_issue(user, issue):
    if issue.reporter_id == user.id:
        raise ReportError("You already opened this report.")
    row = IssueSupporter(issue_id=issue.id, user_id=user.id)
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ReportError("You are already listed as affected.") from None


def create_report(user, form, files):
    category = (form.get("category") or "").strip()
    description = (form.get("description") or "").strip()
    photo_consent = form.get("photo_consent") == "on"
    location_consent = form.get("location_consent") == "on"
    public_map_consent = form.get("public_map_consent") == "on"
    duplicate_action = (form.get("duplicate_action") or "").strip()
    try:
        lat = float(form.get("lat") or "")
        lng = float(form.get("lng") or "")
    except ValueError:
        lat = lng = None

    if duplicate_action == "support":
        match_id = session.get("duplicate_match_id")
        if not match_id:
            raise ReportError("That similar report is no longer available. You can submit a new report.")
        _begin_immediate()
        try:
            issue = db.session.get(Issue, match_id)
            if issue is None or issue.status == "confirmed":
                db.session.rollback()
                raise ReportError("That similar report is no longer available. You can submit a new report.")
            _support_issue(user, issue)
            db.session.commit()
        except ReportError:
            db.session.rollback()
            raise
        raise SupportAccepted()

    errors = []
    if category not in current_app.config["CATEGORIES"]:
        errors.append("Choose a category.")
    if len(description) < 10 or len(description) > 1000:
        errors.append("Describe the issue in 10–1000 characters.")
    if not photo_consent:
        errors.append("Photo consent is required to submit a report.")
    if not location_consent or lat is None or lng is None:
        errors.append("Set a map pin and consent to store the location.")
    if lat is not None and lng is not None and (lat < -90 or lat > 90 or lng < -180 or lng > 180):
        errors.append("Location is out of range.")
    if errors:
        raise ReportError("\n".join(errors))

    force_create = duplicate_action == "different"
    _begin_immediate()
    try:
        if not force_create:
            match = find_nearby_duplicate(category, lat, lng)
            if match:
                session["duplicate_match_id"] = match["issue"].id
                payload = duplicate_public_payload(match)
                db.session.rollback()
                raise DuplicateFound(payload)
        try:
            filename = save_issue_photo(files.get("photo"))
            check = _photo_quality(user, filename)
        except UploadError as exc:
            db.session.rollback()
            raise ReportError(str(exc)) from exc

        issue = Issue(
            public_id=new_public_id(),
            reporter_id=user.id,
            category=category,
            description=description,
            lat=lat,
            lng=lng,
            location_consent=True,
            public_map_consent=public_map_consent,
            status="reported",
            possible_duplicate=force_create,
            needs_review=check.needs_review,
        )
        db.session.add(issue)
        db.session.flush()
        db.session.add(
            IssuePhoto(
                issue_id=issue.id,
                kind="before",
                filename=filename,
                dhash=check.dhash or None,
                uploaded_by=user.id,
            )
        )
        record_status(issue, user, "reported", note="Issue reported by citizen.", initial=True)
        db.session.commit()
        session.pop("duplicate_match_id", None)
        from app.services.notifications import notify_new_issue

        notify_new_issue(issue)
        return issue
    except DuplicateFound:
        raise
    except ReportError:
        db.session.rollback()
        raise


def confirm_issue(issue, user):
    if "confirmed" not in citizen_allowed(issue.status):
        raise TransitionError("This report cannot be confirmed yet.")
    record_status(issue, user, "confirmed", note="Citizen confirmed the repair.")
    db.session.commit()


def reopen_issue(issue, user, note, photo_file=None):
    if "reopened" not in citizen_allowed(issue.status):
        raise TransitionError("This report cannot be reopened.")
    note = (note or "").strip()
    if len(note) < 8:
        raise TransitionError("Explain why the issue is still unresolved (at least 8 characters).")
    if photo_file and photo_file.filename:
        try:
            filename = save_issue_photo(photo_file)
            check = _photo_quality(user, filename, error_cls=TransitionError)
        except UploadError as exc:
            raise TransitionError(str(exc)) from exc
        db.session.add(
            IssuePhoto(
                issue_id=issue.id,
                kind="before",
                filename=filename,
                dhash=check.dhash or None,
                uploaded_by=user.id,
            )
        )
        if check.needs_review:
            issue.needs_review = True
    record_status(issue, user, "reopened", note=note)
    db.session.commit()


def apply_staff_transition(public_id, actor, to_status, note, photo_file=None):
    note = (note or "").strip()
    if len(note) > 500:
        raise TransitionError("Keep the note under 500 characters.")
    issue = db.session.execute(
        select(Issue).where(Issue.public_id == public_id).with_for_update()
    ).scalar_one_or_none()
    if issue is None or not staff_can_access(actor, issue):
        return None
    db.session.refresh(issue)
    allowed = staff_allowed(issue.status)
    if to_status not in allowed:
        raise TransitionError(
            "That status change is not allowed from " + status_label(issue.status) + "."
        )
    if to_status == "marked_resolved":
        has_file = photo_file and photo_file.filename
        if not has_file and not issue.has_after_photo():
            raise TransitionError("An after-repair photo is required before marking resolved.")
        if has_file:
            try:
                filename = save_issue_photo(photo_file)
                check = _photo_quality(actor, filename, error_cls=TransitionError)
            except UploadError as exc:
                raise TransitionError(str(exc)) from exc
            db.session.add(
                IssuePhoto(
                    issue_id=issue.id,
                    kind="after",
                    filename=filename,
                    dhash=check.dhash or None,
                    uploaded_by=actor.id,
                )
            )
            if check.needs_review:
                issue.needs_review = True
    record_status(issue, actor, to_status, note=note or None)
    db.session.commit()
    if to_status == "marked_resolved":
        try:
            from app.services.notifications import notify_marked_resolved

            notify_marked_resolved(issue)
        except Exception:
            import logging

            logging.getLogger("civic.notifications").warning(
                "Resolved report email could not be sent."
            )
    return issue


def auto_confirm_stale():
    days = int(current_app.config.get("AUTO_CONFIRM_DAYS", 7))
    cutoff = utcnow() - timedelta(days=days)
    actor = User.query.filter(User.role.in_(("staff", "admin"))).first()
    if actor is None:
        return 0
    issues = (
        Issue.query.filter_by(status="marked_resolved")
        .filter(Issue.updated_at <= cutoff)
        .all()
    )
    count = 0
    for issue in issues:
        record_status(
            issue,
            actor,
            "confirmed",
            note="Auto-confirmed after " + str(days) + " days.",
        )
        count += 1
    if count:
        db.session.commit()
    return count


def delete_citizen_account(user, password=None, skip_password=False):
    if not skip_password:
        if not password or not user.check_password(password):
            raise ReportError("Password is incorrect.")
    user_id = user.id
    IssueSupporter.query.filter_by(user_id=user_id).delete()
    issues = Issue.query.options(selectinload(Issue.photos)).filter_by(reporter_id=user_id).all()
    filenames = [photo.filename for issue in issues for photo in issue.photos]
    for issue in issues:
        db.session.delete(issue)
    row = db.session.get(User, user_id)
    if row is not None:
        db.session.delete(row)
    db.session.commit()
    for filename in filenames:
        delete_photo_file(filename)


def public_pin_rows():
    rounding = current_app.config["COORDINATE_ROUNDING"]
    limit = int(current_app.config.get("PUBLIC_PIN_LIMIT", 200))
    from app.services.images import round_coordinates
    from app.services.status_machine import status_label
    from app.config import category_label

    rows = (
        db.session.query(Issue.category, Issue.status, Issue.lat, Issue.lng)
        .filter(Issue.public_map_consent.is_(True))
        .filter(Issue.status != "confirmed")
        .order_by(Issue.created_at.desc())
        .limit(limit)
        .all()
    )
    pins = []
    for category, status, lat, lng in rows:
        rlat, rlng = round_coordinates(lat, lng, rounding)
        pins.append(
            {
                "category": category_label(category),
                "status": status,
                "status_label": status_label(status),
                "lat": rlat,
                "lng": rlng,
            }
        )
    return pins
