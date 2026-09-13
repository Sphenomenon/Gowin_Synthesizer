"""Validated parameter presets. Files contain controls, never recorded audio."""
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path

from instrument_backend import DEFAULT_SAMPLE_RATE, VOICE_COUNT, envelope_step, gain_word

WAVEFORMS = {"三角波": 0, "脉冲波": 1, "正弦波": 2}
WAVE_NAMES = tuple(WAVEFORMS)


@dataclass
class VoicePatch:
    waveform: int = 0
    velocity: float = 0.20
    attack_ms: float = 5.0
    decay_ms: float = 120.0
    sustain: float = 0.625
    release_ms: float = 100.0

    def validate(self):
        if type(self.waveform) is not int or self.waveform not in range(3):
            raise ValueError("音色必须是三角波、脉冲波或正弦波")
        for name in ("velocity", "sustain", "attack_ms", "decay_ms", "release_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} 必须是有限数值")
            limit = 1 if name in ("velocity", "sustain") else 10000
            if not 0 <= value <= limit:
                raise ValueError(f"{name} 必须在 0 至 {limit} 之间")
            if not math.isfinite(value):
                raise ValueError(f"{name} 必须是有限数值")
        return self

    def commands(self, voice):
        self.validate()
        if type(voice) is not int or voice not in range(VOICE_COUNT):
            raise ValueError("声部编号必须在 0 至 31 之间")
        sustain = gain_word(self.sustain)
        return [
            (5, voice, self.waveform), (4, voice, gain_word(self.velocity)),
            (6, voice, envelope_step(self.attack_ms, DEFAULT_SAMPLE_RATE)),
            (7, voice, envelope_step(self.decay_ms, DEFAULT_SAMPLE_RATE, 0x80000000-sustain)),
            (8, voice, sustain),
            (9, voice, envelope_step(self.release_ms, DEFAULT_SAMPLE_RATE)),
        ]


FACTORY = {
    "三角 · 温和起音": VoicePatch(),
    "正弦 · 柔和长音": VoicePatch(2, 0.22, 18, 180, 0.60, 250),
    "三角 · 短拨弦": VoicePatch(0, 0.25, 2, 230, 0.08, 90),
    "脉冲 · 复古音色": VoicePatch(1, 0.14, 5, 90, 0.45, 140),
}


def factory_preset(name):
    return [replace(FACTORY[name]) for _ in range(VOICE_COUNT)]


def load_preset(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024:
        raise ValueError("预设文件过大，最多允许 64 KiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] not in (1, 2):
        raise ValueError("不支持的预设格式，需 version=1 或 2")
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 80:
        raise ValueError("预设名称需要 1 至 80 个字符")
    voices = data.get("voices")
    expected = 4 if data["version"] == 1 else VOICE_COUNT
    if not isinstance(voices, list) or len(voices) != expected:
        raise ValueError(f"version={data['version']} 预设必须包含恰好 {expected} 个声部")
    patches = []
    for values in voices:
        if not isinstance(values, dict) or set(values) != set(VoicePatch.__dataclass_fields__):
            raise ValueError("声部参数字段不完整或存在未知字段")
        patches.append(VoicePatch(**values).validate())
    if data["version"] == 1:
        # Preserve all four legacy timbres by repeating their bank, with no aliases.
        patches = [replace(patches[voice % 4]) for voice in range(VOICE_COUNT)]
    return data["name"], patches


def save_preset(path, name, voices):
    if not isinstance(name, str) or not 1 <= len(name) <= 80 or len(voices) != VOICE_COUNT:
        raise ValueError("预设需要有效名称和 32 个声部")
    data = {"version": 2, "name": name, "voices": [asdict(v.validate()) for v in voices]}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
