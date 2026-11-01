#!/usr/bin/env python3
"""First-M Push entries using the real USB owner, FIFO, display and lights."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    names = ['rtl/push2_usb_a_control.sv', 'rtl/audio/push2_controls.sv',
             'rtl/display_data/push2_surface_pixels.sv',
             *['rtl/push2/' + name for name in ('push2_playlist_hold.sv', 'push2_song_menu.sv',
               'push2_score_guide.sv', 'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')],
             'sim/usb2/tb_workstation_m_core_push_entries.sv', 'sim/usb2/tb_workstation_no_cnn_owner.sv']
    hashes = {name: sha(ROOT / name) for name in names}
    snapshot = output / 'source-snapshot'
    for name in names:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    support = []
    for name in ('src/migration/gw138k_stream_cdc.sv', 'src/usb_host/gw138k_usb_event_fifo.v',
                 'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v'):
        target = output / Path(name).name
        target.write_bytes(baseline.read_bytes(name))
        support.append(target)
    sources = [snapshot / name for name in names[:-2]] + support
    result = dict(schema=1, passed=False, source_sha256=hashes, support_baseline=baseline.evidence(),
                  support_sha256={p.name: sha(p) for p in support}, cases={}, hardware_tested=False)

    def execute(name, top, selected, expected_error=None):
        binary = output / (name + '.vvp')
        argv = ['iverilog', '-g2012', '-s', top, '-o', str(binary), *map(str, selected)]
        compiled = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        (output / (name + '-compile.log')).write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(name + ': ' + compiled.stdout + compiled.stderr)
        executed = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=60)
        text = executed.stdout + executed.stderr
        (output / (name + '-run.log')).write_text(text)
        if expected_error:
            passed = executed.returncode != 0 and expected_error in text
        else:
            passed = executed.returncode == 0 and 'PASS ' in text
        result['cases'][name] = dict(passed=passed, argv=argv, returncode=executed.returncode,
            expected_error=expected_error, log=text, compiled_source_sha256={str(p): sha(p) for p in selected})
        if not passed:
            raise RuntimeError(name + ': ' + text)
        print(text.strip(), flush=True)

    try:
        tb = snapshot / names[-2]
        execute('core', 'tb_workstation_m_core_push_entries', sources + [tb])
        execute('legacy-no-cnn', 'tb_workstation_no_cnn_owner', sources + [snapshot / names[-1]])
        for label, relative, anchor, replacement, error in (
            ('entry-guard-removed', 'rtl/audio/push2_controls.sv', '!MEDIA_CONTROLS_ENABLE &&',
             "1'b0 &&", 'no CNN audio mapping changed'),
            ('labels-restored', 'rtl/display_data/push2_surface_pixels.sv', '!MEDIA_CONTROLS_ENABLE && tile<2',
             "1'b0 && tile<2", 'retired Push label still rendered'),
            ('score-led-restored', 'rtl/push2/push2_lights.sv',
             'MEDIA_CONTROLS_ENABLE ? (score_running?126:1) : 0',
             '(score_running?126:1)', 'retired score button lit'),
        ):
            source = snapshot / relative
            text = source.read_text()
            if text.count(anchor) != 1:
                raise ValueError('mutation anchor changed: ' + label)
            mutant = output / (label + '.sv')
            mutant.write_text(text.replace(anchor, replacement))
            selected = [mutant if p == source else p for p in sources] + [tb]
            execute(label, 'tb_workstation_m_core_push_entries', selected, error)
        result['source_inputs_unchanged_during_run'] = all(sha(ROOT / n) == h for n, h in hashes.items())
        if not result['source_inputs_unchanged_during_run']:
            raise ValueError('source changed during run')
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
