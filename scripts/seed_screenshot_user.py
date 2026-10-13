import io
import sys
from pathlib import Path

from PIL import Image
from werkzeug.datastructures import FileStorage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app, db
from app.models import User
from app.services.issues import create_report


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (80, 80), color=(20, 80, 120)).save(buf, format="JPEG")
    buf.seek(0)
    return buf


def main():
    app = create_app()
    with app.app_context():
        email = "screenshot@example.com"
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, role="citizen", auth_provider="password")
            user.set_password("password1")
            db.session.add(user)
            db.session.commit()
        if not user.issues:
            photo = FileStorage(stream=jpeg(), filename="hole.jpg", content_type="image/jpeg")
            create_report(
                user,
                {
                    "category": "pothole",
                    "description": "Deep pothole on the corner near the school gate.",
                    "lat": "33.6844",
                    "lng": "73.0479",
                    "photo_consent": "on",
                    "location_consent": "on",
                },
                {"photo": photo},
            )
        print("ready")


if __name__ == "__main__":
    main()
