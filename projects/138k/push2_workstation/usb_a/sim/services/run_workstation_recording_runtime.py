#!/usr/bin/env python3
"""Verify R00's real PCM/APB CDC, object service and owner8/native DDR path.

The recording runtime and optional third media owner are maintained RTL. Other
runtime/BLE media owners are terminal-handshake fixtures; this does not test
their audio paths, the sample clock core, physical CDC, P&R, or board operation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = 'tb_workstation_recording_runtime.sv'
TOP = 'tb_workstation_recording_runtime'
SOURCES = (
    'rtl/services/workstation_recording_ddr_service.sv',
    'rtl/services/workstation_recording_seal_bridge.sv',
    'rtl/services/workstation_media_preparation.sv',
    'rtl/workstation/workstation_recording_runtime.sv',
    'rtl/audio/workstation_pcm_observation_bridge.sv',
    'rtl/audio/workstation_pcm_ddr_backend.sv',
    'rtl/memory/workstation_recording_ddr_native_bridge.sv',
    'rtl/memory/workstation_recording_ddr_client_queues.sv',
    'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
    'rtl/memory/workstation_sdp.sv', 'rtl/music/music_async_fifo.sv',
    'rtl/timing/basic_pitch_ddr_client_queues.sv',
    'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv',
)
CASE_NAMES = (
    'pcm_download_bytes_snapshot', 'normal_seal_registered_hold',
    'cancel_before_native_accept', 'observer_reset_drains_accepted_read',
    'sticky_owner_ledger_fault', 'pending_create_media_seal',
    'create_no_source_deadline', 'immutable_actual_context',
    'third_media_owner_stale_ack_native_drain', 'fault_fences_snapshot_same_edge',
    'capture_source_gap', 'actual_48k_descriptor_and_bytes',
    'sticky_observation_loss_requires_common_reset',
)
MUTANTS = {
    'ungated_error': (0, SOURCES[0], '.source_error_i(pcm_valid_i && pcm_error_i)',
        '.source_error_i(pcm_error_i)', 'PCM stereo/sequence byte mismatch'),
    'hold_drops_request': (1, SOURCES[1], 'request_i && !source_pending && ready_sync',
        'request_i && ready_o', 'seal request lost when hold asserted'),
    'stereo_unswapped': (0, SOURCES[3], '.pcm_pair_i({pcm[15:0],pcm[31:16]})',
        '.pcm_pair_i(pcm)', 'PCM stereo/sequence byte mismatch'),
    'observer_reset_clears_loss': (12, SOURCES[3],
        '.reset_ni(reset_ni),.source_clk_i(source_clk_i),.destination_clk_i(memory_clk_i),',
        '.reset_ni(reset_ni && preset_n),.source_clk_i(source_clk_i),.destination_clk_i(memory_clk_i),',
        'CPU observer reset rearmed observation loss'),
    'local_ack': (2, SOURCES[6], 'assign native_ready_o=native_accept_i && submitted_o;',
        'assign native_ready_o=slot_valid_o && slot_ready_i;', 'state deadline got= 4 failure= 9'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(root, output):
    root, output = root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root))
    from tools.workstation_baselines import load_baseline
    from tools.workstation_resource_timing import apb
    baseline = load_baseline(root, 'resource_rework_route0')
    original = {name: (root / name).read_bytes() for name in SOURCES}
    original['rtl/ddr_address_map.vh'] = (root / 'rtl/ddr_address_map.vh').read_bytes()
    fixture = Path(__file__).with_name(FIXTURE).read_bytes()
    held = {name: baseline.read_bytes('src/migration/' + name)
        for name in ('gw138k_apb_cdc.sv', 'gw138k_counter_cdc.sv')}
    selected = dict(original)
    selected['locked/gw138k_apb_cdc.sv'] = apb(held['gw138k_apb_cdc.sv'].decode()).encode()
    selected['locked/gw138k_counter_cdc.sv'] = held['gw138k_counter_cdc.sv']
    selected[FIXTURE] = fixture
    identities = {n: sha(b) for n, b in selected.items()}
    result = dict(schema=1, passed=False,
        identity='r00-runtime-owner8-offline-v1-' + sha(json.dumps(identities, sort_keys=True).encode())[:16],
        source_sha256=identities, runner_sha256=sha(Path(__file__).read_bytes()),
        baseline=baseline.evidence(), original_cdc_sha256={n: sha(b) for n, b in held.items()},
        cdc_policy='checked locked counter; checked locked APB with existing resource timing predecode transform',
        boundary='actual recording runtime PCM/APB CDC + service/backend + native bridge + owner8 queues/core + ordered DDR model; optional third media owner',
        media_other_owners='runtime/BLE ready and terminal fixtures; audio behavior is outside this regression',
        configuration=dict(capacity_frames=64, fifo_address_bits=4,
            source_gap_cycles=20000, ddr_budget_cycles=20000,
            memory_period_ns=10, source_period_ns=14, apb_period_ns=22, control_period_ns=26),
        profile_selected_proven=False, top_composition_tested=False,
        sample_clock_core_tested=False, synthesis=False, pnr=False, hardware_tested=False,
        sram_programmed=False, flash_written=False, cases={})
    for n, b in selected.items():
        p = output / 'sources' / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    include = output / 'src/memory'
    include.mkdir(parents=True)
    (include / 'ddr_address_map.vh').write_bytes(original['rtl/ddr_address_map.vh'])
    compiled_names = [*SOURCES, 'locked/gw138k_apb_cdc.sv', 'locked/gw138k_counter_cdc.sv', FIXTURE]

    def execute(job):
        name, index, mutant = job
        stage = output / name
        stage.mkdir()
        files = {n: output / 'sources' / n for n in compiled_names}
        expected = None
        if mutant:
            _, owner, old, new, expected = MUTANTS[mutant]
            text = selected[owner].decode()
            if text.count(old) != 1:
                raise ValueError('mutation anchor drift: ' + mutant)
            files[owner] = stage / Path(owner).name
            files[owner].write_text(text.replace(old, new))
        command = ['iverilog', '-g2012', '-Wall', '-I', str(output), '-s', TOP,
            '-P' + TOP + '.CASE=' + str(index), '-o', str(stage / 'test.vvp'),
            *[str(files[n]) for n in compiled_names]]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=45)
        (stage / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        executed = None
        log = compiled.stdout + compiled.stderr
        if not compiled.returncode:
            executed = subprocess.run(['vvp', str(stage / 'test.vvp')],
                capture_output=True, text=True, timeout=60)
            log = executed.stdout + executed.stderr
        (stage / 'run.log').write_text(log)
        passed = executed is not None and (
            (executed.returncode != 0 and expected in log) if expected else
            (executed.returncode == 0 and 'PASS runtime independent' in log))
        case = dict(case=index, description=CASE_NAMES[index], mutant=mutant,
            passed=passed, rejected=bool(expected and passed), expected_failure=expected,
            compiled_source_sha256={n: sha(p.read_bytes()) for n, p in files.items()},
            compile_argv=command, compile_returncode=compiled.returncode,
            run_returncode=executed.returncode if executed else None,
            log=log, log_sha256=sha(log.encode()))
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        return name, case

    try:
        jobs = [(name, index, None) for index, name in enumerate(CASE_NAMES)]
        jobs += [('negative_' + n, values[0], n) for n, values in MUTANTS.items()]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for name, case in pool.map(execute, jobs):
                result['cases'][name] = case
        result['product_source_unchanged_during_run'] = all((root / n).read_bytes() == b for n, b in original.items())
        result['passed'] = result['product_source_unchanged_during_run'] and all(c['passed'] for c in result['cases'].values())
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['passed']:
        raise SystemExit('R00 runtime regression failed; inspect ' + str(output / 'verification.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.root, arguments.output)
