#!/usr/bin/env python3
"""Prove routed Gray synchronizers and the added TF diagnostic level receivers."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from audit_clk50_cdc_routes import pointer_source
from workstation_timing_constraints import constraints, gray_write_alias_constraints


def audit(build):
    stage = build / 'Prj1'
    sys.path.insert(0, str(stage / 'scripts'))
    from check_video_pll_init import RoutedDesign
    files = [stage / 'impl/pnr/Prj1.sdf', stage / 'impl/pnr/Prj1.vo',
             stage / 'constraints/tang_mega_138k.sdc', stage / 'src/migration/gw138k_stream_cdc.sv',
             stage / 'src/storage/tf_async_byte_fifo.v', stage / 'src/storage/tf_audio_ddr_path.v',
             stage/'rtl/timing/gw138k_level_cdc.sv',stage/'rtl/music/basic_pitch_workstation_link.sv']
    result = dict(passed=False, hardware_tested=False, mailbox={}, gray={}, levels={}, errors=[])
    try:
        vo = files[1].read_text()
        design = RoutedDesign(files[0].read_text(), vo)
        def registers(prefix):
            return {n: ports for n, (kind, ports) in design.cells.items()
                    if n.startswith(prefix) and kind.startswith('DFF')}
        def one(prefix):
            found = registers(prefix + '_')
            if len(found) != 1:
                raise ValueError(prefix + ': missing/ambiguous mailbox register')
            return next(iter(found.items()))
        prefix = 'u_song_command_cdc/'
        clocks, releases = {}, {}
        for domain in ('source', 'destination'):
            stages = [one(prefix + domain + '_release_' + str(i)) for i in range(3)]
            clock = stages[0][1]['CLK']
            clear = stages[0][1]['CLEAR']
            if stages[0][1]['D'] != 'VCC':
                raise ValueError(domain + ': local release chain no longer starts at 1')
            for i, (name, port) in enumerate(stages):
                if port['CLK'] != clock or port['CLEAR'] != clear or (i and port['D'] != stages[i-1][1]['Q']):
                    raise ValueError(domain + ': broken three-stage local reset release')
            clocks[domain] = clock
            releases[domain] = [name for name, _ in stages]
        if clocks['source'] == clocks['destination']:
            raise ValueError('song mailbox does not cross clocks')
        for domain, first, second, source in [
            ('destination', 'req_meta', 'req_sync', 'request_toggle'),
            ('source', 'ack_meta', 'ack_sync', 'acknowledge_toggle')]:
            _, a = one(prefix + first); _, b = one(prefix + second); _, origin = one(prefix + source)
            if a['D'] != origin['Q'] or a['Q'] != b['D'] or a['CLK'] != b['CLK'] or a['CLK'] != clocks[domain] or a['CLK'] == origin['CLK']:
                raise ValueError(first + ': broken mailbox toggle synchronizer')
        _, settled = one(prefix + 'req_settled'); _, sync = one(prefix + 'req_sync')
        if settled['D'] != sync['Q'] or settled['CLK'] != sync['CLK']:
            raise ValueError('song mailbox lost extra payload-settling stage')
        payload = registers(prefix + 'destination_data_')
        if len(payload) != 4:
            raise ValueError('song mailbox payload width changed')
        flights = []
        for name, port in payload.items():
            source, pin = design.drivers[port['D']]
            kind, origin = design.cells[source]
            if not (kind.startswith('DFF') and pin == 'Q' and source.startswith(prefix + 'held_data_') and
                    origin['CLK'] == clocks['source'] and port['CLK'] == clocks['destination']):
                raise ValueError(name + ': payload not directly held in source domain')
            flight = design.arc(source, 'CLK', 'Q') + design.route(source + '/Q', name + '/D')
            if flight > 20:
                raise ValueError(name + ': held payload exceeds 20ns')
            flights.append(flight)
        result['mailbox'] = dict(local_release_chains=releases, payload_bits=len(payload),
                                 maximum_payload_flight_ns=max(flights), extra_request_settling_stage=True)
        for instance, msb in [
            ('u_managed/u_audio/u_workstation/effects/delay_stage/u_write_fifo', 9),
            ('u_managed/u_audio/u_workstation/effects/delay_stage/u_read_fifo', 9),
            ('u_music/u_ddr_req_cdc', 4), ('u_music/u_ddr_rsp_cdc', 2),
            ('u_score_push_cdc', 2), ('u_playlist_bridge/fifo', 2),
            ('u_tf_audio/u_pcm_cdc', 4),
            ('u_tf_audio/u_path/u_capture_fifo', 12),
            ('u_tf_audio/u_path/u_playback_fifo', 12),
        ]:
            is_tf = instance.startswith('u_tf_audio/')
            for gray, meta, second, binary in [
                ('rd_gray', 'rd_gray_w1', 'rd_gray_w2', 'rd_bin') if is_tf else
                ('read_gray', 'read_gray_meta', 'read_gray_sync', 'read_binary'),
                ('wr_gray', 'wr_gray_r1', 'wr_gray_r2', 'wr_bin') if is_tf else
                ('write_gray', 'write_gray_meta', 'write_gray_sync', 'write_binary'),
            ]:
                targets = registers(instance + '/' + meta + '_')
                successors = registers(instance + '/' + second + '_')
                if len(targets) != msb + 1 or len(successors) != msb + 1:
                    raise ValueError(f'{instance}/{meta}: incomplete two-stage pointer width')
                flights, chains = [], []
                for name, port in targets.items():
                    source, pin, gates = pointer_source(design, vo, port['D'], port['CLK'], instance)
                    kind, origin = design.cells[source]
                    if not (kind.startswith('DFF') and pin == 'Q' and origin['CLK'] != port['CLK'] and
                            (source.startswith(instance + '/' + gray + '_') or
                             source.startswith(instance + '/' + binary + '_' + str(msb) + '_'))):
                        raise ValueError(f'{name}: nonregistered Gray source or unexpected binary bit')
                    matched = []
                    for dest, dest_port in successors.items():
                        previous, previous_pin, _ = pointer_source(design, vo, dest_port['D'], dest_port['CLK'], instance)
                        if previous == name and previous_pin == 'Q' and dest_port['CLK'] == port['CLK']:
                            matched.append(dest)
                    if len(matched) != 1:
                        raise ValueError(f'{name}: missing unique second synchronizer')
                    flight = design.arc(source, 'CLK', 'Q')
                    last = source + '/Q'
                    for gate in gates:
                        ports = design.cells[gate][1]
                        gate_pin = next(k for k, v in ports.items()
                                        if k.startswith('I') and design.drivers[v] == (source, 'Q'))
                        flight += design.route(last, gate + '/' + gate_pin) + design.arc(gate, gate_pin, 'F')
                        last = gate + '/F'
                    flight += design.route(last, name + '/D')
                    if flight > 10:
                        raise ValueError(f'{name}: pointer flight {flight} > 10ns')
                    flights.append(flight)
                    chains.append([source, name, matched[0]])
                result['gray'][instance + '/' + gray] = dict(pointer_bits=msb + 1,
                    maximum_flight_ns=max(flights), chains=chains, binary_alias_msb_only=True)
        # Only the first Q -> second D may consume a metastability stage.
        level_pairs=[('tf_format_meta50','tf_format_sync50'),('tf_source_meta50','tf_source_sync50'),
            ('u_push/analysis_done_meta','u_push/analysis_done_sync'),
            ('u_tf_audio/u_path/pb_meta','u_tf_audio/u_path/pb_sync'),
            ('u_tf_audio/u_path/pb_done_meta','u_tf_audio/u_path/pb_done_sync')]
        for first, second in level_pairs:
            a, b = registers(first + '_'), registers(second + '_')
            if len(a) != 1 or len(b) != 1:
                raise ValueError(first + ': missing diagnostic receiver')
            a_name, a_port = next(iter(a.items())); b_name, b_port = next(iter(b.items()))
            source, pin = design.drivers[a_port['D']]
            source_ports = design.cells[source][1]
            if pin != 'Q' or source_ports['CLK'] == a_port['CLK'] or a_port['CLK'] != b_port['CLK'] or a_port['Q'] != b_port['D']:
                raise ValueError(first + ': broken level synchronizer')
            consumers = [n for n, (kind, ports) in design.cells.items()
                         if any(net == a_port['Q'] and design.drivers.get(net) != (n, key)
                                for key, net in ports.items())]
            if consumers != [b_name]:
                raise ValueError(first + ': metastability stage has extra consumers: ' + repr(consumers))
            result['levels'][first] = [source, a_name, b_name]
        trace_meta=registers('u_music/u_trace_cdc/meta_')
        trace_sync=registers('u_music/u_trace_cdc/sync_')
        if len(trace_meta)!=7 or len(trace_sync)!=7:
            raise ValueError('missing seven DDR diagnostic level receivers')
        ddr_clock=next(iter(registers('u_music/u_ddr_req_cdc/write_gray_meta_').values()))['CLK']
        def source_clocks(net,visiting=None):
            if net in design.constants:return set()
            visiting=set() if visiting is None else visiting
            if net in visiting:raise ValueError('diagnostic source combinational loop')
            driver,pin=design.drivers[net];kind,ports=design.cells[driver]
            if kind.startswith('DFF'):
                if pin!='Q':raise ValueError('unexpected diagnostic FF driver')
                return {ports['CLK']}
            if kind=='INV':inputs=['I']
            elif kind.startswith('LUT'):inputs=[key for key in ports if key.startswith('I')]
            else:raise ValueError('unexpected diagnostic source primitive: '+kind)
            clocks=set()
            for key in inputs:clocks.update(source_clocks(ports[key],visiting|{net}))
            return clocks
        diagnostic=[]
        for name,port in trace_meta.items():
            matches=[(n,p) for n,p in trace_sync.items() if p['D']==port['Q'] and p['CLK']==port['CLK']]
            if len(matches)!=1 or port['CLK']==ddr_clock or source_clocks(port['D'])!={ddr_clock}:
                raise ValueError(name+': broken DDR diagnostic source/receiver')
            consumers=[n for n,(_,ports) in design.cells.items() if any(net==port['Q'] and design.drivers.get(net)!=(n,key) for key,net in ports.items())]
            if consumers!=[matches[0][0]]:raise ValueError(name+': metastability stage has other consumers')
            diagnostic.append([name,matches[0][0]])
        result['ddr_diagnostic_levels']=dict(bits=7,chains=diagnostic,source_clock=ddr_clock)
        release=[one('u_push/audio_release_'+str(i)) for i in range(2)]
        if release[0][1]['D']!='VCC' or release[1][1]['D']!=release[0][1]['Q'] or release[0][1]['CLK']!=release[1][1]['CLK']:
            raise ValueError('broken audio local reset release')
        result['audio_local_release']=[name for name,_ in release]
        file_meta=registers('u_tf_audio/u_path/file_size_meta_')
        file_sync=registers('u_tf_audio/u_path/file_size_sync_ui_')
        file_flights=[]
        if not file_meta or len(file_meta)!=len(file_sync):
            raise ValueError('missing held file-size receiver')
        for name,port in file_meta.items():
            source,pin=design.drivers[port['D']];kind,origin=design.cells[source]
            if not(kind.startswith('DFF') and pin=='Q' and source.startswith('u_tf_audio/u_path/u_dma/staged_file_size_') and origin['CLK']!=port['CLK']):
                raise ValueError(name+': unexpected held file-size source')
            successors=[n for n,p in file_sync.items() if p['D']==port['Q'] and p['CLK']==port['CLK']]
            if len(successors)!=1:raise ValueError(name+': missing second file-size sampler')
            flight=design.arc(source,'CLK','Q')+design.route(source+'/Q',name+'/D')
            if flight>10:raise ValueError(name+': held file-size flight exceeds10ns')
            file_flights.append(flight)
        result['held_file_size']=dict(bits=len(file_meta),maximum_flight_ns=max(file_flights))
        commands = [line for line in constraints().splitlines() if line.startswith('set_')]
        sdc = files[2].read_text()
        if not all(line in sdc for line in commands):
            raise ValueError('missing targeted CDC constraints')
        # Extra alias exceptions are permitted only for the two registered
        # write-pointer MSBs already proven above, with the same 10 ns bound.
        alias_block = gray_write_alias_constraints()
        if alias_block.strip() in sdc:
            checked = []
            for fifo in ('u_write_fifo', 'u_read_fifo'):
                key = 'u_managed/u_audio/u_workstation/effects/delay_stage/' + fifo + '/write_gray'
                bus = result['gray'][key]
                aliases = [chain for chain in bus['chains'] if '/write_binary_' in chain[0]]
                if any('/write_binary_9_' not in chain[0] or '/write_gray_meta_9_' not in chain[1]
                       for chain in aliases):
                    raise ValueError(key + ': alias exception does not match the proven MSB')
                checked.extend(aliases)
            result['write_gray_alias_constraints'] = dict(bound_ns=10, chains=checked,
                                                         maximum_binary_bit=9)
        result['passed'] = True
        result['evidence_sha256'] = {str(p.relative_to(build)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    except (OSError, ValueError, KeyError, AssertionError) as exc:
        result['errors'].append(str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    result = audit(build)
    (build / 'workstation_cdc.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], errors=result['errors'],
                         checked_gray_buses=len(result['gray']), checked_levels=len(result['levels'])), indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
