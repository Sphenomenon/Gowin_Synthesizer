#!/usr/bin/env python3
"""Numerical/pixel equivalence gates for full-workstation timing changes."""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='New staged Prj1 directory')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'results/song_guide_full83_20261006_203125_607466/Prj1')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    baseline = args.baseline.resolve()
    out = args.out.resolve() if args.out else ROOT / 'results' / datetime.now().strftime('timing_equivalence_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    print(out, flush=True)
    references = {}
    for name, rel in [('unified_oscillator_engine', 'legacy/rtl/audio/unified_oscillator_engine.sv'),
                      ('push2_song_screen', 'src/push2/push2_song_screen.sv'),
                      ('push2_surface_pixels', 'src/push2/push2_surface_pixels.sv')]:
        source = baseline / rel
        ref = out / (name + '_reference.sv')
        text = source.read_text()
        anchor = 'module ' + name
        if text.count(anchor) != 1:
            raise ValueError('unexpected reference module definition: ' + str(source))
        text = text.replace(anchor, anchor + '_reference', 1)
        if name == 'push2_surface_pixels':
            text = text.replace('push2_song_screen song_screen', 'push2_song_screen_reference song_screen')
        ref.write_text(text)
        references[name] = ref
    engine = project / 'legacy/rtl/audio/unified_oscillator_engine.sv'
    screen = project / 'src/push2/push2_song_screen.sv'
    audio = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                   key=lambda p: (not p.name.endswith('_pkg.sv'), p.name))
    tests = {
        'mix_quantizer': [engine],
        'push_decimal': [screen],
        'push_song_pixels': [screen, references['push2_song_screen'], project / 'src/video/video_font_5x7.v'],
        'engine_timing_ab': audio + [references['unified_oscillator_engine']],
        'push_surface_pipeline': [project / 'src/push2/push2_surface_pixels.sv', screen,
                                  references['push2_surface_pixels'], references['push2_song_screen'],
                                  project / 'src/video/video_font_5x7.v'],
    }
    pixel_sources = [project / rel for rel in [
        'src/usb_a/push2_usb_a_control.sv', 'src/push2/push2_surface_pixels.sv',
        'src/push2/push2_song_screen.sv', 'src/video/video_font_5x7.v',
        'src/push2/push2_controls.sv', 'src/push2/push2_midi_rx.sv',
        'src/push2/push2_lights.sv', 'src/push2/push2_led_tx.sv',
        'src/push2/push2_playlist_hold.sv', 'src/usb_a/push2_song_menu.sv',
        'src/usb_a/push2_score_guide.sv', 'src/usb_host/gw138k_usb_event_fifo.v',
        'src/migration/gw138k_stream_cdc.sv']]
    tests['push_pixel_mmio'] = pixel_sources + [references['push2_surface_pixels'], references['push2_song_screen']]
    pipeline=project/'rtl/timing/gw138k_mmio_pipeline.sv'
    if pipeline.exists():
        from mmio_fixture import pixel
        (out/'tb_push_pixel_mmio_bridge.sv').write_text(pixel((HERE/'tb_push_pixel_mmio.sv').read_text()))
        tests['push_pixel_mmio_bridge']=pixel_sources + [references['push2_surface_pixels'],references['push2_song_screen'],pipeline]
        tests['mmio_pipeline']=[pipeline,project/'src/usb_a/push2_screen_fifo_streamer.sv']
    inputs = {baseline / 'legacy/rtl/audio/unified_oscillator_engine.sv',
              baseline / 'src/push2/push2_song_screen.sv', baseline / 'src/push2/push2_surface_pixels.sv', Path(__file__).resolve()}
    for name, sources in tests.items():
        generated=out/('tb_'+name+'.sv')
        sources.append(generated if generated.exists() else HERE/('tb_'+name+'.sv'))
        inputs.update(sources)
    if pipeline.exists():inputs.update([HERE/'mmio_fixture.py',HERE/'tb_push_pixel_mmio.sv'])
    hashes = {str(p): sha(p) for p in sorted(inputs)}
    (out / 'inputs_sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    result = dict(passed=False, tests={}, hardware_tested=False, project=str(project), baseline=str(baseline))
    try:
        for name, sources in tests.items():
            top = 'tb_' + name
            binary = out / (name + '_obj') / ('V' + top)
            commands = [('compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                '--top-module', top, '--Mdir', str(binary.parent), '-I' + str(project), *map(str, sources)]),
                ('run', [str(binary)])]
            for step, command in commands:
                log = out / (name + '_' + step + '.log')
                with log.open('w') as stream:
                    completed = subprocess.run(command, cwd=project, stdout=stream,
                                               stderr=subprocess.STDOUT, timeout=600)
                if completed.returncode:
                    raise RuntimeError(log.read_text()[-7000:])
            text = (out / (name + '_run.log')).read_text()
            if 'PASS ' + name not in text:
                raise ValueError('missing equivalence PASS: ' + name)
            result['tests'][name] = 'passed'
            print(text, flush=True)
        if hashes != {str(p): sha(p) for p in sorted(inputs)}:
            raise ValueError('timing-test inputs changed during verification')
        result['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
