# -*- coding: utf-8 -*-
import json
import sys
import time
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pc.voice.voice_interaction as voice_module
from pc.voice.voice_interaction import VoiceInteraction, VoiceInteractionConfig


def make_frame():
    frame = np.full((520, 720, 3), 255, dtype=np.uint8)
    cv2.putText(frame, 'HF', (245, 260), cv2.FONT_HERSHEY_SIMPLEX, 4.8, (0, 0, 0), 12, cv2.LINE_AA)
    return frame


def main():
    report_path = ROOT / 'tmp' / 'voice_session_finalize_report.json'
    tts_messages = []

    def fake_speak(text):
        tts_messages.append(str(text))

    def fake_stop():
        tts_messages.append('[STOP_TTS]')

    original_speak = voice_module.speak_async
    original_stop = voice_module.stop_tts
    original_ask = voice_module.ask_assistant_with_rag

    def fake_ask(frame=None, question='', rag_context='', model_name=''):
        text = str(question)
        if '请仅从以下用户口述内容中提取适合写入实验室知识库的有效知识' in text:
            return json.dumps([
                '实验规范：涉及氢氟酸操作时，必须在通风橱内进行，并佩戴耐酸手套、护目镜和面屏。',
                '实验记录：实验完成后要检查废液桶液位，并在交接表中登记。'
            ], ensure_ascii=False)
        if '介绍当前系统状态' in text:
            return '系统当前状态正常。'
        return '测试回答。'

    voice_module.speak_async = fake_speak
    voice_module.stop_tts = fake_stop
    voice_module.ask_assistant_with_rag = fake_ask
    try:
        cfg = VoiceInteractionConfig()
        agent = VoiceInteraction(cfg)
        agent.set_ai_backend('ollama', model='gemma3:4b')
        agent.get_latest_frame_callback = make_frame
        session_id = agent.open_runtime_session(mode='voice_test', source='pc_local', metadata={'project_name': '自动测试', 'experiment_name': '整轮语音归档'})

        agent.process_text_command('介绍当前系统状态', source='pc_local', speak_response=True)
        agent.process_text_command('帮我记录 实验规范：涉及氢氟酸操作时，必须在通风橱内进行，并佩戴耐酸手套、护目镜和面屏。实验完成后要检查废液桶液位，并在交接表中登记。', source='pc_local', speak_response=True)
        agent.process_text_command('请识别一下这个化学品标签', source='pc_local', speak_response=True)
        agent.process_text_command('不用了', source='pc_local', speak_response=False)
        session_dir = ROOT / 'pc' / 'log' / 'voice_rounds' / session_id
        agent.close_runtime_session()

        summary_json = session_dir / 'session_summary.json'
        summary_md = session_dir / 'session_summary.md'
        payload = json.loads(summary_json.read_text(encoding='utf-8')) if summary_json.exists() else {}
        docs_dir = ROOT / 'pc' / 'knowledge_base' / 'docs'
        extracted_note = None
        for note in sorted(docs_dir.glob('VoiceNote_*.txt'), reverse=True):
            content = note.read_text(encoding='utf-8', errors='ignore')
            if (
                '[语音会话知识提取]' in content
                and '废液桶液位' in content
                and '专家结论' not in content
                and 'HF 且未检测到手套' not in content
            ):
                extracted_note = str(note)
                break

        report = {
            'session_id': session_id,
            'session_dir': str(session_dir),
            'summary_json_exists': summary_json.exists(),
            'summary_md_exists': summary_md.exists(),
            'round_count': payload.get('round_count'),
            'knowledge_items': payload.get('knowledge_items', []),
            'knowledge_item_count': payload.get('knowledge_item_count', 0),
            'knowledge_note_file': extracted_note,
            'tts_messages': tts_messages,
            'pass': bool(
                summary_json.exists()
                and summary_md.exists()
                and payload.get('knowledge_items')
                and extracted_note
                and all('专家结论' not in item for item in payload.get('knowledge_items', []))
                and all('HF 且未检测到手套' not in item for item in payload.get('knowledge_items', []))
            ),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        voice_module.speak_async = original_speak
        voice_module.stop_tts = original_stop
        voice_module.ask_assistant_with_rag = original_ask


if __name__ == '__main__':
    main()
