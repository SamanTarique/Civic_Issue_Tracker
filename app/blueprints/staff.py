from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy.orm import selectinload

from app import db
from app.models import Issue
from app.services.issues import (
    TransitionError,
    apply_staff_transition,
    paginate_query,
    staff_can_access,
    staff_queue_query,
)
from app.services.status_machine import STATUS_ORDER, staff_allowed, status_label

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


def _staff_required():
    if not current_user.is_authenticated or not current_user.is_staff:
        abort(403)


@staff_bp.before_request
def require_staff():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.path))
    _staff_required()


@staff_bp.route("")
def queue():
    status_filter = (request.args.get("status") or "").strip()
    allowed = list(STATUS_ORDER)
    query = staff_queue_query(current_user, status_filter if status_filter in allowed else None)
    page = request.args.get("page", 1, type=int)
    pagination = paginate_query(query, page)
    return render_template(
        "staff/queue.html",
        pagination=pagination,
        issues=pagination.items,
        status_filter=status_filter,
        status_options=allowed,
    )


@staff_bp.route("/<public_id>", methods=["GET", "POST"])
def detail(public_id):
    if request.method == "POST":
        if (request.form.get("action") or "").strip() == "clear_review":
            issue = Issue.query.filter_by(public_id=public_id).first_or_404()
            if not staff_can_access(current_user, issue):
                abort(404)
            issue.needs_review = False
            db.session.commit()
            flash("Review flag cleared.", "success")
            return redirect(url_for("staff.detail", public_id=public_id))
        try:
            issue = apply_staff_transition(
                public_id,
                current_user,
                (request.form.get("status") or "").strip(),
                request.form.get("note"),
                request.files.get("photo"),
            )
        except TransitionError as exc:
            flash(str(exc), "error")
            return redirect(url_for("staff.detail", public_id=public_id))
        if issue is None:
            abort(404)
        flash("Status updated to " + status_label(issue.status) + ".", "success")
        return redirect(url_for("staff.detail", public_id=public_id))
    issue = (
        Issue.query.options(
            selectinload(Issue.photos),
            selectinload(Issue.events),
            selectinload(Issue.reporter),
            selectinload(Issue.supporters),
        )
        .filter_by(public_id=public_id)
        .first_or_404()
    )
    if not staff_can_access(current_user, issue):
        abort(404)
    return render_template("staff/detail.html", issue=issue, allowed=staff_allowed(issue.status))
