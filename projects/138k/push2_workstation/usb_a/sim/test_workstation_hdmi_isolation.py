#!/usr/bin/env python3
"""Isolated native UI source policy, deterministic input and DDR pixel regression."""

from pathlib import Path
import hashlib
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_hdmi_isolation as hdmi
from tools import workstation_pinout as pinout
from test_workstation_pinout import fixture


def verify_shared_ui(stage, output):
    output.mkdir(parents=True)
    reference = output / 'reference_renderer.v'
    text = (stage / 'src/video/feedback_renderer.v').read_text()
    anchor = 'module feedback_renderer #'
    if text.count(anchor) != 1:
        raise ValueError('reference renderer module changed')
    reference.write_text(text.replace(anchor, 'module p10_feedback_renderer #'))
    fixture_source = ROOT / 'sim/p11/tb_shared_display.sv'
    fixture_text = fixture_source.read_text()
    first = fixture_text.index('    reg sample_valid=0;')
    last = fixture_text.index('    reg start=0,ref_start=0;')
    fixture_text = fixture_text[:first] + '''    wire sample_valid;
    wire [31:0] pcm, sample_data, trigger_reference;
    workstation_hdmi_demo input_data(.clk(source_clk), .reset_n, .sample_valid,
        .sample_data, .output_pcm(pcm), .trigger_reference);
''' + fixture_text[last:]
    if fixture_text.count('.trigger_reference(32\'d0)') != 2:
        raise ValueError('UI reference trigger fixture changed')
    fixture_text = fixture_text.replace('.trigger_reference(32\'d0)', '.trigger_reference(trigger_reference)')
    fixture_path = output / 'tb_shared_display.sv'
    fixture_path.write_text(fixture_text)
    preview = output / 'tb_hdmi_ui.sv'
    preview.write_text('''`timescale 1ns/1ps
module tb_hdmi_ui;
    tb_shared_display testbench();
    integer image_file, pair_index;
    reg [63:0] pair_data;
    initial begin
        wait(testbench.pixel_count == 1036800);
        image_file = $fopen("current_ui.ppm", "wb");
        if (!image_file) $fatal(1, "cannot open UI preview");
        $fwrite(image_file, "P6\\n1920 1080\\n255\\n");
        for (pair_index = 0; pair_index < 1036800; pair_index = pair_index + 1) begin
            pair_data = testbench.reference_frame[pair_index];
            $fwrite(image_file, "%c%c%c%c%c%c", pair_data[23:16], pair_data[15:8], pair_data[7:0],
                    pair_data[55:48], pair_data[47:40], pair_data[39:32]);
        end
        $fclose(image_file);
    end
endmodule
''')
    names = ('feedback_renderer', 'feedback_dashboard', 'feedback_wave_align', 'feedback_capture',
             'output_audio_capture', 'output_audio_analysis', 'audio_analysis_rom', 'video_font_5x7')
    sources = [stage / 'src/memory/display_data_layout_pkg.sv', stage / 'src/memory/display_data_writer.v',
               stage / 'src/memory/display_data_reader.v',
               *(stage / f'src/video/{name}.v' for name in names), reference,
               stage / 'rtl/display_data/workstation_hdmi_demo.sv', fixture_path, preview]
    commands = (
        ('compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                     '--top-module', 'tb_hdmi_ui', '--Mdir', str(output / 'obj'),
                     '-I' + str(stage), *map(str, sources)]),
        ('simulation', [str(output / 'obj/Vtb_hdmi_ui')]),
    )
    for label, command in commands:
        process = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=300)
        (output / (label + '.log')).write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(label + ': ' + (process.stdout + process.stderr)[-6000:])
    log = (output / 'simulation.log').read_text()
    if '1036800 P10 pixel pairs identical' not in log or 'PASS startup invalid analysis' not in log:
        raise RuntimeError('shared UI regression did not finish')
    result = dict(passed=True, scope='actual UI shared DDR export/reload; 3 frames, stalls, startup, pixel comparison',
                  compared_pixel_pairs=1036800, hardware_tested=False,
                  input='workstation_hdmi_demo: 48 kHz, 375/750 Hz stereo triangle',
                  fixture_source_sha256=hdmi.digest(fixture_source),
                  inputs_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
                  preview_sha256=hdmi.digest(output / 'current_ui.ppm'))
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


class Isolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'out', prefix='test_hdmi_')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def prepare(self, dynamic=True):
        profile, payloads, core = fixture()
        plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)
        with patch.object(hdmi, 'prepare_pinout', return_value=(self.output / 'pinout', plan)):
            return hdmi.prepare(ROOT, self.output, self.output / 'prepared', 'C11027D0', dynamic)

    def test_minimal_profile_keeps_native_ui_and_queued_ddr(self):
        stage, manifest = self.prepare()
        self.assertFalse(manifest['full_workstation'])
        self.assertFalse(manifest['release_ready'])
        self.assertEqual(len(manifest['enabled_inputs']), 38)
        baseline = hdmi.load_baseline(ROOT, 'resource_rework_route0')
        for name in hdmi.LOCKED_SOURCES:
            payload = baseline.read_bytes(name)
            if name in hdmi.ADAPTATIONS:
                payload = hdmi.ADAPTATIONS[name](payload.decode()).encode()
            self.assertEqual((stage / name).read_bytes(), payload, name)
        self.assertIn('basic_pitch_ddr_client_queues u_arbiter', (stage / 'src/video/hdmi_display.v').read_text())
        display = (stage / 'src/video/hdmi_display.v').read_text()
        self.assertIn('assign merged_ready=arbiter_writer_ready && !scan_fetch_busy;', display)
        self.assertIn('.writer_valid(merged_req && !scan_fetch_busy)', display)
        self.assertIn('.writer_ready(arbiter_writer_ready)', display)
        self.assertIn('.fetch_busy(scan_fetch_busy)', display)
        self.assertEqual((stage / 'src/memory/ddr_address_map.vh').read_bytes(), (ROOT / 'rtl/ddr_address_map.vh').read_bytes())
        sdc = (stage / 'display.sdc').read_text()
        self.assertEqual(sdc.count('create_clock '), 1)
        self.assertEqual(sdc.count('create_generated_clock '), 5)
        self.assertNotIn('get_pins {u_video/', sdc)
        self.assertNotIn('usb_48m', sdc)
        self.assertIn('set_min_delay 0.800', sdc)
        self.assertIn('u_display/u_memory/', (stage / 'display.cst').read_text())
        self.assertIn('wloadn_3_s0" R17C2[0][A]', (stage / 'display.cst').read_text())
        self.assertIn('ddr_init_internal_r_s0" R52C59[0][B]', (stage / 'display.cst').read_text())
        self.assertNotIn('usb', (stage / 'display.cst').read_text())
        self.assertEqual((stage / 'hdmi_isolation_config.vh').read_text(), '`define HDMI_ISOLATION_DYNAMIC 1\n')
        self.assertNotIn('-verilog_define', (stage / 'run.tcl').read_text())
        self.assertIn('set_option -bit_security 0', (stage / 'run.tcl').read_text())
        with self.assertRaises(FileExistsError):
            hdmi.prepare(ROOT, self.output, stage, 'C11027D0')

    def test_observer_keeps_status_and_runtime_counters(self):
        stage, manifest = self.prepare()
        self.assertEqual(manifest['signal_schema'], 'hdmi-isolation-memory-video-counters-64-v1')
        expected = ['reset_n'] + [f'debug_status[{bit}]' for bit in reversed(range(63))]
        self.assertEqual(list(manifest['signals']), expected)
        configuration = ET.parse(stage / 'display.gao')
        self.assertEqual([signal.text for signal in configuration.findall('./AoCore/SignalList/Signal')], expected)
        probe = (stage / 'rtl/display_data/workstation_hdmi_isolation.sv').read_text()
        self.assertIn('reg [62:0] debug_status', probe)
        self.assertIn('video_diagnostics[127:96], video_diagnostics[71:64]', probe)
        self.assertIn('video_diagnostics[39:32], memory_flags,', probe)
        self.assertIn('video_diagnostics[13:8], video_diagnostics[64]', probe)

    def test_counter_observer_decode(self):
        decoder = runpy.run_path(str(ROOT / 'reports/workstation_hdmi_flicker_20261028/capture.py'))['decode']
        word = (0x89abcdef << 31) | (0xab << 23) | (0xcd << 15) | (0xcb << 7) | (0x2f << 1) | 1
        values = [1] + [int(bit) for bit in f'{word:063b}']
        sample = decoder(values)
        self.assertEqual(sample['underrun_lines'], 0x89abcdef)
        self.assertEqual(sample['rendered_frames_mod256'], 0xab)
        self.assertEqual(sample['video_frames_mod256'], 0xcd)
        self.assertEqual(sample['memory_flags_hex'], '0xCB')
        self.assertEqual(sample['video_flags_hex'], '0x2F')
        self.assertTrue(sample['memory_flags']['ddr_calibrated'])
        self.assertFalse(sample['memory_flags']['underrun_seen'])
        with self.assertRaises(ValueError):
            decoder(values[:-1])

    def test_static_selection_and_input_drift(self):
        stage, manifest = self.prepare(False)
        self.assertFalse(manifest['dynamic_input'])
        self.assertEqual((stage / 'hdmi_isolation_config.vh').read_text(), '`define HDMI_ISOLATION_DYNAMIC 0\n')
        (stage / 'hdmi_isolation_config.vh').write_text('changed\n')
        with patch.object(subprocess, 'run') as run, self.assertRaisesRegex(ValueError, 'input changed'):
            hdmi.build(stage)
        run.assert_not_called()

    def test_scan_trace_is_observer_only(self):
        trace = runpy.run_path(str(ROOT / 'reports/workstation_hdmi_flicker_20261028/scan_trace.py'))
        self.assertEqual(len(trace['TRACE_SIGNALS']), 64)
        self.assertEqual(len(set(trace['SIGNALS'])), 128)
        stage, manifest = self.prepare()
        before = {name: hdmi.digest(stage / name) for name in manifest['enabled_inputs']}
        with patch.object(hdmi, 'prepare', return_value=(stage, manifest)):
            trace['prepare'](stage, self.output, 'C11028D3')
        after = json.loads((stage / 'inputs.json').read_text())
        self.assertEqual(after['signal_schema'], trace['SCHEMA'])
        self.assertEqual(after['storage_depth'], 8192)
        self.assertEqual(after['sample_clock'], 'u_display/memory_clk')
        for name, expected in before.items():
            self.assertEqual(hdmi.digest(stage / name), expected, name)
        decoded = trace['decode_trace']([1] * 64)
        self.assertEqual(decoded['fetch_line'], 2047)
        self.assertEqual(decoded['fetch_epoch'], 255)
        self.assertEqual(decoded['issued'], 511)
        self.assertEqual(decoded['received'], 511)
        self.assertEqual(decoded['front_valid'], 1)

    @unittest.skipUnless(shutil.which('iverilog'), 'requires iverilog')
    def test_scan_window_under_direction_change_pressure(self):
        stage, _ = self.prepare()
        command = [sys.executable, str(ROOT / 'sim/display/run_scanout.py'), '--project', str(stage),
                   '--native-queues', '--case', 'stable', '--write-turnaround-cycles', '100']
        unprotected = subprocess.run(command + ['--output', str(self.output / 'unprotected')],
                                     capture_output=True, text=True, timeout=60)
        self.assertNotEqual(unprotected.returncode, 0)
        self.assertIn('unexpected black line', unprotected.stdout)
        protected = subprocess.run(command + ['--output', str(self.output / 'protected'), '--scan-write-window'],
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(protected.returncode, 0, protected.stdout + protected.stderr)
        self.assertIn('black_lines=0 underruns=0', protected.stdout)

    def test_zero_tool_exit_without_outputs_is_not_success(self):
        stage, _ = self.prepare()
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            result = hdmi.build(stage)
        self.assertEqual(result['tool_returncode'], 0)
        self.assertEqual(result['returncode'], 1)
        self.assertIn('impl/pnr/ao_0.fs', result['missing_outputs'])

    def test_timing_reuse_keeps_default_workstation_targets(self):
        report = self.output / 'Prj1/impl/pnr/Prj1_tr_content.html'
        report.parent.mkdir(parents=True)
        report.write_text('<html></html>')
        default = hdmi.audit_timing(self.output)
        isolated = hdmi.audit_timing(self.output, report_path=report, targets={'clk_50m': 50.0})
        self.assertIn('missing/changed clock requirement: audio_76m8', default['problems'])
        self.assertNotIn('missing/changed clock requirement: audio_76m8', isolated['problems'])
        self.assertFalse(isolated['timing_closed'])
        self.assertIn('missing/changed clock requirement: clk_50m', isolated['problems'])

    def test_cli_profile_conflicts_do_not_prepare(self):
        base = [sys.executable, str(ROOT / 'build.py')]
        profile = ['--hdmi-isolation', '--hdmi-output', str(self.output / 'prepared'),
                   '--netlist-dir', str(self.output), '--user-code', 'C11027E4']
        for options in (profile + ['--current-workstation'],
                        profile + ['--prepare-only', '--synthesis-only'],
                        ['--hdmi-output', str(self.output / 'prepared')]):
            result = subprocess.run(base + options, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse((self.output / 'prepared').exists())

    @unittest.skipUnless(shutil.which('iverilog'), 'requires iverilog')
    def test_input_cadence_replay_and_metadata(self):
        testbench = self.output / 'tb_input.sv'
        testbench.write_text('''`timescale 1ns/1ps
module tb_input;
    reg clk = 0, reset_n = 0;
    always #5 clk = ~clk;
    wire sample_valid;
    wire signed [31:0] sample_data;
    wire [31:0] output_pcm, trigger_reference, active_voices, status_data;
    wire [2:0] effect_mask;
    wire [5:0] effect_order;
    wire [31:0] static_status;
    workstation_hdmi_demo #(.CLOCK_HZ(1000), .SAMPLE_HZ(48)) dynamic_input(
        .clk, .reset_n, .sample_valid, .sample_data, .output_pcm, .trigger_reference,
        .active_voices, .status_data, .effect_mask, .effect_order);
    workstation_hdmi_demo #(.CLOCK_HZ(1000), .SAMPLE_HZ(48), .DYNAMIC(0)) static_input(
        .clk, .reset_n, .status_data(static_status));
    reg [31:0] captured [0:143];
    reg signed [31:0] left_value, right_value;
    integer round_index, cycle_index, samples;
    initial begin
        for (round_index = 0; round_index < 2; round_index = round_index + 1) begin
            reset_n = 0; repeat(3) @(negedge clk); reset_n = 1; samples = 0;
            for (cycle_index = 0; cycle_index < 3000; cycle_index = cycle_index + 1) begin
                @(negedge clk);
                if (sample_valid) begin
                    if (round_index == 0) captured[samples] = output_pcm;
                    else if (captured[samples] !== output_pcm) $fatal(1, "replay differs");
                    left_value = $signed(output_pcm[31:16]); right_value = $signed(output_pcm[15:0]);
                    if (sample_data !== ((left_value + right_value) <<< 15)) $fatal(1, "PCM mix");
                    if (trigger_reference !== (left_value <<< 16)) $fatal(1, "trigger scale");
                    samples = samples + 1;
                end
                if (static_status !== 32'h48444d49) $fatal(1, "static scene changed");
            end
            if (samples != 144) $fatal(1, "sample cadence: %0d", samples);
            if (status_data !== 32'h48444d03 || effect_mask !== 3) $fatal(1, "dynamic scene");
        end
        $display("PASS input cadence, replay, PCM scale and static/dynamic metadata"); $finish;
    end
endmodule
''')
        binary = self.output / 'input.vvp'
        subprocess.run(['iverilog', '-g2012', '-s', 'tb_input', '-o', str(binary), str(testbench),
                        str(ROOT / 'rtl/display_data/workstation_hdmi_demo.sv')], check=True, capture_output=True)
        result = subprocess.run(['vvp', str(binary)], check=True, capture_output=True, text=True, timeout=30)
        self.assertIn('PASS input cadence', result.stdout)

    @unittest.skipUnless(shutil.which('verilator'), 'requires verilator')
    def test_shared_ddr_ui_pixels(self):
        stage, _ = self.prepare()
        result = verify_shared_ui(stage, self.output / 'shared_ui')
        self.assertTrue(result['passed'])


if __name__ == '__main__':
    unittest.main()
