#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Microphone and local speech-recognition quick check."""

from __future__ import annotations

import json
import os
import sys
import time

import pyaudio


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(str(text).encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def check_audio() -> bool:
    safe_print("==== 系统麦克风列表 ====")
    p = pyaudio.PyAudio()

    has_mic = False
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get("maxInputChannels", 0) > 0:
            safe_print(f"[{i}] {dev.get('name')}")
            has_mic = True

    if not has_mic:
        safe_print("[ERROR] 未检测到任何麦克风设备，请检查硬件连接。")
        p.terminate()
        return False

    safe_print("\n[INFO] 尝试物理调用麦克风...")
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=4000,
        )
        safe_print("[INFO] 麦克风已成功开启，正在校准环境底噪...")

        for _ in range(5):
            stream.read(4000, exception_on_overflow=False)

        safe_print("[INFO] 硬件通讯一切正常。")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        model_path = os.path.join(project_root, "pc", "voice", "model")

        if os.path.exists(model_path):
            try:
                from vosk import KaldiRecognizer, Model, SetLogLevel

                SetLogLevel(-1)
                model = Model(model_path)
                rec = KaldiRecognizer(model, 16000)

                safe_print("\n" + "=" * 50)
                safe_print("[VOICE] 交互测试：请对着麦克风说出【你好】")
                safe_print("=" * 50 + "\n")

                success = False
                start_time = time.time()
                timeout = 15

                while time.time() - start_time < timeout:
                    data = stream.read(4000, exception_on_overflow=False)

                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        text = str(result.get("text", "")).replace(" ", "")
                        if text:
                            safe_print(f"[VOICE] 听到声音: '{text}'")
                            if "你好" in text or "您好" in text:
                                safe_print("\n[INFO] MIC验证通过")
                                success = True
                                break
                    else:
                        partial = json.loads(rec.PartialResult())
                        partial_text = str(partial.get("partial", "")).replace(" ", "")
                        if partial_text and ("你好" in partial_text or "您好" in partial_text):
                            safe_print(f"-> 听到声音: '{partial_text}'")
                            safe_print("\n[INFO] MIC验证通过")
                            success = True
                            break

                if not success:
                    safe_print("\n[WARN] 等待超时或未识别到“你好”。")
                    safe_print("[WARN] 如果您确实说话了，可能是麦克风音量太小或环境噪音太大。")
                    safe_print("[INFO] 硬件流媒体获取正常，将继续启动系统...")

            except Exception as exc:
                safe_print(f"\n[WARN] 语音识别引擎临时加载异常: {exc}")
                safe_print("[INFO] 仅完成基础硬件流媒体测试。")
        else:
            safe_print("\n[INFO] 离线语音模型尚未就绪，本次跳过语义验证环节。")
            safe_print("请随便说一句话测试基础收音。")
            for _ in range(15):
                stream.read(4000, exception_on_overflow=False)
            safe_print("[INFO] 录音截取成功。")

        stream.stop_stream()
        stream.close()
    except Exception as exc:
        safe_print(f"\n[ERROR] 麦克风调用失败: {exc}")
        return False
    finally:
        p.terminate()

    return True


if __name__ == "__main__":
    check_audio()
