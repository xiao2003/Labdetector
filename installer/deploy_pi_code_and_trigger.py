#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过局域网把 Pi 代码投递到树莓派并触发后台自治安装。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import List


PUTTY_DIR = Path(r"C:\Program Files\PuTTY")
PLINK = PUTTY_DIR / "plink.exe"
PSCP = PUTTY_DIR / "pscp.exe"
REPO_ROOT = Path(__file__).resolve().parents[1]
PI_SOURCE_DIR = REPO_ROOT / "pi"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="投递 Pi 代码并触发后台自治安装")
    parser.add_argument("--host", required=True, help="树莓派 IP 或主机名")
    parser.add_argument("--user", required=True, help="树莓派 SSH 用户名")
    parser.add_argument("--password", required=True, help="树莓派 SSH 密码")
    parser.add_argument("--hostkey", required=True, help="树莓派 SSH host key")
    parser.add_argument("--remote-base-dir", default=None, help="远程基目录，默认 /home/<user>/NeuroLab")
    parser.add_argument("--source-dir", default=str(PI_SOURCE_DIR), help="本地 Pi 代码目录")
    return parser.parse_args()


def _run(command: List[str], timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
    )


def _plink_base(args: argparse.Namespace) -> List[str]:
    return [
        str(PLINK),
        "-batch",
        "-ssh",
        "-pw",
        args.password,
        "-hostkey",
        args.hostkey,
        f"{args.user}@{args.host}",
    ]


def _pscp_base(args: argparse.Namespace) -> List[str]:
    return [
        str(PSCP),
        "-batch",
        "-pw",
        args.password,
        "-hostkey",
        args.hostkey,
    ]


def _remote_run(args: argparse.Namespace, command: str, timeout: int = 7200) -> str:
    result = _run([*_plink_base(args), command], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"远程命令失败: {command}")
    return result.stdout


def _copy_to_remote(args: argparse.Namespace, local_path: Path, remote_path: str, timeout: int = 7200) -> None:
    result = _run([*_pscp_base(args), str(local_path), f"{args.user}@{args.host}:{remote_path}"], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"远程上传失败: {remote_path}")


def _build_temp_archive(source_dir: Path) -> Path:
    if not source_dir.exists():
        raise RuntimeError(f"Pi 源码目录不存在：{source_dir}")
    temp_dir = Path(tempfile.mkdtemp(prefix="neurolab_pi_deploy_"))
    archive_path = temp_dir / "pi_code_bundle.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in source_dir.rglob("*"):
            relative = path.relative_to(source_dir)
            if any(part in {"__pycache__", ".venv", "runtime_state"} for part in relative.parts):
                continue
            if path.is_file() and path.suffix in {".pyc", ".pyo"}:
                continue
            archive.add(path, arcname=Path("pi") / relative)
    return archive_path


def main() -> int:
    args = _parse_args()
    if not PLINK.exists() or not PSCP.exists():
        raise RuntimeError("未检测到 PuTTY plink/pscp，请先安装 PuTTY。")

    source_dir = Path(args.source_dir).resolve()
    archive_path = _build_temp_archive(source_dir)
    remote_base_dir = args.remote_base_dir or f"/home/{args.user}/NeuroLab"
    remote_archive = f"{remote_base_dir}/pi_code_bundle.tar.gz"
    remote_project_dir = f"{remote_base_dir}/pi"

    try:
        _remote_run(args, f"mkdir -p {remote_base_dir}")
        _copy_to_remote(args, archive_path, remote_archive, timeout=600)
        _remote_run(
            args,
            " && ".join(
                [
                    f"mkdir -p {remote_base_dir}",
                    f"rm -rf {remote_project_dir}/.venv {remote_project_dir}/runtime_state {remote_project_dir}/voice/model",
                    f"tar -xzf {remote_archive} -C {remote_base_dir}",
                    f"cd {remote_project_dir}",
                    "python3 pi_cli.py install-runtime --background",
                ]
            ),
            timeout=600,
        )
    finally:
        shutil.rmtree(archive_path.parent, ignore_errors=True)

    summary = {
        "success": True,
        "host": args.host,
        "remote_project_dir": remote_project_dir,
        "status_command": f"cd {remote_project_dir} && python3 pi_cli.py install-status",
        "log_command": f"cd {remote_project_dir} && python3 pi_cli.py install-log --tail 60",
        "start_command": f"cd {remote_project_dir} && bash start_pi_node.sh",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
