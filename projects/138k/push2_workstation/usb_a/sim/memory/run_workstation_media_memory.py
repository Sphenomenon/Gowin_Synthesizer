#!/usr/bin/env python3
"""Exercise the unselected W-media BIST/owner5/6/8 composition, without a board."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MODULE = 'rtl/memory/workstation_media_memory.sv'
TB = 'sim/memory/tb_workstation_media_memory.sv'
SOURCES = (
    'rtl/memory/workstation_ddr_bist.v',
    'rtl/music/basic_pitch_ddr_arbiter_pipeline.sv',
    'rtl/music/basic_pitch_ddr_client_queues.sv',
    'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
    'rtl/memory/workstation_recording_ddr_client_queues.sv',
    MODULE,
)
INPUTS = (*SOURCES, TB, 'rtl/ddr_address_map.vh',
          'rtl/memory/WORKSTATION_MEDIA_MEMORY_CONTRACT.md',
          'sim/memory/run_workstation_media_memory.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    include = output / 'include/src/memory/ddr_address_map.vh'
    include.parent.mkdir(parents=True)
    include.write_bytes((ROOT / 'rtl/ddr_address_map.vh').read_bytes())
    hashes = {name: sha(ROOT / name) for name in INPUTS}
    result = dict(schema=1, passed=False, source_sha256=hashes,
                  stage='unselected_task3_w_media_memory_component',
                  actual_components=['ddr3_bist', 'basic_pitch_ddr_client_slot',
                                     'workstation_recording_ddr_client_queues',
                                     'workstation_recording_ddr_arbiter_pipeline'],
                  physical_address_map=True, owners=[0, 5, 6, 8],
                  native_model='ordered 256-bit BL8 memory with per-byte write masks and independently delayed reads',
                  production_profile_selected=False, synthesis=False, pnr=False,
                  bitstream_identity=None, hardware_tested=False, sram_programmed=False, flash_written=False,
                  deadline_guarantee=False, cases={})

    def execute(name, *, seed=7, phase=0, priority=False, mutant=None, expected=None):
        stage = output / name
        stage.mkdir()
        selected = {n: ROOT / n for n in SOURCES}
        if mutant is not None:
            selected[MODULE] = stage / 'workstation_media_memory.sv'
            selected[MODULE].write_text(mutant)
        top = 'tb_media_memory_priority_budget' if priority else 'tb_workstation_media_memory'
        argv = ['iverilog', '-g2012', '-s', top, '-I' + str(output / 'include'), '-I' + str(ROOT),
                '-o', str(stage / 'test.vvp')]
        if not priority:
            argv += [f'-P{top}.SEED={seed}', f'-P{top}.PHASE={phase}']
        argv += [str(selected[n]) for n in SOURCES] + [str(ROOT / TB)]
        compiled = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=45)
        (stage / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(name + ' compilation failed: ' + compiled.stdout + compiled.stderr)
        run_argv = ['vvp', str(stage / 'test.vvp')]
        observed = subprocess.run(run_argv, cwd=ROOT, text=True, capture_output=True, timeout=45)
        log = observed.stdout + observed.stderr
        (stage / 'run.log').write_text(log)
        case = dict(compile_argv=argv, run_argv=run_argv, returncode=observed.returncode,
                    compiled_module_sha256=sha(selected[MODULE]),
                    compile_log_sha256=sha(stage / 'compile.log'), run_log_sha256=sha(stage / 'run.log'),
                    log=log, metrics={k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', log)})
        result['cases'][name] = case
        if expected:
            case.update(expected_failure=expected, rejected=observed.returncode != 0 and expected in log)
            if not case['rejected']:
                raise RuntimeError(name + ' negative control escaped: ' + log)
            print('PASS rejected ' + name, flush=True)
        else:
            if observed.returncode or 'PASS ' not in log:
                raise RuntimeError(name + ' failed: ' + log)
            print(log.strip(), flush=True)

    try:
        for seed, phase in ((7, 0), (31, 3), (127, 9)):
            execute('actual_seed' + str(seed), seed=seed, phase=phase)
        execute('queued_core_saturation_negative_budget', priority=True)
        original = (ROOT / MODULE).read_text()

        def mutation(before, after):
            if original.count(before) != 1:
                raise ValueError('mutation anchor drift: ' + before)
            return original.replace(before, after)

        for name, before, after, expected in (
            ('recording_mask_lost', '.recording_mask(recording_mask_i)', '.recording_mask(32\'d0)',
             'native command/data/mask preserved in owner order'),
            ('recording_response_wrong_owner', 'assign recording_response_o=client_ready_o && recording_response;',
             'assign recording_response_o=client_ready_o && music_response;', 'returned owner is exclusive'),
            ('fault_does_not_fence_native_dispatch', '.app_ready(app_ready_i && !transport_fault_o)',
             '.app_ready(app_ready_i)', 'unowned late response fences on the same edge'),
        ):
            execute(name, mutant=mutation(before, after), expected=expected)
        lint = ['verilator', '--lint-only', '--Wno-fatal', '--top-module', 'workstation_media_memory',
                '-I' + str(output / 'include'), '-I' + str(ROOT), *[str(ROOT / n) for n in SOURCES]]
        checked = subprocess.run(lint, cwd=ROOT, text=True, capture_output=True, timeout=45)
        (output / 'lint.log').write_text(checked.stdout + checked.stderr)
        log = checked.stdout + checked.stderr
        warnings = re.findall(r'^%Warning-([A-Z0-9_]+): (.*?):(\d+):\d+:', log, re.M)
        reviewed = [('TIMESCALEMOD', str(ROOT / 'rtl/memory/workstation_ddr_bist.v'), '3'),
                    ('WIDTHTRUNC', str(ROOT / 'rtl/memory/workstation_ddr_bist.v'), '23'),
                    ('WIDTHEXPAND', str(ROOT / 'rtl/memory/workstation_ddr_bist.v'), '115')]
        result['lint'] = dict(argv=lint, returncode=checked.returncode, log_sha256=sha(output / 'lint.log'),
                              log=log, exact_reviewed_inherited_warnings=warnings,
                              inherited_bist_sha256=sha(ROOT / 'rtl/memory/workstation_ddr_bist.v'),
                              no_new_or_unreviewed_warnings=warnings == reviewed)
        if checked.returncode or warnings != reviewed or '%Error' in log:
            raise RuntimeError('Verilator lint failed or inherited warning inventory drifted: ' + log)
        result['source_unchanged_during_run'] = hashes == {name: sha(ROOT / name) for name in INPUTS}
        if not result['source_unchanged_during_run']:
            raise ValueError('component source drift during verification')
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
