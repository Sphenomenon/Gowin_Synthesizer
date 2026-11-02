#!/usr/bin/env python3
"""Actual paired endpoints through the policy-locked prepared APB CDC and PCM1 owner."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True,
                        help='Prepared workstation/Prj1; only policy-locked APB RTL is consumed')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    repo = root.parents[3]
    project, output = args.project.resolve(), args.output.resolve()
    if output.is_relative_to(project) or output.is_relative_to(repo):
        raise ValueError('evidence output must be outside source and frozen prepared project')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, error=None, invocations=[], cases=[],
                  validation_stage='offline_actual_endpoint_APB_CDC_PCM_owner_simulation',
                  project=str(project), project_used_for='policy-locked prepared APB CDC only',
                  parent_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
                  hardware_tested=False, physical_CDC_accepted=False, sustained_phone_audio_accepted=False,
                  covered=['actual M/W PHONE_WINDOW_BLOCK endpoints and capability negotiation',
                           '512 posted stereo window words applied through real held-command APB CDC',
                           'four 128-frame PCM1 COMMITs ordered after actual owner completions',
                           'SELECT and at least 160 exact nonzero stereo owner sample outputs',
                           'ordered clock target, STOP, PANIC, generation change and link fencing',
                           'mixed new/legacy phone-window capability refusal'],
                  not_verified=['LCD PHY/electrical or real communication throughput/jitter/latency',
                                'actual phone, Bluetooth/HCI/SBC decoding and production firmware',
                                'DSP/D effects/master gain, I2S/DAC or control-to-sound latency',
                                'continuous refill, long recording/download concurrency or actual CNN',
                                'whole-board synthesis, physical resources, routed timing/CDC/PLL or deployment'])
    inputs = {}
    try:
        policy_rel = 'tools/workstation_ae350_pcm_cdc_policy.json'
        policy_path = root / policy_rel
        policy = json.loads(policy_path.read_text())
        relative = Path(policy['prepared_APB_source'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('prepared APB source escapes project')
        apb = (project / relative).resolve()
        if not apb.is_relative_to(project) or sha(apb) != policy['prepared_APB_sha256']:
            raise ValueError('prepared APB source differs from strict reviewed policy')
        report['prepared_APB'] = dict(path=str(apb), relative_path=str(relative),
                                      sha256=sha(apb), expected_sha256=policy['prepared_APB_sha256'],
                                      policy_path=policy_rel, policy_sha256=sha(policy_path))
        sources = ['rtl/workstation/' + name + '.sv' for name in (
            'workstation_task3_m_bus_endpoint', 'workstation_task3_w_bus_endpoint',
            'workstation_task3_phone_window_tx', 'workstation_task3_phone_window_rx',
            'workstation_task3_pcm_block_tx', 'workstation_task3_pcm_block_rx',
            'workstation_task3_record_ingress', 'workstation_task3_final_tap_export',
            'workstation_task3_phone_command_ingress', 'workstation_task3_phone_command_proxy',
            'workstation_task3_phone_command_mux', 'workstation_task3_record_source_gate')]
        sources += ['rtl/music/workstation_task3_tf_analysis_source.sv',
                    'rtl/music/workstation_task3_score_commit_m.sv',
                    'rtl/audio/workstation_ae350_pcm_owner.sv']
        bench = 'sim/audio/tb_workstation_task3_phone_window_owner.sv'
        tracked = [*sources, bench, 'rtl/workstation/task3_paired_channels.vh', policy_rel,
                   str(Path(__file__).resolve().relative_to(root))]
        inputs = {rel: sha(root / rel) for rel in tracked}
        report['inputs_sha256'] = inputs
        snapshot = output / 'inputs'
        for rel in tracked:
            dest = snapshot / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, dest)
            if sha(dest) != inputs[rel]:
                raise ValueError('input changed while snapshotting: ' + rel)
        cdc_copy = snapshot / 'prepared' / relative
        cdc_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(apb, cdc_copy)
        if sha(cdc_copy) != policy['prepared_APB_sha256']:
            raise ValueError('prepared APB changed during snapshot')

        def run(argv, name):
            result = subprocess.run(argv, cwd=snapshot, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=90)
            log = output / (name + '.log')
            log.write_text(result.stdout)
            report['invocations'].append(dict(argv=argv, returncode=result.returncode,
                                               log=str(log), log_sha256=sha(log)))
            if result.returncode:
                raise ValueError('failed command: ' + str(log))
            return result.stdout

        top = 'tb_workstation_task3_phone_window_owner'
        for name, mixed in (('real_owner', False), ('mixed_policy', True)):
            binary = output / (name + '.vvp')
            run(['iverilog', '-g2012', '-I.', '-s', top,
                 *(['-P' + top + '.W_PHONE_WINDOW=0'] if mixed else []),
                 '-o', str(binary), bench, *sources, str(cdc_copy)], name + '_compile')
            result = run(['vvp', str(binary)], name + '_run')
            if mixed:
                match = re.search(r'PASS phone window mixed checks=(\d+)', result)
                if not match or int(match[1]) < 1:
                    raise ValueError('mixed policy rejection evidence absent')
                case = dict(name=name, passed=True, checks=int(match[1]))
            else:
                match = re.search(r'PASS phone window real owner checks=(\d+) words=(\d+) blocks=(\d+) nonzero=(\d+)', result)
                if not match:
                    raise ValueError('actual owner completion evidence absent')
                checks, words, blocks, nonzero = map(int, match.groups())
                if checks < 500 or words < 512 or blocks < 104 or nonzero < 160:
                    raise ValueError('actual owner coverage shortfall')
                case = dict(name=name, passed=True, checks=checks, applied_owner_words=words,
                            transmitted_window_blocks=blocks, exact_nonzero_stereo_samples=nonzero)
            report['cases'].append(case)
        report['source_unchanged'] = inputs == {rel: sha(root / rel) for rel in tracked}
        report['prepared_APB_unchanged'] = sha(apb) == policy['prepared_APB_sha256']
        if not report['source_unchanged'] or not report['prepared_APB_unchanged']:
            raise ValueError('verification inputs changed during run')
        report['passed'] = True
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        report['error'] = str(exc)
        report['source_unchanged'] = bool(inputs) and all(
            (root / rel).is_file() and sha(root / rel) == expected for rel, expected in inputs.items())
    target = output / 'verification.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], verification=str(target), error=report['error'])))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
