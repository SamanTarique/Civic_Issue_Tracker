import logging
import smtplib
import threading
from email.message import EmailMessage

from flask import current_app, url_for

from app.config import department_for_category

_LOG = logging.getLogger("civic.notifications")

_DEPT_EMAIL_KEYS = {
    "Roads": "DEPT_EMAIL_ROADS",
    "Sanitation": "DEPT_EMAIL_SANITATION",
    "Water": "DEPT_EMAIL_WATER",
    "Electric": "DEPT_EMAIL_ELECTRIC",
    "Other": "DEPT_EMAIL_OTHER",
}


def department_inbox(department):
    key = _DEPT_EMAIL_KEYS.get(department) or "DEPT_EMAIL_OTHER"
    return (current_app.config.get(key) or "").strip()


def _osm_link(lat, lng):
    return "https://www.openstreetmap.org/?mlat={0}&mlon={1}#map=18/{0}/{1}".format(lat, lng)


def build_department_email(issue, staff_login_url):
    from app.config import category_label

    description = (issue.description or "")[:300]
    body = (
        "New civic report\n"
        "Tracking ID: {pid}\n"
        "Category: {cat}\n"
        "Description: {desc}\n"
        "Map: {osm}\n"
        "Staff login: {login}\n"
    ).format(
        pid=issue.public_id,
        cat=category_label(issue.category),
        desc=description,
        osm=_osm_link(issue.lat, issue.lng),
        login=staff_login_url,
    )
    return "New report " + issue.public_id, body


def _deliver(to_addr, subject, body):
    backend = (current_app.config.get("EMAIL_BACKEND") or "console").strip().lower()
    if backend == "memory":
        box = current_app.config.setdefault("_EMAIL_OUTBOX", [])
        box.append({"to": to_addr, "subject": subject, "body": body})
        return
    if backend == "console":
        print(subject)
        print(body)
        return
    if backend != "smtp":
        return
    host = current_app.config.get("SMTP_HOST") or ""
    port = int(current_app.config.get("SMTP_PORT") or 587)
    user = current_app.config.get("SMTP_USER") or ""
    password = current_app.config.get("SMTP_PASSWORD") or ""
    mail_from = current_app.config.get("SMTP_FROM") or user
    use_tls = current_app.config.get("SMTP_TLS", True)
    timeout = float(current_app.config.get("EMAIL_TIMEOUT") or 8)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = mail_from
    message["To"] = to_addr
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if use_tls:
            smtp.starttls()
        if user:
            smtp.login(user, password)
        smtp.send_message(message)


def _send_job(app, to_addr, subject, body):
    try:
        with app.app_context():
            _deliver(to_addr, subject, body)
    except Exception:
        _LOG.warning("Department notification could not be sent.")


def notify_new_issue(issue):
    if issue.is_demo and not current_app.config.get("EMAIL_FOR_DEMO"):
        return
    department = department_for_category(
        issue.category, current_app.config.get("CATEGORY_DEPARTMENT")
    )
    to_addr = department_inbox(department)
    if not to_addr:
        return
    try:
        staff_login_url = url_for("auth.login", _external=True)
    except Exception:
        staff_login_url = "/login"
    subject, body = build_department_email(issue, staff_login_url)
    app = current_app._get_current_object()
    if current_app.config.get("TESTING"):
        _send_job(app, to_addr, subject, body)
        return
    thread = threading.Thread(
        target=_send_job,
        args=(app, to_addr, subject, body),
        daemon=True,
    )
    thread.start()
