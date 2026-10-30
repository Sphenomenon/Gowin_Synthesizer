#!/usr/bin/env python3
"""Compile maintained AE350 workstation firmware, without changing a project or board."""

from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.stage_usb_firmware import compiler_prefix, sha
from tools.workstation_baselines import load_baseline


IMPORTED_SOURCES = ('start.S', 'ui_main.c', 'ui_render.c', 'ui_runtime.c')
IMPORTED_HEADERS = ('audio_services.h', 'firmware_checks.h', 'ui_model.h', 'ui_render.h')
FIRST_PARTY_SOURCES = ('audio_clock_service.c',)
FIRST_PARTY_HEADERS = ('audio_clock_service.h',)
SOURCES = (*IMPORTED_SOURCES, *FIRST_PARTY_SOURCES)
HEADERS = (*IMPORTED_HEADERS, *FIRST_PARTY_HEADERS)
INPUTS = (*SOURCES, *HEADERS, 'boot.ld', 'provenance.json')
ROM_BASE, ROM_BYTES = 0x80000000, 16384
RAM_START, RAM_END, MIN_STACK_BYTES = 0x200, 0x2000, 4096


def decode_rom(path):
    """Read the ROM's exact 4096 little-endian words; reject truncated references."""
    words = Path(path).read_text().splitlines()
    if len(words) != ROM_BYTES // 4 or any(not re.fullmatch('[0-9a-fA-F]{8}', word) for word in words):
        raise ValueError('AE350 reference ROM must contain exactly 4096 hexadecimal words')
    return b''.join(int(word, 16).to_bytes(4, 'little') for word in words)


def memory_report(size_text, symbols_text, start_text, binary_bytes):
    rows = [line.split() for line in size_text.splitlines()]
    values = next((row for row in rows if len(row) >= 6 and all(value.isdecimal() for value in row[:3])), None)
    if values is None:
        raise ValueError('cannot read AE350 text/data/bss sizes')
    text, data, bss = map(int, values[:3])
    symbols = {}
    for line in symbols_text.splitlines():
        fields = line.split()
        if len(fields) == 3 and re.fullmatch('[0-9a-fA-F]+', fields[0]):
            symbols[fields[2]] = int(fields[0], 16)
    required = ('_start', '__data_load_start', '__data_start', '__data_end', '__bss_start', '__bss_end')
    if any(name not in symbols for name in required):
        raise ValueError('AE350 linker symbols missing: ' + ', '.join(name for name in required if name not in symbols))
    if symbols['_start'] != ROM_BASE:
        raise ValueError('AE350 reset entry must remain at 0x80000000')
    stack_literals = re.findall(r'^\s*li\s+sp,\s*(0x[0-9a-fA-F]+|[0-9]+)\s*$', start_text, re.MULTILINE)
    if len(stack_literals) != 1 or int(stack_literals[0], 0) != RAM_END:
        raise ValueError('AE350 startup must establish the audited stack top at 0x2000')
    if not 0 < binary_bytes <= ROM_BYTES or text + data > ROM_BYTES:
        raise ValueError('AE350 Boot ROM overflow or empty binary')
    if not (RAM_START == symbols['__data_start'] <= symbols['__data_end'] <=
            symbols['__bss_start'] <= symbols['__bss_end'] <= RAM_END - MIN_STACK_BYTES):
        raise ValueError('AE350 RAM globals overlap the reserved 4096-byte stack')
    if not (ROM_BASE <= symbols['__data_load_start'] <= ROM_BASE + ROM_BYTES and
            symbols['__data_load_start'] + data <= ROM_BASE + ROM_BYTES):
        raise ValueError('AE350 initialized data escapes the Boot ROM')
    static_end = symbols['__bss_end']
    return dict(rom_capacity_bytes=ROM_BYTES, binary_bytes=binary_bytes, text_bytes=text,
                initialized_data_bytes=data, bss_bytes=bss, physical_ram_bytes=RAM_END,
                ram_reserved_prefix_bytes=RAM_START, static_ram_span_bytes=static_end - RAM_START,
                static_ram_end=static_end, stack_top=RAM_END, stack_capacity_bytes=RAM_END - static_end,
                minimum_stack_bytes=MIN_STACK_BYTES, symbols={name: symbols[name] for name in required},
                whole_program_stack_bound_verified=False, hardware_stack_watermark_verified=False)


