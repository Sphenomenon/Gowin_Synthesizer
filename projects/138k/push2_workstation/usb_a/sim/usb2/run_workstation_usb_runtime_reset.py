#!/usr/bin/env python3
"""Real USB MMIO owner/queue/session reset isolation, with old-reset control."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(source):
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S))


def instance(source, name):
    matches = list(re.finditer(r'\b' + re.escape(name) + r'\s*\(', source))
    if len(matches) != 1:
        raise ValueError('Instance anchor changed: ' + name)
    start = matches[0].end()
    depth = 1
    for offset in range(start, len(source)):
        depth += (source[offset] == '(') - (source[offset] == ')')
        if depth == 0:
            return compact(source[start:offset])
    raise ValueError('Unclosed instance: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    top = ROOT / 'rtl/workstation/gw138k_push_workstation_top.v'
    wrapper = ROOT / 'rtl/workstation/workstation_usb2_input.sv'
    sources = [ROOT / name for name in (
        'rtl/push2_usb_a_control.sv', 'rtl/audio/push2_controls.sv',
        'rtl/workstation/workstation_usb2_service_adapter.sv',
        'rtl/display_data/push2_surface_pixels.sv', 'rtl/control/workstation_session.sv')]
    sources += [ROOT / 'rtl/push2' / name for name in (
        'push2_playlist_hold.sv', 'push2_song_menu.sv', 'push2_score_guide.sv',
        'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')]
    sources += [project / name for name in (
        'src/migration/gw138k_stream_cdc.sv', 'src/usb_host/gw138k_usb_event_fifo.v',
        'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v')]
    bench = Path(__file__).with_name('tb_workstation_usb_runtime_reset.sv')
    sources += [bench]
    inputs = sources + [top, wrapper, Path(__file__).resolve(),
        project.parents[1] / 'workstation_profile.json', project.parents[1] / 'integration_inputs.json']
    hashes = {str(path): digest(path) for path in inputs}
    source_identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, identity='native-usb-runtime-reset-offline-v1-' + source_identity[:16],
        source_set_sha256=source_identity, input_sha256=hashes, hardware_tested=False, profile_changed=False,
        synthesis_tested=False, sram_deployed=False, flash_deployed=False, bitstream_identity=None,
        source_policy='Maintained real MMIO service adapter/input owner/generated prepared FIFO/session, with explicit source-hashed prepared support',
        validation_scope='Adapter/lifecycle regression; real 13-event attach initialization and modeled held-note/volume application',
        limits='No ULPI/device/USB enumeration, production firmware execution, DSP/physical audio retention, physical clocks/CDC/timing/resources or board acceptance',
        configuration=dict(usb_hz=48000000, compute_hz=76800000, short_qualification_pulse_ns=3,
            negative_control='Old PLL-qualified audio_reset_n connection; same actual RTL and stimulus'), commands={})

    def run(name, command, timeout=90):
        result['commands'][name] = list(map(str, command))
        with (output / (name + '.log')).open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        return (output / (name + '.log')).read_text()

    try:
        preprocessed = output / 'runtime_top.pre.v'
        run('preprocess_runtime_top', ['iverilog', '-g2012', '-E', '-DWORKSTATION_CUSTOM_138K',
            '-DWORKSTATION_RUNTIME_NATIVE', '-o', str(preprocessed), str(top)])
        selected = preprocessed.read_text()
        native_usb = instance(selected, 'u_native_usb')
        required = ('.audio_reset_n(runtime_reset_n)', '.reset_n(usb_reset_n)', '.clk_audio(audio_clk)')
        if not all(item in native_usb for item in required) or 'wireruntime_reset_n=reset_n&&memory_guard_started;' not in compact(selected):
            raise ValueError('Native top no longer preserves runtime-owned USB audio reset')
        owner_ports = instance(wrapper.read_text(), 'input_owner')
        if '.audio_reset_n(audio_reset_n)' not in owner_ports or '.feedback_reset_n(feedback_reset_n)' not in owner_ports:
            raise ValueError('Native USB wrapper does not forward selected reset to input owner/feedback')
        if 'wirefeedback_reset_n=FEEDBACK_AUDIO_DOMAIN!=0?audio_reset_n:feedback_release_q[1];' not in compact(wrapper.read_text()):
            raise ValueError('Audio-domain feedback reset source changed')
        prefix = selected[:selected.index('u_native_usb')]
        if not re.search(r'workstation_usb2_input\s*#\(\.FEEDBACK_AUDIO_DOMAIN\(1\)\)\s*$', prefix):
            raise ValueError('Actual native USB feedback domain selection changed')
        result['actual_top_binding'] = dict(preprocessed_sha256=digest(preprocessed),
            audio_reset_n='runtime_reset_n', runtime_reset_n='reset_n && memory_guard_started',
            usb_reset_n='usb_reset_n', compute_clock='audio_clk', feedback_audio_domain=1,
            wrapper_forwards_audio_reset=True, passed=True)
        compile_log = run('compile', ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps',
            '-j', '4', '-Wno-fatal', '--top-module', 'tb_workstation_usb_runtime_reset',
            '--Mdir', str(output / 'obj'), *map(str, sources)], 180)
        warnings = re.findall(r'^%Warning-([^:]+): ([^\n]+)', compile_log, re.M)
        own = [dict(kind=kind, message=message) for kind, message in warnings if bench.name + ':' in message]
        result['fixture_warnings'] = own
        result['warning_counts'] = {kind: sum(k == kind for k, _ in warnings) for kind, _ in warnings}
        if own or any(kind == 'UNOPTFLAT' for kind, _ in warnings):
            raise ValueError('New fixture warning or combinational loop')
        log = run('run', [str(output / 'obj/Vtb_workstation_usb_runtime_reset')], 60)
        print(log, end='')
        rows = re.findall(r'USB_RUNTIME_RESET (old=\d+[^\n]*)', log)
        cases = {int(values['old']): values for values in (
            {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', row)} for row in rows)}
        if set(cases) != {0, 1}:
            raise ValueError('Missing current/old reset comparison')
        current, old = cases[0], cases[1]
        for case in (current, old):
            if case['detaches'] != 1 or case['panics'] != 1 or case['barriers'] != case['attaches'] + case['panics'] or case['default_events'] != 13 * case['attaches'] or case['recovery_checks'] != 2 or case['detach_flush_checks'] != 1:
                raise ValueError('Incomplete real lifecycle/default/flush coverage')
        if current['attaches'] != 2 or old['attaches'] != 4 or current['resumed_queue_events'] != 2:
            raise ValueError('Reset isolation or old-connection negative control failed')
        if 'PASS usb_runtime_reset: recoveries=2 current_phantom_attach=0 old_phantom_attach=2 real_detach_reattach=1 panic=1 retained_queue_events=2 real_session_defaults=13' not in log:
            raise ValueError('Missing final reset isolation oracle')
        result.update(metrics=dict(current=current, old_connection=old, current_phantom_attaches=0,
            old_phantom_attaches=2, old_extra_default_events=26), checks=[
                'actual_preprocessed_native_top_reset_binding', 'real_mmio_service_adapter',
                'real_input_owner_and_generated_event_fifo', 'real_13_event_attach_session',
                'short_qualification_pulse_no_phantom_attach', 'stopped_compute_recovery_no_defaults',
                'queued_events_preserved_and_ordered', 'real_mmio_detach_reattach_after_compute_recovery',
                'pre_detach_queue_flushed', 'push_mapping_after_reattach', 'panic_once_preserves_modeled_volume',
                'old_pll_reset_reproduces_two_phantom_attaches'])
        if {str(path): digest(path) for path in inputs} != hashes:
            raise ValueError('Source drift during reset isolation verification')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], passed=True, source_set_sha256=source_identity)))


if __name__ == '__main__':
    main()
