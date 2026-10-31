#!/usr/bin/env python3
"""Check the frozen W recording diagnostic retirement against its actual VG."""
import argparse
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_usb_firmware import sha
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_demo_audit import audit_w_recording_diagnostic_retirement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stage = args.candidate.resolve() / 'workstation/Prj1'
    vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
    source = stage / 'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv'
    out = args.output.resolve()
    if out.exists() or ROOT in out.parents:
        raise ValueError('new evidence directory outside source required')
    identities = {str(p): sha(p) for p in (vg, source, Path(__file__),
        ROOT / 'tools/workstation_demo_audit.py', ROOT / 'tools/workstation_demo_policy.py')}
    n = SynthesisNetlist(vg.read_text(), 'workstation_custom_138k_top')
    baseline = audit_w_recording_diagnostic_retirement(stage, n)
    mutants = {}

    def rejected(label, expected):
        try:
            audit_w_recording_diagnostic_retirement(stage, n)
        except ValueError as error:
            if expected not in str(error):
                raise
            mutants[label] = dict(rejected=True, failure=str(error))
        else:
            raise ValueError('negative control survived: ' + label)

    original_read = Path.read_text
    original_text = source.read_text()
    with patch.object(Path, 'read_text', lambda p, *a, **kw:
            original_text + '\nwire resumed_consumer=raw_start_done_i;\n'
            if p == source else original_read(p, *a, **kw)):
        rejected('source_consumer_resurrected', 'diagnostic gained a source consumer')
    driver = baseline['true_status']['raw_channel_fault']['driver']
    old = n.cells.pop(driver)
    try:
        rejected('real_fault_driver_removed', 'true completion/fault driver missing')
    finally:
        n.cells[driver] = old
    driver = baseline['true_status']['raw_committed[0]']['driver']
    old = n.cells[driver]['ports']['CLK']
    n.cells[driver]['ports']['CLK'] = 'wrong_clock'
    try:
        rejected('committed_frame_clock_bypassed', 'committed frame driver missing')
    finally:
        n.cells[driver]['ports']['CLK'] = old
    changes = []
    for p, c in n.cells.items():
        if not p.startswith('u_bluetooth/u_core/application/command_endpoint/recording/'):
            continue
        if not re.fullmatch(r'LUT[1-6]|ALU', c['kind']):
            continue
        for pin, value in list(c['ports'].items()):
            if re.fullmatch(r'I[0-5]|CIN', pin) and n.pin(p, pin) == 'raw_committed[0]':
                changes.append((p, pin, value)); c['ports'][pin] = "1'b0"
    assert changes
    try:
        rejected('committed_frame_consumers_bypassed', 'netlist consumer missing: raw_committed[0]')
    finally:
        for p, pin, value in changes:
            n.cells[p]['ports'][pin] = value
    n.cells['resurrected_diagnostic'] = dict(kind='LUT1', ports={'I0': 'raw_failure', 'F': 'probe'}, parameters={})
    try:
        rejected('diagnostic_actual_alias_resurrected', 'diagnostic has an actual alias')
    finally:
        del n.cells['resurrected_diagnostic']
    assert identities == {p: sha(Path(p)) for p in identities}
    out.mkdir(parents=True)
    report = dict(stage='frozen_W_actual_recording_diagnostic_retirement', inputs_sha256=identities,
                  baseline=baseline, mutants=mutants, immutable_inputs_unchanged=True,
                  PNR=False, hardware_tested=False)
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(actual_status_sources=baseline['true_status_source_count'],
                         negative_controls_rejected=len(mutants), output=str(out))))


if __name__ == '__main__':
    main()
