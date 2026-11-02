#!/usr/bin/env python3
"""Reproducible typed M/W endpoint composition and opt-out source identity."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    repo = root.parents[3]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = ['rtl/workstation/' + name + '.sv' for name in (
        'workstation_task3_w_bus_endpoint', 'workstation_task3_m_bus_endpoint',
        'workstation_task3_record_ingress', 'workstation_task3_final_tap_export',
        'workstation_task3_phone_command_ingress', 'workstation_task3_phone_command_proxy',
        'workstation_task3_phone_command_mux', 'workstation_task3_record_source_gate')]
    sources += ['rtl/music/workstation_task3_tf_analysis_source.sv',
                'rtl/music/workstation_task3_score_commit_m.sv',
                'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv']
    opted_sources = [
        'rtl/bluetooth/cpu_owner/ble_protocol_command.v',
        'rtl/bluetooth/cpu_owner/bt_gatt.v',
        'rtl/bluetooth/hci_owner/workstation_hci_native_core.v',
        'rtl/bluetooth/hci_owner/workstation_hci_bluetooth.sv']
    helper = 'tools/workstation_task3_w_paired_profile.py'
    extra = ['rtl/workstation/task3_paired_channels.vh',
             'sim/audio/tb_workstation_task3_paired_bus.sv',
             'sim/audio/run_workstation_task3_paired_bus.py', helper,
             'rtl/workstation/workstation_task3_w_paired_top_reference.json']
    inputs = {rel: sha(root / rel) for rel in sources + opted_sources + extra}
    commands = []
    def run(argv, log):
        result = subprocess.run(argv, cwd=root, text=True, capture_output=True)
        path = output / log
        path.write_text(result.stdout + result.stderr)
        commands.append(dict(argv=argv, returncode=result.returncode,
                             log=str(path), log_sha256=sha(path)))
        if result.returncode:
            raise ValueError('failed command: ' + ' '.join(argv))
        return result.stdout
    passed, error, macro_off, roundtrip = False, None, [], False
    try:
        binary = output / 'paired_bus.vvp'
        run(['iverilog', '-g2012', '-I.', '-s', 'tb_workstation_task3_paired_bus',
             '-o', str(binary), 'sim/audio/tb_workstation_task3_paired_bus.sv', *sources], 'build.log')
        result = run(['vvp', str(binary)], 'run.log')
        match = re.search(r'PASS task3 paired typed bus checks=(\d+) record_frames=21 phone_commands=2 status=6 engine_frames=4', result)
        if not match:
            raise ValueError('paired endpoint pass evidence absent')
        include = output / 'native_bluetooth'
        include.mkdir()
        (include / 'patch_path.vh').write_text('`define WORKSTATION_BLE_PATCH_FILE "preprocess-only-unused.mem"\n')
        # The new recording-idle observation is opt-in at all four maintained
        # layers. Verify actual macro-off tokens against the current commit.
        for index, rel in enumerate(opted_sources):
            historical = output / ('head_' + Path(rel).name)
            git_path = (root / rel).relative_to(repo)
            historical.write_bytes(subprocess.run(['git', 'show', 'HEAD:' + str(git_path)],
                cwd=repo, capture_output=True, check=True).stdout)
            old, current = output / f'old_{index}.v', output / f'current_{index}.v'
            run(['iverilog', '-E', '-g2012', '-I.', '-I' + str(output), '-o', str(old), str(historical)], f'preprocess_old_{index}.log')
            run(['iverilog', '-E', '-g2012', '-I.', '-I' + str(output), '-o', str(current), rel], f'preprocess_current_{index}.log')
            normalize = lambda path: ''.join(re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(), flags=re.S).split())
            equal = normalize(old) == normalize(current)
            macro_off.append(dict(source=rel, macro_off_tokens_unchanged=equal,
                                  parent_source_sha256=sha(historical), current_source_sha256=sha(root / rel)))
            if not equal:
                raise ValueError('opt-out HCI source changed: ' + rel)
        sys.path.insert(0, str(root))
        from tools import workstation_task3_w_paired_profile as profile
        text = (root / profile.TOP).read_text()
        selected = profile.apply_top(root, text)
        if profile.inverse_top(root, selected) != text:
            raise ValueError('W paired top exact inverse failed')
        # Exercise both constraints layers without relying on cached candidates.
        sdc = ('set_max_delay 10.000 -from [get_regs {u_managed/pcm_apb.commands/request_held*}] '
               '-to [get_regs {u_managed/pcm_apb.commands/request_local*}]\n'
               'set_false_path -to [get_pins {u_managed/runtime/cpu_pcm.session/live_o*/CLEAR}]\n')
        selected, evidence = profile.constraints(sdc)
        if profile.restore_constraints(selected, evidence) != sdc:
            raise ValueError('W paired constraints exact inverse failed')
        roundtrip = True
        passed = True
    except (ValueError, subprocess.CalledProcessError) as exc:
        error = str(exc)
    unchanged = inputs == {rel: sha(root / rel) for rel in inputs}
    report = dict(schema=1, passed=passed and unchanged, error=error,
        parent_commit=subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo,
                                     capture_output=True, text=True, check=True).stdout.strip(),
        source_unchanged=unchanged, inputs_sha256=inputs, invocations=commands,
        checks=int(match[1]) if passed else 0, record_frames=21, remote_phone_commands=2,
        actual_M_W_endpoint_composition=True, actual_record_ingress=True,
        actual_recording_engine=True, actual_recording_engine_frames=4,
        M_owner_response_fixture=True, physical_sample_tick_counter_fixture=True,
        macro_off_HCI=macro_off, exact_top_and_SDC_roundtrip=roundtrip,
        covered=['actual HCI state before phone ARM', 'both PCM1 and M clock targets',
                 'held command payload and matched response', 'M final tap to W real record ingress',
                 'actual busy-object arm rejection', 'fresh generation rearm',
                 'actual REC_START acquires M tap via ch9', 'same physical engine captures and seals',
                 'terminal object automatically cancels tap',
                 'link loss fencing', 'timeout error and matching cancellation',
                 'malformed high padding', 'PANIC'],
        not_verified=['physical LCD/electrical/framing/CDC', 'actual phone HCI/SBC decode',
                      'physical DAC or control-to-sound latency', 'D DSP and master gain',
                      '60-second DDR capture or BLE download', 'full board synthesis/resources/timing'])
    target = output / 'verification.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], verification=str(target), error=error)))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
