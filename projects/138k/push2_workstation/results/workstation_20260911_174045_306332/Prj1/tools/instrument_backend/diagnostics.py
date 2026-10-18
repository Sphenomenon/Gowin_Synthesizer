"""Read-only diagnostic transactions, called by the serial transport's owner."""
from __future__ import annotations

import math
import struct

from .protocol import OPCODES, OPCODE_NAMES, OUTPUT_OPCODES, VIDEO_STATUS_BYTES, LATENCY_STATUS_BYTES, VOICE_ONSET_STATUS_BYTES, VOICE_COUNT

VOICE_ONSET_FLAGS = ("valid", "sample_seen", "dac_seen", "was_active", "cancelled", "expired",
                     "amp_muted_at_dac", "observer_overflow")
VOICE_ONSET_STATES = {"not_triggered": "尚未触发", "waiting_sample": "等待有效 PCM 贡献",
                      "waiting_dac": "等待 DAC 双槽完成", "complete": "数字端点已完成",
                      "cancelled": "已停止等待（取消，不代表无声）", "expired": "已过期／未检测到完整端点",
                      "observer_overflow": "观测器溢出，不能作为精确测量"}


def read_voice_onset_status(transport, voice: int) -> bytes:
    """Read the selected slot's latest NOTE_ON snapshot without touching sound state."""
    if type(voice) is not int or voice not in range(VOICE_COUNT):
        raise ValueError("voice must be in 0..31")
    snapshot = bytearray()
    for index in range(VOICE_ONSET_STATUS_BYTES):
        ack = transport.command(OPCODES["voice-onset"], voice, index)
        value = ack.voice_onset_status_byte
        if value is None:
            raise RuntimeError(f"voice-onset byte {index} has no valid hardware status")
        snapshot.append(value)
    return bytes(snapshot)


def decode_voice_onset_status(data: bytes, expected_voice: int | None = None) -> dict:
    """Decode a per-slot NOTE_ON record; endpoint zero and missing are distinct.

    The threshold is this slot's /32 contribution quantized to PCM16, not the
    mixed sample or analog sound. Expired/overflow records yield no exact endpoints.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) != VOICE_ONSET_STATUS_BYTES:
        raise ValueError("voice onset status must contain exactly 32 bytes")
    if data[0] != 1:
        raise ValueError(f"unsupported voice-onset schema {data[0]}; expected 1")
    if data[1] not in range(VOICE_COUNT) or (expected_voice is not None and data[1] != expected_voice):
        raise ValueError("voice-onset snapshot does not match the requested voice")
    words = struct.unpack("<8I", data)
    if words[2] == 0 or words[6] >> 24:
        raise ValueError("voice-onset clock must be positive and revision reserved bits must be zero")
    status = {"schema": data[0], "voice": data[1], "sequence": data[2], "flags": data[3],
              "note_id": words[1], "clock_hz": words[2], "revision": words[6],
              **{name: bool(data[3] & (1 << bit)) for bit, name in enumerate(VOICE_ONSET_FLAGS)}}
    exact = status["valid"] and not status["expired"] and not status["observer_overflow"]
    for name, value, seen in (("sample", words[3], status["sample_seen"]),
                              ("dac", words[4], status["dac_seen"]),
                              ("cancel", words[7], status["cancelled"])):
        status[f"trigger_to_{name}_cycles"] = value if exact and seen else None
        status[f"trigger_to_{name}_ms"] = value * 1000 / words[2] if exact and seen else None
    status["elapsed_cycles"] = words[5] if status["valid"] else None
    status["elapsed_ms"] = words[5] * 1000 / words[2] if exact else None
    status["exact"] = exact
    if not status["valid"]:
        state = "not_triggered"
    elif status["observer_overflow"]:
        state = "observer_overflow"
    elif status["expired"]:
        state = "expired"
    elif status["dac_seen"]:
        state = "complete"
    elif status["sample_seen"]:
        state = "waiting_dac"
    elif status["cancelled"]:
        state = "cancelled"
    else:
        state = "waiting_sample"
    status["state"] = state
    status["state_text"] = VOICE_ONSET_STATES[state]
    return status

LATENCY_FLAGS = ("trace_valid", "state_sample_seen", "note_nonzero_sample_seen",
                 "dac_state_done", "dac_note_done", "ack_ready_seen", "ack_done_seen", "expired")
LATENCY_CYCLE_FIELDS = ("uart_rx_cycles", "packet_to_commit_cycles",
                        "commit_to_state_sample_cycles", "commit_to_note_sample_cycles",
                        "commit_to_dac_state_cycles", "commit_to_dac_note_cycles",
                        "start_to_ack_ready_cycles", "start_to_ack_done_cycles",
                        "latest_compute_cycles", "sample_period_cycles", "trace_age_cycles")


def read_latency_status(transport) -> bytes:
    """One complete hardware snapshot; index 0 latches, failures are not retried."""
    snapshot = bytearray()
    for index in range(LATENCY_STATUS_BYTES):
        ack = transport.command(OPCODES["latency-status"], 0xFF, index)
        value = ack.latency_status_byte
        if value is None:
            raise RuntimeError(f"latency-status byte {index} has no valid hardware status")
        snapshot.append(value)
    return bytes(snapshot)


def decode_latency_status(data: bytes) -> dict:
    """Schema 1 durations, with missing endpoints represented by None, never zero.

    Digital DAC endpoints are the last BCK rising edge of the stereo frame;
    neither these counters nor a nonzero voice contribution measure audible sound.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) != LATENCY_STATUS_BYTES:
        raise ValueError("latency status must contain exactly 64 bytes")
    words = struct.unpack("<16I", data)
    if data[0] != 1:
        raise ValueError(f"unsupported latency-status schema {data[0]}; expected 1")
    if words[1] & ~0xFF:
        raise ValueError("latency-status schema 1 has nonzero reserved flag bits")
    if words[3] == 0:
        raise ValueError("latency-status clock_hz must be positive")
    status = {"schema": data[0], "sequence": data[1], "opcode": data[2], "voice": data[3],
              "opcode_name": OPCODE_NAMES.get(data[2], "UNKNOWN"),
              "flags": words[1], "trace_id": words[2], "clock_hz": words[3],
              "overwritten_pending_count": words[15],
              **{name: bool(words[1] & (1 << bit)) for bit, name in enumerate(LATENCY_FLAGS)}}
    trace = status["trace_valid"]
    note = trace and status["opcode"] == OPCODES["note-on"]
    valid = (trace, trace, trace and status["state_sample_seen"],
             note and status["note_nonzero_sample_seen"], trace and status["dac_state_done"],
             note and status["dac_note_done"], trace and status["ack_ready_seen"],
             trace and status["ack_done_seen"], True, True, trace)
    for name, value, seen in zip(LATENCY_CYCLE_FIELDS, words[4:15], valid):
        status[name] = value if seen else None
        status[name.removesuffix("_cycles") + "_ms"] = value * 1000 / words[3] if seen else None
    return status


