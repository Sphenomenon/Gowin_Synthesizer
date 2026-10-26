"""Decode the temporary 64-bit whole-workstation GAO capture offline."""

from collections import Counter
from pathlib import Path
import argparse
import csv
import hashlib
import json
import runpy


SIGNALS = runpy.run_path(str(Path(__file__).with_name('prepare_workstation_jtag.py')))['SIGNALS']
MEMORY_FLAGS = ('ddr_calibrated', 'bist_done', 'bist_failed', 'front_valid',
                'fetch_arbiter_or_shared_load_fault', 'underrun_seen',
                'ddr_pll_locked', 'video_pll_locked')
VIDEO_FLAGS = ('hpd', 'video_locked', 'pixel_reset_released', 'scanout_reset_released',
               'serializer_reset_asserted', 'measurement_valid')


def decode(source):
    source = Path(source)
    records = list(csv.reader(source.read_text().splitlines(), skipinitialspace=True))
    header_index = next((index for index, row in enumerate(records)
                         if row and row[0].startswith('time unit:')), None)
    if header_index is None:
        raise ValueError('GAO CSV header missing')
    header = [value.strip() for value in records[header_index]]
    if header[-1] == '':
        header.pop()
    if header[1:] != list(SIGNALS):
        raise ValueError('GAO CSV does not match the configured 64-bit observation')
    samples = []
    for row in records[header_index + 1:]:
        if not row:
            continue
        values = [value.strip() for value in row]
        if values[-1] == '':
            values.pop()
        if len(values) != len(header) or any(value not in ('0', '1') for value in values[1:]):
            raise ValueError('GAO sample has missing, non-binary or extra values')
        if int(values[0]) != len(samples):
            raise ValueError('GAO sample indices are not contiguous')
        samples.append(dict(zip(SIGNALS, map(int, values[1:]))))
    if len(samples) != 1024:
        raise ValueError('expected exactly 1024 GAO samples')

    def word(sample, prefix, low, width):
        return sum(sample[f'{prefix}[{bit}]'] << (bit - low) for bit in range(low, low + width))

    def snapshot(sample):
        memory = word(sample, 'memory_flags', 0, 8)
        video = word(sample, 'video_diagnostics', 8, 6)
        return dict(reset_released=bool(sample['reset_n']), memory_flags_hex=f'0x{memory:02X}',
                    memory_flags={name: bool(memory & (1 << bit)) for bit, name in enumerate(MEMORY_FLAGS)},
                    video_flags_hex=f'0x{video:02X}',
                    video_flags={name: bool(video & (1 << bit)) for bit, name in enumerate(VIDEO_FLAGS)},
                    pixel_blocks_per_window=word(sample, 'video_diagnostics', 16, 16),
                    vblank_low8=word(sample, 'video_diagnostics', 32, 8),
                    rendered_frames_low8=word(sample, 'video_diagnostics', 64, 8),
                    underruns_low8=word(sample, 'video_diagnostics', 96, 8),
                    audio_reset_released=bool(sample['u_runtime/flags_sync[1]']),
                    audio_pll_locked=bool(sample['u_runtime/flags_sync[0]']),
                    sample_gray_low4=word(sample, 'u_runtime/sample_sync', 0, 4),
                    uart_state=word(sample, 'u_runtime/state', 0, 2),
                    uart_tx=sample['debug_uart_tx_d'])

    signals = {}
    for name in SIGNALS:
        values = [sample[name] for sample in samples]
        signals[name] = dict(values=dict(Counter(map(str, values))),
                             transitions=sum(previous != current for previous, current in zip(values, values[1:])))
    return dict(source=str(source.resolve()), csv_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                samples=len(samples), signals=signals, first=snapshot(samples[0]), last=snapshot(samples[-1]),
                reset_released_throughout=all(sample['reset_n'] for sample in samples),
                root_cause_confirmed=False,
                limitations=['CSV indices are samples, not independently measured microseconds.',
                             'Counter projections are low 8 bits and wrap; use separated captures to assess progress.',
                             'Audio Gray low bits are not a binary sample total.',
                             'CSV decoding alone does not establish bitstream identity or successful live RAM reads.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = decode(args.capture)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: result[name] for name in ('samples', 'first', 'last')}, indent=2))
