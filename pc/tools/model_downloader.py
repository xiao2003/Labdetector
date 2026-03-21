#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download and prepare bundled speech models when missing."""

from __future__ import annotations

import os
import time
import urllib.request
import zipfile

from pc.app_identity import resource_path

try:
    from modelscope import snapshot_download
except ImportError:
    snapshot_download = None


VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"
SENSEVOICE_MODEL_REPO = "iic/SenseVoiceSmall"


def check_and_download_vosk() -> bool:
    """Ensure the bundled Vosk model directory exists and is ready to use."""
    target_dir = str(resource_path("pc/voice/model"))
    zip_path = os.path.join(target_dir, "model_temp.zip")

    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except OSError:
            pass

    model_am_path = os.path.join(target_dir, "am")
    if os.path.exists(model_am_path):
        return True

    print("\n[INFO] \u6b63\u5728\u68c0\u67e5\u79bb\u7ebf\u8bed\u97f3\u6a21\u578b\u76ee\u5f55...")
    print(f"[INFO] \u76ee\u6807\u8def\u5f84: {target_dir}")

    os.makedirs(target_dir, exist_ok=True)

    try:
        print("[INFO] \u5f00\u59cb\u4e0b\u8f7d Vosk \u4e2d\u6587\u79bb\u7ebf\u6a21\u578b\uff08\u7ea6 42MB\uff09...")
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path)

        print("[INFO] \u6b63\u5728\u89e3\u538b\u79bb\u7ebf\u8bed\u97f3\u6a21\u578b...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                filename = os.path.basename(member)
                if not filename:
                    continue
                source = zip_ref.open(member)
                target_file_path = os.path.join(target_dir, os.path.relpath(member, "vosk-model-small-cn-0.22"))
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                with open(target_file_path, "wb") as target:
                    target.write(source.read())

        print("[INFO] \u6b63\u5728\u6821\u9a8c\u79bb\u7ebf\u8bed\u97f3\u6a21\u578b\u6587\u4ef6...")
        time.sleep(1.0)

        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except OSError:
            print("[WARN] \u4e34\u65f6\u538b\u7f29\u5305\u5220\u9664\u5931\u8d25\uff0c\u53ef\u5728\u7a0d\u540e\u624b\u52a8\u6e05\u7406\u3002")

        print("[INFO] \u79bb\u7ebf\u8bed\u97f3\u6a21\u578b\u51c6\u5907\u5b8c\u6210")
        return True

    except Exception as exc:
        print(f"[ERROR] \u79bb\u7ebf\u8bed\u97f3\u6a21\u578b\u4e0b\u8f7d\u5931\u8d25: {exc}")
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except OSError:
            pass
        return False


def check_and_download_sensevoice() -> bool:
    """Ensure the bundled SenseVoice model directory exists and is ready to use."""
    target_dir = str(resource_path("pc/voice/models/SenseVoiceSmall"))
    model_file = os.path.join(target_dir, "configuration.json")

    if os.path.exists(model_file):
        return True

    print("\n[INFO] 正在检查 SenseVoice 语音模型目录...")
    print(f"[INFO] 目标路径: {target_dir}")
    os.makedirs(target_dir, exist_ok=True)

    if snapshot_download is None:
        print("[ERROR] 未安装 modelscope，无法自动下载 SenseVoice 模型。")
        return False

    try:
        print("[INFO] 开始下载 SenseVoiceSmall 语音模型（首次下载体积较大，请耐心等待）...")
        download_kwargs = {
            "model_id": SENSEVOICE_MODEL_REPO,
            "local_dir": target_dir,
        }
        try:
            downloaded_dir = snapshot_download(
                local_dir_use_symlinks=False,
                **download_kwargs,
            )
        except TypeError:
            # Older modelscope versions do not support local_dir_use_symlinks.
            downloaded_dir = snapshot_download(**download_kwargs)
        print(f"[INFO] SenseVoice 模型下载完成: {downloaded_dir}")
        return os.path.exists(model_file)
    except Exception as exc:
        print(f"[ERROR] SenseVoice 模型下载失败: {exc}")
        return False
