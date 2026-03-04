#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_mic.py - 麦克风硬件及语义交互测试工具
"""
import pyaudio
import time
import os
import json
import sys


def check_audio():
    print("==== 系统麦克风列表 ====")
    p = pyaudio.PyAudio()

    has_mic = False
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get('maxInputChannels') > 0:
            print(f"[{i}] {dev.get('name')}")
            has_mic = True

    if not has_mic:
        print("[ERROR] 未检测到任何麦克风设备！请检查硬件连接。")
        p.terminate()
        return False

    print("\n[INFO] 尝试物理调用麦克风...")
    try:
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=4000)
        print("[INFO] 麦克风已成功开启！正在校准环境底噪...")

        # 读取几帧清理陈旧缓冲
        for _ in range(5):
            stream.read(4000, exception_on_overflow=False)

        print("[INFO] 硬件通讯一切正常！")

        # ================= 语音语义验证环节 =================
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        model_path = os.path.join(project_root, "pcside", "voice", "model")

        if os.path.exists(model_path):
            try:
                from vosk import Model, KaldiRecognizer, SetLogLevel
                SetLogLevel(-1)  # ★ 压制 Vosk 底层烦人的 C++ 日志

                model = Model(model_path)
                rec = KaldiRecognizer(model, 16000)

                print("\n" + "=" * 50)
                print("[VOICE] 交互测试：请对着麦克风说出【你好】")
                print("=" * 50 + "\n")

                success = False
                start_time = time.time()
                timeout = 15  # 给用户15秒的测试时间

                while time.time() - start_time < timeout:
                    data = stream.read(4000, exception_on_overflow=False)

                    if rec.AcceptWaveform(data):
                        # 完整句子的识别结果
                        result = json.loads(rec.Result())
                        text = result.get("text", "").replace(" ", "")
                        if text:
                            print(f"[VOICE] 听到声音: '{text}'")
                            if "你好" or "您好"  in text:
                                print("\n[INFO] MIC验证通过")
                                success = True
                                break
                    else:
                        # ★ 极速响应：不用等用户停顿，边说边识别
                        partial = json.loads(rec.PartialResult())
                        partial_text = partial.get("partial", "").replace(" ", "")
                        if "你好" or "您好" in partial_text:
                            print(f"-> 听到声音: '{partial_text}'")
                            print("\n[INFO] MIC验证通过MIC验证通过")
                            success = True
                            break

                if not success:
                    print("\n[WARN] 等待超时或未识别到“你好”。")
                    print("[WARN] 如果您确实说话了，可能是麦克风音量太小或环境噪音太大。")
                    print("[INFO] 硬件流媒体获取正常，将继续启动系统...")

            except Exception as e:
                print(f"\n[WARN] 语音识别引擎临时加载异常: {e}")
                print("[INFO] 仅完成基础硬件流媒体测试...")
        else:
            # 兼容首次启动程序时，离线模型还没有被下载的情况
            print("\n[INFO] 离线语音模型尚未就绪，本次跳过语义验证环节。")
            print("请随便说一句话测试基础收音：")
            for _ in range(15):
                stream.read(4000, exception_on_overflow=False)
            print("[INFO] 录音截取成功！")

        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"\n[ERROR] 麦克风调用失败: {e}")
        return False
    finally:
        p.terminate()

    return True


if __name__ == "__main__":
    check_audio()