#!/usr/bin/env python3
"""Stage and compile the live USB-A firmware without modifying frozen inputs.

Both workstation builders use this path so a new adapter cannot accidentally
ship with the old accepted firmware ROM. No board operations are performed.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess


USB2_VENDOR_MANIFEST_SHA256 = '901833fa2083c9a09db62045c5b12e63360c3f61e7775847ca78ddaeb5c76ba6'


def verify_usb2_cpu_vendor(root):
    vendor = Path(root) / 'vendor/usb_host_fs_8fc3'
    manifest = vendor / 'inputs.json'
    if sha(manifest) != USB2_VENDOR_MANIFEST_SHA256:
        raise ValueError('USB2 CPU vendor manifest identity changed')
    records = json.loads(manifest.read_text())
    for relative, expected in records.items():
        if sha(vendor / relative) != expected:
            raise ValueError('USB2 CPU immutable vendor source changed: ' + relative)
    return vendor


def stage_usb2_cpu_firmware(root, output, entry, riscv_prefix=None, *, workstation=False, allow_high_speed=True, ram_bytes=65536):
    root, output, entry = map(Path, (root, output, entry))
    if not workstation and not allow_high_speed:
        raise ValueError('full-speed-only policy requires workstation firmware')
    vendor = verify_usb2_cpu_vendor(root)
    prefix = compiler_prefix(riscv_prefix)
    sources = [vendor / 'firmware/start.S', entry,
               root / 'drivers/usb2/workstation_usb2_host.c', root / 'drivers/usb2/workstation_usb2_cpu_port.c']
    headers = [root / 'drivers/usb2/workstation_usb2_host.h', root / 'drivers/usb2/workstation_usb2_cpu_port.h']
    if workstation:
        sources += [root / 'drivers/usb2/workstation_usb2_backend.c', vendor / 'firmware/minlibc.c',
                    vendor / 'firmware/usb/usb_core.c']
        headers += [root / 'firmware.c', root / 'gw25k_panel.h', root / 'drivers/usb2/workstation_usb2_backend.h',
                    vendor / 'firmware/minlibc.h', vendor / 'firmware/usb/usb_core.h',
                    vendor / 'firmware/usb/usb_defs.h', vendor / 'firmware/usb/usb_hw.h']
    linker = vendor / 'firmware/baremetal.ld'
    for source in [*sources, *headers, linker]:
        if not source.is_file():
            raise FileNotFoundError('missing explicit USB2 CPU firmware input: ' + str(source))
    identities = {str(source.relative_to(root)): sha(source) for source in [*sources, *headers, linker]}
    compiler_version = subprocess.run([prefix + '-gcc', '--version'], text=True, capture_output=True,
                                      check=True).stdout.splitlines()[0]
    output.mkdir(parents=True, exist_ok=False)
    if ram_bytes not in (49152, 65536):
        raise ValueError('USB CPU RAM must be 48 or 64 KiB')
    # Adapt only generated startup/linker inputs; vendor originals stay frozen.
    startup = sources[0].read_text()
    startup = once(startup, '.equ    STACK_TOP, 0x10000', f'.equ    STACK_TOP, 0x{ram_bytes:x}')
    (output / 'start.S').write_text(startup)
    script = once(linker.read_text(), 'LENGTH = 0x10000', f'LENGTH = 0x{ram_bytes:x}')
    (output / 'baremetal.ld').write_text(script)
    common = ['-march=rv32i', '-mabi=ilp32', '-mno-relax', '-msmall-data-limit=0']
    with (output / 'build.log').open('w') as log:
        objects = []
        for index, source in enumerate(sources):
            target = 'start.o' if index == 0 else f'source_{index}.o'
            objects.append(target)
            profile_flags = ['-DWORKSTATION_USB2_NATIVE', '-I', str(root), '-I', str(vendor / 'firmware'),
                             '-I', str(vendor / 'firmware/usb')] if workstation else []
            if not allow_high_speed:
                profile_flags += ['-DWORKSTATION_USB2_FORCE_FS']
            warning_flags = ['-Wall'] if vendor in source.parents else ['-Wall', '-Wextra', '-Werror']
            subprocess.run([prefix + '-gcc', *common, '-std=c11', '-O2' if workstation else '-Os', '-ffreestanding',
                            '-ffunction-sections', '-fdata-sections', *warning_flags,
                            *profile_flags, '-I', str(root / 'drivers/usb2'), '-c', str((output / 'start.S' if index == 0 else source).resolve()), '-o', target],
                           cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([prefix + '-gcc', *common, '-nostdlib', '-Wl,-e,_start,--gc-sections,--build-id=none,-T,baremetal.ld',
                        *objects, '-lgcc', '-o', 'firmware.elf'], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([prefix + '-objcopy', '-O', 'binary', 'firmware.elf', 'firmware.bin'], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    size = subprocess.run([prefix + '-size', str(output / 'firmware.elf')], text=True, capture_output=True, check=True)
    symbols = subprocess.run([prefix + '-nm', '-n', str(output / 'firmware.elf')], text=True, capture_output=True, check=True)
    used = static_memory_bytes(size.stdout)
    end = static_memory_end(symbols.stdout)
    binary = (output / 'firmware.bin').read_bytes()
    limit = ram_bytes-8192 if ram_bytes == 49152 else 60000
    if not binary or max(len(binary), used, end) >= limit:
        raise ValueError('USB2 CPU firmware exceeds its static memory/stack budget')
    for relative, expected in identities.items():
        if sha(root / relative) != expected:
            raise ValueError('USB2 CPU firmware input changed during compilation: ' + relative)
    padded = binary.ljust(ram_bytes, b'\0')
    rom = output / 'usb2_cpu.hex'
    rom.write_text(''.join(f'{int.from_bytes(padded[index:index+4], "little"):08x}\n'
                           for index in range(0, len(padded), 4)))
    if ram_bytes==49152:
        rows=rom.read_text().splitlines(keepends=True)
        for bank in range(3):
            (output / f'usb2_cpu_bank{bank}.hex').write_text(''.join(rows[bank*4096:(bank+1)*4096]))
    return dict(isa='rv32i', abi='ilp32', compiler_prefix=prefix, compiler_version=compiler_version,
                firmware_profile='workstation' if workstation else 'probe',
                high_speed_allowed=bool(allow_high_speed),
                entry=str(entry.relative_to(root)), input_sha256=identities,
                firmware_bytes=len(binary), static_ram_bytes=used, static_ram_end=end, stack_margin_bytes=ram_bytes-end, ram_bytes=ram_bytes,
                generated_startup_sha256=sha(output / 'start.S'), generated_linker_sha256=sha(output / 'baremetal.ld'),
                elf_sha256=sha(output / 'firmware.elf'), binary_sha256=sha(output / 'firmware.bin'), rom_sha256=sha(rom),
                vendor_manifest_sha256=USB2_VENDOR_MANIFEST_SHA256, hardware_tested=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('expected one USB driver patch anchor: ' + old[:100])
    return text.replace(old, new)


def compiler_prefix(value=None):
    """Resolve a GNU bare-metal RISC-V toolchain, preserving the Linux default."""
    explicit = value or os.environ.get('GW138K_RISCV_PREFIX')
    candidates = [explicit] if explicit else [
        str(Path.home() / '.local/opt/amd/2025.2.1/gnu/riscv/lin/bin/riscv64-unknown-elf'),
        'riscv64-unknown-elf', 'riscv32-unknown-elf', 'riscv-none-elf',
    ]
    for candidate in candidates:
        if candidate and all(shutil.which(candidate + '-' + tool + ('.exe' if os.name == 'nt' else '')) for tool in ('gcc', 'objcopy', 'size', 'nm')):
            return candidate
    raise FileNotFoundError(
        'RISC-V bare-metal gcc/objcopy/size/nm are required; pass --riscv-prefix '
        'or set GW138K_RISCV_PREFIX (prefix ends before -gcc)')


def patch_preloaded_driver(firmware):
    """Split FIFO loading from the vendor driver's unchanged token handling."""
    source = firmware / 'usb/usb_hw.c'
    text = source.read_text()
    signature = ('int usbhw_transfer_out(uint8_t pid, int device_addr, int endpoint, '
                 'int handshake, uint8_t request, uint8_t *tx, int tx_length)')
    preloaded = ('int usbhw_transfer_out_preloaded(uint8_t pid, int device_addr, int endpoint, '
                 'int handshake, uint8_t request, int tx_length)')
    wrapper = signature + '''
{
    for (int l=0;l<tx_length;l++)usbhw_reg_write(USB_WR_DATA, tx[l]);
    return usbhw_transfer_out_preloaded(pid,device_addr,endpoint,handshake,request,tx_length);
}
'''
    text = once(text, signature, wrapper + '\n' + preloaded)
    text = once(text, '    int l;\n    uint32_t ctrl = 0;', '    uint32_t ctrl = 0;')
    begin = text.index('    // Load DATAx transfer into address 0+')
    end = text.index('    // Transfer data length', begin)
    source.write_text(text[:begin] + text[end:])
    header = firmware / 'usb/usb_hw.h'
    header.write_text(once(header.read_text(), 'void usbhw_init(uint32_t base);',
                           preloaded + ';\nvoid usbhw_init(uint32_t base);'))


