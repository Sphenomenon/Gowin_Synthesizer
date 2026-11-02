#!/usr/bin/env python3
"""M batch executor and atomic owner snapshots through the real async APB CDC."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

REFERENCE = '6ebb5e41233c78e6af7959fb350dd9661c402de4'
OWNER = 'rtl/audio/workstation_ae350_pcm_owner.sv'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True,
                        help='explicit prepared Prj1; only policy-locked APB CDC is consumed')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    repo = root.parents[3]
    project, output = args.project.resolve(), args.output.resolve()
    if output.is_relative_to(project) or output.is_relative_to(repo):
        raise ValueError('evidence must remain outside source/prepared candidate')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, validation_stage='offline_M_batch_real_async_APB_owner',
                  hardware_tested=False, physical_CDC_accepted=False, routed_timing_verified=False,
                  sustained_phone_audio_accepted=False, invocations=[], error=None)
    tracked, inputs = [], {}
    try:
        policy_relative = 'tools/workstation_ae350_pcm_cdc_policy.json'
        policy = json.loads((root/policy_relative).read_text())
        relative = Path(policy['prepared_APB_source'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('invalid prepared APB path')
        apb = (project/relative).resolve()
        if not apb.is_relative_to(project) or sha(apb) != policy['prepared_APB_sha256']:
            raise ValueError('actual APB source differs from reviewed policy')
        bench = 'sim/audio/tb_workstation_task3_phone_batch_m.sv'
        executor = 'rtl/workstation/workstation_task3_phone_batch_m.sv'
        tracked = [OWNER, bench, executor, policy_relative,
                   'rtl/workstation/TASK3_PHONE_BATCH_CONTRACT.md',
                   str(Path(__file__).resolve().relative_to(root))]
        inputs = {rel: sha(root/rel) for rel in tracked}
        snapshot = output/'inputs'
        for rel in tracked:
            dest = snapshot/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root/rel, dest)
            if sha(dest) != inputs[rel]:
                raise ValueError('source changed during snapshot: '+rel)
        cdc = snapshot/'prepared'/relative
        cdc.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(apb, cdc)
        reference_bytes = subprocess.check_output(
            ['git', 'show', REFERENCE+':projects/138k/push2_workstation/usb_a/'+OWNER], cwd=repo)
        original = reference_bytes.decode()
        anchor = 'module workstation_ae350_pcm_owner #('
        if original.count(anchor) != 1 or 'SNAPSHOT_ENABLE' in original:
            raise ValueError('pre-feature owner reference drifted')
        reference = snapshot/'default_reference.sv'
        reference.write_text(original.replace(anchor, 'module workstation_ae350_pcm_owner_default_reference #('))
        report.update(inputs_sha256=inputs, prepared_APB=dict(path=str(apb), sha256=sha(apb)),
            default_reference=dict(revision=REFERENCE, raw_sha256=hashlib.sha256(reference_bytes).hexdigest(),
                                   adaptation='one exact module-name replacement', adapted_sha256=sha(reference)))

        def run(argv, name):
            result = subprocess.run(argv, cwd=snapshot, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=120)
            log = output/(name+'.log')
            log.write_text(result.stdout)
            report['invocations'].append(dict(argv=argv, returncode=result.returncode,
                                               log=str(log), log_sha256=sha(log)))
            if result.returncode:
                raise ValueError('failed command: '+str(log))
            return result.stdout

        binary = output/'batch_m.vvp'
        run(['verilator', '--lint-only', '-Wno-fatal', '--top-module',
             'workstation_task3_phone_batch_m', executor], 'executor_lint')
        run(['verilator', '--lint-only', '-Wno-fatal', '--top-module',
             'workstation_ae350_pcm_owner', '-GSNAPSHOT_ENABLE=1', OWNER], 'owner_lint')
        run(['iverilog', '-g2012', '-s', 'tb_workstation_task3_phone_batch_m',
             '-o', str(binary), bench, OWNER, executor, str(reference), str(cdc)], 'compile')
        result = run(['vvp', str(binary)], 'run')
        match = re.search(r'PASS phone batch M checks=(\d+) compared_cycles=(\d+) owner_reads=(\d+) owner_writes=(\d+) audio_ticks=(\d+)', result)
        if not match:
            raise ValueError('actual owner/snapshot evidence absent')
        checks, cycles, reads, writes, ticks = map(int, match.groups())
        report.update(checks=checks, default_reference_cycles=cycles, actual_owner_reads=reads,
                      actual_owner_writes=writes, continuing_audio_ticks=ticks,
                      covered=['real asynchronous 50MHz/76.8MHz held-command APB CDC',
                               'atomic 20-word capture, post-capture context changes, observer reset and no-wrap ID',
                               'SNAP actual ID/version/CAPS and production CAP3 false',
                               'full key ARM, complete two-slot COMMIT, SELECT/history/sample applied ID and STOP',
                               'original missing-frame bitmap rejection; no alternate PCM publication',
                               'shape/token/sequence/duplicate/owner/probe/capture/timeout/cancel negatives',
                               'default-off cycle equivalence to immutable pre-feature Git source',
                               'enabled read-only snapshot preserves original queue/bitmap/audio state'],
                      not_verified=['paired M/W endpoints or new firmware integration',
                                    'LCD electrical transport and measured throughput/latency',
                                    'RF/SBC, D DSP, final DAC, whole-board resources/CDC/STA/PLL or deployment'])
        report['source_unchanged'] = inputs == {rel: sha(root/rel) for rel in tracked}
        report['prepared_APB_unchanged'] = sha(apb) == policy['prepared_APB_sha256']
        report['passed'] = checks >= 600 and cycles > 10000 and writes >= 270 and ticks > 5 and report['source_unchanged'] and report['prepared_APB_unchanged']
        if not report['passed']:
            raise ValueError('coverage/input invariance shortfall')
    except Exception as error:
        report['error'] = str(error)
    (output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'], error=report['error'], evidence=str(output/'verification.json'))))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
