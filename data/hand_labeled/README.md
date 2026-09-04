# Hand-Labeled Traffic Dataset

This folder is the project-owned training/evaluation dataset for the curated
31-camera tracking subset.

## Files

- `images/` stores captured camera snapshots.
- `annotations.csv` stores one row per image.
- `contact_sheets/` stores quick review sheets for manual labeling.

## Label Status

- `human_reviewed`: counts were manually reviewed from the image.
- `needs_review`: image was collected but still needs a manual label.
- `machine_seed`: counts were bootstrapped by a deterministic prior and must not
  be used as ground truth evaluation data.

Only `human_reviewed` rows should be used for final validation metrics.

## Annotation Columns

- `image_file`: path relative to this folder.
- `camera_id`, `camera_name`, `district`, `lat`, `lng`: camera metadata.
- `captured_at`: UTC timestamp when the frame was captured.
- `total_count`, `car_count`, `motorbike_count`: visible vehicle counts.
- `density_level`: `low`, `moderate`, `heavy`, or `severe`.
- `label_status`: review status described above.
- `split`: suggested training split.
- `notes`: label caveats such as blur, occlusion, or partial visibility.

## Workflow

1. Capture new frames:

   ```bash
   python scripts/collect_training_snapshots.py --limit 31
   ```

2. Build a contact sheet:

   ```bash
   python scripts/make_label_contact_sheet.py
   ```

3. Review each image and update `annotations.csv`.

4. Use `human_reviewed` rows for training or evaluation.
