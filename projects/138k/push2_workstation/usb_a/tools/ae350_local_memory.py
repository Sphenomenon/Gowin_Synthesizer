"""Capacity/image/stack checks for the explicit AE350 local-memory variant.

These are offline checks. They do not establish actual CSR or bus behavior.
"""
from pathlib import Path
import hashlib
import re
import struct

ROM_BASE, ROM_BYTES = 0x80000000, 16384
ILM_BASE, ILM_END = 0xA0000000, 0xA0010000
DLM_BASE, DLM_END = 0xA0200000, 0xA0210000


def symbol_values(text):
    return {parts[2]: int(parts[0], 16) for line in text.splitlines()
            if len(parts := line.split()) == 3 and re.fullmatch('[0-9a-fA-F]+', parts[0])}


def local_memory_report(size_text, symbols_text, binary_bytes, rom_bytes=ROM_BYTES):
    if rom_bytes not in (16384, 65536):
        raise ValueError('unsupported physical local-memory cold ROM capacity')
    symbols = symbol_values(symbols_text)
    required = ('_start', 'local_memory_entry', 'local_trap', 'local_halt', 'local_fail', 'services_main',
                'local_copy_ilm', 'local_copy_data', 'local_clear_bss', 'local_enter_ilm', '__ilm_load_start',
                '__ilm_start', '__ilm_end', '__data_load_start', '__data_start', '__data_end',
                '__bss_start', '__bss_end', '__stack_bottom', '__stack_top', '__heap_start',
                '__heap_end', '__image_end', 'local_data_probe', 'local_bss_probe')
    if any(name not in symbols for name in required):
        raise ValueError('local-memory linker symbols missing')
    s = symbols
    if s['_start'] != ROM_BASE or not ROM_BASE <= s['local_trap'] < s['__ilm_load_start']:
        raise ValueError('local-memory reset/trap must remain in cold ROM')
    if not (ILM_BASE == s['__ilm_start'] <= s['local_memory_entry'] < s['__ilm_end'] <= ILM_END - 4):
        raise ValueError('ILM runtime span or reserved final-word probe invalid')
    if not s['__ilm_start'] <= s['services_main'] < s['__ilm_end']:
        raise ValueError('service entry must execute in ILM')
    if not (DLM_BASE + 256 == s['__data_start'] <= s['local_data_probe'] < s['__data_end'] <=
            s['__bss_start'] <= s['local_bss_probe'] < s['__bss_end'] <= s['__stack_bottom'] <
            s['__stack_top'] == DLM_END):
        raise ValueError('DLM data/BSS/stack bounds invalid')
    if s['__stack_top'] - s['__stack_bottom'] != 16384 or s['__heap_start'] != s['__heap_end']:
        raise ValueError('local-memory profile requires 16 KiB stack and zero heap')
    if not (0 < binary_bytes <= rom_bytes and s['__image_end'] == ROM_BASE + binary_bytes and
            ROM_BASE < s['__ilm_load_start'] < s['__data_load_start'] < s['__image_end'] <= ROM_BASE + rom_bytes):
        raise ValueError('selected physical cold-image bounds invalid')
    ilm_bytes = s['__ilm_end'] - s['__ilm_start']
    if s['__ilm_load_start'] + ilm_bytes != s['__data_load_start']:
        raise ValueError('cold ILM and initialized-data load spans are not contiguous')
    if any(s[name] % 4 for name in required if name.startswith('__')):
        raise ValueError('loader span is not word aligned')
    rows = [line.split() for line in size_text.splitlines()]
    row = next((r for r in rows if len(r) >= 6 and all(v.isdecimal() for v in r[:3])), None)
    if row is None:
        raise ValueError('cannot read local-memory text/data/BSS sizes')
    text, data, bss = map(int, row[:3])
    if text + data != binary_bytes or data != s['__data_end'] - s['__data_start'] or bss != s['__bss_end'] - s['__bss_start']:
        raise ValueError('GNU size and load/runtime spans disagree')
    return dict(rom_capacity_bytes=rom_bytes, binary_bytes=binary_bytes, text_bytes=text,
                initialized_data_bytes=data, bss_bytes=bss, ilm_capacity_bytes=65536,
                ilm_runtime_bytes=ilm_bytes, ilm_reserved_final_word_bytes=4, dlm_capacity_bytes=65536,
                ram_reserved_prefix_bytes=256, static_ram_span_bytes=s['__bss_end'] - s['__data_start'],
                static_ram_end=s['__bss_end'], heap_bytes=0, stack_top=DLM_END,
                stack_bottom=s['__stack_bottom'], stack_capacity_bytes=16384, minimum_stack_bytes=16384,
                unallocated_dlm_bytes=s['__stack_bottom'] - s['__bss_end'],
                symbols={name: s[name] for name in required}, whole_program_stack_bound_verified=False,
                hardware_stack_watermark_verified=False)


