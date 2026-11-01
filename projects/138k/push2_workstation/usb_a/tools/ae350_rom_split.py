"""Fail-closed capacity/ELF checks for the unselected ROM128 split experiment."""
from pathlib import Path
import hashlib
import struct

from tools.ae350_local_memory import symbol_values, ROM_BASE, ILM_BASE, DLM_BASE

ROM_BYTES = 131072
COLD_BASE = ROM_BASE + 65536


def split_memory_report(size_text, symbols_text, binary, elf_path, rom_bytes=ROM_BYTES,*,headless_worker=False):
    if rom_bytes != ROM_BYTES:
        raise ValueError('split experiment requires explicit 128 KiB ROM; 96 KiB is unsupported')
    s = symbol_values(symbols_text)
    required = ('_start', 'local_memory_entry', 'local_trap', 'local_halt', 'local_fail',
        'services_main', 'local_copy_ilm', 'local_copy_data', 'local_clear_bss', 'local_enter_ilm',
        '__ilm_load_start', '__ilm_start', '__ilm_end', '__data_load_start', '__data_start', '__data_end',
        '__data_image_end', '__rom_text_start', '__rom_text_end', '__bss_start', '__bss_end',
        '__stack_bottom', '__stack_top', '__heap_start', '__heap_end', '__image_end',
        'local_data_probe', 'local_bss_probe', 'a138_classic_init', 'a138_classic_acl',
        'ui_render_rows', 'a138_sbc_decode', 'OI_CODEC_SBC_DecodeFrame',
        'a138_ble_business_firmware_init', 'a138_ble_business_firmware_pump')
    if headless_worker:
        required=tuple(n for n in required if n not in ('ui_render_rows','a138_ble_business_firmware_init','a138_ble_business_firmware_pump'))+(
            'a138_classic_runtime_firmware_init','a138_classic_runtime_firmware_pump','a138_classic_runtime_init_session')
    if any(name not in s for name in required):
        raise ValueError('split linker or retained business symbols missing')
    if not (s['_start'] == ROM_BASE <= s['local_trap'] < s['__ilm_load_start']):
        raise ValueError('reset/trap must remain in lower ROM bank')
    if not (ILM_BASE == s['__ilm_start'] <= s['local_memory_entry'] < s['__ilm_end'] <= ILM_BASE + 65532):
        raise ValueError('ILM span or reserved final word invalid')
    hot=('services_main', 'a138_sbc_decode', 'OI_CODEC_SBC_DecodeFrame')+(
         ('a138_classic_runtime_firmware_init','a138_classic_runtime_firmware_pump') if headless_worker else
         ('a138_ble_business_firmware_init', 'a138_ble_business_firmware_pump'))
    for name in hot:
        if not ILM_BASE <= s[name] < s['__ilm_end']:
            raise ValueError('retained hot business escaped ILM: ' + name)
    if not (COLD_BASE == s['__rom_text_start'] < s['__rom_text_end'] <= ROM_BASE + ROM_BYTES):
        raise ValueError('cold executable bank invalid')
    for name in (('a138_classic_init','a138_classic_acl') if headless_worker else ('a138_classic_init', 'a138_classic_acl', 'ui_render_rows')):
        if not COLD_BASE <= s[name] < s['__rom_text_end']:
            raise ValueError('cold function not placed in upper ROM: ' + name)
    if not (DLM_BASE + 256 == s['__data_start'] <= s['local_data_probe'] < s['__data_end'] <=
            s['__bss_start'] <= s['local_bss_probe'] < s['__bss_end'] <= s['__stack_bottom'] == DLM_BASE + 49152 <
            s['__stack_top'] == DLM_BASE + 65536):
        raise ValueError('DLM prefix, globals or reserved stack invalid')
    if s['__heap_start'] != s['__heap_end'] or s['__heap_start'] != s['__bss_end']:
        raise ValueError('experiment must preserve zero heap')
    ilm = s['__ilm_end'] - s['__ilm_start']
    if not (ROM_BASE < s['__ilm_load_start'] < s['__data_load_start'] < s['__data_image_end'] <= COLD_BASE):
        raise ValueError('hot load bank overflow or bad copy span')
    if s['__ilm_load_start'] + ilm != s['__data_load_start']:
        raise ValueError('hot ILM/data load spans not contiguous')
    if s['__data_image_end'] != s['__data_load_start'] + s['__data_end'] - s['__data_start']:
        raise ValueError('DLM initialized load span invalid')
    if not (len(binary) > 65536 and len(binary) <= ROM_BYTES and
            s['__image_end'] == ROM_BASE + len(binary) == s['__rom_text_end']):
        raise ValueError('actual cold binary does not match physical upper bank')
    if any(s[name] % 4 for name in required if name.startswith('__')):
        raise ValueError('loader span not word aligned')
    raw = Path(elf_path).read_bytes()
    if raw[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('expected little-endian ELF32')
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', raw)
    if h[1] != 2 or h[2] != 243 or h[4] != ROM_BASE or h[9] != 32 or h[11] != 40:
        raise ValueError('ELF header geometry invalid')
    reconstructed, covered, segments = bytearray(len(binary)), set(), []
    for i in range(h[10]):
        kind, offset, vma, lma, size, memsize, flags, alignment = struct.unpack_from('<IIIIIIII', raw, h[5] + i*h[9])
        if kind != 1 or not size:
            continue
        if size > memsize or offset + size > len(raw) or not ROM_BASE <= lma < lma+size <= ROM_BASE+len(binary):
            raise ValueError('ELF load segment escapes actual binary')
        indexes = set(range(lma-ROM_BASE, lma-ROM_BASE+size))
        if covered & indexes:
            raise ValueError('overlapping ELF load segments')
        covered |= indexes
        reconstructed[lma-ROM_BASE:lma-ROM_BASE+size] = raw[offset:offset+size]
        segments.append(dict(run_address=vma, load_address=lma, file_bytes=size, memory_bytes=memsize, flags=flags))
    if reconstructed != binary:
        raise ValueError('ELF load segments do not reconstruct split binary')
    sections = [struct.unpack_from('<IIIIIIIIII', raw, h[6]+i*h[11]) for i in range(h[12])]
    names = sections[h[13]]
    strings = raw[names[4]:names[4]+names[5]]
    result = {}
    allowed = {'.boot': (ROM_BASE, s['__ilm_load_start']), '.rom_text': (COLD_BASE, s['__rom_text_end']),
        '.text': (ILM_BASE, s['__ilm_end']), '.rodata': (ILM_BASE, s['__ilm_end']),
        '.data': (s['__data_start'], s['__data_end']), '.bss': (s['__bss_start'], s['__bss_end'])}
    for section in sections:
        name_offset, kind, flags, address, offset, size, *_ = section
        name = strings[name_offset:strings.find(b'\0', name_offset)].decode('ascii')
        if not flags & 2 or not size:
            continue
        if name not in allowed or name in result:
            raise ValueError('unexpected allocated ELF section: ' + name)
        lower, upper = allowed[name]
        if not lower <= address < address+size <= upper or (kind == 8) != (name == '.bss'):
            raise ValueError('ELF section placement invalid: ' + name)
        if name in ('.boot', '.rom_text', '.text') and not flags & 4:
            raise ValueError('code section lacks executable flag')
        result[name] = dict(address=address, bytes=size,
            sha256=None if kind == 8 else hashlib.sha256(raw[offset:offset+size]).hexdigest())
    if set(result) != set(allowed):
        raise ValueError('split allocated ELF section missing')
    row = next((r for line in size_text.splitlines() if len(r := line.split()) >= 6 and all(v.isdecimal() for v in r[:3])), None)
    if row is None:
        raise ValueError('GNU size summary missing')
    text, data, bss = map(int, row[:3])
    if (text != sum(result[n]['bytes'] for n in ('.boot','.rom_text','.text','.rodata')) or
            data != result['.data']['bytes'] or bss != result['.bss']['bytes']):
        raise ValueError('GNU size and actual ELF sections disagree')
    payload = text + data
    return dict(rom_capacity_bytes=ROM_BYTES, binary_bytes=len(binary), payload_bytes=payload,
        padding_hole_bytes=len(binary)-payload, upper_rom_code_bytes=result['.rom_text']['bytes'],
        cold_code_unallocated_bytes=ROM_BASE+ROM_BYTES-s['__rom_text_end'],
        hot_load_bank_bytes=s['__data_image_end']-ROM_BASE,
        hot_load_unallocated_bytes=COLD_BASE-s['__data_image_end'],
        ilm_capacity_bytes=65536, ilm_runtime_bytes=ilm, ilm_reserved_final_word_bytes=4,
        ilm_usable_remaining_bytes=65532-ilm, dlm_capacity_bytes=65536,
        static_ram_span_bytes=s['__bss_end']-s['__data_start'], ram_reserved_prefix_bytes=256,
        stack_capacity_bytes=16384, unallocated_dlm_bytes=s['__stack_bottom']-s['__bss_end'], heap_bytes=0,
        symbols={name:s[name] for name in required},
        elf_image_validation=dict(binary_reconstructed=True, sections=result, segments=segments),
        selected_in_production=False, hardware_acceptance=False)
