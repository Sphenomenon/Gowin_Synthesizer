#!/usr/bin/env python3
"""Validate the routed structure behind the narrow song-command CDC exceptions."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def audit(build):
    stage = build / 'Prj1'
    sys.path.insert(0, str(stage / 'scripts'))
    from check_video_pll_init import RoutedDesign
    pnr = stage / 'impl/pnr'
    files = [pnr / 'Prj1.sdf', pnr / 'Prj1.vo', stage / 'constraints/tang_mega_138k.sdc',
             stage / 'src/migration/gw138k_stream_cdc.sv']
    result = {'passed': False, 'structure_passed': False, 'hardware_tested': False,
              'errors': [], 'scope': 'song-command mailbox only; not overall timing closure'}
    try:
        design = RoutedDesign(files[0].read_text(), files[1].read_text())
        prefix = 'u_song_command_cdc/'

        def regs(name):
            return {n: ports for n, (kind, ports) in design.cells.items()
                    if n.startswith(prefix + name) and kind.startswith('DFF')}

        def one(name):
            matches = regs(name + '_')
            if len(matches) != 1:
                raise ValueError(f'{name}: expected exactly one register, found {len(matches)}')
            return next(iter(matches.items()))

        chains = {}
        clocks = {}
        for domain in ('source', 'destination'):
            stages = [one(f'{domain}_release_{i}') for i in range(3)]
            clocks[domain] = stages[0][1]['CLK']
            clear = stages[0][1]['CLEAR']
            if stages[0][1]['D'] != 'VCC':
                raise ValueError(f'{domain}: release chain does not start at constant 1')
            for i, (name, port) in enumerate(stages):
                if port['CLK'] != clocks[domain] or port['CLEAR'] != clear:
                    raise ValueError(f'{domain}: inconsistent local release clock/reset')
                if i and port['D'] != stages[i-1][1]['Q']:
                    raise ValueError(f'{domain}: broken release stage {i}')
            chains[domain] = [name for name, _ in stages]
        if clocks['source'] == clocks['destination']:
            raise ValueError('song-command clocks unexpectedly identical')
        synchronizers = {}
        for domain, first, second, source in [
                ('destination', 'req_meta', 'req_sync', 'request_toggle'),
                ('source', 'ack_meta', 'ack_sync', 'acknowledge_toggle')]:
            first_name, a = one(first)
            second_name, b = one(second)
            _, origin = one(source)
            if a['D'] != origin['Q'] or a['Q'] != b['D']:
                raise ValueError(f'{first}/{second}: broken asynchronous sampling chain')
            if a['CLK'] != b['CLK'] or a['CLK'] != clocks[domain] or a['CLK'] == origin['CLK']:
                raise ValueError(f'{first}/{second}: inconsistent clocks')
            synchronizers[first] = [first_name, second_name]
        _, settled = one('req_settled')
        _, sync = one('req_sync')
        if settled['D'] != sync['Q'] or settled['CLK'] != sync['CLK']:
            raise ValueError('held payload no longer has the extra request-settling stage')
        payload = regs('destination_data_')
        if len(payload) != 4:
            raise ValueError(f'expected four song index bits, found {len(payload)}')
        flights = []
        for name, port in payload.items():
            source, pin = design.drivers[port['D']]
            kind, origin = design.cells[source]
            if not (source.startswith(prefix + 'held_data_') and pin == 'Q' and
                    kind.startswith('DFF') and origin['CLK'] == clocks['source'] and
                    port['CLK'] == clocks['destination']):
                raise ValueError(f'{name}: no longer directly driven by held payload')
            flight = design.arc(source, 'CLK', 'Q') + design.route(source + '/Q', name + '/D')
            if flight > 20:
                raise ValueError(f'{name}: held-data flight {flight} exceeds 20ns')
            flights.append(flight)
        from build_full_song_85_clk50_timing import CDC_CONSTRAINTS
        sdc = files[2].read_text()
        commands = [line for line in CDC_CONSTRAINTS.splitlines() if line.startswith('set_')]
        result.update(structure_passed=True, local_release_chains=chains,
                      synchronizers=synchronizers, extra_request_settling_stage=True,
                      payload_bits=len(payload), maximum_payload_flight_ns=max(flights),
                      required_constraints_present=all(line in sdc for line in commands))
        result['evidence_sha256'] = {str(p.relative_to(build)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in files}
        result['passed'] = result['structure_passed'] and result['required_constraints_present']
    except (OSError, ValueError, KeyError, AssertionError) as exc:
        result['errors'].append(str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--structure-only', action='store_true',
                        help='diagnostic only: do not require new constraints in an old build')
    args = parser.parse_args()
    build = args.build.resolve()
    output = args.output or build / 'clk50_cdc_routed_audit.json'
    if output.exists():
        parser.error('preserve previous audit; choose a new --output')
    result = audit(build)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    if not result['structure_passed' if args.structure_only else 'passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
