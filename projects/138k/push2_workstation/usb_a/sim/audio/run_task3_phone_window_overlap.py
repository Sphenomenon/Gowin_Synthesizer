#!/usr/bin/env python3
"""Reject phone-window/normal-command overlap at the actual M endpoint."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    root = Path(__file__).resolve().parents[2]
    sources = ['rtl/workstation/' + name + '.sv' for name in (
        'workstation_task3_m_bus_endpoint', 'workstation_task3_phone_window_rx',
        'workstation_task3_pcm_block_tx', 'workstation_task3_final_tap_export',
        'workstation_task3_phone_command_ingress')]
    sources += ['rtl/music/workstation_task3_tf_analysis_source.sv', 'rtl/music/workstation_task3_score_commit_m.sv']
    bench = 'sim/audio/tb_task3_phone_window_overlap.sv'
    tracked = sources + [bench, 'rtl/workstation/task3_paired_channels.vh', str(Path(__file__).resolve().relative_to(root))]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {p: sha(root / p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'inputs'
    report = dict(schema=1, passed=False, error=None, inputs_sha256=before, invocations=[], mutants=[],
                  scope='actual M endpoint and phone-window RX with deterministic held-command owner fixture; overlap, PANIC and cancel only',
                  hardware_tested=False, actual_APB_CDC_or_PCM_owner=False, physical_LCD_or_latency=False)
    try:
        for rel in tracked:
            dest = snapshot / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, dest)
            if sha(dest) != before[rel]:
                raise ValueError('input drift during snapshot: ' + rel)

        def invoke(name, argv, required=True):
            result = subprocess.run(argv, cwd=snapshot, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            log = output / (name + '.log')
            log.write_text(result.stdout)
            report['invocations'].append(dict(argv=argv, exit_code=result.returncode, log=str(log), log_sha256=sha(log)))
            if required and result.returncode:
                raise ValueError('failed invocation: ' + str(log))
            return result

        top = 'tb_task3_phone_window_overlap'
        binary = output / 'overlap.vvp'
        invoke('compile', ['iverilog', '-g2012', '-I.', '-s', top, '-o', str(binary), bench, *sources])
        result = invoke('run', ['vvp', str(binary)])
        match = re.search(r'PASS phone window overlap checks=(\d+) cases=(\d+) applied=(\d+) responses=(\d+) samples=(\d+)', result.stdout)
        if not match:
            raise ValueError('coverage/completion counters absent')
        checks, cases, applied, responses, samples = map(int, match.groups())
        if checks < 50 or cases != 6 or applied != 1 or responses != 3 or samples < 20:
            raise ValueError('overlap coverage incomplete')
        report['coverage'] = dict(checks=checks, cases=cases, applied_model_commands=applied, ordinary_responses=responses, independent_model_samples=samples)
        endpoint = sources[0]
        original = (snapshot / endpoint).read_text()
        mutations = [
            ('unlocked_window_preemption', [
                ('else if(phone_window_overlap)phone_window_protocol_fault<=1;', "else if(1'b0)phone_window_protocol_fault<=1;"),
                (' && (!phone_ingress_live || phone_window_eligible)', '')]),
            ('accept_overlapping_RPC', [(
                'phone_matches && !phone_window_busy && !phone_batch_busy && !phone_batch_fault)',
                'phone_matches && !phone_batch_busy && !phone_batch_fault)')]),
        ]
        for name, edits in mutations:
            changed = original
            for old, new in edits:
                if changed.count(old) != 1:
                    raise ValueError('mutation anchor drift: ' + name)
                changed = changed.replace(old, new)
            mutated = snapshot / (name + '.sv')
            mutated.write_text(changed)
            mutant = output / (name + '.vvp')
            invoke(name + '_compile', ['iverilog', '-g2012', '-I.', '-s', top, '-o', str(mutant), bench,
                                     *[str(mutated) if p == endpoint else p for p in sources]])
            result = invoke(name + '_run', ['vvp', str(mutant)], required=False)
            rejected = result.returncode != 0 and 'PASS phone window overlap' not in result.stdout
            report['mutants'].append(dict(name=name, rejected=rejected))
            if not rejected:
                raise ValueError('mutation survived: ' + name)
        report['inputs_unchanged'] = before == {p: sha(root / p) for p in tracked}
        if not report['inputs_unchanged']:
            raise ValueError('inputs changed during verification')
        report['passed'] = True
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        report['error'] = str(exc)
    target = output / 'verification.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], verification=str(target), error=report['error'])))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
