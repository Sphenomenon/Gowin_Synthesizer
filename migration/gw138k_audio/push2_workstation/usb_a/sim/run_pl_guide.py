#!/usr/bin/env python3
"""Production RTL guide/MMIO regression; no hardware or generated stubs.

The existing workstation frozen Prj1 supplies the unchanged MIDI decoder,
CDC, audio FIFO and font. Pass --baseline when that accepted build lives in a
separate checkout. The test records the exact source hashes used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT.parent / 'results' /
                        'workstation_20260911_174045_306332' / 'Prj1')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    sources = [
        ROOT / 'rtl/push2_usb_a_control.sv',
        ROOT / 'rtl/audio/push2_controls.sv',
        ROOT / 'rtl/display_data/push2_surface_pixels.sv',
        *[ROOT / 'rtl/push2' / name for name in (
            'push2_playlist_hold.sv', 'push2_song_menu.sv', 'push2_score_guide.sv',
            'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')],
        *[args.baseline / name for name in (
            'src/migration/gw138k_stream_cdc.sv',
            'src/usb_host/gw138k_usb_event_fifo.v',
            'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v')],
        ROOT / 'sim/tb_pl_guide.sv',
    ]
    for source in sources:
        if not source.is_file():
            parser.error(f'missing production RTL: {source}; pass --baseline Prj1')
    out = args.out or Path(tempfile.mkdtemp(prefix='pl-guide-'))
    out.mkdir(parents=True, exist_ok=True)
    passed = False
    try:
        command = ['iverilog', '-g2012', '-s', 'tb_pl_guide', '-o', str(out / 'test'),
                   *map(str, sources)]
        for name, cmd in [('compile', command), ('test', ['vvp', str(out / 'test')])]:
            result = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=120)
            (out / (name + '.log')).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f'{name} failed:\n{(result.stdout + result.stderr)[-6000:]}')
            if name == 'test':
                print(result.stdout.strip())
        passed = True
    finally:
        (out / 'verification.json').write_text(json.dumps({
            'passed': passed, 'hardware_tested': False,
            'inputs': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in [Path(__file__), *sources]},
        }, indent=2) + '\n')
        print(out)


if __name__ == '__main__':
    main()
