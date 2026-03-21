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
from pc.knowledge_base.rag_engine import knowledge_manager
from pc.core.expert_manager import expert_manager


def make_chem_frame():
    frame = np.full((520, 720, 3), 255, dtype=np.uint8)
    cv2.rectangle(frame, (120, 80), (600, 440), (245, 245, 245), -1)
    cv2.rectangle(frame, (150, 110), (570, 410), (255, 255, 255), -1)
    cv2.putText(frame, 'HF', (245, 260), cv2.FONT_HERSHEY_SIMPLEX, 4.8, (0, 0, 0), 12, cv2.LINE_AA)
    cv2.putText(frame, 'CHEMICAL', (180, 350), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 4, cv2.LINE_AA)
    return frame


def main():
    out = ROOT / 'tmp' / 'voice_runtime_check_report.json'
    note_probe = f'自动测试语音记录 {int(time.time())}'
    tts_messages = []

    def fake_speak(text):
        tts_messages.append(str(text))

    def fake_stop():
        tts_messages.append('[STOP_TTS]')

    original_speak = voice_module.speak_async
    original_stop = voice_module.stop_tts
    voice_module.speak_async = fake_speak
    voice_module.stop_tts = fake_stop
    try:
        cfg = VoiceInteractionConfig()
        cfg.asr_engine = 'auto'
        interaction = VoiceInteraction(cfg)
        interaction.set_ai_backend('ollama', model='gemma3:4b')
        interaction.get_latest_frame_callback = make_chem_frame
        interaction.open_runtime_session(mode='camera', source='pc_local', metadata={'project_name': '自动语音回归', 'experiment_name': 'README三场景校验'})

        results = []

        before = len(tts_messages)
        qa_resp = interaction.process_text_command('介绍当前系统状态', source='pc_local', speak_response=True, metadata={'scenario': 'qa'})
        results.append({
            'scenario': 'qa',
            'command': '介绍当前系统状态',
            'response': qa_resp,
            'tts_delta': tts_messages[before:],
            'pass': bool(qa_resp and tts_messages[before:]),
        })

        before = len(tts_messages)
        note_resp = interaction.process_text_command(f'帮我记录 {note_probe}', source='pc_local', speak_response=True, metadata={'scenario': 'note'})
        docs_dir = ROOT / 'pc' / 'knowledge_base' / 'docs'
        file_hit = False
        matched_file = ''
        for note in sorted(docs_dir.glob('VoiceNote_*.txt'), reverse=True):
            content = note.read_text(encoding='utf-8', errors='ignore')
            if note_probe in content:
                file_hit = True
                matched_file = str(note)
                break
        results.append({
            'scenario': 'note',
            'command': f'帮我记录 {note_probe}',
            'response': note_resp,
            'tts_delta': tts_messages[before:],
            'knowledge_file_saved': file_hit,
            'knowledge_file': matched_file,
            'pass': bool(file_hit and ('知识库' in note_resp or '写入' in note_resp)),
        })

        before = len(tts_messages)
        cmd = '请识别一下这个化学品标签'
        bundle = expert_manager.route_voice_command(cmd, make_chem_frame(), {'source': 'pc_local', 'query': cmd, 'question': cmd, 'detected_classes': ['bottle']})
        expert_resp = interaction.process_text_command(cmd, source='pc_local', speak_response=True, metadata={'scenario': 'voice_expert'})
        results.append({
            'scenario': 'voice_expert',
            'command': cmd,
            'response': expert_resp,
            'tts_delta': tts_messages[before:],
            'matched_expert_codes': bundle.get('matched_expert_codes', []),
            'group_results': bundle.get('group_results', {}),
            'pass': bool(bundle.get('matched_expert_codes') and bundle.get('group_results') and expert_resp),
        })

        report = {
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'readme_voice_expectations': ['语音问答', '语音记录并回灌知识库', '语音唤醒专家并播报结果'],
            'results': results,
            'tts_messages': tts_messages,
            'pass_count': sum(1 for item in results if item.get('pass')),
            'fail_count': sum(1 for item in results if not item.get('pass')),
        }
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(out)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        voice_module.speak_async = original_speak
        voice_module.stop_tts = original_stop

if __name__ == '__main__':
    main()
