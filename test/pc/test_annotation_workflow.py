from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.training.annotation_store import annotation_store
from pc.training.train_manager import TrainingManager


def main() -> int:
    manager = TrainingManager()
    workspace = manager.build_training_workspace("annotation_panel_smoke")
    workspace_dir = Path(str(workspace["workspace_dir"]))

    sample_dir = workspace_dir / "synthetic_samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    specs = [
        ("sample_alpha.png", "ALPHA", (80, 80, 260, 260), (30, 140, 210)),
        ("sample_beta.png", "BETA", (180, 120, 430, 320), (200, 70, 70)),
        ("sample_gamma.png", "GAMMA", (120, 100, 460, 300), (70, 170, 80)),
    ]
    for name, text, rect, color in specs:
        canvas = np.full((420, 560, 3), 255, dtype=np.uint8)
        x1, y1, x2, y2 = rect
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness=-1)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (20, 20, 20), thickness=3)
        cv2.putText(canvas, text, (x1 + 18, y1 + 90), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 255), 3, cv2.LINE_AA)
        output = sample_dir / name
        cv2.imwrite(str(output), canvas)
        generated.append(str(output))

    import_summary = annotation_store.import_images(workspace_dir, generated)
    items = annotation_store.list_images(workspace_dir)
    assert import_summary["imported_count"] == 3, import_summary
    assert len(items) >= 3, items

    target = items[0]
    save_summary = annotation_store.save_annotations(
        workspace_dir=workspace_dir,
        image_name=target["name"],
        image_width=560,
        image_height=420,
        boxes=[
            {"class_name": "flask", "x1": 80, "y1": 80, "x2": 260, "y2": 260},
            {"class_name": "label", "x1": 120, "y1": 300, "x2": 240, "y2": 360},
        ],
    )

    dataset_yaml = workspace_dir / "pi_detector" / "dataset.yaml"
    label_path = Path(save_summary["label_path"])
    meta_path = workspace_dir / "pi_detector" / "annotation_meta.json"
    summary_path = workspace_dir / "workspace_summary.json"

    assert dataset_yaml.exists(), dataset_yaml
    assert label_path.exists(), label_path
    assert meta_path.exists(), meta_path
    assert summary_path.exists(), summary_path

    report = {
        "workspace_dir": str(workspace_dir),
        "import_summary": import_summary,
        "save_summary": save_summary,
        "dataset_yaml": dataset_yaml.read_text(encoding="utf-8"),
        "label_content": label_path.read_text(encoding="utf-8"),
        "meta": json.loads(meta_path.read_text(encoding="utf-8")),
        "workspace_summary": json.loads(summary_path.read_text(encoding="utf-8")),
    }
    output = Path(__file__).resolve().parent / "annotation_workflow_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
