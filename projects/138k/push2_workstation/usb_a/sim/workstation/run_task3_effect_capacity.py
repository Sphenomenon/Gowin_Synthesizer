#!/usr/bin/env python3
"""Compare source-bound LCD capacity evidence with optional stereo32 effects.

This is an offline integration decision, never a runtime budget grant or a
new wire protocol. Reproduce capacity first with run_task3_lcd_budget.py.
"""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FRAME_BYTES = 52
PAYLOAD_BYTES = 32
SAMPLE_RATE = 48000
PLANNING_HEADROOM_PERCENT = 20
REVIEWED_SOURCES = {
    'rtl/workstation/workstation_task3_lcd_phy.sv':
        'd2ba6cb9be0f1597fe700c1200643eb9654aa2b16d46c69ae2d4bf75c4ee82eb',
    'rtl/workstation/workstation_task3_pcm_block_rx.sv':
        'f99c22adf34e09c3593a04c7be7a91d5e9e7760fec7f2468d20f617b879c92d4',
    'rtl/workstation/workstation_task3_phone_window_tx.sv':
        'dad7e5da287f9fea61a962ee9016fdbb2fa280ad99a8b132a9b5b61fab91cdfc',
    'rtl/workstation/task3_paired_channels.vh':
        'aa1ec82c2a4a368fabce7e3c75ecbe166433d773ba2793c036946b35e390b73d',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_capacity(capacity):
    if not capacity.get('passed') or not capacity.get('source_unchanged'):
        raise ValueError('capacity run did not pass with unchanged sources')
    sources = [ROOT / ('rtl/workstation/workstation_task3_lcd_' + n + '.sv')
               for n in ('transport', 'phy')]
    sources += [Path(__file__).with_name(n) for n in
                ('tb_task3_lcd_budget.sv', 'run_task3_lcd_budget.py')]
    if capacity['source_sha256'] != {str(p): sha(p) for p in sources}:
        raise ValueError('capacity source identity changed')
    if capacity['M_clock_Hz'] != 50000000 or len(capacity['trials']) != 4:
        raise ValueError('capacity clock/matrix changed')
    transport = sources[0].read_text()
    for anchor in ('reg [415:0] tx_packet,rx_packet;', 'input wire [255:0] tx_payload_i,',
                   'tx_length_i<=32', 'if(tx_index==51)'):
        if transport.count(anchor) != 1:
            raise ValueError('capacity framing identity changed')
    # Reconcile each measured row with the independently retained raw log.
    records = []
    pattern = r'BUDGET_MODEL receiver=(\d+) packets=(\d+) payload_bytes=(\d+) elapsed_ns=(\d+) '
    for command in capacity['commands']:
        log = Path(command['log'])
        if command['exit_code'] or sha(log) != command['log_sha256']:
            raise ValueError('capacity command/log changed')
        records += [tuple(map(int, row)) for row in re.findall(pattern, log.read_text())]
    if len(records) != 8:
        raise ValueError('missing raw capacity rows')
    directions = {'M_to_W': [], 'W_to_M': []}
    for trial in capacity['trials']:
        if trial['W_clock_Hz'] not in (50000000, 1e9 / 22):
            raise ValueError('unexpected worker clock')
        if {r['receiver'] for r in trial['directions']} != {'M', 'W'}:
            raise ValueError('missing capacity direction')
        for row in trial['directions']:
            elapsed_ps = round(row['elapsed_model_ns'] * 1000)
            raw = (0 if row['receiver'] == 'M' else 1, row['packets'], row['payload_bytes'], elapsed_ps)
            if raw not in records:
                raise ValueError('capacity row disagrees with raw log')
            records.remove(raw)
            if row['packets'] != 1024 or row['payload_bytes'] != 32768 or elapsed_ps <= 0:
                raise ValueError('invalid capacity counts')
            pps = Fraction(row['packets'] * 10**12, elapsed_ps)
            if abs(float(pps) - row['simulated_business_packets_per_second']) > 1e-6:
                raise ValueError('capacity units disagree')
            if abs(float(pps * PAYLOAD_BYTES) - row['simulated_payload_Bps']) > 1e-6:
                raise ValueError('capacity payload units disagree')
            direction = 'W_to_M' if row['receiver'] == 'M' else 'M_to_W'
            directions[direction].append(dict(worker_clock_Hz=trial['W_clock_Hz'],
                receiver_ready=trial['receiver_ready'], packets_per_second=float(pps),
                business_wire_Bps=float(pps * FRAME_BYTES), payload_Bps=float(pps * PAYLOAD_BYTES)))
    return directions


def evaluate(capacity):
    for name, expected in REVIEWED_SOURCES.items():
        if sha(ROOT / name) != expected:
            raise ValueError('reviewed state/credit/window policy changed: ' + name)
    directions = verify_capacity(capacity)
    block_rx = (ROOT / 'rtl/workstation/workstation_task3_pcm_block_rx.sv').read_text()
    if len(re.findall(r'parameter integer CREDIT_BATCH=4\b', block_rx)) != 1:
        raise ValueError('block credit cadence changed')
    block_pps = SAMPLE_RATE // 6
    # A128-frame firmware block uses26 window5 frames and at least two
    # snapshot/commit exchanges. These are the maintained v3 lower bounds.
    phone_pps = Fraction(SAMPLE_RATE, 128) * (26 + 2)
    scenarios = []
    for name, phone, record, analysis in (
        ('paired_minimum', True, True, True),
        ('effects_only', False, False, False),
        ('phone_and_effects', True, False, False),
        ('phone_record_and_effects', True, True, False),
        ('phone_record_analysis_and_effects', True, True, True),
    ):
        for samples in ((0,) if name == 'paired_minimum' else (2, 3)):
            effects_pps = Fraction(SAMPLE_RATE, samples) if samples else Fraction(0)
            m = (phone_pps if phone else 0) + block_pps * (record + analysis) + effects_pps
            # Credit updates follow at least four consumed blocks. Budget up
            # to one update per four; delayed updates can coalesce. Initial
            # ARM/credit traffic remains additional,not part of this bound.
            w_floor = (phone_pps if phone else 0) + effects_pps
            w = w_floor + Fraction(block_pps, 4) * (record + analysis)
            rates = dict(M_to_W=float(m * FRAME_BYTES), W_to_M=float(w * FRAME_BYTES))
            floors = dict(M_to_W=float(m * FRAME_BYTES), W_to_M=float(w_floor * FRAME_BYTES))
            checks = {}
            usable_fraction = (100 - PLANNING_HEADROOM_PERCENT) / 100
            for direction, measured in directions.items():
                nominal = min(x['business_wire_Bps'] for x in measured if x['worker_clock_Hz'] == 50000000)
                stress = min(x['business_wire_Bps'] for x in measured)
                checks[direction] = dict(required_lower_bound_Bps=floors[direction],
                    with_block_credit_allowance_Bps=rates[direction],
                    nominal_model_Bps=nominal, all_tested_model_min_Bps=stress,
                    nominal_model_fits=rates[direction] <= nominal,
                    all_tested_models_fit=rates[direction] <= stress,
                    nominal_with_planning_headroom_fits=rates[direction] <= nominal * usable_fraction,
                    all_models_with_planning_headroom_fit=rates[direction] <= stress * usable_fraction)
            scenarios.append(dict(name=name, stereo32_samples_per_packet=samples,
                packet_assumption='no effects' if not samples else
                    '10-byte header/flags envelope;not an assigned wire format' if samples == 2 else
                    '8-byte token/index PCM-only floor;per-sample flags omitted,not a valid format',
                directions=checks, required_streams_retained=True,
                new_effect_business_admitted=False))
    # Conservative best-case state-residency floor, ignoring all phase waits,
    # CRC construction, packet gaps and maintenance: each nibble needs at
    # least5 receiver clocks to raise ACK,2 sender clocks to lower REQ,
    #2 receiver clocks to lower ACK and2 sender clocks before the next REQ.
    # Two nibbles plus the byte-to-byte TX_IDLE edge:14 receiver+9 sender
    # periods. At nominal50MHz this is460ns/byte,an intentionally loose upper
    # bound. Source-bound evidence is not a formal CDC or physical proof.
    byte_floor_ns = 14 * 20 + 9 * 20
    upper = 1e9 / byte_floor_ns
    all_lower = next(s for s in scenarios if s['name'] == 'phone_record_analysis_and_effects'
                     and s['stereo32_samples_per_packet'] == 3)
    return dict(directions=directions, scenarios=scenarios,
        planning_headroom_percent=PLANNING_HEADROOM_PERCENT,
        headroom_policy='Offline planning assumption,not measured jitter allowance or production admission.',
        nominal_state_residency=dict(byte_period_floor_ns=byte_floor_ns,
            raw_byte_rate_upper_bound=upper,
            all_streams_even_PCM_only_floor_exceeds_M_to_W_upper_bound=
                all_lower['directions']['M_to_W']['required_lower_bound_Bps'] > upper),
        credit_policy='Steady full-block allowance up to one credit frame per4 consumed blocks;delayed credits may coalesce. Distinct from the no-credit lower bound.',
        omitted_traffic='Initial caps/ARM,initial credits,recognition results,status,additional polling,downloads,retries and congestion headroom.',
        decision='Do not integrate optional remote reverb into unchanged paired-v3 transport. '
                 'The full simultaneous workload exceeds even the favorable source-based upper bound. '
                 'Retain local M effects and both fallbacks;never evict phone/recording or silently discard analysis to admit it.',
        physical_budget_authorized=False, protocol_extension_selected=False, hardware_tested=False)


def run(capacity_path, output):
    output.mkdir(parents=True, exist_ok=False)
    capacity = json.loads(capacity_path.read_text())
    result = evaluate(capacity)
    controls = []
    for name in ('failed_run', 'changed_source', 'payload_as_packets', 'wrong_direction', 'changed_elapsed'):
        broken = deepcopy(capacity)
        if name == 'failed_run':
            broken['passed'] = False
        elif name == 'changed_source':
            key = next(iter(broken['source_sha256']))
            broken['source_sha256'][key] = '0' * 64
        elif name == 'payload_as_packets':
            broken['trials'][0]['directions'][0]['simulated_business_packets_per_second'] *= 32
        elif name == 'wrong_direction':
            broken['trials'][0]['directions'][0]['receiver'] = 'W'
        else:
            broken['trials'][0]['directions'][0]['elapsed_model_ns'] *= .5
        try:
            evaluate(broken)
        except ValueError as error:
            controls.append(dict(name=name, rejected=True, reason=str(error)))
        else:
            raise ValueError('invalid evidence was accepted: ' + name)
    result.update(schema=1, passed=True, capacity_evidence=dict(path=str(capacity_path), sha256=sha(capacity_path)),
        negative_controls=controls, source_sha256={str(p.relative_to(ROOT)): sha(p) for p in
            (Path(__file__), *(ROOT / n for n in REVIEWED_SOURCES))})
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('passed', 'decision', 'nominal_state_residency')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capacity', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.capacity.resolve(), arguments.output.resolve())
