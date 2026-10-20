#!/usr/bin/env python3
"""Validate routed structures behind targeted clk50 mailbox/Gray/level CDC exceptions."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys


def pointer_source(design, vo, net, receiver_clock, instance):
    """Unwrap only the existing FIFO local clear-to-zero LUT, proving its truth table.

    The pointer itself must still be a registered Gray bit. Clear gating does
    not change which pointer bits cross, and its delay remains in the flight.
    """
    source, pin = design.drivers[net]
    kind, ports = design.cells[source]
    if kind.startswith('DFF'):
        return source, pin, []
    if kind != 'LUT3' or pin != 'F':
        raise ValueError(f'{source}: pointer has unsupported combinational logic')
    inputs = {key: value for key, value in ports.items() if key.startswith('I')}
    data = []
    controls = {}
    for key, value in inputs.items():
        cell, output = design.drivers[value]
        cell_kind, origin = design.cells[cell]
        if not cell_kind.startswith('DFF') or output != 'Q':
            raise ValueError(f'{source}: clear gate input is not registered')
        if origin['CLK'] != receiver_clock:
            data.append((key, cell, output))
        else:
            match = re.fullmatch(re.escape(instance) + r'/clear_(wr|rd)_(meta|seen)_.*', cell)
            shared_tf = instance in ('u_tf_audio/u_path/u_capture_fifo', 'u_tf_audio/u_path/u_playback_fifo')
            alias = re.fullmatch(r'u_tf_audio/u_path/u_(capture|playback)_fifo/clear_(wr|rd)_(meta|seen)_.*', cell)
            if shared_tf and alias:
                # Both byte FIFOs share restart_toggle. Gowin merges their
                # identical first-stage clear samplers in the same clock.
                # The meta/seen D relation and gate truth table are still proved.
                controls[key] = ('shared_tf_restart', alias[3])
            elif match:
                controls[key] = match.groups()
            elif (instance == 'u_tf_audio/u_pcm_cdc' and
                  re.fullmatch(r'u_tf_audio/clear_meta_.*', cell)):
                # Identical audio-domain clear samplers are merged into the
                # parent's clear_meta by Gowin. Prove its relation to seen below.
                controls[key] = ('rd', 'meta')
            else:
                data.append((key, cell, output))
    if len(data) != 1 or len(controls) != 2:
        # The second synchronizer input is a same-clock first-stage register;
        # identify it only after proving the other two inputs are clear state.
        data = [(key, *design.drivers[value]) for key, value in inputs.items() if key not in controls]
    if len(data) != 1 or len(controls) != 2:
        raise ValueError(f'{source}: expected pointer plus two local clear inputs')
    domain = {value[0] for value in controls.values()}
    if len(domain) != 1 or {value[1] for value in controls.values()} != {'meta', 'seen'}:
        raise ValueError(f'{source}: clear gate controls do not form local meta/seen pair')
    meta_key = next(key for key, value in controls.items() if value[1] == 'meta')
    seen_key = next(key for key, value in controls.items() if value[1] == 'seen')
    meta_cell = design.drivers[inputs[meta_key]][0]
    seen_cell = design.drivers[inputs[seen_key]][0]
    if design.cells[seen_cell][1]['D'] != design.cells[meta_cell][1]['Q']:
        raise ValueError(f'{source}: clear seen does not sample the checked local meta')
    pattern = r'defparam\s+\\' + re.escape(source) + r"\s+\.INIT=8'h([0-9a-fA-F]+);"
    found = re.findall(pattern, vo)
    if len(found) != 1:
        raise ValueError(f'{source}: missing unambiguous clear LUT truth table')
    init = int(found[0], 16)
    control_bits = [int(key[1:]) for key in controls]
    data_bit = int(data[0][0][1:])
    for value in range(8):
        want = ((value >> data_bit) & 1) if ((value >> control_bits[0]) & 1) == ((value >> control_bits[1]) & 1) else 0
        if ((init >> value) & 1) != want:
            raise ValueError(f'{source}: clear LUT is not pointer when equal, zero when clearing')
    return data[0][1], data[0][2], [source]


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
        vo = files[1].read_text()
        design = RoutedDesign(files[0].read_text(), vo)
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
                    source, pin, gates = pointer_source(design, vo, port['D'], port['CLK'], instance)
                    kind, origin = design.cells[source]
                    if not (kind.startswith('DFF') and pin == 'Q' and origin['CLK'] != port['CLK'] and
                            (source.startswith(instance + '/' + gray + '_') or
                             source.startswith(instance + '/' + binary + '_' + str(msb) + '_'))):
                        raise ValueError(f'{name}: Gray bus no longer comes from registered source/aliased MSB')
                    successors = []
                    for target, (target_kind, target_ports) in design.cells.items():
                        if (target.startswith(instance + '/' + second + '_') and
                            target_kind.startswith('DFF') and target_ports['CLK'] == port['CLK']):
                            previous, previous_pin, _ = pointer_source(
                                design, vo, target_ports['D'], port['CLK'], instance)
                            if previous == name and previous_pin == 'Q':
                                successors.append((target, target_ports))
                    if len(successors) != 1:
                        raise ValueError(f'{name}: missing unique second same-clock Gray synchronizer')
                    flight = design.arc(source, 'CLK', 'Q')
                    last_pin = source + '/Q'
                    for gate in gates:
                        ports = design.cells[gate][1]
                        input_pin = next(key for key, value in ports.items()
                                         if key.startswith('I') and design.drivers[value] == (source, 'Q'))
                        flight += design.route(last_pin, gate + '/' + input_pin)
                        flight += design.arc(gate, input_pin, 'F')
                        last_pin = gate + '/F'
                    flight += design.route(last_pin, name + '/D')
                    if flight > 10:
                        raise ValueError(f'{name}: Gray source flight {flight} exceeds 10ns')
                    bus_flights.append(flight)
                    stages.append([source, name, successors[0][0]])
                gray_checks[instance + '/' + gray] = {
                    'pointer_bits': len(targets), 'maximum_flight_ns': max(bus_flights),
                    'bit_chains': stages, 'aliased_binary_msb_only': msb,
                    'local_clear_gates_truth_table_checked': True,
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
