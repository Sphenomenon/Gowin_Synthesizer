#!/usr/bin/env python3
"""Live USB/attach RTL against accepted full83 audio dependencies; no board I/O.

This is a subsystem simulation, not a replacement for the complete workstation
builder or its CNN/DDR acceptance checks. Frozen inputs are never modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT / 'results/song_guide_full83_20261006_203125_607466/Prj1')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--event-reference', type=Path, help='Compare old workstation routing and PCM on every audio cycle')
    args = parser.parse_args()
    base = args.baseline.resolve()
    out = args.out.resolve() if args.out else Path(tempfile.mkdtemp(prefix='workstation-attach-'))
    out.mkdir(parents=True, exist_ok=True)
    print(out, flush=True)
    audio = sorted((base / 'legacy/rtl/audio').glob('*.sv'), key=lambda p: (not p.name.endswith('_pkg.sv'), str(p)))
    sources = audio + [base / 'legacy/rtl/input/midi_stream_decoder.sv',
        base / 'src/ae350/gw138k_three_event_arbiter.sv',
        base / 'rtl/music/music_async_fifo.sv',
        base / 'src/migration/gw138k_stream_cdc.sv',
        base / 'src/usb_host/gw138k_usb_event_fifo.v',
        base / 'src/push2/push2_midi_rx.sv', base / 'src/video/video_font_5x7.v',
        ROOT / 'rtl/audio/gw138k_event_workstation.sv',
        ROOT / 'rtl/audio/gw138k_usb_lifecycle_merge.sv', ROOT / 'rtl/audio/push2_controls.sv',
        ROOT / 'rtl/push2_usb_a_control.sv', ROOT / 'rtl/display_data/push2_surface_pixels.sv']
    sources += sorted((ROOT / 'rtl/audio/scope_vec').glob('*.sv'))
    sources += sorted((ROOT / 'rtl/audio/delay_ddr').glob('*.sv'))
    sources += [ROOT / 'rtl/push2' / name for name in ('push2_playlist_hold.sv', 'push2_song_menu.sv',
        'push2_score_guide.sv', 'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')]
    vendor = ROOT / 'vendor/usb_host_fs_8fc3/firmware'
    staged = out / 'source'
    (staged / 'sim').mkdir(parents=True)
    inputs = sources + [Path(__file__), ROOT / 'rtl/ddr_address_map.vh']
    for name in ('firmware.c', 'gw25k_panel.h', 'sim/test_generic_midi.c',
                 'sim/tb_generic_midi.sv', 'sim/tb_workstation_attach.sv', 'sim/tb_usb_lifecycle_merge.sv',
                 'sim/test_gw25k_panel.c'):
        source = ROOT / name
        shutil.copy2(source, staged / name)
        inputs.append(source)
    if args.event_reference:
        from timing.event_reference import add_reference
        reference_module,reference_inputs=add_reference(staged,args.event_reference.resolve())
        sources.append(reference_module);inputs+=reference_inputs
    mmio_pipeline=base/'rtl/timing/gw138k_mmio_pipeline.sv'
    if mmio_pipeline.exists():
        from timing.mmio_fixture import attach
        sources.append(mmio_pipeline);inputs.extend([mmio_pipeline,ROOT/'sim/timing/mmio_fixture.py'])
        for name in ['tb_generic_midi.sv','tb_workstation_attach.sv']:
            fixture=staged/'sim'/name;fixture.write_text(attach(fixture.read_text()));inputs.append(fixture)
    inputs += [vendor / 'minlibc.h', *sorted((vendor / 'usb').glob('*.h'))]
    inputs += sorted((ROOT / 'rtl/audio/scope_vec/data').glob('*.mem'))
    inputs += [p for name in ('data', 'matlab') for p in (base / 'sim' / name).rglob('*') if p.is_file()]
    if not audio or any(not p.is_file() for p in inputs):
        parser.error('accepted audio baseline or live source is missing; pass --baseline Prj1')
    (out / 'rtl').symlink_to(ROOT / 'rtl', target_is_directory=True)
    for name in ('data', 'matlab'):
        (out / 'sim').mkdir(exist_ok=True)
        (out / 'sim' / name).symlink_to(base / 'sim' / name, target_is_directory=True)
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (out / 'inputs.json').write_text(json.dumps(hashes, indent=2) + '\n')
    commands = [('firmware_compile', ['gcc', '-std=c99', '-O2', '-fsanitize=address,undefined',
        '-fno-omit-frame-pointer', '-I' + str(vendor), '-I' + str(vendor / 'usb'),
        str(staged / 'sim/test_generic_midi.c'), '-o', str(out / 'generic_midi')]),
        ('firmware_test', [str(out / 'generic_midi'), str(out / 'generic_events.mem')])]
    for top in ('tb_generic_midi', 'tb_workstation_attach', 'tb_usb_lifecycle_merge'):
        commands += [(top + '_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', top, '--Mdir', str(out / top), '-I' + str(ROOT / 'rtl'),
            *map(str, sources), str(staged / 'sim' / (top + '.sv'))]),
            (top + '_test', [str(out / top / ('V' + top))])]
    commands += [('feedback_host_compile', ['gcc', '-std=c99', '-O1', '-g',
        '-Wall', '-Wextra', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
        '-I' + str(vendor), '-I' + str(vendor / 'usb'),
        str(staged / 'sim/test_gw25k_panel.c'), '-o', str(out / 'feedback_host')]),
        ('feedback_host_test', [str(out / 'feedback_host'), '--audio-feedback', str(out / 'audio_feedback.txt')])]
    passed = False
    try:
        for name, command in commands:
            with (out / (name + '.log')).open('w') as log:
                result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            print(name, result.returncode, flush=True)
            if result.returncode:
                raise RuntimeError((out / (name + '.log')).read_text()[-6000:])
            if name.endswith('_test'):
                print((out / (name + '.log')).read_text(), flush=True)
        if hashes != {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}:
            raise RuntimeError('simulation inputs changed during verification')
        passed = True
    finally:
        (out / 'verification.json').write_text(json.dumps(dict(passed=passed, hardware_tested=False,
            scope='USB MMIO/CDC/FIFO + real audio attach, cancellation, PANIC, Push/GW25K and 12 actual MMIO captures consumed by the production PL Host; no CNN/full-board build',
            actual_audio_feedback_captures=12, production_host_feedback_tested=passed,
            baseline=str(base), inputs='inputs.json',event_reference=str(args.event_reference) if args.event_reference else None), indent=2) + '\n')


if __name__ == '__main__':
    main()
