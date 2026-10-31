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
    runtime128=(memory,capacity)==(LOCAL_PROFILE,131072)and configuration.get('ae350_firmware_policy')=='ae350_classic_runtime_failclosed_v1'and configuration.get('hci_transport_policy')=='native_shared_hci_owner_v1'and configuration.get('ae350_pcm_policy')=='ae350_decoded_pcm_source_v1'
    if (memory, capacity) not in ((DEFAULT_PROFILE, 16384), (LOCAL_PROFILE, 65536)) and not runtime128:
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
    if chosen['boot_rom_bytes']==131072:
        from tools.workstation_classic_runtime import decode_rom as decode_runtime_rom
        decode_runtime_rom(stage/'firmware/boot.mem')
    else:decode_rom(stage / 'firmware/boot.mem', chosen['boot_rom_bytes'])
    entries = ElementTree.parse(stage / 'Prj1.gprj').find('FileList')
    enabled = [entry.get('path') for entry in entries if entry.get('enable') == '1']
    expanded = chosen['memory_profile'] == LOCAL_PROFILE
    if enabled.count(SOURCE) != int(expanded) or enabled.count(PARENT) != int(not expanded):
        raise ValueError('AE350 physical ROM compilation owner changed')
    if expanded:
        storage='explicit_128k_pl_boot_rom_split'if chosen['boot_rom_bytes']==131072 else'explicit_64k_pl_boot_rom'
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
