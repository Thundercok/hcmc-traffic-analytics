"""Build a contact sheet for quickly reviewing hand-labeled images."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "hand_labeled"
ANNOTATIONS = DATA_DIR / "annotations.csv"
OUT_DIR = DATA_DIR / "contact_sheets"


def _load_rows() -> list[dict[str, str]]:
    with ANNOTATIONS.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thumb-width", type=int, default=320)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--status", default="", help="Optional label_status filter")
    args = parser.parse_args()

    rows = _load_rows()
    if args.status:
        rows = [r for r in rows if r.get("label_status") == args.status]

    if not rows:
        print("no rows to render")
        return 1

    font = _font(16)
    small = _font(13)
    pad = 12
    label_h = 64
    thumbs = []

    for idx, row in enumerate(rows, start=1):
        img_path = DATA_DIR / row["image_file"]
        if not img_path.exists():
            continue
        img = Image.open(img_path).convert("RGB")
        scale = args.thumb_width / img.width
        thumb_h = int(img.height * scale)
        img = img.resize((args.thumb_width, thumb_h))

        tile = Image.new("RGB", (args.thumb_width, thumb_h + label_h), "white")
        tile.paste(img, (0, 0))
        draw = ImageDraw.Draw(tile)
        label = (
            f"{idx:02d} | {row['camera_id'][-6:]} | "
            f"{row.get('total_count') or '?'} total | {row.get('density_level') or 'unlabeled'}"
        )
        draw.rectangle((0, thumb_h, args.thumb_width, thumb_h + label_h), fill=(245, 247, 250))
        draw.text((8, thumb_h + 7), label, fill=(20, 30, 40), font=font)
        draw.text((8, thumb_h + 32), row.get("camera_name", "")[:44], fill=(60, 70, 80), font=small)
        thumbs.append(tile)

    if not thumbs:
        print("no image files found")
        return 1

    tile_w = args.thumb_width
    tile_h = max(t.height for t in thumbs)
    columns = max(1, args.columns)
    rows_count = (len(thumbs) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (columns * tile_w + (columns + 1) * pad, rows_count * tile_h + (rows_count + 1) * pad),
        (230, 234, 240),
    )

    for i, tile in enumerate(thumbs):
        x = pad + (i % columns) * (tile_w + pad)
        y = pad + (i // columns) * (tile_h + pad)
        sheet.paste(tile, (x, y))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"contact_sheet_{stamp}.jpg"
    sheet.save(out, quality=92)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
