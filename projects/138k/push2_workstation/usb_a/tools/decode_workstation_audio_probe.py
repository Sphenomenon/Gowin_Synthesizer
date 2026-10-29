#!/usr/bin/env python3
"""Read an800-bit GAO CSV; never connects to or controls a board."""
import argparse
import csv
import json
from pathlib import Path

from workstation_audio_probe import load_config, ROOT, sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode_words(words, config):
    require(len(words) == 25 and words[0] == int(config['debug_signature'], 16), 'Wrong APB1 signature or width')
    sample = dict(zip(config['debug_words_low_first'], words))
    status = words[2]
    bits = {name: bool(status & (1 << bit)) for name, bit in config['status_bits'].items()}
    sample['decoded_status'] = bits
    required = ('ready', 'active_valid', 'audio_reset_released', 'raw48_qualified', 'raw44_qualified', 'raw48_present', 'raw44_present',
                'selected_qualified', 'prefill_sync', 'running_sync', 'snapshot_valid', 'probe_complete')
    forbidden = ('busy', 'fault', 'active44', 'quiesce', 'transaction_mute', 'flush', 'serial_quiet_sync', 'probe_error')
    require(all(bits[name] for name in required) and not any(bits[name] for name in forbidden), 'Not a complete, valid, running, unflushed final48k observation')
    require((status >> 24) & 15 == 8, 'Probe FSM is not COMPLETE')
    require(words[3] == 2 and words[7:12] == [1, 2, 2, 0, 0], 'Wrong committed epoch, completion/accept/apply/error counts')
    require(words[12] > 0 and words[14] == 2 and words[15:17] == [0, 0], 'Final snapshot is empty, stale, or contains serializer errors')
    flags = words[17]
    require(flags & (1 << 5) and not flags & ((1 << 4) | (1 << 3) | (1 << 6)), 'Snapshot has no physical complete frame, wrong mode/error, or internal mute')
    require(words[18] > 0 and words[19] == 1, 'No completed atomic snapshots or wrong DCS select/fault/reject status')
    require(all(value > 0 for value in words[20:23]), 'A retained epoch has no complete physical frames')
    for index, nominal in [(4, 12288), (5, 16934.4), (6, 12288), (23, 12288), (24, 16934.4)]:
        require(abs(words[index] - nominal) <= nominal * .002 + 4, 'Measured source/selected rate outside2000ppm plus4edge CDC quantization: word' + str(index))
    sample['scope'] = 'Digital clock/transaction and zero-PCM physical serializer completion; no analog/DAC lock acceptance'
    return sample


def decode(path, config=None):
    config = load_config(ROOT) if config is None else config
    rows = list(csv.reader(Path(path).read_text().splitlines()))
    data = next((i for i, row in enumerate(rows) if row == ['Data:']), None)
    require(data is not None and len(rows) > data + 2, 'No GAO Data section')
    require(len(rows[data+1]) == 2 and rows[data+1][1].strip() == 'audio_probe_debug[799:0]', 'Unexpected GAO bus')
    samples = []
    for row in rows[data+2:]:
        if not row:
            continue
        require(len(row) == 2, 'Unexpected GAO sample columns')
        value = int(row[1].strip(), 16)
        require(value.bit_length() <= 800, 'GAO sample exceeds800bits')
        samples.append(decode_words([(value >> (32*i)) & 0xffffffff for i in range(25)], config))
    require(len(samples) == 128, 'Expected128 GAO samples')
    heartbeats = [sample['reference_heartbeat'] for sample in samples]
    deltas = [(b-a) & 0xffffffff for a, b in zip(heartbeats, heartbeats[1:])]
    require(sum(delta == 1 for delta in deltas) >= 126, 'Heartbeat does not prove a live consecutive50MHz capture')
    return dict(passed=True, source=str(Path(path).resolve()), sha256=sha(path), sample_count=len(samples),
                samples_with_consecutive_heartbeat=sum(delta == 1 for delta in deltas),
                latest=max(samples, key=lambda sample: (sample['snapshot_completed_frames'], sample['reference_heartbeat'])))


def self_test():
    config = load_config(ROOT)
    words = [0] * 25
    words[0] = 0x41504231
    for name in ('ready', 'active_valid', 'audio_reset_released', 'raw48_qualified', 'raw44_qualified', 'raw48_present', 'raw44_present',
                 'selected_qualified', 'prefill_sync', 'running_sync', 'snapshot_valid', 'probe_complete'):
        words[2] |= 1 << config['status_bits'][name]
    words[2] |= 8 << 24
    words[3:12] = [2, 12288, 16934, 12288, 1, 2, 2, 0, 0]
    words[12:25] = [500, 499, 2, 0, 0, 0x26, 100, 1, 300, 300, 500, 12288, 16934]
    decode_words(words, config)
    rejected = []
    for index, bit, label in [(2, 7, 'flush'), (17, 4, 'physical_frame_error')]:
        changed = list(words); changed[index] |= 1 << bit
        try: decode_words(changed, config)
        except ValueError: rejected.append(label)
    changed = list(words); changed[14] = 1
    try: decode_words(changed, config)
    except ValueError: rejected.append('stale_epoch')
    require(len(rejected) == 3, 'Decoder failed to reject invalid observation')
    return dict(passed=True, rejected=rejected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', nargs='?', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    try:
        if args.self_test:
            result = self_test()
        else:
            require(args.csv is not None, 'Specify CSV or --self-test')
            result = decode(args.csv)
    except (OSError, ValueError, KeyError, IndexError) as error:
        parser.exit(2, 'Probe capture rejected: ' + str(error) + '\n')
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.json:
        args.json.write_text(text)
    print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
