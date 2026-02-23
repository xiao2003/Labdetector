import speech_recognition as sr

print("==== 🎤 系统麦克风列表 ====")
for index, name in enumerate(sr.Microphone.list_microphone_names()):
    print(f"[{index}] {name}")

print("\n==== 🚀 尝试物理调用麦克风 ====")
r = sr.Recognizer()
try:
    # 尝试打开默认麦克风
    with sr.Microphone() as source:
        print("✅ 麦克风已成功开启！正在校准环境底噪...")
        r.adjust_for_ambient_noise(source, duration=1)
        print("✅ 硬件通讯一切正常！请说一句话测试：")
        audio = r.listen(source, timeout=3, phrase_time_limit=3)
        print("✅ 录音截取成功！")
except Exception as e:
    print(f"\n❌ 致命拦截：Python 无法访问麦克风！")
    print(f"🔍 真实底层报错原因: {e}")