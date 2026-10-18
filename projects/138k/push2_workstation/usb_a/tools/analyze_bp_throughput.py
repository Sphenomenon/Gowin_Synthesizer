#!/usr/bin/env python3
"""Analyze B138 dwell logs with the accepted active-wave OLS method; no board I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import re

WORDS = re.compile(r'^\s*([\d.]+)s bp=([0-9A-F]{8}) tf=([0-9A-F]{8}) nn=([0-9A-F]{8}) sd=([0-9A-F]{8})')
METHOD = 'ordinary-least-squares stream_wave vs timestamp, 48kHz/model E, waves 10..160, excluding capture/CQT/result-valid, >=100 frame span'


def analyze(path):
    points, segments, score_steps = [], [], []
    first_score = last_score = None
    reports = ignored = 0

    def finish():
        if len(points) < 3 or points[-1][1]-points[0][1] < 100:
            return
        mt = sum(t for t, _ in points)/len(points)
        mw = sum(w for _, w in points)/len(points)
        denominator = sum((t-mt)**2 for t, _ in points)
        if denominator <= 0:
            return
        slope = sum((t-mt)*(w-mw) for t, w in points)/denominator
        segments.append({'start': points[0][0], 'end': points[-1][0],
                         'frames': [points[0][1], points[-1][1]], 'n': len(points), 'ols_fps': slope})

    for line in path.read_text().splitlines():
        match = WORDS.match(line)
        if not match:
            continue
        elapsed = float(match[1])
        bp, tf, nn, sd = (int(match[i], 16) for i in range(2, 6))
        reports += 1
        if ((sd >> 2) & 15) != 14 or tf >> 16 != 48000:
            ignored += 1
            continue
        score = sd >> 24
        if first_score is None:
            first_score = score
        if last_score is not None and score != last_score:
            score_steps.append({'time': elapsed, 'from': last_score, 'to': score,
                                'delta_mod256': (score-last_score) & 255, 'raw_words': match[0].strip()})
        last_score = score
        wave = (bp >> 20) & 511
        state = (nn >> 26) & 63
        # result_valid overloads the frame field: never use it for restarts.
        if bp & 16 or state in (0, 1, 2) or not 10 <= wave <= 160:
            continue
        if points and wave < points[-1][1]:
            finish()
            points = []
        points.append((elapsed, wave))
    finish()
    return {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'method': METHOD,
            'cnn_segments': segments, 'mean_fps': sum(s['ols_fps'] for s in segments)/len(segments) if segments else None,
            'reports': reports, 'non48k_or_nonE_reports': ignored,
            'first_observed_score': first_score, 'score_steps': score_steps,
            'first_window_verified': False,
            'first_window_note': 'Score transitions alone do not prove song identity or a complete first window; correlate cold restart and window completion evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--acceptance-reference', type=Path,
                        default=Path(__file__).resolve().parents[1]/'reports/CNN_83_ACCEPTANCE_20261006.json')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('preserve previous analysis; choose a new output path')
    result = analyze(args.log)
    reference = json.loads(args.acceptance_reference.read_text())['verification_sources']['throughput']
    result['reference'] = {key: reference[key] for key in ('method', 'full82_mean_fps', 'full83_mean_fps')}
    assert result['method'] == reference['method'], 'acceptance method changed'
    if result['mean_fps'] is not None:
        for name in ('full82', 'full83'):
            fps = reference[name+'_mean_fps']
            result['delta_percent_from_'+name] = 100*(result['mean_fps']/fps-1)
        result['no_regression_from_full82_cache_reference'] = result['mean_fps'] >= reference['full82_mean_fps']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: result[key] for key in ('mean_fps', 'first_observed_score', 'cnn_segments')}, indent=2))


if __name__ == '__main__':
    main()
