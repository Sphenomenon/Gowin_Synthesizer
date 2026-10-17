#!/usr/bin/env python3
"""Stage and compile the live USB-A firmware without modifying frozen inputs.

Both workstation builders use this path so a new adapter cannot accidentally
ship with the old accepted firmware ROM. No board operations are performed.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess


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
        if candidate and all(shutil.which(candidate + '-' + tool) for tool in ('gcc', 'objcopy', 'size', 'nm')):
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


def stage_usb_firmware(root, stage, output, riscv_prefix=None):
    """Compile live firmware, bind both ROM paths, return reproducible metadata.

    ``stage`` is the copied Prj1 tree. The exact same 64 KiB little-endian
    image is used by root-relative and src/usb_a-relative readmemh paths.
    ``output/firmware`` keeps the compiler's source, object and ELF evidence.
    """
    root, stage, output = map(Path, (root, stage, output))
    prefix = compiler_prefix(riscv_prefix)
    live = [root / 'firmware.c', root / 'gw25k_panel.h']
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
        for name in ('start.S', 'firmware.c', 'minlibc.c', 'usb/usb_core.c', 'usb/usb_hw.c'):
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
