#!/usr/bin/env python3
"""Real Push USB MMIO -> sole clock service -> existing rate-switch RTL.

The fixture joins USB and service in one ideal test domain; the separate
production transport and real dual-crystal DSP/I2S path are integration gates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--default-reference', type=Path, help='Exact frozen USB owner for the default-parameter public-output miter')
    ap.add_argument('--negative', choices=('source_queue_gate', 'held_repeat', 'stale_generation', 'wrong_target', 'apb_priority', 'release_quiet',
                                         'media_prepare', 'media_admission', 'media_gate'))
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    usb = ROOT/'rtl/push2_usb_a_control.sv'
    service = ROOT/'rtl/services/workstation_audio_clock_service.sv'
    selected_usb, selected_service = usb, service
    if args.negative:
        owner, before, after = {
            'source_queue_gate': (usb, 'rate_toggle_o<=rate_control_ready_i && rate_release_quiet==0;', 'rate_toggle_o<=rate_control_ready_i && rate_release_quiet==0 && queue_write_ready;'),
            'held_repeat': (usb, 'else if(!rate_button_down)begin', 'else begin'),
            'release_quiet': (usb, 'rate_control_ready_i && rate_release_quiet==0', 'rate_control_ready_i'),
            'stale_generation': (service, 'push_generation_i==push_generation_o && push_admission_error==BUS_OK', 'push_admission_error==BUS_OK'),
            'wrong_target': (service, "push_operation={1'b0,!core_active_44k1_i}", "push_operation={1'b0,core_active_44k1_i}"),
            'apb_priority': (service, 'push_fire && !(bus_fire && command_write_i)', 'push_fire'),
            'media_prepare': (service, 'push_needs_media_stop=ENABLE_MEDIA_POLICY', "push_needs_media_stop=1'b0"),
            'media_admission': (service, 'prepare_media && !media_stop_ready_i', "1'b0 && !media_stop_ready_i"),
            'media_gate': (service, 'if(!switch_permit_i || core_busy_i || core_dsp_fault_i', "if(1'b0 || core_busy_i || core_dsp_fault_i"),
        }[args.negative]
        original = owner.read_text()
        if original.count(before) != 1:
            raise ValueError('negative anchor drift: '+args.negative)
        target = out/owner.name
        target.write_text(original.replace(before, after))
        if owner == usb:
            selected_usb = target
        else:
            selected_service = target
    project = args.project.resolve()
    media_tb = Path(__file__).with_name('tb_push_rate_media.sv')
    media_negative = args.negative and args.negative.startswith('media_')
    top = 'tb_push_rate_media' if media_negative else 'tb_push_rate_control'
    sources = [selected_usb, selected_service, ROOT/'rtl/audio/workstation_sample_rate_switch.sv',
        project/'rtl/workstation/workstation_fifo_write_reset.sv',
        ROOT/'rtl/audio/push2_controls.sv', ROOT/'rtl/display_data/push2_surface_pixels.sv',
        *[ROOT/'rtl/push2'/name for name in ('push2_playlist_hold.sv', 'push2_song_menu.sv',
            'push2_score_guide.sv', 'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')],
        *[project/name for name in ('src/migration/gw138k_stream_cdc.sv',
            'src/usb_host/gw138k_usb_event_fifo.v', 'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v')],
        media_tb if media_negative else Path(__file__).with_name('tb_push_rate_control.sv')]
    reference_sources = []
    if args.default_reference:
        if args.negative:
            ap.error('default miter and negative controls run separately')
        reference = args.default_reference.resolve()
        text = reference.read_text()
        anchor = 'module push2_usb_a_control #('
        assert text.count(anchor) == 1, 'default reference rename anchor drift'
        renamed = out/'push2_usb_a_control_before.sv'
        renamed.write_text(text.replace(anchor, 'module push2_usb_a_control_before #('))
        reference_sources = [reference, renamed, Path(__file__).with_name('tb_push_rate_default.sv')]
    inputs = {str(p): sha(p) for p in dict.fromkeys([*sources, *reference_sources, media_tb, usb, service, Path(__file__).resolve()])}
    report = dict(passed=False, input_sha256=inputs, negative_control=args.negative,
        hardware_tested=False, synthesis_tested=False, source_transport_CDC_tested=False,
        scope='Actual USB MMIO decoder/mapper/generated FIFO, shared admission/service FSM and existing rate-switch RTL',
        limits='Ideal common USB/service test clock and ideal core clock-status inputs; no dual-crystal DSP/I2S, physical CDC or board acceptance')
    try:
        argv = ['iverilog', '-g2012', '-s', top, '-o', str(out/'test.vvp'), *map(str, sources)]
        process = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        (out/'compile.log').write_text(process.stdout+process.stderr)
        process.check_returncode()
        process = subprocess.run(['vvp', str(out/'test.vvp')], cwd=out, capture_output=True, text=True, timeout=60)
        log = process.stdout+process.stderr
        (out/'run.log').write_text(log)
        if args.negative:
            expected = {
                'source_queue_gate': 'rate transaction mismatch', 'held_repeat': 'held press repeated',
                'stale_generation': 'stale generation entered reopened admission', 'wrong_target': 'rate transaction mismatch',
                'apb_priority': 'APB write did not reject simultaneous Push', 'release_quiet': 'short release/repress escaped debounce',
                'media_prepare': 'media service not ready', 'media_admission': 'Push bypassed media readiness',
                'media_gate': 'Push bypassed post-media gate',
            }[args.negative]
            report['expected_negative_failure'] = expected
            if process.returncode == 0 or 'FATAL:' not in log or expected not in log:
                raise ValueError('negative control unexpectedly passed')
            report['negative_control_rejected'] = True
        elif process.returncode or 'PASS push_rate_control ' not in log:
            raise ValueError('targeted runtime failed: '+log[-3000:])
        else:
            argv = ['iverilog', '-g2012', '-s', 'tb_push_rate_media', '-o', str(out/'media.vvp'),
                    str(service), str(ROOT/'rtl/audio/workstation_sample_rate_switch.sv'), str(media_tb)]
            process = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            (out/'media-compile.log').write_text(process.stdout+process.stderr)
            process.check_returncode()
            process = subprocess.run(['vvp', str(out/'media.vvp')], cwd=out, capture_output=True, text=True, timeout=60)
            media_log = process.stdout+process.stderr
            (out/'media-run.log').write_text(media_log)
            if process.returncode or 'PASS push_rate_media ' not in media_log:
                raise ValueError('Push media policy failed: '+media_log[-3000:])
            report['push_media_policy_passed'] = True
            print(media_log, end='')
        if reference_sources:
            argv = ['iverilog', '-g2012', '-s', 'tb_push_rate_default', '-o', str(out/'default.vvp'),
                    *map(str, [*sources[:-1], *reference_sources[1:]])]
            process = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            (out/'default-compile.log').write_text(process.stdout+process.stderr)
            process.check_returncode()
            process = subprocess.run(['vvp', str(out/'default.vvp')], cwd=out, capture_output=True, text=True, timeout=60)
            default_log = process.stdout+process.stderr
            (out/'default-run.log').write_text(default_log)
            if process.returncode or 'PASS push_rate_default ' not in default_log:
                raise ValueError('default-parameter miter failed: '+default_log[-3000:])
            report['default_USB_public_output_miter_passed'] = True
            print(default_log, end='')
        assert inputs == {p: sha(p) for p in inputs}, 'consumed input drift'
        report.update(passed=True, log_sha256=sha(out/'run.log'), inputs_unchanged_during_run=True)
        print(log, end='')
    finally:
        (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
