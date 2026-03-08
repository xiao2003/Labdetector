from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict


def _ensure_repo_imports() -> None:
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    for candidate in (current_dir.parent.parent, current_dir.parent):
        if (candidate / "pc").exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            break


def _load_runner(kind: str):
    _ensure_repo_imports()
    if kind == "llm":
        try:
            from pc.training.llm_finetune import run_llm_finetune
        except Exception:
            from llm_finetune import run_llm_finetune
        return run_llm_finetune
    if kind == "pi":
        try:
            from pc.training.pi_detector_finetune import run_pi_detector_finetune
        except Exception:
            from pi_detector_finetune import run_pi_detector_finetune
        return run_pi_detector_finetune
    raise ValueError(f"未知训练类型: {kind}")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NeuroLab Hub training worker")
    parser.add_argument("--kind", choices=["llm", "pi"], required=True)
    parser.add_argument("--payload-json", required=True)
    parser.add_argument("--result-json", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload_path = Path(args.payload_json).resolve()
    result_path = Path(args.result_json).resolve()
    payload = _read_json(payload_path)
    try:
        runner = _load_runner(args.kind)
        if args.kind == "llm":
            result = runner(
                train_path=str(payload.get("train_path") or ""),
                eval_path=str(payload.get("eval_path") or ""),
                output_dir=str(payload.get("output_dir") or ""),
                base_model=str(payload.get("base_model") or ""),
                epochs=int(payload.get("epochs") or 1),
                batch_size=int(payload.get("batch_size") or 1),
                learning_rate=float(payload.get("learning_rate") or 2e-4),
                lora_r=int(payload.get("lora_r") or 8),
                lora_alpha=int(payload.get("lora_alpha") or 16),
            )
        else:
            result = runner(
                dataset_yaml=str(payload.get("dataset_yaml") or ""),
                output_dir=str(payload.get("output_dir") or ""),
                base_weights=str(payload.get("base_weights") or ""),
                epochs=int(payload.get("epochs") or 20),
                imgsz=int(payload.get("imgsz") or 640),
                device=str(payload.get("device") or ""),
                deploy_to_pi=bool(payload.get("deploy_to_pi", False)),
            )
        _write_json(result_path, {"ok": True, "result": result})
        return 0
    except Exception as exc:
        _write_json(
            result_path,
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

