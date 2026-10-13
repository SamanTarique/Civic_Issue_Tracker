import re
import tempfile
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageDraw, ImageFile, ImageFont, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
STORED_NAME = re.compile(r"^[a-f0-9]{32}\.jpg$")
THUMB_NAME = re.compile(r"^[a-f0-9]{32}_thumb\.jpg$")
DEMO_NAME = re.compile(r"^demo-[a-z0-9-]+\.jpg$")

ImageFile.LOAD_TRUNCATED_IMAGES = False


class UploadError(ValueError):
    pass


def round_coordinates(lat, lng, digits=None):
    digits = digits if digits is not None else current_app.config["COORDINATE_ROUNDING"]
    return round(float(lat), digits), round(float(lng), digits)


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        rgba.close()
        return background
    return image.convert("RGB")


def _upload_root() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]).resolve()


def thumb_name(filename: str) -> str:
    return filename.replace(".jpg", "_thumb.jpg")


def is_stored_filename(filename: str) -> bool:
    return bool(filename and STORED_NAME.fullmatch(filename))


def is_demo_filename(filename: str) -> bool:
    return bool(filename and DEMO_NAME.fullmatch(filename))


def demo_static_dir() -> Path:
    return Path(current_app.root_path) / "static" / "demo"


def generate_labelled_demo_jpeg(color=(80, 120, 160), caption="DEMO", copy_public=False):
    image = Image.new("RGB", (320, 240), color=color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 312, 232), outline=(255, 255, 255), width=4)
    try:
        font = ImageFont.load_default()
    except OSError:
        font = None
    label = caption if caption.startswith("DEMO") else "DEMO · " + caption
    draw.text((20, 100), label, fill=(255, 255, 255), font=font)
    root = _upload_root()
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    destination = root / filename
    image.save(destination, format="JPEG", quality=80, optimize=True, exif=b"")
    image.close()
    _write_thumbnail(destination)
    if copy_public:
        public_dir = Path(current_app.root_path) / "static" / "demo"
        public_dir.mkdir(parents=True, exist_ok=True)
        (public_dir / filename).write_bytes(destination.read_bytes())
    return filename


def save_issue_photo(file_storage: FileStorage) -> str:
    if not file_storage or not file_storage.filename:
        raise UploadError("Please attach a photo.")

    suffix = Path(file_storage.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadError("Use a JPEG, PNG, or WebP photo.")

    upload_root = _upload_root()
    upload_root.mkdir(parents=True, exist_ok=True)
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = current_app.config.get("IMAGE_MAX_PIXELS", 20_000_000)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            file_storage.save(tmp)
            tmp.flush()
            size = tmp.tell()
        if size == 0:
            raise UploadError("The photo file is empty.")
        if size > current_app.config["MAX_CONTENT_LENGTH"]:
            raise UploadError("That photo is too large.")

        with Image.open(tmp_path) as probe:
            probe.verify()

        with Image.open(tmp_path) as image:
            if image.format == "JPEG":
                max_edge = current_app.config["IMAGE_MAX_EDGE"]
                image.draft("RGB", (max_edge, max_edge))
            mime = Image.MIME.get(image.format, "")
            if mime not in current_app.config["ALLOWED_IMAGE_MIMES"]:
                raise UploadError("Use a JPEG, PNG, or WebP photo.")
            transposed = ImageOps.exif_transpose(image)
            working = transposed if transposed is not None else image
            rgb = _flatten_to_rgb(working)
            max_edge = current_app.config["IMAGE_MAX_EDGE"]
            rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            filename = f"{uuid.uuid4().hex}.jpg"
            destination = upload_root / filename
            rgb.save(
                destination,
                format="JPEG",
                quality=current_app.config["IMAGE_JPEG_QUALITY"],
                optimize=True,
                exif=b"",
            )
            rgb.close()
            if transposed is not None and transposed is not image:
                transposed.close()
        _write_thumbnail(destination)
        return filename
    except Image.DecompressionBombError as exc:
        raise UploadError("That photo is too large.") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise UploadError("That file is not a valid image.") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def _write_thumbnail(full_path: Path) -> None:
    thumb_edge = int(current_app.config.get("THUMB_MAX_EDGE", 320))
    thumb_path = full_path.with_name(full_path.stem + "_thumb.jpg")
    with Image.open(full_path) as image:
        if image.format == "JPEG":
            image.draft("RGB", (thumb_edge, thumb_edge))
        image.thumbnail((thumb_edge, thumb_edge), Image.Resampling.LANCZOS)
        image.save(
            thumb_path,
            format="JPEG",
            quality=current_app.config["IMAGE_JPEG_QUALITY"],
            optimize=True,
            exif=b"",
        )


def delete_photo_file(filename: str) -> None:
    if is_demo_filename(filename):
        return
    if not is_stored_filename(filename):
        return
    root = _upload_root()
    for name in (filename, thumb_name(filename)):
        path = (root / name).resolve()
        if path.is_file() and path.parent == root:
            path.unlink()


def find_orphan_uploads():
    root = _upload_root()
    if not root.is_dir():
        return []
    from app.models import IssuePhoto

    known = set()
    for filename in (row[0] for row in IssuePhoto.query.with_entities(IssuePhoto.filename)):
        if filename:
            known.add(filename)
            known.add(thumb_name(filename))
    orphans = []
    for path in root.iterdir():
        if path.is_file() and path.name not in known:
            orphans.append(path.name)
    return orphans


def backfill_thumbnails():
    root = _upload_root()
    if not root.is_dir():
        return 0
    count = 0
    for path in root.glob("*.jpg"):
        if path.name.endswith("_thumb.jpg"):
            continue
        if not is_stored_filename(path.name):
            continue
        thumb_path = root / thumb_name(path.name)
        if thumb_path.is_file():
            continue
        _write_thumbnail(path)
        count += 1
    return count


def resolve_photo_path(filename: str, thumb=False) -> Path:
    if is_demo_filename(filename):
        root = demo_static_dir().resolve()
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            raise FileNotFoundError
        return path
    if not is_stored_filename(filename):
        raise FileNotFoundError
    name = thumb_name(filename) if thumb else filename
    if thumb and not THUMB_NAME.fullmatch(name):
        raise FileNotFoundError
    root = _upload_root()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise FileNotFoundError
    return path
