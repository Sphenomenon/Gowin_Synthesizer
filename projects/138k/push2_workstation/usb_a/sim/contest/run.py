#!/usr/bin/env python3
"""Offline contest witness: 32 live HDL voices at 48 kHz through existing DAC pins.

The current PT8211 serial format is explicitly not claimed as standard I2S.
No FPGA tools, board access, timing experiment or programming are performed.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from scipy.signal import find_peaks

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True, help='Prepared full83 Prj1')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    base = args.baseline.resolve()
    metadata = json.loads((base.parent / 'build_metadata.json').read_text())
    if metadata['cnn_source_policy'] != 'accepted_full83':
        parser.error('this functional witness requires accepted_full83 preparation')
    out = args.output.resolve() if args.output else ROOT / 'results' / datetime.now().strftime('contest_synth_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in (base / 'legacy/rtl/audio').glob('*.sv')
                     if p.name != 'unified_oscillator_engine.sv')
    sources += [base / 'legacy/rtl/input/midi_stream_decoder.sv',
                base / 'src/ae350/gw138k_three_event_arbiter.sv',
                base / 'rtl/music/music_async_fifo.sv',
                ROOT / 'rtl/audio/unified_oscillator_engine.sv',
                ROOT / 'rtl/audio/gw138k_event_workstation.sv',
                base / 'src/audio/pt8211_tx.v', base / 'src/audio/pt8211_observer.v']
    sources += sorted((ROOT / 'rtl/audio/scope_vec').glob('*.sv'))
    sources += sorted((ROOT / 'rtl/control').glob('*.sv'))
    sources += sorted((ROOT / 'rtl/audio/delay_ddr').glob('*.sv'))
    sources += [HERE / 'tb_realtime_synth.sv']
    inputs = sources + [Path(__file__).resolve(), ROOT / 'rtl/ddr_address_map.vh',
                       base.parent / 'build_metadata.json', base.parent / 'workstation_inputs.json']
    for folder in (base / 'sim/data', base / 'sim/matlab', ROOT / 'rtl/audio/scope_vec/data'):
        inputs += [p for p in folder.rglob('*') if p.is_file()]
    hashes = {str(p): digest(p) for p in inputs}
    (out / 'inputs_sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    manifest = json.loads((base.parent / 'workstation_inputs.json').read_text())
    for p in inputs:
        if p.is_relative_to(base):
            rel = p.relative_to(base).as_posix()
            if rel in manifest and digest(p) != manifest[rel]:
                raise RuntimeError('prepared input drift: ' + rel)
    result = dict(passed=False, hardware_tested=False, synthesis_run=False, pnr_run=False,
                  baseline=str(base), scope='current HDL synth + existing serial DAC witness',
                  standard_i2s_satisfied=False, sensor_to_analog_latency_measured=False,
                  sustained_hardware_timing_proven=False, inputs='inputs_sha256.json')
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_realtime_synth', '--Mdir', str(out / 'obj'),
                   '-I' + str(ROOT / 'rtl'), *map(str, sources)]
        with (out / 'compile.log').open('w') as log:
            subprocess.run(command, cwd=base, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        # Reuse prepared ROM data without writing runtime artifacts into it.
        (out / 'sim').mkdir(exist_ok=True)
        for name in ('data', 'matlab'):
            link = out / 'sim' / name
            if not link.exists():
                link.symlink_to(base / 'sim' / name, target_is_directory=True)
        if not (out / 'rtl').exists():
            (out / 'rtl').symlink_to(ROOT / 'rtl', target_is_directory=True)
        text = subprocess.run([str(out / 'obj/Vtb_realtime_synth')], cwd=out,
                              capture_output=True, text=True, timeout=300)
        (out / 'test.log').write_text(text.stdout + text.stderr)
        if text.returncode or 'PASS realtime_synth' not in text.stdout:
            raise RuntimeError((text.stdout + text.stderr)[-6000:])
        pcm = np.loadtxt(out / 'serial_pcm16.txt', dtype=np.int32)
        if pcm.shape != (32768, 2) or not np.array_equal(pcm[:, 0], pcm[:, 1]):
            raise RuntimeError('serial capture shape or stereo reconstruction differs')
        samples = pcm[:, 0].astype(float)
        if np.any(np.abs(samples) >= 32767):
            raise RuntimeError('serial PCM clipped')
        spectrum = np.abs(np.fft.rfft((samples - samples.mean()) * np.hanning(len(samples))))
        hz = np.fft.rfftfreq(len(samples), 1 / 48000)
        peaks, _ = find_peaks(spectrum)
        notes = []
        used = set()
        for note in range(60, 92):
            expected = 440 * 2 ** ((note - 69) / 12)
            candidates = peaks[np.abs(hz[peaks] - expected) <= 3]
            if not len(candidates):
                raise RuntimeError(f'no independent local maximum for MIDI {note}')
            index = int(candidates[np.argmax(spectrum[candidates])])
            relative_db = float(20 * np.log10(spectrum[index] / spectrum.max()))
            neighborhood = spectrum[max(1, index - 12):index + 13]
            floor = max(float(np.median(neighborhood)), 1e-12)
            prominence_db = float(20 * np.log10(spectrum[index] / floor))
            if index in used or relative_db < -40 or prominence_db < 15:
                raise RuntimeError(f'weak/non-independent peak MIDI {note}: {relative_db}, {prominence_db}')
            used.add(index)
            notes.append(dict(midi=note, expected_hz=expected, observed_hz=float(hz[index]),
                              relative_db=relative_db, local_prominence_db=prominence_db))
        result.update(sample_rate_hz=48000, active_audible_voices=32,
                      oscillator_samples_per_second=32 * 48000,
                      oscillator_count_basis='one independent phase/step/envelope voice per fundamental; mode A',
                      spectrum_resolution_hz=48000 / len(samples), peaks=notes,
                      frame_cycles=1600, input_scope='internal CPU event port; no USB/sensor emulation')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
        db = 20 * np.log10(np.maximum(spectrum / spectrum.max(), 1e-7))
        ax.plot(hz, db, linewidth=0.8)
        ax.scatter([n['observed_hz'] for n in notes], [n['relative_db'] for n in notes], s=15, color='darkred')
        ax.set(xlim=(220, 1650), ylim=(-90, 5), xlabel='Frequency (Hz)', ylabel='Relative level (dB)',
               title='32 live synthesized voices / 48 kHz / reconstructed PT8211 PCM16')
        ax.grid(alpha=0.25)
        fig.savefig(out / 'spectrum.png', dpi=160)
        plt.close(fig)
        if hashes != {str(p): digest(p) for p in inputs}:
            raise RuntimeError('inputs changed during verification')
        result['passed'] = True
        print(text.stdout.strip())
        print('PASS 32 distinct spectral peaks; nominal throughput 1536000 oscillator-samples/s')
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
        print(out, flush=True)


if __name__ == '__main__':
    main()
