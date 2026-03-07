from __future__ import annotations

import json
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
        raise RuntimeError(f"未安装 Pi 检测模型训练所需依赖: {exc}") from exc

    if not str(base_weights or "").strip():
        raise RuntimeError("请先配置 Pi 检测模型底座权重。")

    yaml_path = Path(dataset_yaml)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Pi 检测训练数据不存在: {yaml_path}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model = YOLO(base_weights)
    results = model.train(
        data=str(yaml_path),
        epochs=max(1, int(epochs)),
        imgsz=max(320, int(imgsz)),
        project=str(output_path),
        name="run",
        device=device or None,
        exist_ok=True,
    )

    run_dir = output_path / "run"
    best_weights = run_dir / "weights" / "best.pt"
    deployed_path = ""
    if deploy_to_pi and best_weights.exists():
        pi_target = Path(__file__).resolve().parents[2] / "pi" / "models" / "detectors"
        pi_target.mkdir(parents=True, exist_ok=True)
        target_file = pi_target / best_weights.name
        shutil.copy2(best_weights, target_file)
        deployed_path = str(target_file)

    summary = {
        "output_dir": str(run_dir),
        "best_weights": str(best_weights),
        "deployed_path": deployed_path,
        "results": str(results),
        "epochs": max(1, int(epochs)),
        "imgsz": max(320, int(imgsz)),
        "base_weights": str(base_weights),
        "dataset_yaml": str(yaml_path),
    }
    (run_dir / "training_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