def input_to_digital_interval(status: dict, ack: dict | None, connection_id, sound_generation=None) -> dict:
    """Bound one matched submission; USB outward/return delays cannot be split.

    Never sum host RTT with FPGA duration as an exact one-way measurement.
    Caller supplies only the latest successful sound ACK of this connection.
    """
    def unavailable(reason):
        return {"available": False, "reason": reason}
    if not status.get("trace_valid"):
        return unavailable("尚无合法声音命令记录")
    if status.get("expired"):
        return unavailable("记录已过期，不能计算总延迟")
    if not ack or ack.get("status") != 0 or ack.get("simulated") or ack.get("timing_source") != "serial":
        return unavailable("需要本连接最近一次真实声音命令的主机计时")
    if connection_id is None or ack.get("connection_id") != connection_id:
        return unavailable("记录不属于当前连接")
    if sound_generation is None or ack.get("sound_generation") != sound_generation:
        return unavailable("历史快照：新声音命令后需重新读取")
    if not (1 <= ack.get("opcode", 0) <= 10 or ack.get("opcode") in OUTPUT_OPCODES):
        return unavailable("需要本连接最近一次成功声音命令")
    identity = ("sequence", "opcode", "voice")
    if any(ack.get(key) != status.get(key) for key in identity):
        return unavailable("FPGA 记录与最近声音命令尚未匹配")
    queue_ms, total_ms = ack.get("queue_wait_ms"), ack.get("host_total_ms")
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
           for value in (queue_ms, total_ms)):
        return unavailable("该命令没有有效的主机意图计时")
    endpoint = "dac_note" if status.get("commit_to_dac_note_ms") is not None else "dac_state"
    dac = status.get(f"commit_to_{endpoint}_ms")
    rx = status.get("uart_rx_ms")
    commit = status.get("packet_to_commit_ms")
    ack_ready = status.get("start_to_ack_ready_ms")
    if any(value is None for value in (dac, rx, commit, ack_ready)):
        return unavailable("等待数字输出端点及 ACK ready 计数")
    start_to_dac = rx + commit + dac
    lower = queue_ms + start_to_dac
    upper = total_ms - ack_ready + start_to_dac
    if upper < lower:
        return unavailable("主机与硬件计时区间不一致，无法给出有效边界")
    reason = ("首个新输出设置帧串完（不代表增益斜坡已结束）" if status.get("opcode") in OUTPUT_OPCODES
              else "单声部非零贡献帧串完" if endpoint == "dac_note"
              else "首个新状态样本帧串完（可能仍为零）")
    return {"available": True, "lower_ms": lower, "upper_ms": upper,
            "endpoint": endpoint, "start_to_dac_ms": start_to_dac,
            "reason": reason}


def read_voice_status(transport) -> int:
    """Read all 32 activity bits from one snapshot; never return partial data.

    The caller owns the transport for all four transactions. Offline transport
    reports its control model, not measured envelope tails.
    """
    snapshot = bytearray()
    for index in range(4):
        ack = transport.command(OPCODES["voice-status"], 0xFF, index)
        if ack.voice_status_byte is None:
            raise RuntimeError(f"voice-status byte {index} is invalid")
        snapshot.append(ack.voice_status_byte)
    return int.from_bytes(snapshot, "little")


def read_video_status(transport) -> bytes:
    """Read indices 0..15 once; index 0 latches the complete hardware snapshot.

    Stop at the first rejected, timed-out or simulated reply. Do not retry index
    0 or return partial data, either of which could misrepresent a snapshot.
    """
    snapshot = bytearray()
    for index in range(VIDEO_STATUS_BYTES):
        ack = transport.command(OPCODES["video-status"], 0xFF, index)
        value = ack.video_status_byte
        if value is None:
            raise RuntimeError(f"video-status byte {index} has no valid hardware status")
        snapshot.append(value)
    return bytes(snapshot)
