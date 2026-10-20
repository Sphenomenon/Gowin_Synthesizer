#!/usr/bin/env python3
"""Finish read-only audits for p31/p32 after their detached offline builds.

No board access, source edits, release selection, commits or programming.
A build passes only when its own STA, CDC, PLL and source-bound collector pass.
"""
from pathlib import Path
import concurrent.futures
from datetime import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREPARE = ROOT / 'results/workstation_incremental_margin_20261018_154046_134049'
JOBS = {
    'p31': ROOT / 'results/timing_p31_resume_domain_margin_20261018_155705_399572',
    'p32': ROOT / 'results/timing_p32_domain_margin_reference12_20261018_160005_905146',
}


def load(path):
    return json.loads(path.read_text())


def alive(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] != 'Z'
    except FileNotFoundError:
        return False


def run(label, suffix, args):
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    (OUT / f'{label}_{suffix}_runner.log').write_text(result.stdout)
    return {'command': args, 'exit_code': result.returncode}


def audit(label, build, collector_options=()):
    record = load(build / 'tool_result.json')
    evidence = {'tool_result': record, 'passed': False}
    if record['exit_code'] or not record['inputs_unchanged'] or not record['synthesis_storage_checked']:
        evidence['status'] = 'build failed; no acceptance'
        return evidence
    commands = {
        'sta': [sys.executable, 'tools/audit_workstation_timing.py', str(build),
                '--require-closed', '--output', str(OUT / f'{label}_sta.json')],
        'cdc': [sys.executable, 'tools/audit_workstation_cdc.py', str(build)],
        'pll': [sys.executable, str(build / 'Prj1/scripts/check_video_pll_init.py'),
                '--root', str(build / 'Prj1'), '--output', str(OUT / f'{label}_pll.json')],
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        future = {key: pool.submit(run, label, key, args) for key, args in commands.items()}
        evidence['commands'] = {key: task.result() for key, task in future.items()}
    cdc_file = build / 'workstation_cdc.json'
    if cdc_file.exists():
        (OUT / f'{label}_cdc.json').write_bytes(cdc_file.read_bytes())
    evidence.update(
        timing_closed=load(OUT / f'{label}_sta.json')['timing_closed'],
        cdc_passed=load(cdc_file)['passed'],
        pll_passed=not load(OUT / f'{label}_pll.json')['errors'])
    if all(evidence[key] for key in ['timing_closed', 'cdc_passed', 'pll_passed']):
        evidence['collector'] = run(label, 'collector', [sys.executable,
            str(OUT / 'collect_evidence.py'), str(build), '--prepare', str(PREPARE), *collector_options])
        evidence['passed'] = evidence['collector']['exit_code'] == 0
    evidence['status'] = 'all gates passed' if evidence['passed'] else 'audited; not accepted'
    return evidence


def main():
    pids = {key: load(OUT / f'{key}_launch.json')['pid'] for key in JOBS}
    result = {'hardware_tested': False, 'jobs': {},
              'watcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    destination = OUT / 'resumed_candidate_audits.json'
    deadline = time.monotonic() + 3 * 3600
    while len(result['jobs']) < len(JOBS):
        for key, build in JOBS.items():
            if key in result['jobs'] or alive(pids[key]):
                continue
            try:
                evidence = audit(key, build) if (build / 'tool_result.json').exists() else {
                    'passed': False, 'status': 'process exited without complete build result'}
            except Exception as exc:
                evidence = {'passed': False, 'status': 'audit error', 'error': repr(exc)}
            result['jobs'][key] = dict(build=str(build.relative_to(ROOT)), **evidence)
            result['updated'] = datetime.now().astimezone().isoformat()
            temporary = destination.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            os.replace(temporary, destination)
            print(key, evidence['status'], flush=True)
        if time.monotonic() >= deadline:
            print('audit watcher timeout; no incomplete build accepted', flush=True)
            return
        if len(result['jobs']) < len(JOBS):
            time.sleep(5)


if __name__ == '__main__':
    main()
