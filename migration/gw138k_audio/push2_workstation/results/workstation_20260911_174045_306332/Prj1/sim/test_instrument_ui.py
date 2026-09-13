"""Preset, voice ownership and Tk integration regressions; never open hardware."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import queue
import struct
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_backend import Ack, decode_latency_status, decode_voice_onset_status
from instrument_ui import app as ui
from instrument_ui.presets import FACTORY, VoicePatch, factory_preset, load_preset, save_preset
from instrument_ui.voice_model import VoiceAllocator


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "preset.json"

    def document(self):
        return {"version": 1, "name": "测试 · 正弦", "voices": [asdict(VoicePatch(waveform=2)) for _ in range(4)]}

    def write_document(self, document):
        self.path.write_text(json.dumps(document), encoding="utf-8")

    def test_factory_voices_are_independent_copies(self):
        name = next(iter(FACTORY))
        voices = factory_preset(name)
        before = FACTORY[name].attack_ms
        voices[0].attack_ms = before + 10
        self.assertEqual(voices[1].attack_ms, before)
        self.assertEqual(FACTORY[name].attack_ms, before)
        self.assertEqual(len(voices), 32)

    def test_legacy_four_voice_preset_repeats_bank_without_shared_objects(self):
        document = self.document()
        for voice, values in enumerate(document["voices"]):
            values["attack_ms"] = 10 + voice
        self.write_document(document)
        _, loaded = load_preset(self.path)
        self.assertEqual(len(loaded), 32)
        self.assertEqual([patch.attack_ms for patch in loaded], [10, 11, 12, 13] * 8)
        loaded[0].attack_ms = 999
        self.assertEqual(loaded[4].attack_ms, 10)

    def test_voice_patch_covers_top_slot_and_rejects_outside_bank(self):
        self.assertTrue(all(command[1] == 31 for command in VoicePatch().commands(31)))
        for invalid in (-1, 32, True):
            with self.assertRaises(ValueError):
                VoicePatch().commands(invalid)

    def test_json_round_trip_keeps_32_distinct_voice_settings(self):
        voices = [VoicePatch(waveform=v % 3, velocity=.1 + v / 100,
                            attack_ms=v * 10, sustain=v / 31) for v in range(32)]
        save_preset(self.path, "测试 · 正弦", voices)
        name, loaded = load_preset(self.path)
        self.assertEqual(name, "测试 · 正弦")
        self.assertEqual(loaded, voices)
        self.assertIn("测试", self.path.read_text(encoding="utf-8"))

    def test_validation_rejects_boolean_nonfinite_out_of_range_and_huge_values(self):
        cases = [("waveform", True), ("waveform", 3), ("waveform", 2.0),
                 ("velocity", True), ("velocity", -.01), ("velocity", 1.01),
                 ("velocity", float("inf")), ("velocity", float("nan")),
                 ("velocity", "0.2"), ("sustain", -1), ("sustain", 10**400),
                 ("attack_ms", -1), ("decay_ms", 10001), ("release_ms", None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                voice = VoicePatch()
                setattr(voice, field, value)
                with self.assertRaises(ValueError):
                    voice.validate()

    def test_load_rejects_bad_schema_missing_unknown_and_wrong_voice_count(self):
        documents = [[], {}, {**self.document(), "version": True},
                     {**self.document(), "name": ""}, {**self.document(), "name": "x" * 81},
                     {**self.document(), "voices": self.document()["voices"][:3]}]
        missing = self.document()
        del missing["voices"][0]["sustain"]
        unknown = self.document()
        unknown["voices"][1]["unknown"] = 1
        documents.extend([missing, unknown])
        for document in documents:
            with self.subTest(document=document):
                self.write_document(document)
                with self.assertRaises(ValueError):
                    load_preset(self.path)

    def test_load_rejects_oversized_and_invalid_json(self):
        for content in (" " * (64 * 1024 + 1), "{bad", "\ufeff{}"):
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_preset(self.path)

    def test_invalid_save_preserves_existing_file(self):
        self.path.write_text("original", encoding="utf-8")
        voices = factory_preset(next(iter(FACTORY)))
        voices[3].velocity = 2
        with self.assertRaises(ValueError):
            save_preset(self.path, "Invalid", voices)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "original")

    def test_patch_commands_include_sine_and_exact_sustain(self):
        commands = VoicePatch(waveform=2, sustain=.5).commands(3)
        self.assertEqual([item[0] for item in commands], [5, 4, 6, 7, 8, 9])
        self.assertTrue(all(item[1] == 3 for item in commands))
        self.assertEqual(commands[0], (5, 3, 2))
        self.assertEqual(commands[4], (8, 3, 0x40000000))


class AllocationTests(unittest.TestCase):
    def test_serial_notes_rotate_before_reusing_a_recent_release(self):
        voices = VoiceAllocator()
        for index in range(64):
            self.assertEqual(voices.press("key", 60), index % 32)
            voices.release("key")

    def test_quiet_slots_precede_tail_slots_then_oldest_free_slot_is_reused(self):
        voices = VoiceAllocator()
        self.assertEqual(voices.press("a", 60), 0)
        voices.release("a")
        self.assertEqual(voices.press("b", 62, active_mask=0b11), 2)
        voices.release("b")
        self.assertEqual(voices.press("c", 64, active_mask=0xFFFFFFFF), 3)
        voices.press("manual", 67, preferred=31, active_mask=0xFFFFFFFF)
        self.assertEqual(voices.note_for_voice(31), 67)

    def test_32_held_notes_do_not_steal_and_33rd_is_ignored(self):
        voices = VoiceAllocator()
        for voice in range(32):
            self.assertEqual(voices.press(f"key:{voice}", 60 + voice), voice)
        self.assertIsNone(voices.press("33rd", 80))
        self.assertEqual(len(voices.owners), 32)
        self.assertEqual(voices.release("key:1"), (1, 61))
        self.assertEqual(voices.press("replacement", 70), 1)

    def test_preferred_reassignment_ignores_stale_key_release(self):
        voices = VoiceAllocator()
        voices.press("keyboard", 60)
        voices.press("manual", 72, preferred=0)
        self.assertIsNone(voices.release("keyboard"))
        self.assertEqual(voices.note_for_voice(0), 72)
        self.assertEqual(voices.release("manual"), (0, 72))

    def test_repeat_is_idempotent_and_release_voice_clears_ownership(self):
        voices = VoiceAllocator()
        self.assertEqual(voices.press("a", 60), 0)
        self.assertIsNone(voices.press("a", 60))
        voices.release_voice(0)
        self.assertIsNone(voices.release("a"))
        voices.press("b", 64)
        voices.clear()
        self.assertEqual(voices.notes, [])

    def test_legacy_capacity_can_be_limited_without_allocating_high_voices(self):
        voices = VoiceAllocator(4)
        for voice in range(4):
            self.assertEqual(voices.press(voice, 60 + voice), voice)
        self.assertIsNone(voices.press("overflow", 80))
        with self.assertRaises(ValueError):
            voices.press("high", 80, preferred=31)


class FakeWorker:
    """No threads or ports: inject acknowledgements explicitly on the UI thread."""
    def __init__(self):
        self.events = queue.Queue()
        self.calls = []
        self.accept = True
        self.is_alive = True
        self.close_requested = False
        self.submission_times = []
        self.submission_background = []

    def connect(self, port, simulated=False, output_controls=None):
        self.calls.append(("connect", port, simulated))
        self.connected_output = output_controls
        self.events.put({"type": "connected", "port": port, "simulated": simulated, "connection_id": 1,
                         "output_controls_supported": {16: True, 17: True},
                         "output_values": dict(zip((16, 17), output_controls or ()))})
        return True

    def disconnect(self):
        self.calls.append(("disconnect",))
        self.events.put({"type": "disconnected"})

    def submit(self, commands, tag="", coalesce_key=None, submitted_at=None, background=False):
        self.calls.append(("submit", list(commands), tag, coalesce_key))
        self.submission_times.append(submitted_at)
        self.submission_background.append(background)
        return self.accept

    def request_latency_status(self):
        self.calls.append(("latency-request",))
        return True

    def cancel_latency_status(self):
        self.calls.append(("latency-cancel",))

    def request_voice_onset_status(self, voice):
        self.calls.append(("onset-request", voice))
        return True

    def cancel_voice_onset_status(self):
        self.calls.append(("onset-cancel",))

    def panic(self):
        self.calls.append(("panic",))
        return True

    def close(self):
        self.close_requested = True


class TkIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.worker = FakeWorker()
        with patch.object(ui, "ControlWorker", return_value=self.worker), patch.object(ui, "list_ports", return_value=[]):
            self.app = ui.InstrumentApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        if not hasattr(self, "root"):
            return
        try:
            for pending in self.root.tk.call("after", "info"):
                self.root.after_cancel(pending)
            self.app.piano.release_all()
            self.root.destroy()
        except tk.TclError:
            pass

    def key_event(self, char="a", widget=None):
        return SimpleNamespace(char=char, keysym=char, widget=widget or self.root)

    def connect(self):
        self.app.offline_var.set(True)
        self.app.toggle_connection()
        self.app._drain_events()
        self.assertTrue(self.app.connected)
        # Most regressions drive patch ACKs themselves; leave startup preload
        # unconfirmed and discard its UI tags to isolate that explicit batch.
        self.app.patch_requests.clear()

    def patch_acks(self, call, *, voice=None, commands=None, connection_id=1):
        for opcode, target, value in call[1] if commands is None else commands:
            if opcode not in (5, 4, 6, 7, 8, 9) or (voice is not None and target != voice):
                continue
            self.worker.events.put({"type": "ack", "active_mask": 0, "rtt_ms": 1,
                                    "opcode": opcode, "voice": target, "status": 0,
                                    "tag": call[2], "connection_id": connection_id})
        self.app._drain_events()

    def test_initializes_without_hardware_and_disables_piano(self):
        self.assertFalse(self.app.connected)
        self.assertFalse(self.app.piano._enabled)
        self.app.note_on("ignored", 60)
        self.assertEqual(self.worker.calls, [])

    def test_output_defaults_and_offline_edits_synchronize_before_playing(self):
        self.assertEqual(self.app.master_volume_var.get(), 100)
        self.assertEqual(self.app.balance_var.get(), 0)
        self.app.master_volume_var.set(75)
        self.app.balance_var.set(-50)
        self.app.change_output(16); self.app.change_output(17)
        self.assertEqual(self.worker.calls, [])
        self.connect()
        self.assertEqual(self.worker.connected_output, (0x60000000, 0x20000000))
        self.assertEqual(self.app.output_confirmed, {16: 0x60000000, 17: 0x20000000})
        self.assertIn("已确认", self.app.output_status_var.get())
        self.app.toggle_connection(); self.app._drain_events()
        self.assertEqual((self.app.master_volume_var.get(), self.app.balance_var.get()), (75, -50))
        self.app.toggle_connection(); self.app._drain_events()
        self.assertEqual(self.worker.connected_output, (0x60000000, 0x20000000))

    def output_ack(self, call, status=0, connection_id=1):
        self.worker.events.put({"type": "ack", "opcode": call[1][0][0], "voice": 255,
                                "active_mask": 0, "rtt_ms": 1, "status": status,
                                "tag": call[2], "connection_id": connection_id})
        self.app._drain_events()

    def test_slider_bursts_keep_latest_values_and_require_current_ack(self):
        self.connect()
        for value in (80, 60, 25):
            self.app.master_volume_var.set(value); self.app.change_output(16)
        self.assertEqual(len(self.app.output_jobs), 1)
        self.app._send_output(16)
        first = self.worker.calls[-1]
        self.assertEqual(first[1], [(16, 255, 0x20000000)])
        self.assertEqual(first[3], "output:16")
        self.assertEqual(self.app.output_confirmed[16], 0x80000000)
        self.assertIn("待确认", self.app.output_status_var.get())
        self.app.master_volume_var.set(100); self.app.change_output(16); self.app._send_output(16)
        latest = self.worker.calls[-1]
        self.assertEqual(latest[1], [(16, 255, 0x80000000)])
        self.output_ack(first)
        self.assertIn(16, self.app.output_pending)
        self.output_ack(latest, connection_id=99)
        self.assertIn(16, self.app.output_pending)
        self.output_ack(latest)
        self.assertNotIn(16, self.app.output_pending)
        self.assertIn("总音量：已确认", self.app.output_status_var.get())

    def test_balance_center_and_panic_reassert_unfinished_controls(self):
        self.connect()
        self.app.balance_var.set(100); self.app.change_output(17); self.app._send_output(17)
        self.assertEqual(self.worker.calls[-1][1], [(17, 255, 0x80000000)])
        self.app.center_balance()
        self.assertEqual(self.worker.calls[-1][1], [(17, 255, 0x40000000)])
        self.assertEqual(self.app.balance_value.cget("text"), "居中")
        self.app.master_volume_var.set(0); self.app.change_output(16)
        self.worker.calls.clear()
        self.app.panic()
        self.assertEqual(self.worker.calls[0], ("panic",))
        self.assertEqual({call[1][0] for call in self.worker.calls[1:]},
                         {(16, 255, 0), (17, 255, 0x40000000)})
        self.assertFalse(self.app.output_jobs)

    def test_unsupported_output_disables_only_affected_control_and_preserves_music(self):
        self.connect()
        self.app.balance_var.set(30); self.app.change_output(17)
        self.worker.events.put({"type": "output_control_unsupported", "opcode": 17, "connection_id": 1})
        self.app._drain_events()
        self.assertIn("disabled", self.app.balance_scale.state())
        self.assertIn("disabled", self.app.balance_center_button.state())
        self.assertNotIn("disabled", self.app.master_scale.state())
        self.assertFalse(self.app.output_jobs)
        self.assertIn("LR：旧位流不支持", self.app.output_status_var.get())
        self.assertTrue(self.app.connected)
        self.app.note_on("music", 60)
        self.assertEqual(self.worker.calls[-1][1][-1][0], 1)

    def test_failed_output_submission_is_not_reported_as_applied(self):
        self.connect(); self.worker.accept = False
        self.app.master_volume_var.set(20); self.app.change_output(16); self.app._send_output(16)
        self.assertIn("总音量：未应用", self.app.output_status_var.get())
        self.assertEqual(self.app.output_confirmed[16], 0x80000000)

    def test_new_note_flushes_pending_volume_before_note_without_waiting(self):
        self.connect(); self.worker.calls.clear()
        self.app.master_volume_var.set(0); self.app.change_output(16)
        self.app.note_on("key", 60)
        self.assertEqual(self.worker.calls[0][1], [(16, 255, 0)])
        self.assertEqual(self.worker.calls[1][1][-1][0], 1)
        self.assertFalse(self.app.output_jobs)

    def test_output_timing_starts_at_latest_slider_event_before_throttle_delay(self):
        self.connect()
        for value, timestamp in ((70, 100.0), (40, 100.01)):
            self.app.master_volume_var.set(value)
            with patch.object(ui.time, "perf_counter", return_value=timestamp):
                self.app.change_output(16)
        self.app._send_output(16)
        self.assertEqual(self.worker.submission_times[-1], 100.01)
        self.assertFalse(self.app.output_intents)

    def test_minimum_window_keeps_output_controls_piano_footer_and_last_card_visible(self):
        self.root.attributes("-alpha", 0.0)
        # Exercise the exact minimum client area, independently of tiling WMs
        # that can enlarge a managed window and invalidate the requested bounds.
        self.root.overrideredirect(True)
        width, height = self.root.minsize()
        self.root.geometry(f"{width}x{height}+0+0")
        self.root.deiconify()
        self.root.update()
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), (width, height))
        footer = self.root.nametowidget(self.app.log.winfo_parent()).grid_slaves(row=6)[0]
        widgets = [self.app.master_scale, self.app.balance_scale, self.app.balance_center_button,
                   self.app.master_value, self.app.balance_value, self.app.piano, self.app.log,
                   self.app.envelope, *footer.winfo_children()]
        for voice in (3, 31):
            self.app.select_voice(voice); self.root.update_idletasks()
            card = self.root.nametowidget(self.app.voice_pills[voice].winfo_parent())
            for widget in widgets + card.winfo_children():
                with self.subTest(voice=voice, widget=str(widget)):
                    self.assertTrue(widget.winfo_ismapped())
                    x = widget.winfo_rootx() - self.root.winfo_rootx()
                    y = widget.winfo_rooty() - self.root.winfo_rooty()
                    self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + widget.winfo_width(), width)
                    self.assertLessEqual(y + widget.winfo_height(), height)

    def test_pages_keep_top_voice_editable_and_all_activity_visible(self):
        self.assertEqual(len(self.app.voice_pages.tabs()), 8)
        self.assertEqual(len(self.app.voice_tiles), 32)
        self.assertEqual(len(self.app.voice_pills), 32)
        self.app.select_voice(31)
        self.assertEqual(self.app.voice_pages.index("current"), 7)
        self.assertEqual(self.app.selected, 31)
        self.connect()
        self.app.manual_on(31)
        self.assertEqual(self.worker.calls[-1][1][-1][1], 31)
        self.app.manual_off(31)
        self.assertEqual(self.worker.calls[-1][1], [(2, 31, 0)])

    def test_full_status_keeps_high_voices_across_low_byte_ack_and_panic_clears_all(self):
        self.connect()
        self.worker.events.put({"type": "voice_status", "active_mask": 0x81010204})
        self.app._drain_events()
        self.assertEqual(self.app.voice_pills[31]._text, "尾音")
        self.worker.events.put({"type": "ack", **Ack(3, 0, 0, 1, 1, "test").as_dict()})
        self.app._drain_events()
        self.assertEqual(self.app.active_mask, 0x81010201)
        self.worker.events.put({"type": "ack", **Ack(4, 13, 0, 0, 1, "test").as_dict()})
        self.app._drain_events()
        self.assertEqual(self.app.active_mask, 0x81010201)
        self.worker.events.put({"type": "ack", **Ack(5, 10, 0, 0, 1, "test").as_dict()})
        self.app._drain_events()
        self.assertEqual(self.app.active_mask, 0)

    def test_apply_all_submits_32_complete_patches(self):
        self.connect()
        self.app.apply_all()
        commands = self.worker.calls[-1][1]
        self.assertEqual(len(commands), 32 * 6)
        self.assertEqual({voice for opcode, voice, value in commands}, set(range(32)))
        self.assertTrue(self.worker.submission_background[-1])

    def test_connection_preloads_32_voices_and_ready_requires_every_slot_ack(self):
        self.app.offline_var.set(True)
        self.app.toggle_connection()
        self.app._drain_events()
        call = self.worker.calls[-1]
        self.assertEqual(len(call[1]), 192)
        self.assertTrue(self.worker.submission_background[-1])
        self.assertIn("正在准备音色 0/32", self.app.patch_ready_var.get())
        self.patch_acks(call, voice=0)
        self.assertIn("正在准备音色 1/32", self.app.patch_ready_var.get())
        self.patch_acks(call)
        self.app._drain_events()
        self.assertEqual(self.app.patch_ready_var.get(), "音色就绪 32/32")
        self.app.note_on("first", 60)
        self.assertEqual([command[0] for command in self.worker.calls[-1][1]], [1])

    def test_foreground_cancels_old_preload_confirmation_and_late_acks_cannot_rewarm(self):
        self.connect()
        self.app.apply_all()
        preload = self.worker.calls[-1]
        self.app.note_on("cold", 60, preferred=31)
        self.assertEqual([command[0] for command in self.worker.calls[-1][1]], [5, 4, 6, 7, 8, 9, 1])
        self.patch_acks(preload, voice=31)
        self.assertNotIn(31, self.app.last_parameters)
        self.worker.events.put({"type": "patch_preload_cancelled", "tag": preload[2], "voice": 0})
        self.patch_acks(preload, voice=0)
        self.assertNotIn(0, self.app.last_parameters)

    def test_connection_reports_only_verified_transport_timer(self):
        for profile, expected in (({"backend": "ftdi-d2xx", "latency_ms": 1}, "USB 定时器 1 ms"),
                                  ({"backend": "ftdi-d2xx"}, "USB 定时器未确认"),
                                  ({"backend": "pyserial"}, "pyserial")):
            self.worker.events.put({"type": "connected", "port": "FAKE", "connection_id": 1,
                                    "transport_profile": profile})
            self.app._drain_events()
            self.assertIn(expected, self.app.message_var.get())

    def test_old_firmware_is_explicitly_limited_and_apply_all_only_touches_four(self):
        self.worker.events.put({"type": "connected", "voice_count": 4, "port": "OLD"})
        self.app._drain_events()
        self.assertIn("旧位流", self.app.message_var.get())
        self.assertEqual(self.app.allocator.voice_count, 4)
        self.app.apply_all()
        self.assertEqual(len(self.worker.calls[-1][1]), 4 * 6)
        before = len(self.worker.calls)
        self.app.manual_on(31)
        self.assertEqual(len(self.worker.calls), before)

    def test_offline_connect_and_disconnect_update_controls(self):
        self.connect()
        self.assertEqual(self.worker.calls[0], ("connect", "离线", True))
        self.assertTrue(self.app.piano._enabled)
        self.app.note_on("a", 60)
        self.app.toggle_connection()
        self.app._drain_events()
        self.assertFalse(self.app.connected)
        self.assertFalse(self.app.piano._enabled)
        self.assertEqual(self.app.allocator.owners, {})

    def test_typing_in_editable_widgets_never_starts_notes(self):
        self.connect()
        before = len(self.worker.calls)
        for cls in (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Text):
            widget = cls(self.root)
            self.app._key_down(self.key_event(widget=widget))
            widget.destroy()
        self.assertEqual(len(self.worker.calls), before)
        self.assertEqual(self.app.allocator.owners, {})

    def test_repeated_keyboard_press_does_not_retrigger(self):
        self.connect()
        event = self.key_event()
        self.app._key_down(event)
        before = len(self.worker.calls)
        self.app._key_down(event)
        self.assertEqual(len(self.worker.calls), before)
        self.assertEqual(self.app.allocator.owners, {"key:a": (0, 60)})

    def test_windows_key_release_submits_immediately_without_a_tk_timer(self):
        self.connect()
        self.app.window_system = "win32"
        event = self.key_event()
        self.app._key_down(event)
        with patch.object(self.root, "after") as after, patch.object(self.root, "after_idle") as idle:
            self.app._key_up(event)
        self.assertEqual(self.app.allocator.owners, {})
        self.assertEqual(self.worker.calls[-1][1], [(2, 0, 0)])
        after.assert_not_called()
        idle.assert_not_called()

    def test_x11_repeat_pair_is_filtered_at_idle_and_real_release_keeps_event_time(self):
        self.connect()
        self.app.window_system = "x11"
        event = self.key_event()
        self.app._key_down(event)
        before = len(self.worker.calls)
        self.app._key_up(event)
        self.app._key_down(event)
        self.root.update_idletasks()
        self.assertEqual(len(self.worker.calls), before)
        self.assertEqual(self.app.allocator.owners, {"key:a": (0, 60)})
        clock = SimpleNamespace(now=1.0)
        with patch.object(ui, "time", SimpleNamespace(perf_counter=lambda: clock.now)):
            self.app._key_up(event)
            self.assertEqual(len(self.worker.calls), before)
            clock.now = 1.004
            self.root.update_idletasks()
        self.assertEqual(self.worker.calls[-1][1], [(2, 0, 0)])
        self.assertEqual(self.worker.submission_times[-1], 1.0)

    def test_selected_patch_requires_all_six_acks_then_note_on_sends_one_packet(self):
        self.connect()
        self.app.apply_selected()
        call = self.worker.calls[-1]
        self.assertEqual(self.app.last_parameters, {})
        self.patch_acks(call, commands=[call[1][-1]])
        self.assertEqual(self.app.last_parameters, {})
        self.patch_acks(call, commands=call[1][:-1])
        self.assertEqual(self.app.last_parameters[0], self.app.patches[0])
        self.app.note_on("warm", 60, preferred=0)
        self.assertEqual([command[0] for command in self.worker.calls[-1][1]], [1])

    def test_apply_all_confirms_each_voice_independently_including_top_slot(self):
        self.connect()
        self.app.apply_all()
        call = self.worker.calls[-1]
        self.patch_acks(call, voice=31)
        self.assertEqual(set(self.app.last_parameters), {31})
        self.app.note_on("warm-top", 60, preferred=31)
        self.assertEqual([command[0] for command in self.worker.calls[-1][1]], [1])
        self.app.note_on("cold-bottom", 64, preferred=0)
        self.assertEqual([command[0] for command in self.worker.calls[-1][1]], [5, 4, 6, 7, 8, 9, 1])

    def test_apply_all_complete_ack_batch_warms_all_32_slots(self):
        self.connect()
        self.app.apply_all()
        call = self.worker.calls[-1]
        self.patch_acks(call)  # GUI drains at most 100 ACKs per tick
        self.app._drain_events()
        self.assertEqual(len(self.app.last_parameters), 32)
        self.assertEqual(self.app.patch_requests, {})

    def test_new_apply_tag_panic_and_old_connection_cannot_warm_stale_patch(self):
        self.connect()
        self.app.apply_selected()
        old = self.worker.calls[-1]
        self.app.env_vars["attack_ms"].set("17")
        self.app.apply_selected()
        current = self.worker.calls[-1]
        self.assertNotEqual(old[2], current[2])
        self.assertEqual(old[3], current[3])
        self.patch_acks(old)
        self.assertEqual(self.app.last_parameters, {})
        self.patch_acks(current, connection_id=0)
        self.assertEqual(self.app.last_parameters, {})
        self.app.panic()
        self.patch_acks(current)
        self.assertEqual(self.app.last_parameters, {})

    def test_unconfirmed_and_rejected_apply_keep_necessary_note_parameters(self):
        self.connect()
        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                self.worker.accept = accepted
                self.app.apply_selected()
                if not accepted:
                    self.assertEqual(self.app.patch_requests, {})
                self.worker.accept = True
                self.app.note_on("cold", 60, preferred=0)
                self.assertEqual([command[0] for command in self.worker.calls[-1][1]], [5, 4, 6, 7, 8, 9, 1])
                self.app.panic()

    def test_rejected_parameter_ack_cannot_confirm_otherwise_complete_patch(self):
        self.connect()
        self.app.apply_selected()
        call = self.worker.calls[-1]
        self.worker.events.put({"type": "ack", "active_mask": 0, "rtt_ms": 1,
                                "opcode": 5, "voice": 0, "status": 3,
                                "tag": call[2], "connection_id": 1})
        self.patch_acks(call)
        self.assertEqual(self.app.last_parameters, {})
        self.assertEqual(self.app.patch_requests, {})

    def test_modifier_change_during_hold_does_not_lose_note_off(self):
        self.connect()
        self.app._key_down(SimpleNamespace(char="a", keysym="a", keycode=65, state=0, widget=self.root))
        # Ctrl changes the text character but the released physical key is A.
        self.app._key_up(SimpleNamespace(char="\x01", keysym="a", keycode=65, state=4, widget=self.root))
        deadline = time.perf_counter() + .15
        while self.app.allocator.owners and time.perf_counter() < deadline:
            self.root.update()
            time.sleep(.005)
        self.assertEqual(self.app.allocator.owners, {})
        self.assertEqual(self.worker.calls[-1][1], [(2, 0, 0)])

    def test_shift_change_during_punctuation_hold_does_not_lose_note_off(self):
        self.connect()
        self.app._key_down(SimpleNamespace(char=";", keysym="semicolon", keycode=186, state=0, widget=self.root))
        self.app._key_up(SimpleNamespace(char=":", keysym="colon", keycode=186, state=1, widget=self.root))
        deadline = time.perf_counter() + .15
        while self.app.allocator.owners and time.perf_counter() < deadline:
            self.root.update()
            time.sleep(.005)
        self.assertEqual(self.app.allocator.owners, {})

    def test_explicit_patch_apply_cannot_leave_stale_note_on_parameter_cache(self):
        self.connect()
        original_attack = self.app.patches[0].attack_ms
        self.app.note_on("key:a", 60)
        self.patch_acks(self.worker.calls[-1])
        self.assertIn(0, self.app.last_parameters)
        self.app.note_off("key:a")
        self.app.env_vars["attack_ms"].set(str(original_attack + 25))
        self.app.apply_selected()
        self.app.env_vars["attack_ms"].set(str(original_attack))
        self.app.note_on("key:a", 60, preferred=0)
        self.assertIn(6, [command[0] for command in self.worker.calls[-1][1]])

    def test_old_ack_after_explicit_apply_cannot_restore_obsolete_cache(self):
        self.connect()
        original_attack = self.app.patches[0].attack_ms
        self.app.note_on("key:a", 60)
        first_call = self.worker.calls[-1]
        self.app.env_vars["attack_ms"].set(str(original_attack + 25))
        self.app.apply_selected()
        self.patch_acks(first_call)
        self.assertNotIn(0, self.app.last_parameters)
        self.app.env_vars["attack_ms"].set(str(original_attack))
        self.app.note_on("replacement", 64, preferred=0)
        self.assertIn(6, [command[0] for command in self.worker.calls[-1][1]])

    def test_old_ack_after_panic_cannot_restore_cancelled_patch_cache(self):
        self.connect()
        self.app.note_on("key:a", 60)
        first_call = self.worker.calls[-1]
        self.app.panic()
        self.patch_acks(first_call)
        self.assertEqual(self.app.last_parameters, {})
        self.app.note_on("key:a", 60)
        self.assertIn(6, [command[0] for command in self.worker.calls[-1][1]])

    def test_envelope_plot_shows_actual_release_from_sustain(self):
        plot = self.app.envelope
        with patch.object(plot, "winfo_width", return_value=500), \
                patch.object(plot, "winfo_height", return_value=250):
            # R is a full-scale slope: from 50% it falls in 100 ms. With a
            # labelled 200 ms illustrative hold, release begins 2/3 across.
            plot.set_envelope(0, 0, .5, 200)
            coords = plot.coords("envelope_curve")
            left, note_off, right = coords[0], coords[6], coords[8]
            self.assertAlmostEqual((note_off - left) / (right - left), 2 / 3)
            labels = [plot.itemcget(item, "text") for item in plot.find_all()
                      if plot.type(item) == "text"]
            self.assertTrue(any("实际 R 100 ms" in label for label in labels))
            plot.set_envelope(0, 50, 0, 200)
            coords = plot.coords("envelope_curve")
            self.assertEqual(coords[6], coords[8])

    def test_manual_reassignment_does_not_release_on_old_keyboard_key_up(self):
        self.connect()
        self.app.note_on("key:a", 60)
        self.app.note_vars[0].set("72")
        self.app.manual_on(0)
        before = len(self.worker.calls)
        self.app.note_off("key:a")
        self.assertEqual(len(self.worker.calls), before)
        self.assertEqual(self.app.allocator.note_for_voice(0), 72)
        self.app.manual_off(0)
        self.assertEqual(self.worker.calls[-1][1], [(2, 0, 0)])

    def test_rejected_manual_reassignment_keeps_old_owner_for_note_off(self):
        self.connect()
        self.app.note_on("key:a", 60)
        self.worker.accept = False
        self.app.note_vars[0].set("72")
        self.app.manual_on(0)
        self.assertEqual(self.app.allocator.owners.get("key:a"), (0, 60))
        self.worker.accept = True
        self.app.note_off("key:a")
        self.assertEqual(self.worker.calls[-1][1], [(2, 0, 0)])

    def test_rejected_auto_note_restores_cursor_and_owner_state(self):
        self.connect()
        before_cursor = self.app.allocator.next_voice
        self.worker.accept = False
        self.app.note_on("reject", 60)
        self.assertEqual(self.app.allocator.next_voice, before_cursor)
        self.assertEqual(self.app.allocator.owners, {})
        self.worker.accept = True
        self.app.note_on("retry", 60)
        self.assertEqual(self.app.allocator.note_for_voice(0), 60)

    def test_confirmed_tails_are_passed_to_auto_allocation(self):
        self.connect()
        self.worker.events.put({"type": "voice_status", "active_mask": 0b11})
        self.app._drain_events()
        self.app.note_on("new", 60)
        self.assertEqual(self.app.allocator.note_for_voice(2), 60)

    def test_note_intent_timestamp_precedes_patch_conversion_and_release_work(self):
        self.connect()
        clock = SimpleNamespace(now=1.0)
        original = self.app._read_editor
        def slow_editor():
            clock.now = 2.0
            return original()
        with patch.object(ui, "time", SimpleNamespace(perf_counter=lambda: clock.now, strftime=time.strftime)), \
                patch.object(self.app, "_read_editor", side_effect=slow_editor):
            self.app.note_on("timed", 60)
            self.assertEqual(self.worker.submission_times[-1], 1.0)
            clock.now = 3.0
            self.app.note_off("timed")
            self.assertEqual(self.worker.submission_times[-1], 3.0)

    def test_latency_window_uses_matching_connection_and_unknown_does_not_disconnect(self):
        self.connect()
        self.app.open_latency()
        window = self.app.latency_window
        window.pages.select(1)
        window._tab_changed()
        self.assertIn(("latency-request",), self.worker.calls)
        self.worker.events.put({"type": "ack", **Ack(12, 1, 0, 1, 5, "test").as_dict(),
                                "voice": 31, "connection_id": 1, "timing_source": "serial",
                                "queue_wait_ms": 1.5, "host_total_ms": 6.5})
        self.app._drain_events()
        self.assertEqual(window.host_vars["queue_wait_ms"].get(), "1.500 ms")
        self.worker.events.put({"type": "latency_unsupported", "connection_id": 1})
        self.app._drain_events()
        self.assertTrue(self.app.connected)
        self.assertIn("需下载新版位流", window.info_var.get())
        self.assertFalse(window.auto_var.get())
        window.close()
        self.assertIsNone(self.app.latency_window)
        self.assertIn(("latency-cancel",), self.worker.calls[-2:])
        self.assertEqual(self.worker.calls[-1], ("onset-cancel",))

    def test_new_sound_ack_invalidates_old_latency_interval_even_after_sequence_wrap(self):
        self.connect()
        self.app.open_latency()
        window = self.app.latency_window
        ack = {"type": "ack", **Ack(7, 1, 0, 1, 5, "test").as_dict(),
               "voice": 31, "connection_id": 1, "sound_generation": 10,
               "timing_source": "serial", "queue_wait_ms": 2, "host_total_ms": 7}
        self.worker.events.put(ack)
        raw = struct.pack("<16I", 1 | 7 << 8 | 1 << 16 | 31 << 24, 0x7F, 123, 50_000_000,
                          50_000, 100, 1000, 2000, 3000, 4000, 55_000, 90_000, 226, 1024, 120_000, 0)
        self.worker.events.put({"type": "latency_status", "connection_id": 1, "sound_generation": 10,
                                "status": decode_latency_status(raw)})
        self.app._drain_events()
        self.assertIn("3.082–6.982 ms", window.interval_var.get())
        self.assertEqual(window.stage_vars["latest_compute_ms"].get(), "4.52 µs")
        self.worker.events.put({**ack, "sound_generation": 266})
        self.app._drain_events()
        self.assertIn("历史快照", window.interval_var.get())
        self.assertIn("历史记录", window.record_var.get())
        self.assertNotIn("3.082", window.interval_var.get())
        self.assertEqual(window.stage_vars["latest_compute_ms"].get(), "4.52 µs")
        window.close()

    def test_onset_tab_defaults_to_one_selected_voice_and_has_32_cached_rows(self):
        self.connect()
        self.app.open_latency()
        window = self.app.latency_window
        self.assertEqual(window.pages.index("current"), 0)
        self.assertEqual(len(window.onset_table.get_children()), 32)
        self.assertEqual([call for call in self.worker.calls if call[0] == "onset-request"], [("onset-request", 0)])
        self.assertNotIn(("latency-request",), self.worker.calls)
        window.onset_voice.set(31)
        window._select_onset_voice()
        self.assertEqual(self.worker.calls[-1], ("onset-request", 31))
        self.assertEqual(window.onset_table.selection(), ("31",))
        self.assertEqual(window.onset_cache, {})
        window.close()

    def test_onset_cache_survives_parameters_release_and_other_voice_until_same_voice_note_on(self):
        self.connect()
        self.app.open_latency()
        window = self.app.latency_window
        window.onset_voice.set(31); window._select_onset_voice()
        raw = struct.pack("<8I", 1 | 31 << 8 | 7 << 16 | 0x4F << 24, 18, 50_000_000, 226, 1300, 1300, 5, 0)
        self.worker.events.put({"type": "voice_onset_status", "connection_id": 1, "voice": 31,
                                "status": decode_voice_onset_status(raw)})
        self.app._drain_events()
        self.assertEqual(window.onset_vars["trigger_to_sample_ms"].get(), "4.52 µs")
        self.assertIn("活动声部重触发", window.onset_state_var.get())
        self.assertIn("静音", window.onset_amp_var.get())
        for opcode, voice in ((4, 31), (2, 31), (1, 0)):
            self.worker.events.put({"type": "ack", **Ack(9, opcode, 0, 0, 1, "test").as_dict(),
                                    "connection_id": 1, "voice": voice, "sound_generation": 15})
            self.app._drain_events()
            self.assertEqual(window.onset_vars["trigger_to_sample_ms"].get(), "4.52 µs")
            self.assertEqual(window.onset_cache[31]["status"]["note_id"], 18)
        self.worker.events.put({"type": "ack", **Ack(10, 1, 0, 0, 1, "test").as_dict(),
                                "connection_id": 1, "voice": 31, "sound_generation": 16})
        self.app._drain_events()
        self.assertEqual(window.onset_vars["trigger_to_sample_ms"].get(), "—")
        self.assertIn("等待查询新记录", window.onset_state_var.get())
        self.assertIn("新触发待查询", window.onset_table.item("31", "values")[3])
        self.worker.events.put({"type": "connected", "connection_id": 2, "port": "NEW", "voice_count": 32})
        self.app._drain_events()
        self.assertEqual(window.onset_cache, {})
        window.close()

    def test_onset_overflow_hides_exact_times_and_unsupported_keeps_music_connected(self):
        self.connect()
        self.app.open_latency()
        window = self.app.latency_window
        raw = struct.pack("<8I", 1 | 7 << 16 | 0x87 << 24, 1, 50_000_000, 226, 1300, 1400, 1, 0)
        self.worker.events.put({"type": "voice_onset_status", "connection_id": 1, "voice": 0,
                                "status": decode_voice_onset_status(raw)})
        self.app._drain_events()
        self.assertEqual(window.onset_vars["trigger_to_sample_ms"].get(), "—")
        self.assertIn("溢出", window.onset_state_var.get())
        self.worker.events.put({"type": "voice_onset_unsupported", "connection_id": 1})
        self.app._drain_events()
        self.assertTrue(self.app.connected)
        self.assertIn("需下载新版位流", window.onset_info_var.get())
        window.close()

    def test_rejected_manual_retrigger_keeps_manual_owner_for_release(self):
        self.connect()
        self.app.manual_on(0)
        self.worker.accept = False
        self.app.manual_on(0)
        self.assertEqual(self.app.allocator.owners.get("manual:0"), (0, 60))

    def test_pitch_change_updates_note_highlight_and_owner(self):
        self.connect()
        self.app.note_on("key:a", 60)
        self.app.note_vars[0].set("67")
        self.app.change_pitch(0)
        self.assertEqual(self.app.allocator.note_for_voice(0), 67)
        self.assertEqual(self.app.piano._active_notes, {67})

    def test_bad_envelope_does_not_submit_partial_patch(self):
        self.connect()
        before = len(self.worker.calls)
        self.app.env_vars["attack_ms"].set("not a number")
        self.app.apply_selected()
        self.assertEqual(len(self.worker.calls), before)
        self.assertIn("参数未应用", self.app.message_var.get())

    def test_bad_preset_import_reports_error_instead_of_callback_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "huge.json"
            values = asdict(VoicePatch())
            values["velocity"] = 10**400
            path.write_text(json.dumps({"version": 1, "name": "huge", "voices": [values] * 4}), encoding="utf-8")
            with patch.object(ui.filedialog, "askopenfilename", return_value=str(path)):
                self.app.import_preset()
            self.assertIn("导入失败", self.app.message_var.get())

    def test_focus_loss_panics_and_releases_mouse_state(self):
        self.connect()
        self.app.note_on("mouse:60", 60)
        self.app.piano._pointer_note = 60
        self.app.piano._pointer_down = True
        with patch.object(self.root, "focus_displayof", return_value=None):
            self.app._focus_check()
        self.assertEqual(self.app.allocator.owners, {})
        self.assertIsNone(self.app.piano._pointer_note)
        self.assertFalse(self.app.piano._pointer_down)
        self.assertEqual(self.worker.calls[-1], ("panic",))

    def test_ack_updates_confirmed_activity_and_release_tail(self):
        self.connect()
        self.worker.events.put({"type": "ack", "active_mask": 2, "rtt_ms": 4.2, "tag": "poll"})
        self.app._drain_events()
        self.assertEqual(self.app.voice_pills[1]._text, "尾音")
        self.assertEqual(self.app.rtt_var.get(), "ACK 4.2 ms")
        self.assertIn("1 / 32", self.app.active_label.cget("text"))

    def test_ack_burst_redraws_voice_bank_once_and_keeps_latest_state(self):
        self.connect()
        for index in range(20):
            self.worker.events.put({"type": "ack", **Ack(index, 0, 0, index, 1, "test").as_dict()})
        with patch.object(self.app, "_update_voice_status", wraps=self.app._update_voice_status) as render:
            self.app._drain_events()
        render.assert_called_once()
        self.assertEqual(self.app.active_mask, 19)

    def test_memory_ack_preserves_confirmed_voices_and_next_ping_can_clear_them(self):
        self.connect()
        self.worker.events.put({"type": "ack", **Ack(1, 0, 0, 4, 1, "test").as_dict()})
        self.app._drain_events()
        for status, simulated in ((0, False), (1, False), (0, True), (1, True)):
            with self.subTest(status=status, simulated=simulated):
                ack = Ack(2, 0x0B, status, 0xCB, 4.2, "test", simulated=simulated)
                self.worker.events.put({"type": "ack", **ack.as_dict(), "tag": "memory"})
                self.app._drain_events()
                self.assertEqual(self.app.active_mask, 4)
                self.assertEqual([pill._text for pill in self.app.voice_pills],
                                 ["静音", "静音", "尾音"] + ["静音"] * 29)
                self.assertIn("1 / 32", self.app.active_label.cget("text"))
                self.assertEqual(self.app.rtt_var.get(), "ACK 4.2 ms")
        self.worker.events.put({"type": "ack", **Ack(3, 0, 0, 0, 1, "test").as_dict()})
        self.app._drain_events()
        self.assertEqual(self.app.active_mask, 0)
        self.assertEqual([pill._text for pill in self.app.voice_pills], ["静音"] * 32)

    def test_close_waits_for_worker_before_destroying_tk(self):
        with patch.object(self.root, "destroy") as destroyed:
            started = time.perf_counter()
            self.app.close()
            self.assertLess(time.perf_counter() - started, .1)
            self.assertTrue(self.worker.close_requested)
            self.assertFalse(self.app.piano._enabled)
            destroyed.assert_not_called()
            self.worker.is_alive = False
            deadline = time.perf_counter() + .3
            while not destroyed.called and time.perf_counter() < deadline:
                self.root.update()
                time.sleep(.005)
            destroyed.assert_called_once()


class OfflineLifecycleTests(unittest.TestCase):
    def test_actual_offline_worker_connect_play_release_and_close(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        root.withdraw()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        app = None
        from instrument_backend import worker as worker_module

        def pump_until(condition, timeout=2):
            deadline = time.perf_counter() + timeout
            while not condition() and time.perf_counter() < deadline:
                root.update()
                time.sleep(.005)
            self.assertTrue(condition(), "offline lifecycle timed out")

        try:
            with patch.object(ui, "list_ports", return_value=[]), \
                    patch.object(worker_module, "SerialTransport", side_effect=AssertionError("hardware forbidden")) as hardware:
                app = ui.InstrumentApp(root, offline=True)
                pump_until(lambda: app.connected)
                app.note_on("test", 60)
                pump_until(lambda: app.active_mask == 1)
                app.note_off("test")
                pump_until(lambda: app.active_mask == 0)
                app.apply_all()
                for voice in range(32):
                    app.manual_on(voice)
                pump_until(lambda: app.active_mask == 0xFFFFFFFF)
                self.assertEqual(len(app.allocator.owners), 32)
                app.manual_off(31)
                pump_until(lambda: app.active_mask == 0x7FFFFFFF)
                app.panic()
                pump_until(lambda: app.active_mask == 0)
                app.toggle_connection()
                pump_until(lambda: not app.connected)
                app.close()
                pump_until(lambda: not app.worker.is_alive)
                hardware.assert_not_called()
                self.assertEqual(errors, [])
        finally:
            if app is not None:
                app.worker.close()
                app.worker._thread.join(1)
                self.assertFalse(app.worker.is_alive)
            try:
                for pending in root.tk.call("after", "info"):
                    root.after_cancel(pending)
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
