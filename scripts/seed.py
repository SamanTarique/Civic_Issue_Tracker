"""Create or promote the staff user from STAFF_EMAIL / STAFF_PASSWORD in .env."""

from app import create_app
from app.models import ensure_staff_user


def main():
    app = create_app()
    with app.app_context():
        ensure_staff_user()
        print("Staff account is ready (email taken from STAFF_EMAIL).")


if __name__ == "__main__":
    main()
