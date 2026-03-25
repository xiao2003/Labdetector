from __future__ import annotations

import audioop
import json
import shutil
import subprocess
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class VoiceSampleSpec:
    sample_id: str
    text: str
    category: str
    expected_keywords: List[str]


FIXED_SAMPLE_SPECS: List[VoiceSampleSpec] = [
    VoiceSampleSpec("qa_status", "介绍当前系统状态", "qa", ["系统", "状态"]),
    VoiceSampleSpec("model_risk", "分析当前实验风险并给出处置建议", "model_call", ["风险", "建议"]),
    VoiceSampleSpec("expert_hf", "HF且未戴手套怎么办", "expert_voice", ["手套"]),
    VoiceSampleSpec("expert_ppe", "查看PPE风险", "expert_voice", ["风险"]),
]


def fixed_fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "pc" / "testing" / "assets" / "audio_fixtures"


def default_dynamic_specs() -> List[VoiceSampleSpec]:
    return list(FIXED_SAMPLE_SPECS)


def ensure_fixed_voice_fixtures() -> Dict[str, str]:
    fixture_root = fixed_fixture_root()
    fixture_root.mkdir(parents=True, exist_ok=True)
    manifest_path = fixture_root / "manifest.json"
    rows: List[Dict[str, object]] = []
    resolved: Dict[str, str] = {}
    for spec in FIXED_SAMPLE_SPECS:
        target = fixture_root / f"{spec.sample_id}.wav"
        if not target.exists():
            synthesize_wav_file(spec.text, target)
        rows.append(
            {
                **asdict(spec),
                "path": str(target),
                "speaker_type": "fixed_fixture",
            }
        )
        resolved[spec.sample_id] = str(target)
    manifest_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return resolved


def build_dynamic_voice_suite(output_dir: str | Path, wake_word: str) -> Dict[str, Dict[str, object]]:
    target_root = Path(output_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    suite: Dict[str, Dict[str, object]] = {}

    wake_path = target_root / "wake_word.wav"
    synthesize_wav_file(wake_word, wake_path)
    suite["wake_word"] = {
        "sample_id": "wake_word",
        "path": str(wake_path),
        "text": wake_word,
        "category": "wake_word",
        "expected_keywords": [wake_word],
        "speaker_type": "tts_generated",
    }

    fixed_paths = ensure_fixed_voice_fixtures()
    fixed_copy_root = target_root / "fixed"
    fixed_copy_root.mkdir(parents=True, exist_ok=True)
    dynamic_root = target_root / "dynamic"
    dynamic_root.mkdir(parents=True, exist_ok=True)

    for spec in default_dynamic_specs():
        dynamic_path = dynamic_root / f"{spec.sample_id}.wav"
        synthesize_wav_file(spec.text, dynamic_path)
        suite[f"dynamic_{spec.sample_id}"] = {
            "sample_id": f"dynamic_{spec.sample_id}",
            "path": str(dynamic_path),
            "text": spec.text,
            "category": spec.category,
            "expected_keywords": list(spec.expected_keywords),
            "speaker_type": "tts_generated",
        }

        fixed_source = Path(fixed_paths[spec.sample_id])
        fixed_target = fixed_copy_root / fixed_source.name
        if fixed_source.resolve() != fixed_target.resolve():
            shutil.copy2(str(fixed_source), str(fixed_target))
        suite[f"fixed_{spec.sample_id}"] = {
            "sample_id": f"fixed_{spec.sample_id}",
            "path": str(fixed_target),
            "text": spec.text,
            "category": spec.category,
            "expected_keywords": list(spec.expected_keywords),
            "speaker_type": "fixed_fixture",
        }

    (target_root / "suite_manifest.json").write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8")
    return suite


def synthesize_wav_file(text: str, output_path: str | Path) -> Path:
    if not str(text or "").strip():
        raise ValueError("语音样本文本不能为空。")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_raw = output_file.with_name(output_file.stem + "_raw.wav")
    script_path = output_file.with_suffix(".ps1")
    quoted_output = str(temp_raw).replace("'", "''")
    quoted_text = str(text).replace("'", "''")
    try:
        script = "\n".join(
            [
                "Add-Type -AssemblyName System.Speech",
                f"$out = '{quoted_output}'",
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                "$synth.SetOutputToWaveFile($out)",
                f"$synth.Speak('{quoted_text}')",
                "$synth.Dispose()",
            ]
        )
        script_path.write_text(script, encoding="utf-16")
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        if completed.returncode != 0 or not temp_raw.exists():
            raise RuntimeError(f"Windows 语音合成失败: {completed.stdout.strip()}")
        _normalize_wav_to_pcm16_16k(temp_raw, output_file)
    finally:
        if temp_raw.exists():
            temp_raw.unlink()
        if script_path.exists():
            script_path.unlink()
    return output_file


def _normalize_wav_to_pcm16_16k(source_path: Path, target_path: Path) -> None:
    with wave.open(str(source_path), "rb") as reader:
        channels = reader.getnchannels()
        sample_width = reader.getsampwidth()
        frame_rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())

    if channels > 1:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        channels = 1
    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
        sample_width = 2
    if frame_rate != 16000:
        frames, _ = audioop.ratecv(frames, sample_width, channels, frame_rate, 16000, None)
        frame_rate = 16000

    with wave.open(str(target_path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(frame_rate)
        writer.writeframes(frames)
