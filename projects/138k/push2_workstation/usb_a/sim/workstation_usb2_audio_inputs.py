"""Select unchanged audio inputs from an explicitly audited native candidate."""

from pathlib import Path
import json
import re
import shutil
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha
from tools.workstation_custom_board_audit import audit


AUDIO_SOURCES = (
    'legacy_audio.sv', 'src/audio/pt8211_observer.v', 'src/audio/pt8211_tx.v',
    'src/control/uart_tx.v', 'src/ae350/gw138k_three_event_arbiter.sv',
    'src/ae350/gw138k_controlled_services.sv', 'src/ae350/gw138k_controlled_adapter.sv',
    'src/ae350/gw138k_event_workstation.sv', 'src/usb_host/gw138k_usb_controlled_audio.sv',
    'src/usb_a/gw138k_usb_lifecycle_merge.sv', 'src/migration/gw138k_apb_cdc.sv',
    'src/migration/gw138k_counter_cdc.sv', 'src/push2/gw138k_push_performance_uart.sv',
    'rtl/music/music_async_fifo.sv', 'rtl/audio/scope_vec/scope_control_player.sv',
    'rtl/audio/scope_vec/scope_vec_engine.sv', 'rtl/audio/scope_vec/scope_tf_control.sv',
    'rtl/audio/scope_vec/scope_dac_select.sv', 'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv',
    'rtl/audio/delay_ddr/delay_ddr_dma.sv', 'rtl/audio/serial_spatial_reverb.sv',
    'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
    'rtl/audio/workstation_output_router.sv', 'rtl/audio/workstation_frame_delivery.sv',
    'rtl/control/workstation_session.sv', 'rtl/control/workstation_parameters.sv',
    'rtl/audio/workstation_fpc_audio.sv',
)


def stage_audio(candidate, stage):
    candidate = Path(candidate).resolve()
    result = audit(candidate)
    source = candidate / 'workstation/Prj1'
    manifest = candidate / 'integration_inputs.json'
    metadata = json.loads(manifest.read_text())
    enabled = {entry.get('path') for entry in ElementTree.parse(source / 'Prj1.gprj').find('FileList')
               if entry.get('enable') == '1'}
    if not set(AUDIO_SOURCES).issubset(enabled):
        raise ValueError('audited native candidate does not select the required complete audio chain')
    selected = set(AUDIO_SOURCES)
    pending = list(selected)
    while pending:
        relative = pending.pop()
        for include in re.findall(r'`include\s+"([^"]+)"', (source / relative).read_text()):
            included = source / include
            if not included.is_file():
                included = (source / relative).parent / include
            included = included.resolve()
            if not included.is_relative_to(source) or not included.is_file():
                raise ValueError('missing or escaping audited audio include: ' + include)
            name = included.relative_to(source).as_posix()
            if name not in selected:
                selected.add(name)
                pending.append(name)
    assets = set()
    for directory in ('sim/data/audio_chain', 'sim/matlab/output', 'rtl/audio/scope_vec/data'):
        assets.update(path.relative_to(source).as_posix() for path in (source / directory).rglob('*.mem'))
    identities = {source / relative: sha(source / relative) for relative in sorted(selected | assets)}
    identities[manifest] = sha(manifest)
    copies = {}
    for path, digest in identities.items():
        if path == manifest:
            continue
        relative = path.relative_to(source)
        target = stage / 'audio_inputs' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if sha(target) != digest:
            raise ValueError('audited audio copy changed: ' + str(relative))
        copies[target] = digest
        if relative.as_posix() in assets:
            runtime = stage / relative
            runtime.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, runtime)
            copies[runtime] = digest
    evidence = dict(candidate=str(candidate), identity=result['identity'],
                    integration_inputs_sha256=sha(manifest), source_policy=metadata['source_policy'],
                    source_selection='byte_identical_audio_subset_of_independently_audited_native_candidate',
                    source_snapshot_sha256=metadata['source_snapshot_sha256'],
                    bluetooth_source_snapshot_sha256=metadata['bluetooth']['source_snapshot_sha256'],
                    compilation_sources=list(AUDIO_SOURCES),
                    selected_sha256={str(path.relative_to(source)): digest for path, digest in identities.items()
                                     if path != manifest},
                    audit=result, memory_model='128_KiB_delay_ring_only_not_physical_DDR_controller',
                    physical_audio_verified=False)
    (stage / 'audio_inputs.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return [stage / 'audio_inputs' / relative for relative in AUDIO_SOURCES], evidence, identities, copies
