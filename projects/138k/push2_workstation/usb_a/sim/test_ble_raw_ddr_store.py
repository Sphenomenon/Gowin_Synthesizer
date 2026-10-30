#!/usr/bin/env python3
"""Exercise the raw BLE DDR store; generated simulation files stay in --output."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STORE = 'rtl/memory/workstation_ble_raw_ddr_store.sv'
FIXTURE = 'sim/memory/tb_ble_raw_ddr_store.sv'
SOURCES = (STORE, 'rtl/memory/workstation_sdp.sv', 'rtl/music/music_async_fifo.sv',
           'rtl/memory/workstation_recording_ddr_native_bridge.sv')
CONTRACT = 'rtl/memory/WORKSTATION_BLE_RAW_DDR_STORE.md'
ALLOWED_WARNINGS = {
    ('UNUSEDPARAM', 'rtl/music/music_async_fifo.sv', "Parameter is not used: 'RAM_STYLE'"),
    ('UNUSEDSIGNAL', 'rtl/music/music_async_fifo.sv', "Signal is not used: 'full'"),
    ('SYNCASYNCNET', STORE, "Signal flopped as both synchronous and async: 'workstation_ble_raw_ddr_store.control_release'"),
    ('SYNCASYNCNET', STORE, "Signal flopped as both synchronous and async: 'workstation_ble_raw_ddr_store.memory_release'"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError('negative-control anchor drift: ' + anchor)
    return source.replace(anchor, replacement)


def verify(output):
    output.mkdir(parents=True, exist_ok=False)
    inputs = (*SOURCES, FIXTURE, CONTRACT, str(Path(__file__).resolve().relative_to(ROOT)))
    hashes = {name: sha((ROOT / name).read_bytes()) for name in inputs}
    identity = sha(json.dumps(hashes, sort_keys=True).encode())
    result = dict(schema=1, passed=False, source_set_sha256=identity, source_sha256=hashes,
                  scope='raw storage component; BLE business owner and owner8 integration are external',
                  synthesis=False, pnr=False, hardware_tested=False, sram_programmed=False,
                  flash_written=False, cases={})

    def simulate(name, parameters=None, mutant=None, expected_failure=None):
        stage = output / name
        stage.mkdir()
        source_paths = {name: ROOT / name for name in SOURCES}
        if mutant is not None:
            source_paths[STORE] = stage / 'workstation_ble_raw_ddr_store.sv'
            source_paths[STORE].write_text(mutant)
        parameters = parameters or {}
        argv = ['iverilog', '-g2012', '-s', 'tb_ble_raw_ddr_store', '-o', str(stage / 'test.vvp')]
        argv += ['-Ptb_ble_raw_ddr_store.' + key + '=' + str(value) for key, value in parameters.items()]
        argv += [str(ROOT / FIXTURE), *map(str, source_paths.values())]
        compiled = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        compile_log = compiled.stdout + compiled.stderr
        (stage / 'compile.log').write_text(compile_log)
        if compiled.returncode or compile_log.strip():
            raise RuntimeError(name + ' compile diagnostics: ' + compile_log)
        run_argv = ['vvp', str(stage / 'test.vvp')]
        run = subprocess.run(run_argv, capture_output=True, text=True, timeout=60)
        log = run.stdout + run.stderr
        (stage / 'run.log').write_text(log)
        entry = dict(parameters=parameters, compile_argv=argv, run_argv=run_argv,
                     returncode=run.returncode, compile_log_sha256=sha(compile_log.encode()),
                     run_log=log, run_log_sha256=sha(log.encode()),
                     compiled_store_sha256=sha(source_paths[STORE].read_bytes()))
        if expected_failure:
            entry.update(expected_failure=expected_failure,
                         rejected=run.returncode != 0 and expected_failure in log)
            if not entry['rejected']:
                raise RuntimeError(name + ' negative control escaped: ' + log)
            print('PASS rejected ' + name + ': ' + expected_failure, flush=True)
        else:
            metrics = re.search(r'PASS BLE_RAW_DDR_STORE checks=(\d+) full_frames=(\d+) max_fetch_bytes=(\d+)', log)
            if run.returncode or not metrics:
                raise RuntimeError(name + ' failed: ' + log)
            entry['metrics'] = dict(zip(('checks', 'full_frames', 'max_fetch_bytes'), map(int, metrics.groups())))
            print(name + ': ' + metrics.group(0), flush=True)
        result['cases'][name] = entry

    try:
        simulate('fifo8_async_memory', dict(FIFO_BITS=8, MEM_HALF=7))
        simulate('fifo3_100mhz_memory', dict(FIFO_BITS=3, MEM_HALF=5))
        source = (ROOT / STORE).read_text()
        mutants = (
            ('held_valid_generation_recounted',
             "if(((start_valid_i && !start_seen) || (clear_valid_i && !clear_seen)) &&\n               generation==32'hffffffff)begin",
             "if((start_valid_i || clear_valid_i) && generation==32'hffffffff)begin",
             'held CLEAR at final generation completes once'),
            ('start_rejects_new_epoch_fifo',
             'if(!memory_empty || !memory_closed',
             'if(!memory_empty || fifo_read_valid || !memory_closed', 'real transport drain'),
            ('same_edge_response_rejected',
             'wire response_bad=read_response_i && !read_outstanding && !native_read_commit;',
             'wire response_bad=read_response_i && !read_outstanding;', 'complete fetch publishes cache'),
            ('slot_mistaken_for_native_accept',
             'wire native_commit=published_valid && native_ready;',
             'wire native_commit=published_valid && slot_valid_o && slot_ready_i;', 'ordered close admission'),
            ('partial_mask_lost',
             "ddr_mask_o<=32'hffffffff<<(pack_frames*4);",
             "ddr_mask_o<=32'd0;", 'last partial byte mask preserves unused data'),
        )
        for name, anchor, replacement, expected in mutants:
            simulate(name, mutant=replace_once(source, anchor, replacement), expected_failure=expected)
        lint_argv = ['verilator', '--lint-only', '--timing', '-Wall', '-Wno-fatal',
                     '--top-module', 'workstation_ble_raw_ddr_store', *[str(ROOT / name) for name in SOURCES]]
        lint = subprocess.run(lint_argv, capture_output=True, text=True, timeout=30)
        lint_log = lint.stdout + lint.stderr
        (output / 'lint.log').write_text(lint_log)
        warnings = []
        for code, path, message in re.findall(r'^%Warning-([^:]+): (.*?):\d+:\d+: (.*)$', lint_log, re.M):
            warnings.append((code, str(Path(path).relative_to(ROOT)), message))
        result['lint'] = dict(argv=lint_argv, returncode=lint.returncode,
                              log_sha256=sha(lint_log.encode()), reviewed_warnings=warnings)
        if lint.returncode or len(warnings) != len(ALLOWED_WARNINGS) or set(warnings) != ALLOWED_WARNINGS:
            raise RuntimeError('lint error or reviewed-warning inventory drift: ' + lint_log)
        print('PASS lint: exact four reviewed warnings; no broad diagnostic waiver', flush=True)
        result['source_inputs_unchanged_during_run'] = hashes == {
            name: sha((ROOT / name).read_bytes()) for name in inputs}
        if not result['source_inputs_unchanged_during_run']:
            raise ValueError('source changed during verification')
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args().output.resolve())
