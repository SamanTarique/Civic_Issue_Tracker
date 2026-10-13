"""Print Stage 1 photo-check decisions for a folder of labelled images."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.photo_check import evaluate_path  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate photos with Stage 1 checks (no CLIP).")
    parser.add_argument("folder", nargs="?", default="", help="Folder of labelled photos")
    args = parser.parse_args(argv)
    folder = Path(args.folder) if args.folder else None
    if folder is None or not folder.is_dir():
        print("No photos supplied.")
        return 0
    files = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not files:
        print("No photos supplied.")
        return 0
    print("file\tdecision\treasons")
    for path in files:
        result = evaluate_path(path)
        reasons = "; ".join(result.reasons) if result.reasons else ""
        print(path.name + "\t" + result.decision + "\t" + reasons)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
