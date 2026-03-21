from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _decode(payload: bytes | None) -> str:
    if not payload:
        return ""
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return payload.decode(encoding)
        except Exception:
            continue
    return payload.decode("utf-8", errors="ignore")


def _run(command: List[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return proc.returncode, _decode(proc.stdout).strip()
    except Exception as exc:
        return 1, str(exc)


def detect_gpu_environment() -> Dict[str, Any]:
    logs: List[str] = []
    details: Dict[str, Any] = {
        "python": sys.version.split(" ")[0],
        "torch_installed": False,
        "torch_version": "",
        "torch_cuda_version": "",
        "torch_cuda_available": False,
        "nvidia_smi_available": False,
        "nvidia_gpu_name": "",
        "driver_version": "",
        "needs_driver": False,
        "needs_cuda_torch": False,
        "can_auto_install_cuda_torch": False,
    }

    logs.append(f"[INFO] Python 解释器版本: {details['python']}")
    logs.append(f"[INFO] Python 架构: {'64bit' if sys.maxsize > 2**32 else '32bit'}")
    logs.append(f"[INFO] 操作系统: {sys.platform}")

    try:
        import torch  # type: ignore

        details["torch_installed"] = True
        details["torch_version"] = str(torch.__version__)
        details["torch_cuda_version"] = str(torch.version.cuda or "")
        details["torch_cuda_available"] = bool(torch.cuda.is_available())
        logs.append(f"[INFO] PyTorch 版本: {details['torch_version']}")
        logs.append(f"[INFO] CUDA 版本: {details['torch_cuda_version'] or 'None'}")
        logs.append(f"[INFO] GPU 可用: {details['torch_cuda_available']}")
        if details["torch_cuda_available"]:
            try:
                details["nvidia_gpu_name"] = str(torch.cuda.get_device_name(0))
                logs.append(f"[INFO] GPU 名称: {details['nvidia_gpu_name']}")
            except Exception as exc:
                logs.append(f"[WARN] 无法读取 GPU 名称: {exc}")
    except Exception:
        logs.append("[WARN] 未检测到可用 PyTorch 运行时。")

    code, output = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if code == 0 and output:
        details["nvidia_smi_available"] = True
        first_line = output.splitlines()[0].strip()
        parts = [part.strip() for part in first_line.split(",")]
        if parts:
            details["nvidia_gpu_name"] = parts[0]
        if len(parts) > 1:
            details["driver_version"] = parts[1]
        logs.append(f"[INFO] NVIDIA 驱动已就绪: {first_line}")
    else:
        logs.append("[WARN] 未检测到 nvidia-smi，当前环境可能没有 NVIDIA 驱动或未安装 GPU。")

    if details["nvidia_smi_available"] and not details["torch_cuda_available"]:
        details["needs_cuda_torch"] = True
        details["can_auto_install_cuda_torch"] = True
    elif not details["nvidia_smi_available"] and not details["torch_cuda_available"]:
        details["needs_driver"] = True

    return {"details": details, "logs": logs}


def install_cuda_enabled_pytorch(index_url: str, packages: List[str]) -> Dict[str, Any]:
    target_packages = [pkg.strip() for pkg in packages if pkg.strip()]
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--user",
        "--ignore-installed",
        "--force-reinstall",
        "--no-cache-dir",
        *target_packages,
        "--index-url",
        index_url,
    ]
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, env=env)
    output = _decode(proc.stdout)
    tail_lines = [line for line in output.splitlines() if line.strip()][-20:]
    return {
        "ok": proc.returncode == 0,
        "logs": tail_lines,
        "command": " ".join(command),
    }


def main() -> None:
    report = detect_gpu_environment()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