def verify_elf_image(path, binary, symbols, rom_bytes=ROM_BYTES):
    """Reconstruct objcopy's ROM image from ELF32 PT_LOAD physical addresses."""
    raw = Path(path).read_bytes()
    if len(raw) < 52 or raw[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('expected little-endian ELF32')
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', raw)
    _, elf_type, machine, _, entry, phoff, shoff, _, _, phsize, phnum, shsize, shnum, shstrndx = header
    if elf_type != 2 or machine != 243 or entry != ROM_BASE or phsize != 32 or shsize != 40:
        raise ValueError('ELF reset, machine or header geometry invalid')
    image = bytearray(len(binary))
    covered = set()
    segments = []
    for i in range(phnum):
        kind, offset, vma, lma, size, memsize, flags, alignment = struct.unpack_from('<IIIIIIII', raw, phoff + i * phsize)
        if kind != 1 or size == 0:
            continue
        if size > memsize or offset + size > len(raw) or not ROM_BASE <= lma < lma + size <= ROM_BASE + len(binary):
            raise ValueError('ELF load segment escapes actual cold image')
        indexes = set(range(lma - ROM_BASE, lma - ROM_BASE + size))
        if covered & indexes:
            raise ValueError('overlapping ELF load segments')
        covered |= indexes
        image[lma - ROM_BASE:lma - ROM_BASE + size] = raw[offset:offset + size]
        segments.append(dict(run_address=vma, load_address=lma, file_bytes=size, memory_bytes=memsize,
                             flags=flags, alignment=alignment))
    if bytes(image) != binary:
        raise ValueError('ELF load segments do not reconstruct firmware.bin')
    sections = [struct.unpack_from('<IIIIIIIIII', raw, shoff + i * shsize) for i in range(shnum)]
    names = sections[shstrndx]
    strings = raw[names[4]:names[4] + names[5]]
    result = {}
    for section in sections:
        name_offset, kind, flags, address, offset, size, *_ = section
        name = strings[name_offset:strings.find(b'\0', name_offset)].decode('ascii')
        if not flags & 2 or not size:
            continue
        if name not in ('.boot', '.text', '.rodata', '.data', '.bss'):
            raise ValueError('unexpected allocated local-memory ELF section: ' + name)
        lower, upper = ((ROM_BASE, ROM_BASE + rom_bytes) if name == '.boot' else
                        (ILM_BASE, ILM_END - 4) if name in ('.text', '.rodata') else
                        (DLM_BASE + 256, symbols['__stack_bottom']))
        if not lower <= address < address + size <= upper or (kind == 8) != (name == '.bss'):
            raise ValueError('ELF section runtime placement invalid: ' + name)
        result[name] = dict(address=address, bytes=size,
                            sha256=None if kind == 8 else hashlib.sha256(raw[offset:offset + size]).hexdigest())
    if set(result) != {'.boot', '.text', '.rodata', '.data', '.bss'}:
        raise ValueError('missing allocated local-memory ELF section')
    return dict(elf32_riscv=True, entry=entry, binary_reconstructed=True, sections=result,
                segments=segments, code_bytes=result['.text']['bytes'], constant_bytes=result['.rodata']['bytes'],
                rom_loader_bytes=result['.boot']['bytes'])


def call_chain_report(output, frames, disassembly, capacity):
    """Conservative sum over GCC's direct graph, rooted at actual services_main.

    Every reachable dynamic/unbounded frame, unknown node, recursion or indirect
    call fails closed. Unreachable exported callback APIs are listed separately.
    The ROM loader is stackless; the ILM assembly self-test uses 16 bytes, then
    restores SP before calling services_main. Interrupts stay disabled.
    """
    graphs = '\n'.join(p.read_text() for p in sorted(Path(output).glob('*.ci')))
    nodes = {}
    edges = {}
    for line in graphs.splitlines():
        n = re.search(r'node: \{ title: "([^"]+)" label: "([^"\\]+)', line)
        if n:
            nodes[n[1]] = n[2]
        e = re.search(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"', line)
        if e:
            edges.setdefault(e[1], set()).add(e[2])
    by_name = {}
    for frame in frames:
        name = frame['function'].split(':', 3)[-1]
        if name in by_name:
            raise ValueError('ambiguous compiler stack function: ' + name)
        by_name[name] = frame
    roots = [node for node, name in nodes.items() if name == 'services_main']
    if len(roots) != 1:
        raise ValueError('missing unique services_main call-graph root')
    visiting, seen = set(), set()
    longest = []

    def visit(node):
        if node in visiting:
            raise ValueError('recursive service call graph')
        if node not in nodes or nodes[node] not in by_name:
            raise ValueError('unresolved service call graph node: ' + node)
        frame = by_name[nodes[node]]
        if frame['kind'] != 'static':
            raise ValueError('non-static service stack frame: ' + nodes[node])
        visiting.add(node)
        children = [visit(child) for child in edges.get(node, ())]
        visiting.remove(node)
        seen.add(node)
        tail_bytes, chain = max(children, default=(0, []), key=lambda x: x[0])
        return frame['bytes'] + tail_bytes, [nodes[node], *chain]

    bound, longest = visit(roots[0])
    bound = max(16, bound)
    if bound > capacity:
        raise ValueError('service call chain exceeds reserved DLM stack')
    # Machine code adds a second guard against missed indirect graph edges.
    reachable_names = {nodes[n] for n in seen}
    verified_edges = {(nodes[parent], nodes[child]) for parent in seen for child in edges.get(parent, ())}
    def normalized(name):
        return re.sub(r'\.(constprop|isra|part)\.\d+', r'.\1', name)
    current = None
    for line in disassembly.splitlines():
        header = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
        if header:
            current = normalized(header[1])
        if current in reachable_names and re.search(r'\b(?:jalr|jr)\b', line) and not re.search(r'\bret\b', line):
            raise ValueError('unresolved machine indirect call in service graph: ' + current)
        if current in reachable_names and re.search(r'\bjal\b', line):
            target = re.search(r'<([^>+]+)(?:\+[^>]*)?>', line)
            if target is None or (current, normalized(target[1])) not in verified_edges:
                raise ValueError('machine direct call escapes verified service graph: ' + current)
        if current in reachable_names and re.search(r'\bj\s', line):
            target = re.search(r'<([^>+]+)(?:\+[^>]*)?>', line)
            if target is None or (normalized(target[1]) != current and
                                  (current, normalized(target[1])) not in verified_edges):
                raise ValueError('machine tail call escapes verified service graph: ' + current)
    return dict(verified=True, scope='cold reset -> local_memory_entry -> services_main; interrupts disabled',
                conservative_peak_bytes=bound, longest_chain=longest, reachable_functions=sorted(reachable_names),
                exported_unreachable_functions=sorted(set(by_name) - reachable_names),
                assembly_loader_stack_bytes=0, assembly_selftest_stack_bytes=16,
                interrupts_enabled=False, hardware_watermark_verified=False,
                tail_calls_counted_as_nested=True)
