#!/usr/bin/env python3
"""Check the selected complete W mapping and reject actual state-pin mutations."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_w_dma_mapping import audit, REFERENCE
from tools.workstation_w_delay_ready import ALTERNATE_SHA256, SOURCE, POLICY


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    candidate = args.candidate.resolve()
    stage = candidate / 'workstation/Prj1'
    metadata = candidate / 'integration_inputs.json'
    record = json.loads(metadata.read_text())
    assert record['w_delay_ready']['policy'] == POLICY
    assert sha(stage / SOURCE) == ALTERNATE_SHA256
    vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
    inputs = [vg, metadata, stage / SOURCE, ROOT / REFERENCE, Path(__file__),
              ROOT / 'tools/workstation_w_dma_mapping.py']
    before = {str(path): sha(path) for path in inputs}
    n = protocol_netlist(vg.read_text(), mapping='synthesis')
    evidence = audit(n)
    controls = []
    for stem, pin, value in [('state_2_s0', 'D', "1'b0"),
                              ('state_0_s0', 'CLK', 'clk_50m')]:
        path = 'u_managed/runtime/delay_dma/' + stem
        original = n.cells[path]['ports'][pin]
        n.cells[path]['ports'][pin] = value
        try:
            audit(n)
        except ValueError as error:
            controls.append(dict(register=path, pin=pin, rejected=True, error=str(error)))
        else:
            raise AssertionError('actual mapped mutation escaped: ' + path + '/' + pin)
        finally:
            n.cells[path]['ports'][pin] = original
    assert before == {str(path): sha(path) for path in inputs}
    report = dict(passed=True, candidate_identity=record['workstation_profile']['candidate_identity'],
                  actual_mapping=evidence, rejected_controls=controls, inputs_sha256=before,
                  frozen_files_unchanged=True, board_accessed=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS complete803-state W DMA mapping and two actual state-pin controls')


if __name__ == '__main__':
    main()
