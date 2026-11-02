#!/usr/bin/env python3
"""Exercise two PCM streams over the real LCD RTL with ideal zero-delay wires."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


def run(output):
    root = Path(__file__).resolve().parents[2]
    sources = [root / ('rtl/workstation/workstation_task3_' + name + '.sv')
               for name in ('lcd_transport', 'lcd_phy', 'pcm_block_tx', 'pcm_block_rx')]
    sources.append(Path(__file__).with_name('tb_task3_pcm_block_transport.sv'))
    tracked = [*sources, Path(__file__).resolve()]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, source_sha256=before,
        scope='actual PCM block TX/RX and LCD transport/PHY, two M-to-W streams, ideal zero-delay wires; endpoint negotiation, CNN engine and recording object are not instantiated',
        M_clock_Hz=50000000, W_clock_Hz_tested=[50000000, 1000000000 / 22],
        recording_source_schedule_Hz=48000, analysis_source_schedule_Hz=48000,
        analysis_source_can_pause=True, source_queue_frames_per_stream=256,
        recording_sink_ready='one receiving clock edge in seven',
        synthetic_M_to_W_control_offered_Hz=5000,
        physical_throughput_Bps=None, physical_RTT_ns=None, hardware_tested=False,
        physical_budget_authorized=False, business_configuration_changed=False,
        trials=[], commands=[])

    def command(name, argv):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
        path = output / (name + '.log')
        path.write_text(result.stdout)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode, log=str(path), log_sha256=sha(path)))
        if result.returncode:
            raise RuntimeError('model failed: ' + str(path))
        return result.stdout

    try:
        report['verilator'] = command('verilator_version', ['verilator', '--version']).strip()
        for half in (10, 11):
            name = 'dual48k_W_half_' + str(half)
            obj = output / (name + '_obj')
            command(name + '_build', ['verilator', '--binary', '--timing', '--build-jobs', '4',
                '--top-module', 'tb_task3_pcm_block_transport', '-GW_HALF_NS=' + str(half),
                '--Mdir', str(obj), *map(str, sources)])
            text = command(name + '_run', [str(obj / 'Vtb_task3_pcm_block_transport')])
            if 'PASS task3_pcm_block_transport' not in text:
                raise RuntimeError('missing model completion')
            pattern = (r'PCM_BLOCK_MODEL frames_per_stream=(\d+) elapsed_ns=(\d+) record_max_gap_ns=(\d+) '
                r'analysis_credit_stall_M_cycles=(\d+) record_frames_during_analysis_stall=(\d+) '
                r'controls_during_analysis_stall=(\d+) controls=(\d+) max_source_queue_analysis=(\d+) max_source_queue_record=(\d+) blocks_analysis=(\d+) blocks_record=(\d+) '
                r'M_probe_results=(\d+) W_probe_results=(\d+) M_probe_max_RTT_cycles=(\d+) W_probe_max_RTT_cycles=(\d+)')
            rows = list(re.finditer(pattern, text))
            if len(rows) != 1:
                raise RuntimeError('missing unique model counters')
            (frames, elapsed_ps, gap_ps, credit_stall, record_progress, control_progress, controls, analysis_max_queue, record_max_queue,
             analysis_blocks, record_blocks, m_probes, w_probes, m_rtt, w_rtt) = map(int, rows[0].groups())
            elapsed_ns, gap_ns = elapsed_ps / 1000, gap_ps / 1000
            if (frames != 4099 or elapsed_ns <= 0 or gap_ns <= 0 or gap_ns > 500000 or
                    credit_stall <= 0 or record_progress < 100 or control_progress < 10 or
                    controls < control_progress or analysis_max_queue <= 0 or analysis_max_queue > 256 or record_max_queue <= 0 or record_max_queue > 256 or analysis_blocks <= 0 or record_blocks <= 0 or
                    m_probes <= 0 or w_probes <= 0 or m_rtt <= 0 or w_rtt <= 0):
                raise RuntimeError('invalid model coverage counters')
            report['trials'].append(dict(W_clock_Hz=1000000000 / (2 * half), W_initial_phase_ns=3,
                frames_received_and_checked_per_stream=frames, elapsed_model_ns=elapsed_ns,
                recording_max_consumer_service_gap_model_ns=gap_ns,
                analysis_consumer_stall_W_cycles=180000,
                analysis_consumer_stall_model_ns=180000 * 2 * half,
                analysis_wait_for_credit_M_cycles=credit_stall,
                recording_frames_delivered_during_analysis_stall=record_progress,
                synthetic_controls_delivered_during_analysis_stall=control_progress,
                synthetic_control_requests_and_matching_echoes=controls,
                maximum_source_queued_frames=dict(analysis=analysis_max_queue, recording=record_max_queue),
                analysis_blocks=analysis_blocks, recording_blocks=record_blocks,
                completed_probe_results=dict(M=m_probes, W=w_probes),
                max_probe_RTT_local_cycles=dict(M=m_rtt, W=w_rtt),
                recording_tick_lost=False, transport_CRC_sequence_or_overflow_fault=False,
                physical_acceptance=False))
            print(text, end='')
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        if not report['source_unchanged']:
            raise RuntimeError('model source changed during run')
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
