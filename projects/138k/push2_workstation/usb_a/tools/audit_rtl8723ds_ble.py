#!/usr/bin/env python3
"""Check Gowin's inferred ROM INIT bits and BLE synchronizer cells."""
from pathlib import Path
import argparse
import hashlib
import json
import re


def audit_rom(netlist, rom_file):
    text = Path(netlist).read_text()
    expected = bytes(int(line, 16) for line in Path(rom_file).read_text().splitlines())
    if len(expected) != 32768:
        raise ValueError('Expected the full padded 32768-byte ROM')
    image = bytearray(32768)
    instances = re.findall(r'\bpROM\s+(patch_mem_patch_mem_([01])_([0-7])_s)\s*\(', text)
    if len(instances) != 16:
        raise ValueError('Expected 16 1-bit Gowin pROMs, got ' + str(len(instances)))
    for name, half, bit in instances:
        if not re.search(r'defparam\s+' + re.escape(name) + r'\.BIT_WIDTH\s*=\s*1;', text):
            raise ValueError('Unexpected ROM width: ' + name)
        if not re.search(r'defparam\s+' + re.escape(name) + r"\.READ_MODE\s*=\s*1'b0;", text):
            raise ValueError('ROM synchronous read mode changed: ' + name)
        chunks = re.findall(r'defparam\s+' + re.escape(name) + r'\.INIT_RAM_([0-9A-Fa-f]{2})\s*=\s*256\'h([0-9A-Fa-f]+);', text)
        if not chunks or any(int(chunk, 16) >= 64 for chunk, _ in chunks):
            raise ValueError('Invalid ROM initialization chunk: ' + name)
        # Unspecified pROM INIT_RAM parameters default to zero; Gowin omits
        # the padded zero tail. The reconstructed full image is still compared.
        for chunk, value in chunks:
            at = int(half)*16384 + int(chunk, 16)*256
            word = int(value, 16)
            for i in range(256):
                image[at+i] |= ((word >> i) & 1) << int(bit)
    if image != expected:
        index = next(i for i, (a, b) in enumerate(zip(image, expected)) if a != b)
        raise ValueError(f'Gowin ROM content mismatch at byte {index}: {image[index]:02x}!={expected[index]:02x}')
    # Cells are retained individually, with no first-to-second-stage false path.
    for name in ('rx_sync_0_s1', 'rx_sync_1_s1'):
        if not re.search(r'\bDFF\w+\s+' + name + r'\s*\(', text):
            raise ValueError('UART synchronizer register removed: ' + name)
    return {'patch_rom_bsram': 16, 'padded_rom_bytes_checked': len(image),
            'padded_rom_sha256': hashlib.sha256(image).hexdigest(),
            'rom_matches': True, 'uart_synchronizer_registers_present': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path, help='BLE result folder containing Prj1')
    args = parser.parse_args()
    stage = args.build / 'Prj1'
    netlists = list((stage / 'impl/gwsynthesis').glob('*.vg'))
    if len(netlists) != 1:
        raise ValueError('Expected one synthesis netlist')
    result = audit_rom(netlists[0], stage / 'vendor/rtl8723ds_ble/rtl8723ds_patch.mem')
    result['netlist'] = str(netlists[0])
    metadata = json.loads((args.build / 'ble_build_metadata.json').read_text())
    synthesized_text = netlists[0].read_text()
    result['compact_memory'] = {}
    for key, identifier, minimum in (('compact_hci', 'parameter_mem', 32), ('compact_h5', 'wire_ram', 36)):
        if metadata.get(key):
            count = len(re.findall(r'\bRAM16\w+\s+' + identifier + r'_\w+\s*\(', synthesized_text))
            if count < minimum:
                raise ValueError('Expected compact RAM was not inferred: ' + identifier)
            result['compact_memory'][identifier + '_ram16_cells'] = count
    output_name = 'ble138k' if metadata['profile'] == 'standalone' else 'Prj1'
    pnr = stage / 'impl/pnr'
    timing_file = pnr / (output_name + '.tr')
    if timing_file.exists():
        timing = timing_file.read_text()
        def worst(analysis):
            header = {'setup': '3.1.1 Setup Paths Table', 'hold': '3.1.2 Hold Paths Table',
                      'recovery': '3.1.3 Recovery Paths Table', 'removal': '3.1.4 Removal Paths Table'}[analysis]
            section = timing[timing.index(header, timing.index('Note:Core Timing Report')):]
            match = re.search(r'(?m)^\s*1\s+(-?[0-9]+\.[0-9]+)\s+', section)
            return float(match[1]) if match else None
        setup_violations = int(re.search(r'<Numbers of Setup Violated Endpoints>:(\d+)', timing)[1])
        hold_violations = int(re.search(r'<Numbers of Hold Violated Endpoints>:(\d+)', timing)[1])
        max_frequency = re.search(r'(?m)^\s*\d+\s+(?:clk50|clk_50m)\s+50\.000\(MHz\)\s+([0-9.]+)\(MHz\)', timing)
        # The only UART input exception must end at stage 0, never stage 1.
        cut = 'set_false_path -from [get_ports {ble_module_uart_tx}] -to [get_pins {u_ble/u_driver/core/transport/uart/rx_sync_0_s1/D}]'
        if not re.search(r'TC_FALSE_PATH\s+Actived\s+' + re.escape(cut), timing):
            raise ValueError('UART stage-0 exception is not active in routed STA')
        routed = (pnr / (output_name + '.vo')).read_text()
        for name in ('rx_sync_0_s1', 'rx_sync_1_s1', 'reset_sync/stages_0_s1', 'reset_sync/stages_1_s1'):
            if name not in routed:
                raise ValueError('Routed synchronization register missing: ' + name)
        result['routed'] = {'setup_violated_endpoints': setup_violations,
            'hold_violated_endpoints': hold_violations,
            'fmax_mhz': float(max_frequency[1]) if max_frequency else None,
            'wns_ns': {kind: worst(kind) for kind in ('setup', 'hold', 'recovery', 'removal')},
            'uart_stage0_exception_active': True, 'rx_reset_sync_registers_preserved': True,
            'wns_scope': 'first standard STA path tables; use overall violation counts for all endpoint/CDC checks'}
        if metadata['profile'] == 'standalone':
            if setup_violations or hold_violations or any(value is None or value < 0 for value in result['routed']['wns_ns'].values()):
                raise ValueError('Standalone BLE did not close timing at 50 MHz')
    result['hardware_tested'] = False
    (args.build / 'ble_rom_cdc_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
