"""Read-only ROM initialization proof for the explicit three-bank USB CPU RAM.

The 48 KiB source/firmware selector is separate from this actual synthesized
primitive proof. A successful prepare never substitutes for these mapped words.
"""
import re
from tools.stage_usb_firmware import sha


def check_banked_rom(stage, native, firmware):
    rom = stage / 'usb2_cpu.hex'
    words = [int(line, 16) for line in rom.read_text().splitlines()]
    if len(words) != 12288 or sha(rom) != firmware['rom_sha256'] or firmware['ram_bytes'] != 49152:
        raise ValueError('48 KiB firmware image identity/capacity changed')
    memories = {name: cell for name, cell in native.cells.items()
                if name.startswith('u_native_usb/host/bus/') and cell['kind'] == 'SDPB'}
    if len(memories) != 24:
        raise ValueError('CPU RAM must map to exactly 24 four-bit BSRAM banks')
    actual = [0]*12288
    covered = set()
    for name, cell in memories.items():
        match = re.fullmatch(r'u_native_usb/host/bus/g_ram48.g_bank\[(\d)\].memory_(\d)_g_ram48.g_bank\[\1\].memory_\2_0_(\d)_s', name)
        if not match:
            raise ValueError('CPU RAM bank mapping changed: '+name)
        bank, byte, nibble = map(int, match.groups())
        key = bank, byte, nibble
        if key in covered or bank >= 3 or byte >= 4 or nibble >= 2:
            raise ValueError('CPU RAM bank inventory changed')
        covered.add(key)
        params = cell['parameters']
        if params.get('BIT_WIDTH_0') != '4' or params.get('BIT_WIDTH_1') != '4':
            raise ValueError('CPU RAM initialization packing changed')
        packed = 0
        for label, value in params.items():
            if label.startswith('INIT_RAM_'):
                index = int(label.removeprefix('INIT_RAM_'), 16)
                literal = re.fullmatch(r"256'h([0-9a-fA-F]{1,64})", value)
                if index >= 64 or not literal:
                    raise ValueError('CPU RAM initialization chunk changed')
                packed |= int(literal[1], 16) << (256*index)
        for address in range(4096):
            actual[bank*4096+address] |= ((packed >> (4*address)) & 15) << (8*byte+4*nibble)
    for index, (expected, value) in enumerate(zip(words, actual)):
        if expected != value:
            raise ValueError(f'CPU synthesized ROM mismatch at word {index}')
    for bank in range(3):
        if [int(line, 16) for line in (stage / f'usb2_cpu_bank{bank}.hex').read_text().splitlines()] != words[bank*4096:(bank+1)*4096]:
            raise ValueError('CPU split ROM input differs from firmware image')
    return dict(words=len(words), bytes=49152, blocks=24, every_word_verified=True)

