from io import BytesIO

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from app import limiter
from sqlalchemy.orm import selectinload

from app import db
from app.models import Issue, IssuePhoto
from app.services.images import _write_thumbnail, resolve_photo_path
from app.services.issues import (
    DuplicateFound,
    ReportError,
    SupportAccepted,
    TransitionError,
    citizen_issue_query,
    confirm_issue,
    create_report,
    paginate_query,
    reopen_issue,
    staff_can_access,
)
from app.services.status_machine import CITIZEN_TRANSITIONS

citizen_bp = Blueprint("citizen", __name__, url_prefix="/reports")


def _issue_for_citizen(public_id):
    issue = (
        Issue.query.options(selectinload(Issue.photos), selectinload(Issue.events))
        .filter_by(public_id=public_id)
        .first_or_404()
    )
    if issue.reporter_id != current_user.id and not current_user.is_staff:
        abort(404)
    return issue


@citizen_bp.route("")
@login_required
def my_reports():
    if current_user.is_staff:
        return redirect(url_for("staff.queue"))
    page = request.args.get("page", 1, type=int)
    pagination = paginate_query(citizen_issue_query(current_user.id), page)
    return render_template("citizen/list.html", pagination=pagination, issues=pagination.items)


def _report_limit_key():
    if current_user.is_authenticated:
        return "user:" + str(current_user.id)
    from flask_limiter.util import get_remote_address

    return get_remote_address()


@citizen_bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute", methods=["POST"], key_func=_report_limit_key)
def new_report():
    if current_user.is_staff:
        return redirect(url_for("staff.queue"))
    if request.method == "POST":
        try:
            issue = create_report(current_user, request.form, request.files)
        except SupportAccepted:
            flash("You're listed as affected. No new ticket was opened.", "success")
            return redirect(url_for("citizen.my_reports"))
        except DuplicateFound as exc:
            return render_template(
                "citizen/new.html",
                map_default_lat=current_app.config["MAP_DEFAULT_LAT"],
                map_default_lng=current_app.config["MAP_DEFAULT_LNG"],
                duplicate=exc.payload,
                form=request.form,
            )
        except ReportError as exc:
            for message in str(exc).split("\n"):
                flash(message, "error")
        else:
            flash("Report submitted. Tracking ID " + issue.public_id, "success")
            return redirect(url_for("citizen.detail", public_id=issue.public_id))

    return render_template(
        "citizen/new.html",
        map_default_lat=current_app.config["MAP_DEFAULT_LAT"],
        map_default_lng=current_app.config["MAP_DEFAULT_LNG"],
        duplicate=None,
        form=None,
    )


@citizen_bp.route("/<public_id>")
@login_required
def detail(public_id):
    issue = _issue_for_citizen(public_id)
    if current_user.is_staff:
        return redirect(url_for("staff.detail", public_id=public_id))
    return render_template(
        "citizen/detail.html",
        issue=issue,
        allowed_citizen=CITIZEN_TRANSITIONS.get(issue.status, ()),
    )


@citizen_bp.route("/<public_id>/confirm", methods=["POST"])
@login_required
def confirm(public_id):
    issue = _issue_for_citizen(public_id)
    if current_user.is_staff or issue.reporter_id != current_user.id:
        abort(403)
    try:
        confirm_issue(issue, current_user)
    except TransitionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("citizen.detail", public_id=public_id))
    flash("Thank you. This issue is marked confirmed.", "success")
    return redirect(url_for("citizen.detail", public_id=public_id))


@citizen_bp.route("/<public_id>/reopen", methods=["POST"])
@login_required
def reopen(public_id):
    issue = _issue_for_citizen(public_id)
    if current_user.is_staff or issue.reporter_id != current_user.id:
        abort(403)
    try:
        reopen_issue(issue, current_user, request.form.get("note"), request.files.get("photo"))
    except TransitionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("citizen.detail", public_id=public_id))
    flash("Report reopened. Staff will see it in their queue.", "success")
    return redirect(url_for("citizen.detail", public_id=public_id))


_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72">'
    b'<rect width="72" height="72" fill="#f8fafc" stroke="#e2e8f0"/>'
    b'<rect x="18" y="22" width="36" height="28" rx="4" fill="#e2e8f0"/>'
    b'<circle cx="28" cy="34" r="4" fill="#94a3b8"/>'
    b'<path d="M22 46l10-10 8 8 6-6 10 10" fill="none" stroke="#94a3b8" stroke-width="2"/>'
    b"</svg>"
)


def _send_photo(photo_id, thumb=False):
    photo = db.session.get(IssuePhoto, photo_id)
    if not photo:
        abort(404)
    issue = photo.issue
    if issue.reporter_id == current_user.id:
        pass
    elif current_user.is_staff and staff_can_access(current_user, issue):
        pass
    else:
        abort(404)
    if thumb:
        try:
            path = resolve_photo_path(photo.filename, thumb=True)
        except FileNotFoundError:
            try:
                full = resolve_photo_path(photo.filename, thumb=False)
                _write_thumbnail(full)
                path = resolve_photo_path(photo.filename, thumb=True)
            except FileNotFoundError:
                response = current_app.response_class(_PLACEHOLDER_SVG, mimetype="image/svg+xml")
                response.headers["Cache-Control"] = "private, no-store"
                return response
    else:
        try:
            path = resolve_photo_path(photo.filename, thumb=False)
        except FileNotFoundError:
            abort(404)
    payload = BytesIO(path.read_bytes())
    response = send_file(
        payload,
        mimetype="image/jpeg",
        download_name=path.name,
        max_age=0,
        etag=False,
        conditional=False,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Content-Type"] = "image/jpeg"
    return response


@citizen_bp.route("/photos/<int:photo_id>")
@login_required
def photo(photo_id):
    return _send_photo(photo_id, thumb=False)


@citizen_bp.route("/photos/<int:photo_id>/thumb")
@login_required
def photo_thumb(photo_id):
    return _send_photo(photo_id, thumb=True)
