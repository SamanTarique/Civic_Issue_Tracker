from dataclasses import dataclass, field
from pathlib import Path

from flask import current_app
from PIL import Image, ImageStat, UnidentifiedImageError

ACCEPT = "ACCEPT"
WARN = "WARN"
REJECT = "REJECT"


@dataclass
class PhotoCheck:
    decision: str
    dhash: str = ""
    reasons: list = field(default_factory=list)
    width: int = 0
    height: int = 0
    blur_var: float = 0.0
    brightness: float = 0.0

    @property
    def needs_review(self):
        return self.decision == WARN

    @property
    def message(self):
        return " ".join(self.reasons) if self.reasons else "Photo accepted."


def _cfg(name, default):
    try:
        return current_app.config.get(name, default)
    except RuntimeError:
        return default


def dhash_hex(gray: Image.Image) -> str:
    small = gray.resize((9, 8), Image.Resampling.BILINEAR)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            bits = (bits << 1) | int(left > right)
    small.close()
    return f"{bits:016x}"


def hamming_hex(left: str, right: str) -> int:
    if not left or not right:
        return 64
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def laplacian_variance(gray: Image.Image) -> float:
    pixels = gray.load()
    width, height = gray.size
    if width < 3 or height < 3:
        return 0.0
    total = 0.0
    squared = 0.0
    count = 0
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            value = (
                pixels[x, y - 1]
                + pixels[x - 1, y]
                + pixels[x + 1, y]
                + pixels[x, y + 1]
                - 4 * pixels[x, y]
            )
            total += value
            squared += value * value
            count += 1
    mean = total / count
    return squared / count - mean * mean


def evaluate_gray(gray: Image.Image, width: int, height: int) -> PhotoCheck:
    min_edge = int(_cfg("PHOTO_MIN_EDGE", 64))
    blur_min = float(_cfg("PHOTO_BLUR_MIN_VARIANCE", 12.0))
    dark_max = float(_cfg("PHOTO_DARK_MEAN", 18.0))
    bright_min = float(_cfg("PHOTO_BRIGHT_MEAN", 237.0))
    reasons = []
    decision = ACCEPT
    working = gray.copy()
    working.thumbnail((128, 128), Image.Resampling.BILINEAR)
    try:
        brightness = float(ImageStat.Stat(working).mean[0])
        blur_var = laplacian_variance(working)
        digest = dhash_hex(working)
    finally:
        working.close()

    if width < min_edge or height < min_edge:
        decision = REJECT
        reasons.append("That photo is too small.")
    if brightness <= dark_max:
        decision = REJECT
        reasons.append("That photo is too dark.")
    if brightness >= bright_min:
        decision = REJECT
        reasons.append("That photo is too bright.")
    if decision != REJECT and blur_var < blur_min:
        decision = WARN
        reasons.append("That photo looks blurry; staff will review it.")

    return PhotoCheck(
        decision=decision,
        dhash=digest,
        reasons=reasons,
        width=width,
        height=height,
        blur_var=blur_var,
        brightness=brightness,
    )


def evaluate_path(path) -> PhotoCheck:
    path = Path(path)
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.draft("L", (128, 128))
            gray = image.convert("L")
        try:
            return evaluate_gray(gray, width, height)
        finally:
            gray.close()
    except (UnidentifiedImageError, OSError, ValueError):
        return PhotoCheck(decision=REJECT, reasons=["That file is not a readable photo."])
