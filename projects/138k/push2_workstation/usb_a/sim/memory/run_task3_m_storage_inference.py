#!/usr/bin/env python3
"""Check generic synchronous memory inference on immutable prepared M inputs.

This is an optional subsystem precheck, not Gowin synthesis or a release gate.
Use a Yosys executable explicitly; yowasp-yosys is supported. No design source
is rewritten, and the two asynchronous controls must fail the same read-clock
predicate that the selected synchronous implementation passes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_task3_paired_audit as paired


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quoted(path):
    # This quotes Yosys script syntax; commands are never passed to a shell.
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


def integer(parameters, key):
    value = parameters[key]
    if not value or set(value) - {'0', '1'}:
        raise ValueError('unknown memory parameter: ' + key)
    return int(value, 2)


def inspect(netlist, module, memory, width, depth):
    top = netlist['modules'][module]
    cells = {name: cell for name, cell in top['cells'].items()
             if cell['type'] == '$mem_v2'}
    if set(cells) != {memory}:
        raise ValueError('expected exactly one unswept memory: ' + module)
    cell = cells[memory]
    p, c = cell['parameters'], cell['connections']
    observed = {key: integer(p, key) for key in (
        'WIDTH', 'SIZE', 'ABITS', 'RD_PORTS', 'WR_PORTS',
        'RD_CLK_ENABLE', 'WR_CLK_ENABLE', 'RD_CLK_POLARITY',
        'WR_CLK_POLARITY', 'RD_TRANSPARENCY_MASK', 'RD_COLLISION_X_MASK')}
    expected = {'WIDTH': width, 'SIZE': depth, 'ABITS': (depth - 1).bit_length(),
                'RD_PORTS': 1, 'WR_PORTS': 1, 'WR_CLK_ENABLE': 1,
                'WR_CLK_POLARITY': 1, 'RD_TRANSPARENCY_MASK': 0}
    for key, value in expected.items():
        if observed[key] != value:
            raise ValueError(f'{module}: {key}={observed[key]}, expected {value}')
    clock = top['ports']['clk_i']['bits']
    if c['WR_CLK'] != clock:
        raise ValueError('write port is not on the actual local clock')
    if c['RD_ARST'] != ['0'] or c['RD_SRST'] != ['0']:
        raise ValueError('memory read port has acquired a reset')
    synchronous = (observed['RD_CLK_ENABLE'] == 1 and
                   observed['RD_CLK_POLARITY'] == 1 and c['RD_CLK'] == clock)
    counters = {name: len(top['netnames'][name]['bits'])
                for name in ('clip_notes', 'cursor', 'note_count')
                if name in top['netnames']}
    return dict(memory=memory, geometry_and_ports=observed,
                read_reset_free=True, synchronous_read=synchronous,
                local_counter_widths=counters)


def main(candidate, output, yosys):
    output.mkdir(parents=True, exist_ok=False)
    manifests = [candidate / name for name in (
        'integration_inputs.json', 'workstation_profile.json')]
    before = {str(path): sha(path) for path in manifests}
    invocations, cases = [], []
    report = dict(schema=1, passed=False, candidate_directory=str(candidate),
                  implementation='generic_Yosys_memory_collect',
                  source_script_sha256=sha(__file__),
                  physical_BSRAM_mapping_verified=False,
                  Gowin_synthesis_passed=False, routed_timing_verified=False,
                  full_CDC_accepted=False, hardware_tested=False,
                  bitstream_sha256=None, sram_programmed=False,
                  flash_programmed=False, invocations=invocations, cases=cases)

    def run(argv, label):
        process = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        text = process.stdout + process.stderr
        log = output / (label + '.log')
        log.write_text(text)
        invocations.append(dict(argv=argv, exit_code=process.returncode,
                                log=str(log), log_sha256=sha(log)))
        if process.returncode:
            raise RuntimeError(f'{label} failed: {text[-1500:]}')
        return text

    try:
        selected = profiles.verify(ROOT, candidate)
        metadata = json.loads(manifests[0].read_text())
        role, _, _, _ = paired.verify_prepared(candidate, metadata)
        if role != 'M' or selected['configuration'].get('m_endpoint_storage_policy') != 'sync_score_and_final_tap_prefetch_v1':
            raise ValueError('explicit M synchronous storage candidate required')
        report.update(candidate_identity=selected['candidate_identity'],
                      configuration_sha256=selected['profile_sha256'],
                      candidate_manifests_sha256=before,
                      source_and_prepared_identity_verified=True,
                      tool_version=run([yosys, '-V'], 'version').strip())
        stage = candidate / 'workstation/Prj1'
        sources = [
            ('workstation_task3_score_commit_m', 'notes', 7, 2048,
             stage / 'rtl/music/workstation_task3_score_commit_m.sv'),
            ('workstation_task3_final_tap_export', 'frames', 98, 256,
             stage / 'rtl/workstation/workstation_task3_final_tap_export.sv')]
        inputs = {str(source): sha(source) for *_, source in sources}
        report['prepared_source_sha256'] = inputs
        for module, memory, width, depth, source in sources:
            for mode in (0, 1):
                label = f'{module}-sync{mode}'
                netlist_path = output / (label + '.json')
                script = output / (label + '.ys')
                script.write_text(
                    f'read_verilog -sv {quoted(source)}\n'
                    f'chparam -set SYNC_READ_STORAGE {mode} {module}\n'
                    f'hierarchy -top {module}\n'
                    'proc\nopt\nmemory_dff\nopt_clean\nmemory_collect\n'
                    f'write_json {quoted(netlist_path)}\n')
                run([yosys, '-s', str(script)], label)
                observed = inspect(json.loads(netlist_path.read_text()),
                                   module, memory, width, depth)
                if observed['synchronous_read'] != bool(mode):
                    raise ValueError('synchronous inference/control mismatch: ' + label)
                if module.endswith('score_commit_m'):
                    expected_bits = 12 if mode else 32
                    if observed['local_counter_widths'] != dict.fromkeys(
                            ('clip_notes', 'cursor', 'note_count'), expected_bits):
                        raise ValueError('score counters no longer match the selected bounds')
                cases.append(dict(case=label, selected_synchronous_mode=bool(mode),
                                  asynchronous_negative_rejected=not bool(mode),
                                  passed=True, observed=observed,
                                  script=str(script), script_sha256=sha(script),
                                  generic_netlist=str(netlist_path),
                                  generic_netlist_sha256=sha(netlist_path)))
        if inputs != {path: sha(path) for path in inputs}:
            raise ValueError('prepared RTL changed during inference')
        if before != {path: sha(path) for path in before}:
            raise ValueError('candidate manifest changed during inference')
        report.update(passed=True, inputs_unchanged=True,
                      synchronous_cases_passed=2, asynchronous_negatives_rejected=2,
                      not_verified=[
                          'Vendor primitive inference and physical BSRAM/RAM16 counts',
                          'Gowin full-design synthesis, mapped CDC and routed timing',
                          'Behavioral lifecycle and read/write collision semantics',
                          'Target LCD throughput, audio latency and hardware acceptance'])
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, identity=report['candidate_identity'],
                          verification=str(output / 'verification.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--yosys', required=True)
    args = parser.parse_args()
    main(args.candidate.resolve(), args.output.resolve(), args.yosys)
