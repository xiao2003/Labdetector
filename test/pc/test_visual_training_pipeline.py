from __future__ import annotations

import json
import sys
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generate_vision_test_data import generate_dataset
from pc.training.pi_detector_finetune import run_pi_detector_finetune


def main() -> int:
    dataset_report = generate_dataset("vision_training_smoke", sample_count=12)
    workspace_dir = Path(str(dataset_report["workspace_dir"]))
    dataset_yaml = Path(str(dataset_report["dataset_yaml"]))
    output_dir = workspace_dir / "outputs" / "pi_detector_smoke"

    started_at = time.time()
    train_result = run_pi_detector_finetune(
        dataset_yaml=str(dataset_yaml),
        output_dir=str(output_dir),
        base_weights="yolov8n.pt",
        epochs=1,
        imgsz=320,
        device="cpu",
        deploy_to_pi=False,
    )
    duration = round(time.time() - started_at, 2)

    best_weights = Path(str(train_result["best_weights"]))
    result_payload = {
        "ok": best_weights.exists(),
        "duration_sec": duration,
        "workspace_dir": str(workspace_dir),
        "dataset_yaml": str(dataset_yaml),
        "best_weights": str(best_weights),
        "output_dir": str(train_result["output_dir"]),
        "class_names": dataset_report["class_names"],
        "imported_count": dataset_report["imported_count"],
    }
    report_path = PROJECT_ROOT / "tmp" / "vision_training_smoke_report.json"
    report_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print(json.dumps(result_payload, ensure_ascii=False, indent=2))
    return 0 if result_payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
