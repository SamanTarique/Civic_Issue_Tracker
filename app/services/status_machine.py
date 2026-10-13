STATUS_ORDER = (
    "reported",
    "acknowledged",
    "in_progress",
    "marked_resolved",
    "confirmed",
    "reopened",
)

STATUS_LABELS = {
    "reported": "Reported",
    "acknowledged": "Acknowledged",
    "in_progress": "In progress",
    "marked_resolved": "Marked resolved",
    "confirmed": "Confirmed",
    "reopened": "Reopened",
}

STAFF_TRANSITIONS = {
    "reported": ("acknowledged", "in_progress"),
    "acknowledged": ("in_progress", "marked_resolved"),
    "in_progress": ("marked_resolved",),
    "reopened": ("in_progress", "marked_resolved"),
}

CITIZEN_TRANSITIONS = {
    "marked_resolved": ("confirmed", "reopened"),
}


def status_label(code):
    if not code:
        return ""
    return STATUS_LABELS.get(code, str(code).replace("_", " ").title())


def staff_allowed(current):
    return STAFF_TRANSITIONS.get(current, ())


def citizen_allowed(current):
    return CITIZEN_TRANSITIONS.get(current, ())