def stage_ae350_firmware(root, output, riscv_prefix=None, *, reference_mem=None):
    """Build to a new directory and return provenance, capacity and ROM comparison.

    The caller explicitly installs output/boot.mem into its new candidate. Accepted
    and pinned profiles keep their locked ROM unless that caller selects this path.
    """
    root, output = Path(root).resolve(), Path(output).resolve()
    source_dir = root / 'firmware/ae350'
    if output.exists():
        raise FileExistsError('AE350 firmware output already exists: ' + str(output))
    for name in INPUTS:
        if not (source_dir / name).is_file():
            raise FileNotFoundError('missing maintained AE350 firmware input: ' + name)
    provenance = json.loads((source_dir / 'provenance.json').read_text())
    baseline = load_baseline(root, 'resource_rework_route0')
    if provenance.get('schema') != 1 or provenance.get('imported_from') != baseline.evidence():
        raise ValueError('AE350 import provenance does not match the locked baseline')
    if set(provenance.get('files', {})) != set((*IMPORTED_SOURCES, *IMPORTED_HEADERS, 'boot.ld')):
        raise ValueError('AE350 imported source inventory drift')
    for name in (*IMPORTED_SOURCES, *IMPORTED_HEADERS, 'boot.ld'):
        if provenance['files'].get(name) != baseline.descriptor['files']['firmware/' + name]:
            raise ValueError('AE350 imported source provenance drift: ' + name)
    if set(provenance.get('first_party_files', {})) != set((*FIRST_PARTY_SOURCES, *FIRST_PARTY_HEADERS)):
        raise ValueError('AE350 first-party source inventory drift')
    for name in (*FIRST_PARTY_SOURCES, *FIRST_PARTY_HEADERS):
        expected = dict(kind='maintained_first_party',
                        source='projects/138k/push2_workstation/usb_a/firmware/ae350/' + name,
                        sha256=sha(source_dir / name))
        if provenance['first_party_files'][name] != expected:
            raise ValueError('AE350 first-party source provenance drift: ' + name)
    if provenance.get('historical_rom') != dict(path='firmware/boot.mem', **baseline.descriptor['files']['firmware/boot.mem']):
        raise ValueError('AE350 historical ROM provenance drift')
    identities = {str((source_dir / name).relative_to(root)): sha(source_dir / name) for name in INPUTS}
    prefix = compiler_prefix(riscv_prefix)
    versions = {}
    for tool in ('gcc', 'objcopy', 'size', 'nm'):
        versions[tool] = subprocess.run([prefix + '-' + tool, '--version'], capture_output=True,
                                        text=True, check=True).stdout.splitlines()[0]
    reference_bytes = baseline.read_bytes('firmware/boot.mem')
    reference_description = dict(policy='locked_resource_rework_route0', sha256=provenance['historical_rom']['sha256'])
    if reference_mem is not None:
        reference_mem = Path(reference_mem).resolve()
        decode_rom(reference_mem)
        reference_bytes = reference_mem.read_bytes()
        reference_description = dict(policy='explicit_reference', path=str(reference_mem), sha256=sha(reference_mem))
    output.mkdir(parents=True, exist_ok=False)
    for name in INPUTS:
        shutil.copyfile(source_dir / name, output / name)
    (output / 'reference_boot.mem').write_bytes(reference_bytes)
    reference_image = decode_rom(output / 'reference_boot.mem')
    common = ['-march=rv32im_zicsr', '-mabi=ilp32', '-msmall-data-limit=0', '-O2', '-ffreestanding',
              '-Wall', '-Wextra', '-Werror']
    commands = []
    with (output / 'build.log').open('w') as log:
        def run(command):
            commands.append(command)
            subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
        objects = []
        for name in SOURCES:
            target = Path(name).with_suffix('.o').name
            run([prefix + '-gcc', *common, '-fstack-usage', '-c', name, '-o', target])
            objects.append(target)
        run([prefix + '-gcc', '-march=rv32im_zicsr', '-mabi=ilp32', '-msmall-data-limit=0',
             '-nostdlib', '-nostartfiles', '-Wl,--build-id=none,-Map=firmware.map,-T,boot.ld',
             *objects, '-o', 'firmware.elf'])
        run([prefix + '-objcopy', '-O', 'binary', 'firmware.elf', 'firmware.bin'])
    size = subprocess.run([prefix + '-size', 'firmware.elf'], cwd=output, capture_output=True, text=True, check=True)
    symbols = subprocess.run([prefix + '-nm', '-n', 'firmware.elf'], cwd=output, capture_output=True, text=True, check=True)
    (output / 'firmware.size').write_text(size.stdout)
    (output / 'firmware.nm').write_text(symbols.stdout)
    binary = (output / 'firmware.bin').read_bytes()
    capacity = memory_report(size.stdout, symbols.stdout, (output / 'start.S').read_text(), len(binary))
    padded = binary.ljust(ROM_BYTES, b'\0')
    rom = output / 'boot.mem'
    rom.write_text(''.join(f'{int.from_bytes(padded[index:index+4], "little"):08x}\n'
                           for index in range(0, ROM_BYTES, 4)))
    for relative, expected in identities.items():
        if sha(root / relative) != expected or sha(output / Path(relative).name) != expected:
            raise ValueError('AE350 firmware input changed during compilation: ' + relative)
    stack_frames = []
    for path in sorted(output.glob('*.su')):
        for line in path.read_text().splitlines():
            fields = line.split('\t')
            if len(fields) == 3 and fields[1].isdecimal():
                stack_frames.append(dict(function=fields[0], bytes=int(fields[1]), kind=fields[2]))
    if any(frame['bytes'] > capacity['stack_capacity_bytes'] for frame in stack_frames):
        raise ValueError('AE350 individual compiler stack frame exceeds stack capacity')
    result = dict(schema=1, firmware_profile='maintained_ae350_workstation', isa='rv32im_zicsr', abi='ilp32',
                  compiler_prefix=prefix, compiler_version=versions['gcc'], tool_versions=versions,
                  source_provenance=provenance, input_sha256=identities,
                  changed_from_import=[name for name in (*IMPORTED_SOURCES, *IMPORTED_HEADERS, 'boot.ld')
                                       if sha(source_dir / name) != provenance['files'][name]['sha256']],
                  first_party_inputs={name: sha(source_dir / name)
                                      for name in (*FIRST_PARTY_SOURCES, *FIRST_PARTY_HEADERS)},
                  imported_inputs={name: sha(source_dir / name)
                                   for name in (*IMPORTED_SOURCES, *IMPORTED_HEADERS, 'boot.ld')},
                  compiled_sources=list(SOURCES),
                  commands=commands, capacity=capacity, compiler_stack_frames=stack_frames,
                  elf_sha256=sha(output / 'firmware.elf'), binary_sha256=sha(output / 'firmware.bin'),
                  rom_sha256=sha(rom), reference_rom=dict(reference_description,
                      byte_identical=rom.read_bytes() == reference_bytes, words_identical=padded == reference_image,
                      differing_words=sum(padded[i:i+4] != reference_image[i:i+4] for i in range(0, ROM_BYTES, 4))),
                  hardware_tested=False, project_rom_installed=False,
                  stack_validation='Compiler per-function sizes and reserved capacity; whole-call-chain and runtime high-water mark remain unverified.')
    (output / 'build_metadata.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new firmware evidence directory')
    parser.add_argument('--riscv-prefix', help='GNU bare-metal tool prefix, ending before -gcc')
    parser.add_argument('--reference-mem', type=Path, help='optional explicit 4096-word comparison ROM')
    args = parser.parse_args()
    result = stage_ae350_firmware(Path(__file__).resolve().parents[1], args.output,
                                args.riscv_prefix, reference_mem=args.reference_mem)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
