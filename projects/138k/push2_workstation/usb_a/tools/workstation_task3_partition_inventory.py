"""Read-only W resource and executable-storage inventory for partition review.

Use an existing, explicitly identified preparation and its synthesis outputs.
This does not prepare a candidate, select a profile, run EDA or prove CDC/STA.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.ae350_rom_split import split_memory_report
from tools.workstation_synthesis_netlist import SynthesisNetlist

EFFECTS = 'u_managed/runtime/service/workstation/runtime_effects.effects'
OWNERS = ('u_native_usb', 'u_native_usb/host/bus', 'u_managed', EFFECTS,
          EFFECTS + '/delay_stage', EFFECTS + '/chorus_stage',
          EFFECTS + '/reverb_stage', 'u_boot_memory', 'u_bluetooth',
          'u_task3_media', 'u_task3_media/cnn_stream')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boot_words(native, expected):
    """Reconstruct both 64-KiB ROM halves from their actual 1-bit pROMs."""
    cells = {p: c for p, c in native.cells.items()
             if p.startswith('u_boot_memory/') and c['kind'] == 'pROM'}
    if len(cells) != 64 or len(expected) != 32768:
        raise ValueError('expected explicit 128-KiB boot ROM and 64 pROMs')
    actual = [0] * len(expected)
    covered = set()
    for path, cell in cells.items():
        match = re.fullmatch(r'u_boot_memory/rom_rom_([01])_(\d+)_s', path)
        if not match:
            raise ValueError('boot ROM packing changed: ' + path)
        half, bit = map(int, match.groups())
        if bit >= 32 or (half, bit) in covered:
            raise ValueError('duplicate or invalid boot ROM bit')
        covered.add((half, bit))
        params = cell['parameters']
        if params.get('BIT_WIDTH') != '1' or cell['ports']['AD'] != 'rom_address[15:2]':
            raise ValueError('boot ROM width/address packing changed')
        packed = 0
        for name, value in params.items():
            if not name.startswith('INIT_RAM_'):
                continue
            index = int(name.removeprefix('INIT_RAM_'), 16)
            literal = re.fullmatch(r"256'h([0-9a-fA-F]{1,64})", value)
            if index >= 64 or literal is None:
                raise ValueError('boot ROM initialization literal changed')
            packed |= int(literal[1], 16) << (256 * index)
        for offset in range(16384):
            actual[half * 16384 + offset] |= ((packed >> offset) & 1) << bit
    for index, (wanted, found) in enumerate(zip(expected, actual)):
        if wanted != found:
            raise ValueError(f'boot ROM mapped initialization differs at word {index}')
    scratch = [p for p, c in native.cells.items()
               if p.startswith('u_boot_memory/') and c['kind'] == 'SDPB']
    if len(scratch) != 8:
        raise ValueError('boot scratch memory inventory changed')
    return dict(pROM_instances=64, scratch_SDPB_instances=8,
                words_compared=len(expected), every_initialization_word_matches=True,
                scope='Initialization and primitive packing only; no AHB/timing proof')


def inspect(stage):
    profile_path = stage.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text())
    configuration = profile['configuration']
    if (configuration.get('demo_role') != 'W' or
            configuration.get('ae350_boot_rom_bytes') != 131072 or
            configuration.get('ae350_pcm_policy') != 'task3_W_HCI_decode_M_PCM1_v1'):
        raise ValueError('inventory requires the explicit paired W ROM128 role')
    for name, expected in profile['staged_input_sha256'].items():
        if sha(stage / name) != expected:
            raise ValueError('prepared W source drift: ' + name)
    synthesis = stage / 'impl/gwsynthesis'
    vg = synthesis / 'custom_138k_integration.vg'
    xml = synthesis / 'custom_138k_integration_syn_rsc.xml'
    firmware = stage.parents[1] / 'ae350_firmware'
    paths = [profile_path, vg, xml, Path(__file__),
             *(firmware / name for name in ('firmware.elf', 'firmware.bin',
               'firmware.size', 'firmware.nm', 'boot.mem')),
             stage / 'firmware/boot.mem']
    before = {str(p): sha(p) for p in paths}
    native = SynthesisNetlist(vg.read_text(), 'workstation_custom_138k_top')
    owners = {}

    def walk(element, prefix=''):
        path = (prefix + '/' if prefix else '') + element.attrib['name']
        if path in OWNERS:
            owners[path] = {key.removeprefix('T_'): int(value.split('(')[0])
                           for key, value in element.attrib.items() if key.startswith('T_')}
        for child in element:
            walk(child, path)

    resource_root = ET.parse(xml).getroot()
    for child in resource_root:
        walk(child)
    if set(owners) != set(OWNERS):
        raise ValueError('resource owner hierarchy changed')
    words = [int(line, 16) for line in (firmware / 'boot.mem').read_text().splitlines()]
    if (stage / 'firmware/boot.mem').read_bytes() != (firmware / 'boot.mem').read_bytes():
        raise ValueError('compiled boot ROM differs from verified firmware')
    binary = (firmware / 'firmware.bin').read_bytes()
    image = b''.join(word.to_bytes(4, 'little') for word in words)
    if len(binary) > len(image) or image[:len(binary)] != binary:
        raise ValueError('boot ROM does not contain the actual ELF binary image')
    boot = boot_words(native, words)
    capacity = split_memory_report((firmware / 'firmware.size').read_text(),
        (firmware / 'firmware.nm').read_text(), binary,
        firmware / 'firmware.elf', headless_worker=True)
    memory_kinds = ('SDPB', 'SDPX9B', 'pROM', 'SP')
    primitives = {owner: dict(collections.Counter(c['kind'] for path, c in native.cells.items()
                  if path.startswith(owner + '/') and c['kind'] in memory_kinds))
                  for owner in OWNERS}
    if before != {str(p): sha(p) for p in paths}:
        raise ValueError('inventory input changed during inspection')
    return dict(schema=1, scope=__doc__, candidate_identity=profile['candidate_identity'],
        configuration=configuration, input_sha256=before,
        prepared_files_verified=len(profile['staged_input_sha256']),
        enabled_compiler_inputs=len(profile['enabled_inputs']),
        owners_inclusive_synthesis_resources=owners, memory_primitive_inventory=primitives,
        resource_count_note='Inclusive owner totals overlap. BSRAM equivalent and primitive '
                            'instances are not physical device usage. AE350 vendor IP is opaque here.',
        boot_ROM=boot, firmware_capacity=capacity, all_inputs_unchanged=True,
        new_synthesis_run=False, new_physical_run=False, routed_timing_verified=False,
        hardware_tested=False, deployment_allowed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-stage', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite inventory evidence')
    result = inspect(args.worker_stage.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(candidate=result['candidate_identity'],
        prepared_files_verified=result['prepared_files_verified'],
        boot_ROM=result['boot_ROM']), ensure_ascii=False))


if __name__ == '__main__':
    main()
