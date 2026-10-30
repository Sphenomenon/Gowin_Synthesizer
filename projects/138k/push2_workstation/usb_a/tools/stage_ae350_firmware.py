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
from tools.ae350_local_memory import local_memory_report, verify_elf_image, call_chain_report


IMPORTED_SOURCES = ('start.S', 'ui_main.c', 'ui_render.c', 'ui_runtime.c')
IMPORTED_HEADERS = ('audio_services.h', 'firmware_checks.h', 'ui_model.h', 'ui_render.h')
FIRST_PARTY_SOURCES = ('audio_clock_service.c',)
FIRST_PARTY_HEADERS = ('audio_clock_service.h',)
RECORDING_SOURCES = ('recording_service.c',)
RECORDING_HEADERS = ('recording_service.h',)
LOCAL_MEMORY_INPUTS = ('start_ilm_dlm.inc', 'boot_ilm_dlm.ld')
MEMORY_PROFILES = ('pl16k_8k', 'ilm64k_dlm64k')
SOURCES = (*IMPORTED_SOURCES, *FIRST_PARTY_SOURCES)
HEADERS = (*IMPORTED_HEADERS, *FIRST_PARTY_HEADERS)
INPUTS = (*SOURCES, *HEADERS, 'boot.ld', 'provenance.json')
ROM_BASE, ROM_BYTES = 0x80000000, 16384
RAM_START, RAM_END, MIN_STACK_BYTES = 0x200, 0x2000, 4096


def selected_sources(recording_api=False):
    return (*SOURCES, *RECORDING_SOURCES) if recording_api else SOURCES


def selected_inputs(recording_api=False, memory_profile='pl16k_8k'):
    if memory_profile not in MEMORY_PROFILES:
        raise ValueError('unknown AE350 memory profile: ' + memory_profile)
    inputs = (*INPUTS, *RECORDING_SOURCES, *RECORDING_HEADERS) if recording_api else INPUTS
    return (*inputs, *LOCAL_MEMORY_INPUTS) if memory_profile == 'ilm64k_dlm64k' else inputs


