#!/usr/bin/env python3
"""Task3 opt-in TF menu regression using production RTL and locked inputs.

Exercises real MMIO, filename pixels, Push/generic controls, event FIFO,
song-command CDC and TF transport/playback policy; no SD PCM or board claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve() if args.out else Path(tempfile.mkdtemp(prefix='tf-menu-no-cnn-'))
    out.mkdir(parents=True, exist_ok=True)
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    locked = []
    for name in ('src/migration/gw138k_stream_cdc.sv',
                 'src/usb_host/gw138k_usb_event_fifo.v',
                 'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v'):
        path = out / 'locked' / name
        baseline.copy_file(name, path)
        locked.append(path)
    sources = [ROOT / 'rtl/push2_usb_a_control.sv', ROOT / 'rtl/audio/push2_controls.sv',
               ROOT / 'rtl/display_data/push2_surface_pixels.sv',
               *[ROOT / 'rtl/push2' / name for name in (
                   'push2_playlist_hold.sv', 'push2_song_menu.sv', 'push2_score_guide.sv',
                   'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')],
               ROOT / 'rtl/audio/scope_vec/scope_tf_transport.sv',
               ROOT / 'rtl/services/workstation_playback_service.sv',
               *locked, ROOT / 'sim/tb_tf_menu_no_cnn.sv']
    top = ROOT / 'rtl/workstation/gw138k_push_workstation_top.v'
    wrapper = ROOT / 'rtl/workstation/workstation_usb2_input.sv'
    passed = False
    preprocessing = {}
    try:
        command = ['iverilog', '-g2012', '-s', 'tb_tf_menu_no_cnn', '-o', str(out / 'test'), *map(str, sources)]
        for name, cmd in [('compile', command), ('test', ['vvp', str(out / 'test')])]:
            result = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=120)
            (out / (name + '.log')).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f'{name} failed:\n{(result.stdout + result.stderr)[-6000:]}')
            if name == 'test':
                print(result.stdout.strip())
        # The macro is deliberately opt-in. These pre-existing top-level token
        # identities were measured before introducing TF_MENU_WITHOUT_CNN.
        compatibility = {
            'default': ((), '81ef2dfd4d62d47d7bd768c61ce19fced14e94eb6d19b8a65299dd1abafc513f'),
            'native': (('WORKSTATION_CUSTOM_138K', 'WORKSTATION_RUNTIME_NATIVE'), '62300be006a4e4b660f028d390bea024d567bdb731409844a8221d83c4d4c635'),
            'no_cnn': (('WORKSTATION_CUSTOM_138K', 'WORKSTATION_RUNTIME_NATIVE', 'WORKSTATION_NO_CNN'), '207f333f95a405c253a66e63346cf7cb687361b0d47c5276e41c1e1ea588362a'),
            'demo_no_tf': (('WORKSTATION_CUSTOM_138K', 'WORKSTATION_RUNTIME_NATIVE', 'WORKSTATION_NO_CNN', 'WORKSTATION_DEMO_NO_TF'), 'f6add9e25ba27cbd962261a754df25a262d83fd4c66e2ab7dbb658bd48f56ca9'),
        }
        for name, (macros, expected) in compatibility.items():
            pp = out / (name + '.v')
            subprocess.run(['iverilog', '-g2012', '-E', '-I', str(ROOT),
                            *['-D' + macro for macro in macros], '-o', str(pp), str(top)],
                           check=True, capture_output=True, text=True)
            payload = pp.read_text()
            tokens = ''.join(re.sub(r'//[^\n]*|/\*.*?\*/', '', payload, flags=re.S).split())
            digest = hashlib.sha256(tokens.encode()).hexdigest()
            if digest != expected:
                raise RuntimeError('unselected top-level tokens changed: ' + name)
            preprocessing[name] = dict(token_sha256=digest, unchanged=True)
        for name, macros in [('task3', compatibility['no_cnn'][0]),
                             ('retired_tf', compatibility['demo_no_tf'][0])]:
            pp = out / (name + '.v')
            subprocess.run(['iverilog', '-g2012', '-E', '-I', str(ROOT),
                            *['-D' + macro for macro in macros], '-DWORKSTATION_TF_MENU_WITHOUT_CNN',
                            '-o', str(pp), str(top)], check=True, capture_output=True, text=True)
            payload = pp.read_text()
            if name == 'task3':
                if (payload.count('u_song_command_cdc(') != 1 or '.TF_MENU_ENABLE(1\'b1)' not in payload or
                        "assign song_cmd_valid=1'b0;" in payload or 'music_basic_pitch_ddr' in payload):
                    raise RuntimeError('task3 actual top did not select independent TF command route')
            elif ('u_song_command_cdc(' in payload or '.TF_MENU_ENABLE(1\'b1)' in payload):
                raise RuntimeError('retired TF was re-enabled by task3 opt-in')
            preprocessing[name] = dict(sha256=hashlib.sha256(pp.read_bytes()).hexdigest())
        passed = True
    finally:
        (out / 'verification.json').write_text(json.dumps({
            'passed': passed, 'hardware_tested': False, 'sd_pcm_tested': False,
            'baseline': baseline.evidence(), 'preprocessing': preprocessing,
            'inputs': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in [Path(__file__), top, wrapper, *sources]},
        }, indent=2) + '\n')
        print(out)


if __name__ == '__main__':
    main()
