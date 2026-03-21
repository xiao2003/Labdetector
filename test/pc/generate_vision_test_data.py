from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np

from pc.training.annotation_store import annotation_store
from pc.training.train_manager import TrainingManager


def _draw_sample(canvas: np.ndarray, kind: str, color: tuple[int, int, int]) -> List[Dict[str, float | str]]:
    boxes: List[Dict[str, float | str]] = []
    h, w = canvas.shape[:2]
    if kind == "flask":
        x1, y1, x2, y2 = 120, 80, 280, 330
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, -1)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (30, 30, 30), 3)
        cv2.putText(canvas, "FLASK", (135, 215), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3, cv2.LINE_AA)
        boxes.append({"class_name": "flask", "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    elif kind == "label":
        x1, y1, x2, y2 = 280, 120, 480, 230
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, -1)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (20, 20, 20), 3)
        cv2.putText(canvas, "LABEL", (305, 185), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3, cv2.LINE_AA)
        boxes.append({"class_name": "label", "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    elif kind == "hazard":
        pts = np.array([[320, 80], [460, 320], [180, 320]], np.int32)
        cv2.fillConvexPoly(canvas, pts, color)
        cv2.polylines(canvas, [pts], True, (20, 20, 20), 4)
        cv2.putText(canvas, "CHEM", (250, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3, cv2.LINE_AA)
        boxes.append({"class_name": "hazard", "x1": 180, "y1": 80, "x2": 460, "y2": 320})
    else:
        center = (w // 2, h // 2)
        cv2.circle(canvas, center, 110, color, -1)
        cv2.circle(canvas, center, 110, (20, 20, 20), 4)
        cv2.putText(canvas, "OBS", (center[0] - 55, center[1] + 15), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3, cv2.LINE_AA)
        boxes.append({"class_name": "observation", "x1": center[0] - 110, "y1": center[1] - 110, "x2": center[0] + 110, "y2": center[1] + 110})
    return boxes


def generate_dataset(workspace_name: str = "vision_panel_regression", sample_count: int = 12) -> Dict[str, object]:
    manager = TrainingManager()
    summary = manager.build_training_workspace(workspace_name)
    workspace_dir = Path(str(summary["workspace_dir"]))
    sample_root = workspace_dir / "synthetic_samples"
    sample_root.mkdir(parents=True, exist_ok=True)

    recipes = [
        ("flask", (50, 170, 240)),
        ("label", (60, 90, 210)),
        ("hazard", (80, 180, 90)),
        ("observation", (160, 120, 60)),
    ]
    image_paths: List[str] = []
    labels_by_name: Dict[str, List[Dict[str, float | str]]] = {}

    for index in range(sample_count):
        kind, color = recipes[index % len(recipes)]
        canvas = np.full((420, 560, 3), 245, dtype=np.uint8)
        cv2.putText(canvas, f"sample-{index+1:02d}", (25, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 40), 2, cv2.LINE_AA)
        boxes = _draw_sample(canvas, kind, color)
        name = f"sample_{index+1:02d}_{kind}.png"
        path = sample_root / name
        cv2.imwrite(str(path), canvas)
        image_paths.append(str(path))
        labels_by_name[name] = boxes

    import_summary = annotation_store.import_images(workspace_dir, image_paths)
    image_rows = {row["name"]: row for row in annotation_store.list_images(workspace_dir)}
    for image_name, boxes in labels_by_name.items():
        row = image_rows.get(image_name)
        if not row:
            continue
        annotation_store.save_annotations(workspace_dir, image_name, 560, 420, boxes)

    dataset_yaml = workspace_dir / "pi_detector" / "dataset.yaml"
    report = {
        "workspace_dir": str(workspace_dir),
        "sample_root": str(sample_root),
        "imported_count": int(import_summary["imported_count"]),
        "dataset_yaml": str(dataset_yaml),
        "class_names": annotation_store.get_classes(workspace_dir),
        "images": list(labels_by_name.keys()),
    }
    return report


def main() -> int:
    report = generate_dataset()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
