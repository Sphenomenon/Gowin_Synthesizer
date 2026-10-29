#!/usr/bin/env python3
"""Generate an unselected dual-rate room bank from the locked48k geometry."""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import math

from generate_room_preset import preset as legacy_preset

ROOT = Path(__file__).resolve().parents[1]
LEGACY_GENERATOR_SHA256 = '87da227eb075569db4e80e2537fd224f42f3c3fed3ed7dadf593e244718a63c6'
Q31 = 1 << 31


def verify_legacy_generator(path=None):
    source = Path(path) if path is not None else Path(__file__).with_name('generate_room_preset.py')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != LEGACY_GENERATOR_SHA256:
        raise ValueError('legacy room generator identity changed; review geometry before regeneration')
    return digest


def choose_fdn_lengths(original, sample_rate):
    if sample_rate == 48000:
        return list(original)
    ideals = [length * sample_rate / 48000 for length in original]
    centers = [round(value) for value in ideals]
    choices = []
    for values in itertools.product(*(range(center - 2, center + 3) for center in centers)):
        if any(value <= 0 or value > capacity for value, capacity in zip(values, original)):
            continue
        if any(math.gcd(a, b) != 1 for a, b in itertools.combinations(values, 2)):
            continue
        errors = [abs(value - ideal) for value, ideal in zip(values, ideals)]
        choices.append((sum(error * error for error in errors), max(errors), values))
    if not choices:
        raise ValueError('no bounded coprime FDN bank')
    return list(min(choices)[2])


def damping_cutoff_hz(alpha, sample_rate):
    cosine = (-1 + 4 * alpha - alpha * alpha) / (2 * alpha)
    return math.acos(cosine) * sample_rate / (2 * math.pi)


def compile_preset():
    legacy_hash = verify_legacy_generator()
    base = legacy_preset()
    source = base['source_m']
    listener = base['listener_m']
    ears = [(listener[0] - base['ear_spacing_m'] / 2, listener[1], listener[2]),
            (listener[0] + base['ear_spacing_m'] / 2, listener[1], listener[2])]
    direct = math.dist(source, listener)
    banks = {}
    for sample_rate in (48000, 44100):
        taps = []
        for old in base['taps']:
            wall, ear = old['wall'], old['ear']
            axis = wall // 2
            image = list(source)
            image[axis] = -source[axis] if wall % 2 == 0 else 2 * base['room_m'][axis] - source[axis]
            distance = math.dist(image, ears[ear])
            seconds = (distance - direct) / base['speed_of_sound']
            delay = round(seconds * sample_rate)
            if not 0 < delay < 2048:
                raise ValueError('early tap exceeds retained48k storage')
            taps.append(dict(wall=wall, ear=ear, delay=delay, gain_q15=old['gain_q15'],
                             ideal_delay_samples=seconds * sample_rate,
                             quantization_error_seconds=delay / sample_rate - seconds))
        if sample_rate == 48000 and any(
                {key: tap[key] for key in ('wall', 'ear', 'delay', 'gain_q15')} != old
                for tap, old in zip(taps, base['taps'])):
            raise ValueError('48k geometry failed to reproduce legacy taps')
        lengths = choose_fdn_lengths(base['fdn_delays'], sample_rate)
        alpha = 0.5 ** (48000 / sample_rate)
        alpha_q31 = round(alpha * Q31)
        input_q31 = Q31 - alpha_q31
        quantized_alpha = alpha_q31 / Q31
        banks[str(sample_rate)] = dict(
            sample_rate=sample_rate, taps=taps, fdn_lengths=lengths,
            fdn_ideal_samples=[value * sample_rate / 48000 for value in base['fdn_delays']],
            fdn_time_error_seconds=[value / sample_rate - old / 48000
                                    for value, old in zip(lengths, base['fdn_delays'])],
            damping=dict(method='matched continuous-time pole, preserving half-life; not exact frequency warping',
                         ideal_alpha=alpha, old_q31=alpha_q31, input_q31=input_q31,
                         quantized_alpha=quantized_alpha,
                         coefficient_error=quantized_alpha-alpha,
                         half_life_seconds=math.log(0.5)/(sample_rate*math.log(quantized_alpha)),
                         cutoff_hz=damping_cutoff_hz(quantized_alpha,sample_rate)),
            loop_gain_numerator=7,loop_gain_denominator=8)
    return dict(schema=1,source_policy='Versioned independent coefficient bank; old generator/preset unchanged; not selected by any profile.',
                legacy_generator_sha256=legacy_hash,source_geometry={key:base[key] for key in
                    ('speed_of_sound','room_m','source_m','listener_m','ear_spacing_m')},
                storage=dict(early_words=2048,fdn_words=base['fdn_delays']),
                fdn_selection='Minimize squared sample error within +/-2 of nearest; pairwise-coprime; tie by max error then tuple.',
                damping_q_fraction=31,banks=banks)


def header(data):
    lines=['// Generated by tools/generate_runtime_room_preset.py; independent unselected bank.']
    for field,name in [('delay','runtime_room_early_delay'),('gain_q15','runtime_room_early_gain')]:
        lines += [f'function automatic [15:0] {name}(input rate_44100, input [3:0] tap);',
                  '  case(tap)']
        for index in range(12):
            a=data['banks']['48000']['taps'][index][field]
            b=data['banks']['44100']['taps'][index][field]
            lines.append(f"    4'd{index}: {name}=rate_44100 ? 16'd{b} : 16'd{a};")
        lines += [f"    default: {name}=16'd0;",'  endcase','endfunction']
    lines += ['function automatic [11:0] runtime_room_fdn_length(input rate_44100, input [1:0] lane);',
              '  case(lane)']
    for lane in range(4):
        a=data['banks']['48000']['fdn_lengths'][lane];b=data['banks']['44100']['fdn_lengths'][lane]
        lines.append(f"    2'd{lane}: runtime_room_fdn_length=rate_44100 ? 12'd{b} : 12'd{a};")
    lines += ["    default: runtime_room_fdn_length=12'd1;",'  endcase','endfunction']
    for rate,name in [('48000','48'),('44100','44')]:
        d=data['banks'][rate]['damping']
        lines += [f"localparam logic signed [31:0] RUNTIME_ROOM_ALPHA_{name}=32'sd{d['old_q31']};",
                  f"localparam logic signed [31:0] RUNTIME_ROOM_INPUT_{name}=32'sd{d['input_q31']};"]
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    data=compile_preset()
    outputs={ROOT/'rtl/audio/runtime_spatial_room_preset.json':json.dumps(data,indent=2)+'\n',
             ROOT/'rtl/audio/runtime_spatial_room_preset.svh':header(data)}
    for path,text in outputs.items():
        if args.check:
            if path.read_text()!=text:
                raise ValueError('runtime room bank is stale: '+str(path))
        else:
            path.write_text(text)
    print(json.dumps({rate:dict(fdn=bank['fdn_lengths'],damping=bank['damping'])
                      for rate,bank in data['banks'].items()},indent=2))


if __name__=='__main__':main()
