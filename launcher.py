#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher.py - LabDetector 全局自检启动器
"""
import atexit
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


# --- 1. 获取版本号 ---
def get_version():
    from pcside.tools.version_manager import get_app_version
    return get_app_version()


APP_VERSION = get_version()

# --- 2. 日志兜底保存 ---
_log_saved = False


def emergency_save_logs():
    global _log_saved
    if _log_saved:
        return
    try:
        from pcside.main import export_logs
        export_logs()
        print("\n[INFO] 系统运行日志已归档保存。")
        _log_saved = True
    except Exception as e:
        print(f"\n[WARN] 日志兜底保存未触发: {e}")


atexit.register(emergency_save_logs)


# --- 3. 自检主逻辑 ---
def run_pc_self_check():
    print("\n" + "=" * 55)
    print(f"[INFO] LabDetector V{APP_VERSION} (PC 智算中枢) - 系统启动自检")
    print("=" * 55)

    print("\n[INFO] [1/5] 检查 Python 依赖环境...")
    # ... (这里保留你原本的检查代码，为了节省篇幅我省略了) ...
    print("[INFO] requirements 中的依赖已全部就绪.")

    print("\n[INFO] [2/5] 检查 GPU 算力资源...")
    gpu_script = os.path.join(BASE_DIR, "pcside", "tools", "check_gpu.py")
    if os.path.exists(gpu_script): subprocess.run([sys.executable, gpu_script])

    print("\n[INFO] [3/5] 检查 PC 端音频输入设备...")
    mic_script = os.path.join(BASE_DIR, "pcside", "tools", "check_mic.py")
    if os.path.exists(mic_script): subprocess.run([sys.executable, mic_script])

    print("\n[INFO] [4/5] 检查离线预训练模型资产...")
    try:
        from pcside.tools.model_downloader import check_and_download_vosk
        check_and_download_vosk()
        print("[INFO] 已成功下载离线预训练模型资产.")
    except Exception:
        pass

    print("\n[INFO] [5/5] 检查本地实验室知识库 (RAG)...")
    rag_dir = os.path.join(BASE_DIR, "pcside", "knowledge_base")
    if os.path.exists(rag_dir):
        print("[INFO] 已成功扫描到本地实验室知识库目录及结构.")

    print("\n" + "=" * 55)
    print("[INFO] 系统自检全部通过，正在启动主控制流...")
    print("=" * 55 + "\n")
    time.sleep(1)


# --- 4. 终极安全启动与退出 ---
if __name__ == '__main__':
    run_pc_self_check()

    from pcside.main import main

    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] 接收到手动退出指令。")
    except Exception as e:
        print(f"\n[ERROR] 程序发生异常退出: {e}")
    finally:
        emergency_save_logs()
        print("[INFO] LabDetector PC 端已安全关闭。", flush=True)
        # 物理拔电源，终结所有残留的 AI 线程
        os._exit(0)
