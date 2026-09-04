"""Collect real camera frames for the hand-labeled training dataset.

The script intentionally writes blank labels by default. Add
`--machine-seed-labels` only when you want rough starter labels that are clearly
marked as non-ground-truth.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "trafficflow-api"
DATA_DIR = ROOT / "data" / "hand_labeled"
IMAGE_DIR = DATA_DIR / "images"
ANNOTATIONS = DATA_DIR / "annotations.csv"

sys.path.insert(0, str(API_ROOT))

from backend.cameras import CAMERAS, get_camera_image_url  # noqa: E402
from backend.data_priors import density_level_from_count, estimate_prediction  # noqa: E402

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://giaothong.hochiminhcity.gov.vn/",
}

FIELDNAMES = [
    "image_file",
    "camera_id",
    "camera_name",
    "district",
    "lat",
    "lng",
    "captured_at",
    "total_count",
    "car_count",
    "motorbike_count",
    "density_level",
    "label_status",
    "labeler",
    "split",
    "source_url",
    "notes",
]


def _read_existing_rows() -> list[dict[str, str]]:
    if not ANNOTATIONS.exists():
        return []
    with ANNOTATIONS.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_rows(rows: list[dict[str, str]]) -> None:
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    with ANNOTATIONS.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _fetch_image(camera_id: str, timeout: int) -> bytes:
    url = f"{get_camera_image_url(camera_id)}&t={int(time.time() * 1000)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if len(data) < 2_000:
        raise ValueError(f"image too small: {len(data)} bytes")
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.width < 64 or img.height < 64:
        raise ValueError(f"unexpected image dimensions: {img.size}")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


def _blank_label_row(camera: dict, image_file: str, captured_at: str, split: str) -> dict:
    return {
        "image_file": image_file,
        "camera_id": camera["id"],
        "camera_name": camera["name"],
        "district": camera["district"],
        "lat": camera["lat"],
        "lng": camera["lng"],
        "captured_at": captured_at,
        "total_count": "",
        "car_count": "",
        "motorbike_count": "",
        "density_level": "",
        "label_status": "needs_review",
        "labeler": "",
        "split": split,
        "source_url": get_camera_image_url(camera["id"]),
        "notes": "",
    }


def _seed_label_row(row: dict, camera: dict, captured_at: datetime) -> dict:
    pred = estimate_prediction(camera, captured_at)
    row.update(
        {
            "total_count": str(pred["total_count"]),
            "car_count": str(pred["car_count"]),
            "motorbike_count": str(pred["motorbike_count"]),
            "density_level": density_level_from_count(pred["total_count"]),
            "label_status": "machine_seed",
            "labeler": "data_priors.py",
            "notes": "Machine-seeded starter label; review before using as ground truth.",
        }
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=len(CAMERAS))
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--force", action="store_true", help="Overwrite existing image files")
    parser.add_argument(
        "--machine-seed-labels",
        action="store_true",
        help="Fill non-ground-truth starter counts from deterministic priors.",
    )
    args = parser.parse_args()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_existing_rows()
    existing_images = {r.get("image_file") for r in rows}

    selected = CAMERAS[args.offset : args.offset + args.limit]
    captured = 0
    failed = 0

    for idx, camera in enumerate(selected, start=args.offset + 1):
        captured_at_dt = datetime.now(timezone.utc)
        captured_at = captured_at_dt.isoformat()
        image_name = f"{idx:03d}_{camera['id']}.jpg"
        image_file = f"images/{image_name}"
        image_path = DATA_DIR / image_file

        if image_file in existing_images and image_path.exists() and not args.force:
            print(f"skip existing {image_file}")
            continue

        try:
            data = _fetch_image(camera["id"], args.timeout)
            image_path.write_bytes(data)
            split = "val" if idx % 5 == 0 else "train"
            row = _blank_label_row(camera, image_file, captured_at, split)
            if args.machine_seed_labels:
                row = _seed_label_row(row, camera, captured_at_dt)
            rows = [r for r in rows if r.get("image_file") != image_file]
            rows.append(row)
            captured += 1
            print(f"captured {image_file}")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            failed += 1
            print(f"failed {camera['id']}: {exc}")
        time.sleep(args.sleep)

    rows.sort(key=lambda r: r.get("image_file", ""))
    _write_rows(rows)
    print(f"done: captured={captured}, failed={failed}, annotations={ANNOTATIONS}")
    return 0 if captured or not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
