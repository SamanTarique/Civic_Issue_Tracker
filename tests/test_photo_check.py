import io
import tracemalloc
from pathlib import Path

from PIL import Image
from werkzeug.datastructures import FileStorage

from app import create_app, db
from app.models import Issue, IssuePhoto
from app.services.images import save_issue_photo
from app.services.photo_check import ACCEPT, REJECT, WARN, evaluate_path, hamming_hex
from tests.conftest import app_config, jpeg_bytes, register, submit_report


def _rgb_bytes(size, color, name="shot.jpg", seed=99):
    buffer = jpeg_bytes(color=color, seed=seed)
    return buffer, name


def _strict(tmp_path):
    return app_config(
        tmp_path,
        PHOTO_MIN_EDGE=64,
        PHOTO_BLUR_MIN_VARIANCE=12.0,
        PHOTO_DARK_MEAN=18.0,
        PHOTO_BRIGHT_MEAN=237.0,
    )


def test_tiny_blurry_dark_bright_unreadable(tmp_path):
    application = create_app(_strict(tmp_path))
    with application.app_context():
        db.create_all()
        tiny = tmp_path / "tiny.jpg"
        Image.new("RGB", (8, 8), (80, 80, 80)).save(tiny, format="JPEG")
        assert evaluate_path(tiny).decision == REJECT
        assert "too small" in evaluate_path(tiny).message

        blur = tmp_path / "blur.png"
        Image.new("RGB", (200, 200), (90, 90, 90)).save(blur, format="PNG")
        assert evaluate_path(blur).decision == WARN

        dark = tmp_path / "dark.jpg"
        Image.new("RGB", (200, 200), (2, 2, 2)).save(dark, format="JPEG")
        assert evaluate_path(dark).decision == REJECT
        assert "too dark" in evaluate_path(dark).message

        bright = tmp_path / "bright.jpg"
        Image.new("RGB", (200, 200), (250, 250, 250)).save(bright, format="JPEG")
        assert evaluate_path(bright).decision == REJECT
        assert "too bright" in evaluate_path(bright).message

        junk = tmp_path / "bad.jpg"
        junk.write_bytes(b"not-a-photo")
        unread = evaluate_path(junk)
        assert unread.decision == REJECT
        assert "readable" in unread.message


def test_same_user_duplicate_rejected_other_user_flagged(client, app):
    payload, name = _rgb_bytes((120, 120), (40, 90, 160), "same.jpg")
    register(client, "photo-a@example.com")
    first = submit_report(client, photo=(payload, name), lat="33.684400", lng="73.047900")
    assert b"Tracking ID" in first.data
    payload, name = _rgb_bytes((120, 120), (40, 90, 160), "same.jpg")
    again = submit_report(client, photo=(payload, name), lat="33.900000", lng="73.300000")
    assert b"nearly identical photo" in again.data
    with app.app_context():
        assert Issue.query.count() == 1
    client.post("/logout")
    register(client, "photo-b@example.com")
    payload, name = _rgb_bytes((120, 120), (40, 90, 160), "same.jpg")
    other = submit_report(client, photo=(payload, name), lat="33.910000", lng="73.310000")
    assert b"Tracking ID" in other.data
    with app.app_context():
        flagged = Issue.query.filter_by(needs_review=True).one()
        assert flagged.reporter.email == "photo-b@example.com"


def test_staff_clears_needs_review(client, app):
    register(client, "photo-staff-owner@example.com")
    payload, name = _rgb_bytes((120, 120), (40, 90, 160), "flag.jpg")
    submit_report(client, photo=(payload, name))
    client.post("/logout")
    register(client, "photo-staff-other@example.com")
    payload, name = _rgb_bytes((120, 120), (40, 90, 160), "flag.jpg")
    submit_report(client, photo=(payload, name), lat="33.900000", lng="73.300000")
    with app.app_context():
        public_id = Issue.query.filter_by(needs_review=True).one().public_id
    client.post("/logout")
    client.post("/login", data={"email": "staff@example.com", "password": "staff-pass-123"})
    queue = client.get("/staff")
    assert b"Needs review" in queue.data
    cleared = client.post(
        "/staff/" + public_id,
        data={"action": "clear_review"},
        follow_redirects=True,
    )
    assert b"Review flag cleared" in cleared.data
    with app.app_context():
        assert Issue.query.filter_by(public_id=public_id).one().needs_review is False


def test_photo_check_output_has_no_exif(app):
    buffer = io.BytesIO()
    image = Image.new("RGB", (80, 80), (30, 80, 120))
    exif = image.getexif()
    exif[271] = "PrivacyCam"
    image.save(buffer, format="JPEG", exif=exif)
    buffer.seek(0)
    storage = FileStorage(stream=buffer, filename="cam.jpg", content_type="image/jpeg")
    with app.app_context():
        filename = save_issue_photo(storage)
        stored = Image.open(Path(app.config["UPLOAD_FOLDER"]) / filename)
        leftover = dict(stored.getexif())
        stored.close()
        assert 271 not in leftover
        check = evaluate_path(Path(app.config["UPLOAD_FOLDER"]) / filename)
        assert "PrivacyCam" not in check.message
        assert check.decision in {ACCEPT, WARN, REJECT}