def decode_rom(path, rom_bytes=ROM_BYTES):
    """Read exactly the selected physical ROM size; locked references stay 16 KiB."""
    if rom_bytes not in (16384, 65536):
        raise ValueError('unsupported AE350 ROM capacity')
    words = Path(path).read_text().splitlines()
    if len(words) != rom_bytes // 4 or any(not re.fullmatch('[0-9a-fA-F]{8}', word) for word in words):
        raise ValueError('AE350 ROM must contain exactly ' + str(rom_bytes // 4) + ' hexadecimal words')
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


def stage_ae350_firmware(root, output, riscv_prefix=None, *, reference_mem=None, recording_api=False,
                         memory_profile='pl16k_8k', boot_rom_bytes=ROM_BYTES):
    """Build to a new directory and return provenance, capacity and ROM comparison.

    The caller explicitly installs output/boot.mem into its new candidate. Accepted
    and pinned profiles keep their locked ROM unless that caller selects this path.
    """
    root, output = Path(root).resolve(), Path(output).resolve()
    if boot_rom_bytes not in (16384, 65536) or (boot_rom_bytes != ROM_BYTES and memory_profile != 'ilm64k_dlm64k'):
        raise ValueError('expanded AE350 cold ROM requires explicit ILM/DLM placement and 64 KiB physical source')
    source_dir = root / 'firmware/ae350'
    inputs = selected_inputs(recording_api, memory_profile)
    sources = selected_sources(recording_api)
    maintained = (*FIRST_PARTY_SOURCES, *FIRST_PARTY_HEADERS, *RECORDING_SOURCES, *RECORDING_HEADERS,
                  *LOCAL_MEMORY_INPUTS)
    if output.exists():
        raise FileExistsError('AE350 firmware output already exists: ' + str(output))
    for name in dict.fromkeys((*inputs, *maintained)):
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
    if set(provenance.get('first_party_files', {})) != set(maintained):
        raise ValueError('AE350 first-party source inventory drift')
    for name in maintained:
        expected = dict(kind='maintained_first_party',
                        source='projects/138k/push2_workstation/usb_a/firmware/ae350/' + name,
                        sha256=sha(source_dir / name))
        if provenance['first_party_files'][name] != expected:
            raise ValueError('AE350 first-party source provenance drift: ' + name)
    if provenance.get('historical_rom') != dict(path='firmware/boot.mem', **baseline.descriptor['files']['firmware/boot.mem']):
        raise ValueError('AE350 historical ROM provenance drift')
    identities = {str((source_dir / name).relative_to(root)): sha(source_dir / name) for name in inputs}
    prefix = compiler_prefix(riscv_prefix)
    versions = {}
    tool_names = ('gcc', 'objcopy', 'size', 'nm', 'objdump') if memory_profile == 'ilm64k_dlm64k' else ('gcc', 'objcopy', 'size', 'nm')
    for tool in tool_names:
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
    for name in inputs:
        shutil.copyfile(source_dir / name, output / name)
    (output / 'reference_boot.mem').write_bytes(reference_bytes)
    reference_image = decode_rom(output / 'reference_boot.mem')
    isa = 'rv32im_zicsr_zifencei' if memory_profile == 'ilm64k_dlm64k' else 'rv32im_zicsr'
    common = ['-march=' + isa, '-mabi=ilp32', '-msmall-data-limit=0', '-O2', '-ffreestanding',
              '-Wall', '-Wextra', '-Werror']
    linker = 'boot.ld'
    if memory_profile == 'ilm64k_dlm64k':
        common += ['-DA138_ILM64K_DLM64K', '-fcallgraph-info=su']
        linker = 'boot_ilm_dlm.ld'
    commands = []
    with (output / 'build.log').open('w') as log:
        def run(command):
            commands.append(command)
            subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
        objects = []
        for name in sources:
            target = Path(name).with_suffix('.o').name
            run([prefix + '-gcc', *common, '-fstack-usage', '-c', name, '-o', target])
            objects.append(target)
        memory_flags = ['-Wl,--defsym=__boot_rom_bytes=' + str(boot_rom_bytes)] if memory_profile == 'ilm64k_dlm64k' else []
        run([prefix + '-gcc', '-march=' + isa, '-mabi=ilp32', '-msmall-data-limit=0', *memory_flags,
             '-nostdlib', '-nostartfiles', '-Wl,--build-id=none,-Map=firmware.map,-T,' + linker,
             *objects, '-o', 'firmware.elf'])
        run([prefix + '-objcopy', '-O', 'binary', 'firmware.elf', 'firmware.bin'])
    size = subprocess.run([prefix + '-size', 'firmware.elf'], cwd=output, capture_output=True, text=True, check=True)
    symbols = subprocess.run([prefix + '-nm', '-n', 'firmware.elf'], cwd=output, capture_output=True, text=True, check=True)
    (output / 'firmware.size').write_text(size.stdout)
    (output / 'firmware.nm').write_text(symbols.stdout)
    binary = (output / 'firmware.bin').read_bytes()
    capacity = (local_memory_report(size.stdout, symbols.stdout, len(binary), boot_rom_bytes)
                if memory_profile == 'ilm64k_dlm64k' else
                memory_report(size.stdout, symbols.stdout, (output / 'start.S').read_text(), len(binary)))
    image_validation = None
    if memory_profile == 'ilm64k_dlm64k':
        image_validation = verify_elf_image(output / 'firmware.elf', binary, capacity['symbols'], boot_rom_bytes)
    padded = binary.ljust(boot_rom_bytes, b'\0')
    rom = output / 'boot.mem'
    rom.write_text(''.join(f'{int.from_bytes(padded[index:index+4], "little"):08x}\n'
                           for index in range(0, boot_rom_bytes, 4)))
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
    stack_analysis = None
    if memory_profile == 'ilm64k_dlm64k':
        disassembly = subprocess.run([prefix + '-objdump', '-d', 'firmware.elf'], cwd=output,
                                     capture_output=True, text=True, check=True).stdout
        (output / 'firmware.dis').write_text(disassembly)
        stack_analysis = call_chain_report(output, stack_frames, disassembly, capacity['stack_capacity_bytes'])
        capacity['whole_program_stack_bound_verified'] = stack_analysis['verified']
    result = dict(schema=1, firmware_profile='maintained_ae350_workstation', isa=isa, abi='ilp32',
                  compiler_prefix=prefix, compiler_version=versions['gcc'], tool_versions=versions,
                  source_provenance=provenance, input_sha256=identities, recording_api_enabled=recording_api,
                  changed_from_import=[name for name in (*IMPORTED_SOURCES, *IMPORTED_HEADERS, 'boot.ld')
                                       if sha(source_dir / name) != provenance['files'][name]['sha256']],
                  first_party_inputs={name: sha(source_dir / name)
                                      for name in maintained if name in inputs},
                  imported_inputs={name: sha(source_dir / name)
                                   for name in (*IMPORTED_SOURCES, *IMPORTED_HEADERS, 'boot.ld')},
                  compiled_sources=list(sources),
                  commands=commands, capacity=capacity, compiler_stack_frames=stack_frames,
                  elf_sha256=sha(output / 'firmware.elf'), binary_sha256=sha(output / 'firmware.bin'),
                  rom_sha256=sha(rom), reference_rom=dict(reference_description,
                      byte_identical=rom.read_bytes() == reference_bytes, words_identical=padded == reference_image,
                      reference_capacity_bytes=ROM_BYTES, selected_capacity_bytes=boot_rom_bytes,
                      differing_words_scope_bytes=ROM_BYTES,
                      differing_words=sum(padded[i:i+4] != reference_image[i:i+4] for i in range(0, ROM_BYTES, 4))),
                  hardware_tested=False, project_rom_installed=False,
                  stack_validation='Compiler per-function sizes and reserved capacity; whole-call-chain and runtime high-water mark remain unverified.')
    result['memory_profile'] = memory_profile
    if memory_profile == 'ilm64k_dlm64k':
        platform_inputs = ('riscv_ae350_config.v', 'src/ae350/riscv_ae350_config.v',
                           'src/ae350/riscv_ae350_top.v', 'src/ae350/gw138k_boot_memory.sv')
        platform_evidence = {name: dict(baseline.descriptor['files'][name]) for name in platform_inputs}
        config_bytes = baseline.read_bytes('src/ae350/riscv_ae350_config.v')
        macros = re.findall(rb'^\s*`define\s+(\w+)', config_bytes, re.MULTILINE)
        if b'AE350_EXT_AHB_MASTER_EN' in macros:
            raise ValueError('reference local-memory cold path unexpectedly has a fabric master port')
        for name in platform_inputs:
            baseline.read_bytes(name)  # Revalidate frozen bytes, without altering them.
        result['reference_platform'] = dict(source_policy='locked_resource_rework_route0_reference_only',
                                            inputs=platform_evidence,
                                            macros=[name.decode('ascii') for name in macros],
                                            caller_must_verify_actual_staged_ip=True)
        result['cold_boot'] = dict(image_storage='existing_16k_pl_boot_rom' if boot_rom_bytes == 16384 else 'explicit_64k_pl_boot_rom', reset_address=ROM_BASE,
                                  image_capacity_bytes=boot_rom_bytes, cpu_copy_to_ilm_dlm=True,
                                  fabric_extended_ahb_master_required=False,
                                  actual_ip_writability_hardware_verified=False,
                                  cache_policy='reject_enabled_i_or_d_cache_on_entry',
                                  hardware_acceptance=False)
        result['elf_image_validation'] = image_validation
        result['call_chain_stack'] = stack_analysis
        result['stack_validation'] = 'Conservative actual service-entry call graph plus compiler frames; hardware watermark remains unverified.'
    (output / 'build_metadata.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new firmware evidence directory')
    parser.add_argument('--riscv-prefix', help='GNU bare-metal tool prefix, ending before -gcc')
    parser.add_argument('--reference-mem', type=Path, help='optional explicit 4096-word comparison ROM')
    parser.add_argument('--recording-api', action='store_true', help='explicit R00 recording service API selection')
    parser.add_argument('--memory-profile', choices=MEMORY_PROFILES, default='pl16k_8k',
                        help='explicit runtime placement; does not install physical ROM')
    parser.add_argument('--boot-rom-bytes', type=int, choices=(16384, 65536), default=16384,
                        help='explicit physical cold ROM size; expanded storage requires matching native ROM source')
    args = parser.parse_args()
    result = stage_ae350_firmware(Path(__file__).resolve().parents[1], args.output,
                                args.riscv_prefix, reference_mem=args.reference_mem, recording_api=args.recording_api,
                                memory_profile=args.memory_profile, boot_rom_bytes=args.boot_rom_bytes)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
