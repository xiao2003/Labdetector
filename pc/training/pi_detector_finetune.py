from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict


def run_pi_detector_finetune(
    *,
    dataset_yaml: str,
    output_dir: str,
    base_weights: str,
    epochs: int = 20,
    imgsz: int = 640,
    device: str = "",
    deploy_to_pi: bool = True,
) -> Dict[str, Any]:
    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError(f"Pi ???????????: {exc}") from exc

    model = YOLO(base_weights)
    results = model.train(
        data=dataset_yaml,
        epochs=max(1, int(epochs)),
        imgsz=max(320, int(imgsz)),
        project=output_dir,
        name="run",
        device=device or None,
        exist_ok=True,
    )

    run_dir = Path(output_dir) / "run"
    best_weights = run_dir / "weights" / "best.pt"
    deployed_path = ""
    if deploy_to_pi and best_weights.exists():
        pi_target = Path(__file__).resolve().parents[2] / "pi" / "models" / "detectors"
        pi_target.mkdir(parents=True, exist_ok=True)
        target_file = pi_target / best_weights.name
        shutil.copy2(best_weights, target_file)
        deployed_path = str(target_file)

    return {
        "output_dir": str(run_dir),
        "best_weights": str(best_weights),
        "deployed_path": deployed_path,
        "results": str(results),
    }