def test_peak_memory_10mb_upload(tmp_path):
    application = create_app(app_config(tmp_path, MAX_CONTENT_LENGTH=12 * 1024 * 1024))
    path = tmp_path / "ten.jpg"
    Image.new("RGB", (1600, 1200), (40, 80, 60)).save(path, format="JPEG", quality=85)
    needed = 10 * 1024 * 1024 - path.stat().st_size
    if needed > 0:
        with path.open("ab") as handle:
            handle.write(b"\x00" * needed)
    size = path.stat().st_size
    storage = FileStorage(stream=open(path, "rb"), filename="ten.jpg", content_type="image/jpeg")
    with application.app_context():
        db.create_all()
        tracemalloc.start()
        filename = save_issue_photo(storage)
        evaluate_path(Path(application.config["UPLOAD_FOLDER"]) / filename)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    storage.stream.close()
    peak_mb = peak / (1024 * 1024)
    (tmp_path / "peak.txt").write_text(
        "file_bytes=" + str(size) + " peak_bytes=" + str(peak) + " peak_mb=" + str(round(peak_mb, 3)),
        encoding="utf-8",
    )
    print("PHOTO_PEAK_MEMORY file_bytes=" + str(size) + " peak_bytes=" + str(peak))
    assert peak_mb < 200
    assert size >= 10 * 1024 * 1024


def test_eval_photos_says_none_supplied(tmp_path):
    from scripts.eval_photos import main

    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty)]) == 0
    assert main([]) == 0


def test_hashes_within_distance_share_a_prefilter_bucket():
    import random

    from app.services.photo_check import prefilter_covers

    rng = random.Random(10)
    for max_distance in (10, 16, 32):
        for _ in range(40):
            left = rng.randrange(1 << 64)
            flips = rng.sample(range(64), rng.randint(0, max_distance))
            right = left
            for bit in flips:
                right ^= 1 << bit
            left_hex = f"{left:016x}"
            right_hex = f"{right:016x}"
            assert hamming_hex(left_hex, right_hex) <= max_distance
            assert prefilter_covers(right_hex, left_hex, max_distance)


def _hash_issue(user):
    from app.models import new_public_id

    return Issue(
        public_id=new_public_id(),
        reporter_id=user.id,
        category="pothole",
        description="Hash lookup fixture for duplicate photos.",
        lat=33.68,
        lng=73.04,
        location_consent=False,
        public_map_consent=False,
        status="reported",
    )


def test_duplicate_hash_is_found_without_loading_every_row(app):
    from app.models import User
    from app.services.issues import similar_photo_candidates
    from app.services.photo_check import prefilter_covers

    query = "0000000000000000"
    near = "0000000000000001"
    inside = "0101010101111110"
    outside = "0101010101111111"
    assert hamming_hex(query, near) == 1
    assert hamming_hex(query, inside) == 10
    assert hamming_hex(query, outside) == 11
    assert prefilter_covers(inside, query, 10)
    assert not prefilter_covers(outside, query, 10)
    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").one()
        issue = _hash_issue(user)
        db.session.add(issue)
        db.session.flush()
        hashes = [outside, "ffffffffffffffff"] * 10
        hashes.extend([near, inside, "000000000000000A"])
        for index, digest in enumerate(hashes):
            db.session.add(
                IssuePhoto(
                    issue_id=issue.id,
                    kind="before",
                    filename="hash-{0}.jpg".format(index),
                    dhash=digest,
                    uploaded_by=user.id,
                )
            )
        db.session.commit()
        stored = IssuePhoto.query.filter(IssuePhoto.dhash.isnot(None)).count()
        rows = similar_photo_candidates(query, 10)
        found = [row[0].lower() for row in rows]
        assert stored > len(rows)
        assert stored >= 23
        assert near in found
        assert inside in found
        assert "000000000000000a" in found
        assert outside not in found
        assert "ffffffffffffffff" not in found
        assert found[0] == near


def test_wider_distance_prefilter_stays_in_sql(app):
    from app.models import User
    from app.services.issues import similar_photo_candidates

    query = "0000000000000000"
    shared_pair = "8888888888888888"
    no_pair = "5555555555555555"
    no_bit = "ffffffffffffffff"
    assert hamming_hex(query, shared_pair) == 16
    assert hamming_hex(query, no_pair) == 32
    assert hamming_hex(query, no_bit) == 64
    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").one()
        issue = _hash_issue(user)
        db.session.add(issue)
        db.session.flush()
        for index, digest in enumerate((shared_pair, no_pair, no_bit)):
            db.session.add(
                IssuePhoto(
                    issue_id=issue.id,
                    kind="before",
                    filename="wide-{0}.jpg".format(index),
                    dhash=digest,
                    uploaded_by=user.id,
                )
            )
        db.session.commit()
        stored = IssuePhoto.query.filter(IssuePhoto.dhash.isnot(None)).count()
        within_16 = [row[0].lower() for row in similar_photo_candidates(query, 16)]
        within_32 = [row[0].lower() for row in similar_photo_candidates(query, 32)]
        assert len(within_16) < stored
        assert within_16 == [shared_pair]
        assert len(within_32) < stored
        assert no_pair in within_32
        assert shared_pair in within_32
        assert no_bit not in within_32
