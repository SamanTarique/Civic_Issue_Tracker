"""Build a short demo slideshow (GIF + optional MP4) from screenshots and title cards."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUT_DIR = ROOT / "docs" / "demo-video"
SIZE = (1280, 720)
BG = (15, 23, 42)
FG = (248, 250, 252)
MUTED = (148, 163, 184)
ACCENT = (56, 189, 248)


def _font(size):
    for name in ("arial.ttf", "segoeui.ttf", "C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def title_card(heading, sub=""):
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, SIZE[0], 8), fill=ACCENT)
    hfont = _font(48)
    sfont = _font(28)
    draw.text((72, 240), heading, fill=FG, font=hfont)
    if sub:
        draw.text((72, 320), sub, fill=MUTED, font=sfont)
    draw.text((72, 640), "Demo project — not connected to any real authority", fill=MUTED, font=_font(20))
    return image


def fit_shot(path):
    src = Image.open(path).convert("RGB")
    canvas = Image.new("RGB", SIZE, (2, 6, 23))
    src.thumbnail((SIZE[0], SIZE[1] - 72), Image.Resampling.LANCZOS)
    x = (SIZE[0] - src.width) // 2
    y = 36 + (SIZE[1] - 72 - src.height) // 2
    canvas.paste(src, (x, y))
    src.close()
    return canvas


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sequence = [
        ("title", "Civic Issue Tracker", "Report a civic issue. Staff track the fix."),
        ("shot", SHOTS / "home-1280.png"),
        ("title", "1. Home", "Public map of rounded, opt-in pins. DEMO repairs only."),
        ("shot", SHOTS / "home-1280.png"),
        ("title", "2. New report", "Photo, map pin, category, and consent."),
        ("shot", SHOTS / "report-form-1280.png"),
        ("title", "3. My reports", "Tracking ID and status on the same ticket."),
        ("shot", SHOTS / "my-reports-1280.png"),
        ("title", "4. Issue detail", "Before / after photos. Confirm or reopen."),
        ("shot", SHOTS / "detail-1280.png"),
        ("title", "Staff queue", "One department per staff user. Admin sees all."),
        ("title", "Thanks", "Demo only. See README.md to run it locally."),
    ]
    frames = []
    durations = []
    for item in sequence:
        if item[0] == "title":
            frames.append(title_card(item[1], item[2] if len(item) > 2 else ""))
            durations.append(2500)
        else:
            path = item[1]
            if path.is_file():
                frames.append(fit_shot(path))
                durations.append(3800)
    gif_path = OUT_DIR / "civic-issue-tracker-demo.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print("Wrote", gif_path)
    try:
        import imageio.v2 as imageio
        import numpy as np

        mp4_path = OUT_DIR / "civic-issue-tracker-demo.mp4"
        writer = imageio.get_writer(str(mp4_path), fps=1, codec="libx264", quality=7)
        for frame, ms in zip(frames, durations):
            for _ in range(max(1, int(round(ms / 1000)))):
                writer.append_data(np.asarray(frame))
        writer.close()
        print("Wrote", mp4_path)
    except Exception as exc:
        print("MP4 skipped:", type(exc).__name__)
    for frame in frames:
        frame.close()


if __name__ == "__main__":
    main()
