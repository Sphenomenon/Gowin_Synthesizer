"""Install the editable first-party composition of the resource-timing candidate."""

import hashlib
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'rtl/workstation/gw138k_push_workstation_top.v': 'src/push2/gw138k_push_workstation_top.v',
    'rtl/workstation/gw138k_controlled_adapter.sv': 'src/ae350/gw138k_controlled_adapter.sv',
    'rtl/workstation/gw138k_usb_controlled_audio.sv': 'src/usb_host/gw138k_usb_controlled_audio.sv',
    'rtl/audio/gw138k_event_workstation.sv': 'src/ae350/gw138k_event_workstation.sv',
    'rtl/audio/workstation_output_router.sv': 'rtl/audio/workstation_output_router.sv',
    'rtl/audio/workstation_frame_delivery.sv': 'rtl/audio/workstation_frame_delivery.sv',
    'rtl/control/workstation_session.sv': 'rtl/control/workstation_session.sv',
    'rtl/control/workstation_parameters.sv': 'rtl/control/workstation_parameters.sv',
    'rtl/services/workstation_playback_service.sv': 'rtl/services/workstation_playback_service.sv',
}


def install(stage):
    stage = Path(stage)
    project = stage / 'Prj1.gprj'
    tree = ET.parse(project)
    files = tree.find('FileList')
    if files is None:
        raise ValueError('project has no FileList')
    names = [entry.get('path') for entry in files]
    if len(names) != len(set(names)):
        raise ValueError('duplicate compilation input')
    missing = [name for name in SOURCES if not (ROOT / name).is_file()]
    if missing:
        raise ValueError('missing composition sources: ' + repr(missing))
    evidence = {}
    for source, destination in SOURCES.items():
        target = stage / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
        evidence[source] = {
            'destination': destination,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        }
        if destination not in names:
            ET.SubElement(files, 'File', path=destination, type='file.verilog', enable='1')
            names.append(destination)
    tree.write(project, encoding='UTF-8', xml_declaration=True)
    return {'policy': 'native_resource_timing_v1', 'sources': evidence}


def verify(stage, evidence):
    if evidence.get('policy') != 'native_resource_timing_v1':
        raise ValueError('unknown composition policy')
    if set(evidence['sources']) != set(SOURCES):
        raise ValueError('incomplete composition manifest')
    files = ET.parse(Path(stage) / 'Prj1.gprj').find('FileList')
    enabled = [entry.get('path') for entry in files
               if entry.get('type') == 'file.verilog' and entry.get('enable') == '1']
    for source, destination in SOURCES.items():
        record = evidence['sources'][source]
        if record.get('destination') != destination or enabled.count(destination) != 1:
            raise ValueError('composition input selection drift: ' + source)
        digest = hashlib.sha256((Path(stage) / destination).read_bytes()).hexdigest()
        if digest != record.get('sha256'):
            raise ValueError('composition source drift: ' + destination)
