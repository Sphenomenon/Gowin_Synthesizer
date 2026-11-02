#!/usr/bin/env python3
"""Measure real firmware MMIO load over actual ideal-wire LCD/PCM1 RTL.

This is a diagnostic model. A successful run validates observations, including
expected refusal/underrun; it never grants sustained or physical audio acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(project, output, duration_ms, phone_batch=False):
    project, output = project.resolve(), output.resolve()
    if duration_ms < 20 or duration_ms > 200:
        raise ValueError('diagnostic window must be 20..200 model milliseconds')
    if output.is_relative_to(ROOT.parents[3]) or output.is_relative_to(project):
        raise ValueError('evidence must be outside repository and prepared project')
    output.mkdir(parents=True, exist_ok=False)
    policy_path = ROOT / 'tools/workstation_ae350_pcm_cdc_policy.json'
    policy = json.loads(policy_path.read_text())
    relative = Path(policy['prepared_APB_source'])
    apb = (project / relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not apb.is_relative_to(project) or sha(apb) != policy['prepared_APB_sha256']:
        raise ValueError('actual prepared APB source differs from locked policy')
    names = ('m_bus_endpoint', 'w_bus_endpoint', 'phone_batch_m', 'phone_batch_w', 'phone_window_tx', 'phone_window_rx',
             'pcm_block_tx', 'pcm_block_rx', 'record_ingress', 'final_tap_export',
             'phone_command_ingress', 'phone_command_proxy', 'phone_command_mux',
             'record_source_gate', 'lcd_transport', 'lcd_phy')
    sources = [ROOT / ('rtl/workstation/workstation_task3_' + n + '.sv') for n in names]
    sources += [ROOT / p for p in ('rtl/music/workstation_task3_tf_analysis_source.sv',
                'rtl/music/workstation_task3_score_commit_m.sv', 'rtl/audio/workstation_ae350_pcm_owner.sv')]
    here = Path(__file__).resolve().parent
    top = here / 'task3_phone_lcd_cosim.sv'
    cpp = here / 'task3_phone_lcd_cosim.cpp'
    adapter = ROOT / 'sim/audio/run_task3_phone_firmware_workload.py'
    tracked = [*sources, top, cpp, Path(__file__).resolve(), adapter, policy_path,
               ROOT / 'rtl/workstation/task3_paired_channels.vh',
               *sorted((ROOT / 'sim/fixtures').glob('task3_phone_firmware_*')),
               *sorted((ROOT / 'firmware/ae350').glob('*.[ch]')),
               ROOT / 'tools/prepare_ae350_sbc.py']
    before = {str(p): sha(p) for p in tracked}
    report = dict(schema='task3-real-firmware-ideal-LCD-workload-v2', passed=False, phone_batch=phone_batch,
                  project=str(project), prepared_APB_sha256=sha(apb), inputs_sha256=before,
                  commands=[], cases=[], hardware_tested=False, bitstream=None,
                  sustained_phone_audio_accepted=False, physical_budget_authorized=False,
                  actual_RTL=['M/W endpoints', 'LCD transport and PHY with default maintenance',
                              'policy-locked M APB held-command CDC', 'original PCM1 owner with optional frozen snapshot'],
                  actual_firmware=['unmodified runtime_pass four times per pump',
                                   'explicit paired-v3 PCM poll/submit/cancel and original runtime timeout' if phone_batch else
                                   'original PCM poll/submit/timeout/cancel/command checks'],
                  observer_reset_policy='batch only: revoke phone lease resets observer APB CDC; owner root/retired stream/capture lifetime remains independent',
                  model_assumptions=['ideal zero-delay cross-wires; no electrical validation',
                     'M50MHz, W50MHz or45.45MHz phase3ns, audio average76.8MHz',
                     'synthetic TF analysis and final-tap sources each offered48k; TF may pause at256 frames',
                     'analysis sink stalls3.96ms; record sink always accepts through actual ingress',
                     'established Classic/security and decoded constant128-frame stereo blocks injected',
                     'idle local HCI model; native C except MMIO costs zero model time',
                     'one private pending block; external producer backlog only observed, never buffered',
                     'fixed48k; clock-owner branch prohibited'],
                  counting_semantics=['first ready/COMMIT/SELECT/failure times are observations after four-pass pump, upper bounds within one pump',
                     'window packet count is endpoint-to-transport acceptance; not wire completion or128-frame firmware block',
                     'sample_ticks counts externally offered sample_take, not DSP/I2S output acceptance',
                     'constant nonzero stereo check is finite owner-output coverage; not unique block order proof'],
                  not_verified=['actual RF/HCI/SBC/CPU scheduling', 'CNN compute or DDR recording/download',
                     'TF card/FAT', 'DSP/D effects/final physical tap/I2S/DAC',
                     'electrical throughput/RTT/jitter', 'P&R/resources/CDC/STA/PLL or deployment'])

    def command(name, argv, cwd=None, timeout=180):
        result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=timeout)
        log = output / (name + '.log')
        log.write_text(result.stdout)
        report['commands'].append(dict(argv=list(map(str, argv)), returncode=result.returncode,
                                      log=str(log), log_sha256=sha(log)))
        if result.returncode:
            raise RuntimeError('failed model command: ' + str(log))
        return result.stdout

    try:
        spec = importlib.util.spec_from_file_location('task3_firmware_builder', adapter)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        library = module.build_library(output / 'firmware', run_smoke=True)
        report['firmware_library'] = dict(path=str(library), sha256=sha(library),
                                         receipt_sha256=sha(output / 'firmware/verification.json'))
        snapshot = output / 'inputs'
        for p in [*sources, top, cpp, ROOT / 'rtl/workstation/task3_paired_channels.vh']:
            target = snapshot / p.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            if sha(target) != before[str(p)]:
                raise RuntimeError('source drift during snapshot: ' + str(p))
        cdc = snapshot / 'prepared_APB.sv'
        shutil.copyfile(apb, cdc)
        if sha(cdc) != policy['prepared_APB_sha256']:
            raise RuntimeError('prepared APB drift during snapshot')
        obj = output / 'obj'
        report['verilator'] = command('verilator_version', ['verilator', '--version']).strip()
        build_log = command('build', ['verilator', '--cc', '--exe', '--build', '-j', '4', '-Wno-fatal',
            '--top-module', 'task3_phone_lcd_cosim', '--Mdir', obj,
            '-GPHONE_BATCH=' + str(int(phone_batch)),
            '-I' + str(snapshot), '-CFLAGS', '-std=c++17 ' + ('-DTASK3_MODEL_PHONE_BATCH ' if phone_batch else '') + '-I' + str(ROOT / 'sim/fixtures'),
            '-LDFLAGS', str(library), snapshot / cpp.relative_to(ROOT),
            *[snapshot / p.relative_to(ROOT) for p in sources], cdc,
            snapshot / top.relative_to(ROOT)], cwd=snapshot)
        # Preserve the three pre-existing width warnings in record_ingress;
        # every other warning remains a hard failure for this diagnostic model.
        warnings = re.findall(r'^%Warning-([^:]+): (.+?):(\d+):.*$', build_log, re.M)
        expected_warnings = [('WIDTHEXPAND', str(snapshot / 'rtl/workstation/workstation_task3_record_ingress.sv'), str(line))
                             for line in (53, 61, 89)]
        report['preserved_existing_model_compile_warnings'] = warnings
        if sorted(warnings) != sorted(expected_warnings):
            raise ValueError('unexpected model compilation warning inventory')
        for half in (10, 11):
            for name, concurrent, inject in [('production_gate', True, False),
                                              ('injected_phone_only', False, True),
                                              ('injected_three_streams', True, True)]:
                case_name = name + '_W' + str(half)
                path = output / (case_name + '.json')
                command(case_name, [obj / 'Vtask3_phone_lcd_cosim', half, int(concurrent),
                                    int(inject), duration_ms, path], timeout=180)
                case = json.loads(path.read_text())
                if case['mmio_errors'] != case['mmio_errors_after_owner_underrun'] or case['clock_reads'] or case['clock_writes']:
                    raise ValueError('unexpected bus error/clock owner branch')
                if case['malformed_packets'] or case['stale_packets']:
                    raise ValueError('unexpected malformed/stale modeled packet')
                if case['final_fault_bits'] & 0xc3:
                    raise ValueError('unexpected transport/CRC/sequence/overflow fault')
                if case['final_fault_bits'] & 0x38:
                    raise ValueError('analysis/record source failed; independent progress not established')
                if case['ticks_after_cancel'] < case['ticks_before_cancel'] + 40:
                    raise ValueError('audio schedule stopped during cancellation')
                if case['owner_selected_after_cancel'] or case['owner_queued_after_cancel']:
                    raise ValueError('actual owner did not retire source/queued PCM after cancellation')
                if concurrent and (case['analysis_received'] < 100 or case['record_received'] < 100 or
                                   not case['stall_done'] or case['record_frames_during_analysis_stall'] < 100):
                    raise ValueError('missing independent stream/analysis congestion coverage')
                if not inject and (case['observed_caps'] != 0x67 or case['window_writes'] or case['owner_source_commands'] or
                                   case['accepted_blocks'] or case['owner_selected'] or case['final_fault_bits']):
                    raise ValueError('production sustained-audio refusal failed')
                if inject and (case['observed_caps'] != 0x67 or case['submit_calls'] < 8 or
                               case['window_writes'] < 128 or case['accepted_blocks'] < 1):
                    raise ValueError('missing real firmware submission workload')
                if inject and not phone_batch and (not case['owner_failed'] or case['owner_failure'] != 4):
                    raise ValueError('expected actual owner underrun was not reproduced; re-evaluate model conclusions')
                if inject and phone_batch and (case['owner_failed'] or case['firmware_fault'] or case['media_fault'] or case['final_fault_bits'] or
                                              case['accepted_blocks'] < duration_ms * 3 // 8 - 1 or case['maximum_offer_backlog_blocks'] > 1 or
                                              case['exact_nonzero_stereo_outputs'] < duration_ms * 48 - 512):
                    raise ValueError('batch mode failed finite model refill coverage; not sustained acceptance')
                case['observation'] = ('production capability refuses sustained phone startup' if not inject else
                    'injected capability only: sustained path fails in this optimistic model' if
                    case['owner_failed'] or case['firmware_fault'] or case['media_fault'] or case['final_fault_bits'] else
                    'injected capability only: finite model window without owner failure; not sustained acceptance')
                report['cases'].append(dict(name=case_name, path=str(path), sha256=sha(path), **case))
                print(case_name, case['observation'], 'commits=', case['accepted_blocks'],
                      'owner_failure=', case['owner_failure'], 'nonzero=', case['exact_nonzero_stereo_outputs'], flush=True)
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        report['prepared_APB_unchanged'] = sha(apb) == policy['prepared_APB_sha256']
        report['firmware_artifacts_unchanged'] = (sha(library) == report['firmware_library']['sha256'] and
            sha(output / 'firmware/verification.json') == report['firmware_library']['receipt_sha256'])
        if not report['source_unchanged'] or not report['prepared_APB_unchanged'] or not report['firmware_artifacts_unchanged']:
            raise ValueError('inputs changed during cosimulation')
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration-ms', type=int, default=40)
    parser.add_argument('--phone-batch', action='store_true', help='explicit paired v3 RTL and firmware; production CAPS remains closed')
    args = parser.parse_args()
    run(args.project, args.output, args.duration_ms, args.phone_batch)
