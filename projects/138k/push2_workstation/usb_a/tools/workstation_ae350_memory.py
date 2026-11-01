"""Explicit AE350 runtime/cold-storage composition, separate from accepted profiles."""
from pathlib import Path
import xml.etree.ElementTree as ElementTree

DEFAULT_PROFILE = 'pl16k_8k'
LOCAL_PROFILE = 'ilm64k_dlm64k'
SOURCE = 'rtl/memory/workstation_ae350_boot_memory.sv'
PARENT = 'src/ae350/gw138k_boot_memory.sv'
PLATFORM = {
    'riscv_ae350_config.v': 'efa61e6fbac3229458928fe486bc960fc8aec2656d9b9400bdffee5f7a0c9460',
    'src/ae350/riscv_ae350_config.v': 'efa61e6fbac3229458928fe486bc960fc8aec2656d9b9400bdffee5f7a0c9460',
    'src/ae350/riscv_ae350_top.v': 'd22df5c257105b5f98133085e20d70377da692bdb9b8398ad6beacf39fdf3d89',
}


def selection(configuration):
    memory = configuration.get('ae350_memory_profile', DEFAULT_PROFILE)
    capacity = configuration.get('ae350_boot_rom_bytes', 16384)
    joint=(memory==LOCAL_PROFILE and configuration.get('hci_transport_policy')=='native_shared_hci_owner_v1'
        and configuration.get('ae350_pcm_policy')=='ae350_decoded_pcm_source_v1')
    runtime=(joint and (capacity,configuration.get('ae350_firmware_policy'))in
        ((131072,'ae350_classic_runtime_failclosed_v1'),(98304,'ae350_classic_runtime_rom96_failclosed_v1')))
    worker=(joint and capacity==131072 and configuration.get('demo_role')=='W' and
        configuration.get('ae350_firmware_policy')=='ae350_worker_session_classic_runtime_v1' and
        configuration.get('recording_owner_policy')=='single_ble_ddr_object_v1')
    audio_worker=(joint and capacity==131072 and configuration.get('demo_role')=='W' and
        configuration.get('ae350_firmware_policy')=='ae350_worker_audio_only_classic_runtime_v1' and
        configuration.get('display_policy')=='disabled_worker_audio_only_v1' and
        configuration.get('recording_owner_policy')=='disabled_worker_audio_only_v1')
    media_worker=(joint and capacity==131072 and configuration.get('demo_role')=='W' and
        configuration.get('ae350_firmware_policy')=='task3_w_headless_media_single_recording_60s_v1' and
        configuration.get('display_policy')=='disabled_worker_media_v1' and
        configuration.get('recording_owner_policy')=='single_C_BLE_ddr_60s_v1')
    if (memory, capacity) not in ((DEFAULT_PROFILE, 16384), (LOCAL_PROFILE, 65536)) and not (runtime or worker or audio_worker or media_worker):
        raise ValueError('unsupported workstation AE350 memory/storage composition')
    return dict(memory_profile=memory, boot_rom_bytes=capacity)


def verify_prepared(stage, build, configuration, sha):
    """Bind actual compiled ROM owner, hard-IP configuration and generated image."""
    stage = Path(stage)
    chosen = selection(configuration)
    if (build.get('memory_profile') != chosen['memory_profile'] or
            build.get('capacity', {}).get('rom_capacity_bytes') != chosen['boot_rom_bytes']):
        raise ValueError('AE350 generated runtime/storage selection changed')
    from tools.stage_ae350_firmware import decode_rom
    if chosen['boot_rom_bytes']in (98304,131072):
        from tools.workstation_classic_runtime import decode_rom as decode_runtime_rom
        decode_runtime_rom(stage/'firmware/boot.mem',chosen['boot_rom_bytes'])
    else:decode_rom(stage / 'firmware/boot.mem', chosen['boot_rom_bytes'])
    entries = ElementTree.parse(stage / 'Prj1.gprj').find('FileList')
    enabled = [entry.get('path') for entry in entries if entry.get('enable') == '1']
    expanded = chosen['memory_profile'] == LOCAL_PROFILE
    if enabled.count(SOURCE) != int(expanded) or enabled.count(PARENT) != int(not expanded):
        raise ValueError('AE350 physical ROM compilation owner changed')
    if expanded:
        storage={65536:'explicit_64k_pl_boot_rom',98304:'explicit_96k_pl_boot_rom_split',131072:'explicit_128k_pl_boot_rom_split'}[chosen['boot_rom_bytes']]
        if (build.get('cold_boot', {}).get('image_capacity_bytes') != chosen['boot_rom_bytes'] or
                build.get('cold_boot', {}).get('image_storage') != storage or
                build.get('cold_boot', {}).get('cache_policy') != 'reject_enabled_i_or_d_cache_on_entry'):
            raise ValueError('AE350 expanded cold boot storage evidence changed')
        for relative, expected in PLATFORM.items():
            if sha(stage / relative) != expected:
                raise ValueError('AE350 selected hard-IP platform drift: ' + relative)
    return dict(**chosen, physical_rom_source=SOURCE if expanded else PARENT,
                cache_policy='disabled_fail_if_enabled' if expanded else 'historical_startup',
                platform_sha256=PLATFORM if expanded else {}, hardware_verified=False)
