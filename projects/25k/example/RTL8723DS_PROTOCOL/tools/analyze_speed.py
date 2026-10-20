#!/usr/bin/env python3
"""Summarize observed callback timing; gaps do not prove negotiated BLE parameters."""
import argparse
from collections import Counter
import json
import statistics


def summarize(report):
    assert report['passed'], 'Refuse to analyze a failed transfer'
    notifications = [n for n in report.get('notifications', []) if n['time'] >= 0]
    gaps = [b['time'] - a['time'] for a, b in zip(notifications, notifications[1:])]
    blocks = report['block_timings']
    bursts = []
    count = 0
    for i, _ in enumerate(notifications):
        if i and gaps[i - 1] >= .005:
            bursts.append(count)
            count = 0
        count += 1
    if count:
        bursts.append(count)
    return {
        'bytes_per_second': report['bytes_per_second'],
        'pcm_bytes': report['pcm_bytes'],
        'blocks': len(blocks),
        'mean_read_data_ms': statistics.mean(b['read_data_s'] for b in blocks) * 1000,
        'mean_write_ms': statistics.mean(report['write_seconds']) * 1000,
        'observed_notifications': len(notifications),
        'callback_gap_5ms_bins': dict(sorted(Counter(round(g * 1000 / 5) * 5 for g in gaps).items())),
        'burst_boundary_ms': 5,
        'mean_callbacks_per_burst': statistics.mean(bursts) if bursts else None,
        'scope': 'Host callback timing, not radio capture or proof of connection interval',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+')
    args = parser.parse_args()
    result = {}
    for path in args.reports:
        with open(path) as f:
            result[path] = summarize(json.load(f))
    print(json.dumps(result, indent=2))