def static_memory_bytes(size_output):
    """Parse GNU size's Berkeley output, including zero-initialized BSS."""
    rows = [line.split() for line in size_output.splitlines()]
    rows = [row for row in rows if len(row) >= 6 and all(word.isdecimal() for word in row[:4])]
    if len(rows) != 1:
        raise ValueError('expected one GNU size text/data/bss/dec row')
    text, data, bss, total = map(int, rows[0][:4])
    if text + data + bss != total:
        raise ValueError('GNU size text/data/bss total mismatch')
    return total


def static_memory_end(nm_output):
    """The linker aligns _ebss after BSS; include gaps as well as section sizes."""
    symbols = [line.split() for line in nm_output.splitlines()]
    matches = [int(row[0], 16) for row in symbols if len(row) == 3 and row[2] == '_ebss']
    if len(matches) != 1:
        raise ValueError('expected one _ebss linker symbol in GNU nm output')
    return matches[0]


def stage_usb_firmware(root, stage, output, riscv_prefix=None, *, entry=None):
    """Compile live firmware, bind both ROM paths, return reproducible metadata.

    ``stage`` is the copied Prj1 tree. The exact same 64 KiB little-endian
    image is used by root-relative and src/usb_a-relative readmemh paths.
    ``output/firmware`` keeps the compiler's source, object and ELF evidence.
    """
    root, stage, output = map(Path, (root, stage, output))
    prefix = compiler_prefix(riscv_prefix)
    live = [root / 'firmware.c', root / 'gw25k_panel.h']
    if entry is not None:
        live.append(root / entry)
    missing = [str(path) for path in live if not path.is_file()]
    if missing:
        raise FileNotFoundError('missing live USB adapter source: ' + ', '.join(missing))
    firmware = output / 'firmware'
    shutil.copytree(root / 'vendor/usb_host_fs_8fc3/firmware', firmware,
                    ignore=shutil.ignore_patterns('*.o', '*.elf', '*.bin'))
    for path in live:
        shutil.copy2(path, firmware / path.name)
    patch_preloaded_driver(firmware)
    with (output / 'firmware_build.log').open('w') as log:
        def run(command):
            subprocess.run(command, cwd=firmware, stdout=log, stderr=subprocess.STDOUT, check=True)
        objects = []
        for name in ('start.S', Path(entry).name if entry else 'firmware.c', 'minlibc.c', 'usb/usb_core.c', 'usb/usb_hw.c'):
            obj = str(Path(name).with_suffix('.o'))
            objects.append(obj)
            run([prefix + '-gcc', '-Wall', '-O2', '-g', '-mabi=ilp32', '-march=rv32i',
                 '-ffreestanding', '-Iusb', '-I.', '-c', name, '-o', obj])
        run([prefix + '-gcc', '-mabi=ilp32', '-march=rv32i',
             '-Wl,--build-id=none,-Bstatic,-T,baremetal.ld', '-nostdlib', *objects,
             '-lgcc', '-o', 'firmware.elf'])
        run([prefix + '-objcopy', '-O', 'binary', 'firmware.elf', 'firmware.bin'])
        result = subprocess.run([prefix + '-size', 'firmware.elf'], cwd=firmware,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=True)
        log.write(result.stdout)
        memory_bytes = static_memory_bytes(result.stdout)
        symbols = subprocess.run([prefix + '-nm', '-n', 'firmware.elf'], cwd=firmware,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, check=True)
        memory_end = static_memory_end(symbols.stdout)
        log.write('Static RAM end (_ebss): ' + str(memory_end) + '\n')
    binary = (firmware / 'firmware.bin').read_bytes()
    if not binary or len(binary) >= 60000 or memory_bytes >= 60000 or memory_end >= 60000:
        raise ValueError('USB firmware text/data/BSS must leave stack space in 64 KiB RAM; '
                         'binary bytes=' + str(len(binary)) + ', static RAM bytes=' + str(memory_bytes) +
                         ', static RAM end=' + str(memory_end))
    padded = binary.ljust(65536, b'\0')
    hexdata = ''.join(f'{int.from_bytes(padded[i:i+4], "little"):08x}\n'
                      for i in range(0, len(padded), 4))
    targets = (stage / 'push2_usb_a.hex', stage / 'src/usb_a/push2_usb_a.hex')
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(hexdata)
    return dict(compiler_prefix=prefix, firmware_bytes=len(binary), static_ram_bytes=memory_bytes,
                static_ram_end=memory_end, stack_margin_bytes=65536-memory_end,
                live_sha256={path.name: sha(path) for path in live},
                staged_source_sha256={str(path.relative_to(firmware)): sha(path)
                                      for path in firmware.rglob('*')
                                      if path.is_file() and path.suffix not in ('.o', '.elf', '.bin')},
                firmware_elf_sha256=sha(firmware / 'firmware.elf'),
                firmware_binary_sha256=sha(firmware / 'firmware.bin'),
                rom_sha256={str(path.relative_to(stage)): sha(path) for path in targets},
                hardware_tested=False)
