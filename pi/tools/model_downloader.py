#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/model_downloader.py - 独立的模型资源自愈管理器 (带静默清理机制)
"""
import os
import time
import urllib.request
import zipfile

VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"


def check_and_download_vosk():
    """检查当前端点的 Vosk 模型，缺失则自动下载，并清理历史僵尸文件"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(base_dir, "voice", "model")
    zip_path = os.path.join(target_dir, "model_temp.zip")

    # =========================================================
    # ★ 新增功能：静默清理上次可能因 Windows 占用而残留的临时文件
    # =========================================================
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except OSError:
            pass  # 删不掉也不报错，绝对静默，不影响主流程

    # 检查模型核心文件是否存在
    model_am_path = os.path.join(target_dir, "am")
    if os.path.exists(model_am_path):
        return True

    print(f"\n[INFO] 未检测到离线语音模型，正在自动获取...")
    print(f"[INFO] 目标路径: {target_dir}")

    os.makedirs(target_dir, exist_ok=True)

    try:
        print("[INFO] 正在下载 Vosk 轻量级中文模型 (约 42MB)...")
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path)

        print("[INFO] 下载完成，正在解压部署...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                filename = os.path.basename(member)
                if not filename: continue
                source = zip_ref.open(member)
                target_file_path = os.path.join(target_dir, os.path.relpath(member, "vosk-model-small-cn-0.22"))
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                with open(target_file_path, "wb") as target:
                    target.write(source.read())

        print("[INFO] 解压完毕，正在清理临时文件...")
        time.sleep(1.0)  # 给杀毒软件1秒钟的时间

        # 尝试第一次清理
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except OSError:
            print(f"[WARN] 临时文件正被系统安全扫描，将推迟至下次启动时静默清理。")

        print("[INFO] 模型部署完成！")
        return True

    except Exception as e:
        print(f"[ERROR] 模型自动部署失败: {e}")
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except OSError:
            pass
        return False
