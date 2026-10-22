"""Separate synthesis policy for the explicit USB2/audio component, not a board."""

from collections import Counter
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha
from tools.workstation_usb2_audio import audio_bundle
from tools.workstation_usb2_soc import PREPARATION_INPUTS, PROBE_ENTRY, SOC_SOURCE_PATHS, WORKSTATION_INPUTS


ROOT = Path(__file__).resolve().parents[1]
REGISTER_LIMIT_EXCLUSIVE = 18432
EXPECTED_MEMORY = dict(SDPB=75, SDPX9B=1, pROM=21, RAM16SDP4=1190, RAM16SDP1=4)
MEMORY_PRIMITIVES = ('SP', 'SPX9', 'SDPB', 'SDPX9B', 'DPB', 'DPX9B', 'pROM', 'pROMX9', 'SDP36KE', 'SDP136K',
                     'RAM16S1', 'RAM16S2', 'RAM16S4', 'RAM16SDP1', 'RAM16SDP2', 'RAM16SDP4', 'ROM16')


def audit_audio_component_synthesis(output):
    output = Path(output)
    manifest = output / 'component_inputs.json'
    metadata = json.loads(manifest.read_text())
    bundle = audio_bundle(ROOT)
    sources = (*SOC_SOURCE_PATHS, *bundle['native_paths'],
               *(relative for relative in bundle['payloads'] if Path(relative).suffix in ('.sv', '.v')))
    expected_sources = sorted(sources, key=lambda relative: not relative.endswith('/audio_math_pkg.sv'))
    if (metadata.get('identity') != 'custom138k-usb2-audio-component-v1' or
            metadata.get('top_module') != 'workstation_usb2_audio' or metadata.get('component') != 'workstation-audio' or
            metadata.get('firmware_profile') != 'workstation' or
            metadata.get('source_policy') != 'explicit_native_audio_and_locked_resource_dependencies' or
            metadata.get('input_owner_provenance') != bundle['provenance'] or
            metadata.get('source_paths') != expected_sources or metadata.get('audio_path_integrated') is not True or
            metadata.get('input_owner_integrated') is not True or
            metadata.get('clocks_hz') != dict(cpu=48000000, reference=50000000, ulpi=60000000,
                                            audio=76800000, memory=100000000)):
        raise ValueError('USB2 audio component source policy changed')
    for flag in ('workstation_integrated', 'place_route_allowed', 'hardware_tested', 'deployment_allowed', 'release_ready'):
        if metadata.get(flag) is not False:
            raise ValueError('USB2 audio component is not board acceptance: ' + flag)
    preparation = tuple(relative for relative in PREPARATION_INPUTS if relative != PROBE_ENTRY)
    expected_inputs = {relative: sha(ROOT / relative)
                       for relative in (*SOC_SOURCE_PATHS, *bundle['native_paths'], *preparation, *WORKSTATION_INPUTS)}
    expected_inputs.update(bundle['input_sha256'])
    if metadata.get('input_sha256') != expected_inputs:
        raise ValueError('USB2 audio original input identity changed')
    staged = metadata['staged_input_sha256']
    expected_staged = {*SOC_SOURCE_PATHS, *bundle['native_paths'], *bundle['payloads'],
                       'usb2_cpu.hex', 'usb2_soc.sdc', 'usb2_soc.gprj', 'synthesis.tcl'}
    if set(staged) != expected_staged:
        raise ValueError('USB2 audio staged input set changed')
    for relative, payload in bundle['payloads'].items():
        if staged.get(relative) != hashlib.sha256(payload).hexdigest():
            raise ValueError('USB2 audio staged dependency identity changed: ' + relative)
    for relative in (*SOC_SOURCE_PATHS, *bundle['native_paths']):
        if staged.get(relative) != expected_inputs[relative]:
            raise ValueError('USB2 audio copied source identity changed: ' + relative)
    for relative, digest in staged.items():
        if sha(output / relative) != digest:
            raise ValueError('USB2 audio synthesis input identity changed: ' + relative)
    netlist = output / 'impl/gwsynthesis/usb2_soc_component.vg'
    text = netlist.read_text()
    if not re.search(r'^\s*module\s+workstation_usb2_audio\s*\(', text, re.M):
        raise ValueError('USB2 audio synthesized top module mismatch')
    scalar_primitives = '(?:' + '|'.join(MEMORY_PRIMITIVES) + '|DFF[A-Z0-9_]*)'
    if re.search(r'^\s*' + scalar_primitives + r'\s+(?:\\\S+\s+|[A-Za-z_$][A-Za-z0-9_$]*\s*)\[', text, re.M):
        raise ValueError('USB2 audio resource gate requires scalar primitive instances')
    primitives = Counter(re.findall(r'^\s*(\w+)\s+\S+\s*\(', text, re.M))
    memory = {name: primitives[name] for name in MEMORY_PRIMITIVES if primitives[name]}
    registers = sum(count for name, count in primitives.items() if re.fullmatch(r'DFF[A-Z0-9_]*', name))
    if memory != EXPECTED_MEMORY or registers >= REGISTER_LIMIT_EXCLUSIVE:
        raise ValueError('USB2 audio RAM/register resource gate failed')
    resource_report = output / 'impl/gwsynthesis/usb2_soc_component_syn_rsc.xml'
    resource = ElementTree.parse(resource_report).getroot()
    reported = {}
    for key in ('T_Register', 'T_Bsram', 'T_Ssram'):
        value = re.fullmatch(r'(\d+)\(\d+\)', resource.get(key, ''))
        if value is None:
            raise ValueError('USB2 audio synthesis resource report is malformed: ' + key)
        reported[key] = int(value[1])
    if (resource.get('name') != metadata['top_module'] or reported['T_Register'] != registers or
            reported['T_Bsram'] != sum(memory[name] for name in ('SDPB', 'SDPX9B', 'pROM')) or
            reported['T_Ssram'] != sum(memory[name] for name in ('RAM16SDP4', 'RAM16SDP1'))):
        raise ValueError('USB2 audio synthesis resource report does not match the component')
    planes = []
    for byte_lane in range(4):
        for bit_lane in range(8):
            instance = f'memory_{byte_lane}_memory_{byte_lane}_0_{bit_lane}_s'
            for port in (0, 1):
                if text.count(f'defparam {instance}.BIT_WIDTH_{port}=1;') != 1:
                    raise ValueError('USB2 audio CPU RAM bit-plane mapping changed')
            chunks = re.findall(r'defparam ' + instance + r"\.INIT_RAM_([0-9A-Fa-f]{2})=256'h([0-9A-Fa-f]+);", text)
            if len({index for index, _ in chunks}) != len(chunks) or any(int(index, 16) >= 64 for index, _ in chunks):
                raise ValueError('USB2 audio CPU ROM initialization chunks changed')
            value = sum(int(value, 16) << (int(index, 16) * 256) for index, value in chunks)
            planes.append(value.to_bytes(2048, 'little'))
    words = [int(word, 16) for word in (output / 'usb2_cpu.hex').read_text().splitlines()]
    if len(words) != 16384 or sha(output / 'usb2_cpu.hex') != metadata['firmware']['rom_sha256']:
        raise ValueError('USB2 audio CPU ROM identity changed')
    for index, expected in enumerate(words):
        actual = sum(((plane[index >> 3] >> (index & 7)) & 1) << bit for bit, plane in enumerate(planes))
        if actual != expected:
            raise ValueError(f'USB2 audio synthesized ROM mismatch at word {index}')
    return dict(validation_stage='component_audio_synthesis_only', identity=metadata['identity'],
                top_module=metadata['top_module'], component_inputs_sha256=sha(manifest),
                auditor_sha256=sha(Path(__file__)), netlist_sha256=sha(netlist),
                resource_report_sha256=sha(resource_report), memory_primitives=memory, registers=registers,
                register_limit_exclusive=REGISTER_LIMIT_EXCLUSIVE, synthesis_bsram_equivalent=reported['T_Bsram'],
                synthesis_ssram=reported['T_Ssram'], verified_rom_words=len(words), rom_sha256=sha(output / 'usb2_cpu.hex'),
                place_route_verified=False, hardware_tested=False, deployment_allowed=False, release_ready=False)
