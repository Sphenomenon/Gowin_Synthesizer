#!/usr/bin/env python3
"""Checked-MMIO host regression and real, deterministic RV32 firmware builds."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_ae350_firmware import INPUTS, IMPORTED_SOURCES, stage_ae350_firmware

OWNED = (
    'firmware/ae350/audio_clock_service.c', 'firmware/ae350/audio_clock_service.h',
    'firmware/ae350/README.md', 'tools/stage_ae350_firmware.py',
    'tools/stage_usb_firmware.py', 'tools/workstation_baselines.py',
    'sim/test_stage_ae350_firmware.py', 'sim/ae350_clock_service_host.c',
    'sim/run_ae350_clock_service_api.py',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output, prefix=None, host_cc=None):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('API evidence output already exists: ' + str(output))
    inputs = tuple(dict.fromkeys((*OWNED, *('firmware/ae350/' + name for name in INPUTS))))
    before = {name: sha(ROOT / name) for name in inputs}
    host_cc = host_cc or shutil.which('cc')
    if not host_cc:
        raise FileNotFoundError('host C compiler not found')
    output.mkdir(parents=True)
    commands = []

    def invoke(name, command):
        result = subprocess.run(command, text=True, capture_output=True, timeout=120)
        log = output / (name + '.log')
        log.write_text(result.stdout + result.stderr)
        commands.append(dict(name=name, command=command, exit_code=result.returncode,
                             log_sha256=sha(log)))
        if result.returncode:
            raise RuntimeError(name + ' failed:\n' + log.read_text()[-6000:])
        return result.stdout

    host_version = invoke('host_version', [host_cc, '--version']).splitlines()[0]
    host_executable = output / 'checked_mmio_host'
    invoke('host_compile', [host_cc, '-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
        '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
        '-I' + str(ROOT / 'firmware/ae350'), str(ROOT / 'firmware/ae350/audio_clock_service.c'),
        str(ROOT / 'sim/ae350_clock_service_host.c'), '-o', str(host_executable)])
    host = invoke('host_execution', [str(host_executable)])
    match = re.fullmatch(r'PASS ae350_clock_service_host checks=(\d+) submit_max=9 poll_max=11\n', host)
    if not match:
        raise ValueError('host regression did not report its checked completion marker')

    first = stage_ae350_firmware(ROOT, output / 'first', prefix)
    second = stage_ae350_firmware(ROOT, output / 'second', prefix)
    for field in ('elf_sha256', 'binary_sha256', 'rom_sha256'):
        if first[field] != second[field]:
            raise ValueError('RV32 output is not deterministic: ' + field)
    # The API is linked as maintained first-party code, with no call or include
    # from the four original compile inputs and no new startup action.
    for name in IMPORTED_SOURCES:
        if 'a138_clock_' in (ROOT / 'firmware/ae350' / name).read_text():
            raise ValueError('unexpected automatic clock API reference: ' + name)
    symbols = (output / 'first/firmware.nm').read_text()
    for symbol in ('a138_clock_mmio_bus', 'a138_clock_probe', 'a138_clock_submit', 'a138_clock_poll'):
        if not re.search(r'(?m)^[0-9a-f]+ T ' + symbol + '$', symbols):
            raise ValueError('API not present in full linked ROM: ' + symbol)
    disassembly = invoke('rv32_disassembly', [first['compiler_prefix'] + '-objdump', '-d',
                                             str(output / 'first/firmware.elf')])
    functions = dict(re.findall(r'(?ms)^[0-9a-f]+ <([^>]+)>:\n(.*?)(?=^[0-9a-f]+ <|\Z)', disassembly))
    fences = {}
    for name in ('mmio_read', 'mmio_write'):
        fences[name] = len(re.findall(r'\b0ff0000f\b', functions.get(name, '')))
        if fences[name] != 2:
            raise ValueError('RV32 adapter must fence before and after I/O: ' + name)
    after = {name: sha(ROOT / name) for name in inputs}
    if before != after:
        raise ValueError('API verification inputs changed during run')
    identity = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=True, identity='ae350-clock-client-offline-v1-' + identity[:16],
        source_set_sha256=identity, input_sha256=before, inputs_unchanged=True,
        host=dict(compiler=host_cc, compiler_version=host_version, checks=int(match[1]),
                  sanitizer='address,undefined', maximum_submit_accesses=9, maximum_poll_accesses=11,
                  no_retry_loops=True, checked_mmio_model=True, physical_mmio_used=False),
        rv32=dict(first=first, second=second, elf_binary_rom_deterministic=True,
                  full_linked_api_symbols_verified=True, io_fence_counts=fences,
                  original_four_compile_sources_preserved=True, automatic_api_references_in_original_sources=False),
        commands=commands, hardware_tested=False, synthesis_invoked=False,
        project_rom_installed=False, sram_deployed=False, flash_deployed=False,
        new_bitstream_identity=None, constraints_complete=False, release_ready=False,
        limits=['Host model verifies the C access contract, not APB CDC/RTL/media behavior',
                'Raw MMIO cannot recover a bus fault without a platform trap handler',
                'Caller serializes page access and discards tickets after observer reset; ID ABA is not fenced',
                'Whole-program stack depth, runtime watermark, physical ROM boot and board behavior remain unverified'])
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--riscv-prefix')
    parser.add_argument('--host-cc')
    args = parser.parse_args()
    result = run(args.output, args.riscv_prefix, args.host_cc)
    print(json.dumps({key: result[key] for key in ('identity', 'source_set_sha256', 'passed', 'hardware_tested')}))


if __name__ == '__main__':
    main()
