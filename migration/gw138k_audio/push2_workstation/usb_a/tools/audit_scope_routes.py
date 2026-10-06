#!/usr/bin/env python3
"""Read-only routed checks for scope transport and final-PCM mailboxes.

Checks the new crossings, not overall timing closure or analog/HDMI behavior.
Only route metrics and hashes are persisted, never audio sample data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    stage = build / 'Prj1'
    out = build / 'scope_routed_audit.json'
    if out.exists():
        parser.error('preserve previous routed audit; use a new build')
    sys.path.insert(0, str(stage / 'scripts'))
    from check_video_pll_init import RoutedDesign
    pnr = stage / 'impl/pnr'
    sdf, netlist = pnr / 'Prj1.sdf', pnr / 'Prj1.vo'
    result = dict(passed=False, overall_timing_closed=None, hardware_tested=False,
                  sample_data_saved=False, crossings={}, errors=[])
    try:
        design = RoutedDesign(sdf.read_text(), netlist.read_text())

        def regs(prefix):
            return {name: ports for name, (kind, ports) in design.cells.items()
                    if name.startswith(prefix) and kind.startswith('DFF')}

        def one(prefix):
            matches = regs(prefix)
            if len(matches) != 1:
                raise ValueError(f'expected one register {prefix}: {len(matches)}')
            return next(iter(matches.items()))

        for instance, width in [('u_tf_control_cdc', 32), ('u_final_output_cdc', 128)]:
            targets = regs(instance + '/destination_data_')
            # Constant metadata/control bits may be optimized, but each retained
            # bit must come directly from the acknowledged source-domain hold.
            if not 0 < len(targets) <= width:
                raise ValueError(f'{instance}: bad retained width {len(targets)}')
            flights = []
            for name, port in targets.items():
                source, pin = design.drivers[port['D']]
                kind, source_ports = design.cells[source]
                if not (source.startswith(instance + '/held_data_') and pin == 'Q'
                        and kind.startswith('DFF') and source_ports['CLK'] != port['CLK']):
                    raise ValueError(f'{instance}: non-held or same-clock source {source}->{name}')
                flight = design.arc(source, 'CLK', 'Q') + design.route(source + '/Q', name + '/D')
                if flight > 20:
                    raise ValueError(f'{instance}: held-data flight {flight} exceeds 20 ns')
                flights.append(flight)
            synchronizers = {}
            for first, second in [('req_meta', 'req_sync'), ('ack_meta', 'ack_sync')]:
                first_name, first_port = one(instance + '/' + first + '_')
                second_name, second_port = one(instance + '/' + second + '_')
                if first_port['Q'] != second_port['D'] or first_port['CLK'] != second_port['CLK']:
                    raise ValueError(f'{instance}: broken {first}/{second} synchronizer')
                synchronizers[first] = [first_name, second_name]
            result['crossings'][instance] = dict(nominal_bits=width,
                retained_destination_bits=len(targets), maximum_hold_flight_ns=max(flights),
                synchronizers=synchronizers)
        first_name, first = one('tf_run_meta_')
        second_name, second = one('tf_run_audio_')
        if first['Q'] != second['D'] or first['CLK'] != second['CLK']:
            raise ValueError('TF pause/run synchronization broken')
        result['tf_run_synchronizer'] = [first_name, second_name]
        result['evidence_sha256'] = {str(p.relative_to(build)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in [sdf, netlist, stage / 'constraints/tang_mega_138k.sdc']}
        result['passed'] = True
    except (OSError, ValueError, AssertionError, KeyError) as exc:
        result['errors'].append(str(exc))
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
