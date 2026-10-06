#!/usr/bin/env python3
"""Validate routed structures behind targeted clk50 mailbox/Gray/level CDC exceptions."""
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
              'errors': [], 'scope': 'song-command mailbox, TF/score/playlist Gray pointers and audio diagnostics; not overall timing closure'}
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
        gray_checks = {}
        for instance, read, write, meta_read, meta_write, second_read, second_write, msb in [
            ('u_tf_audio/u_pcm_cdc', 'rd_gray', 'wr_gray', 'rd_gray_w1', 'wr_gray_r1', 'rd_gray_w2', 'wr_gray_r2', 4),
            ('u_score_push_cdc', 'read_gray', 'write_gray', 'read_gray_meta', 'write_gray_meta', 'read_gray_sync', 'write_gray_sync', 2),
            ('u_playlist_bridge/fifo', 'read_gray', 'write_gray', 'read_gray_meta', 'write_gray_meta', 'read_gray_sync', 'write_gray_sync', 2),
        ]:
            for gray, meta, second, binary in [
                    (read, meta_read, second_read, 'rd_bin' if read == 'rd_gray' else 'read_binary'),
                    (write, meta_write, second_write, 'wr_bin' if write == 'wr_gray' else 'write_binary')]:
                targets = {n: ports for n, (kind, ports) in design.cells.items()
                           if n.startswith(instance + '/' + meta + '_') and kind.startswith('DFF')}
                if len(targets) != msb + 1:
                    raise ValueError(f'{instance}/{meta}: retained pointer width {len(targets)} != {msb+1}')
                bus_flights = []
                stages = []
                for name, port in targets.items():
                    source, pin = design.drivers[port['D']]
                    kind, origin = design.cells[source]
                    if not (kind.startswith('DFF') and pin == 'Q' and origin['CLK'] != port['CLK'] and
                            (source.startswith(instance + '/' + gray + '_') or
                             source.startswith(instance + '/' + binary + '_' + str(msb) + '_'))):
                        raise ValueError(f'{name}: Gray bus no longer comes from registered source/aliased MSB')
                    successors = [(n, ports) for n, (kind, ports) in design.cells.items()
                                  if n.startswith(instance + '/' + second + '_') and kind.startswith('DFF')
                                  and ports['D'] == port['Q'] and ports['CLK'] == port['CLK']]
                    if len(successors) != 1:
                        raise ValueError(f'{name}: missing unique second same-clock Gray synchronizer')
                    flight = design.arc(source, 'CLK', 'Q') + design.route(source + '/Q', name + '/D')
                    if flight > 10:
                        raise ValueError(f'{name}: Gray source flight {flight} exceeds 10ns')
                    bus_flights.append(flight)
                    stages.append([source, name, successors[0][0]])
                gray_checks[instance + '/' + gray] = {
                    'pointer_bits': len(targets), 'maximum_flight_ns': max(bus_flights),
                    'bit_chains': stages, 'aliased_binary_msb_only': msb,
                }
        levels = {}
        for first, second in [('format_meta', 'format_sync'), ('source_meta', 'source_sync')]:
            def level(name):
                hits = [(n, port) for n, (kind, port) in design.cells.items()
                        if n.startswith('u_music/' + name + '_') and kind.startswith('DFF')]
                if len(hits) != 1:
                    raise ValueError(f'{name}: expected exactly one diagnostic synchronizer')
                return hits[0]
            a_name, a = level(first)
            b_name, b = level(second)
            source, pin = design.drivers[a['D']]
            _, origin = design.cells[source]
            if (pin != 'Q' or origin['CLK'] == a['CLK'] or a['Q'] != b['D'] or
                    a['CLK'] != b['CLK'] or a['CLK'] != clocks['destination']):
                raise ValueError(f'{first}/{second}: broken audio->clk50 diagnostic crossing')
            consumers = [n for n, (kind, port) in design.cells.items()
                         if any(net == a['Q'] for key, net in port.items()
                                if design.drivers.get(net) != (n, key))]
            if consumers != [b_name]:
                raise ValueError(f'{first}: raw metastability stage drives other register consumers {consumers}')
            levels[first] = [source, a_name, b_name]
        result['gray_pointer_checks'] = gray_checks
        result['diagnostic_level_checks'] = levels
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
