"""Reuse the validated BLE business transport with native workstation PCM."""

from pathlib import Path
import json
import shutil
import subprocess
import sys

from tools import workstation_pinout
from tools.stage_usb_firmware import sha


SDC = (
    'set_max_delay 10.000 -from [get_regs {u_ble_pcm_cdc/held_data*}] -to [get_regs {u_ble_pcm_cdc/destination_data*}]\n'
    'set_false_path -hold -from [get_regs {u_ble_pcm_cdc/held_data*}] -to [get_regs {u_ble_pcm_cdc/destination_data*}]\n'
    'set_false_path -to [get_pins {u_ble_pcm_cdc/req_meta*/D u_ble_pcm_cdc/ack_meta*/D}]\n'
    'set_false_path -to [get_pins {u_ble_pcm_cdc/source_release*/CLEAR u_ble_pcm_cdc/destination_release*/CLEAR}]\n'
    'set_false_path -from [get_ports {ble_uart_rx_i}] -to [get_pins {u_bluetooth/u_core/transport/uart/rx_sync_0_s*/D}]\n'
    'set_max_delay 2.000 -from [get_pins {u_bluetooth/u_core/transport/uart/rx_sync_0_s*/Q}] '
    '-to [get_pins {u_bluetooth/u_core/transport/uart/rx_sync_1_s*/D}]\n'
    'set_false_path -to [get_ports {ble_uart_tx_o ble_bt_dis_n ble_wl_dis_n}]\n'
)


def prepare(root, directory, stage, pinout_output, plan, *, relative_rom_paths=False):
    repository = root.parents[3]
    protocol = repository / 'projects/25k/example/RTL8723DS_PROTOCOL'
    vendor = repository / 'example/RTL8723DS/vendor/rtl8723ds_ble'
    mapping = json.loads((root / 'boards/custom_138k/bluetooth.json').read_text())
    profile = json.loads((root / 'boards/custom_138k/pinout.json').read_text())
    netlists, _ = workstation_pinout.load_sources(profile, directory)
    carrier, module = netlists['carrier'], netlists['bluetooth']
    for node, network in mapping['anchors'].items():
        if carrier.network(node) != network:
            raise ValueError('Bluetooth connector anchor changed: ' + node)
    occupied = {ball for port in plan['ports'].values() for ball in port['balls']}
    occupied.update(plan['reserved_balls'].values())
    for port, record in mapping['ports'].items():
        connector = record['connector']
        reference = connector*2-1 if connector <= 50 else 202-connector*2
        if reference != record['core_pin'] or record['ball'] in occupied:
            raise ValueError('Bluetooth core connector mapping or ball collision: ' + port)
        carrier.same('J2.'+str(connector), 'FPC3.'+str(record['carrier_pin']))
        module.same('FPC1.'+str(25-record['carrier_pin']), record['module_node'])
        if module.network(record['module_node']) != record['signal']:
            raise ValueError('Bluetooth UART/control direction changed: ' + port)
        occupied.add(record['ball'])
        plan['ports'][port] = dict(balls=[record['ball']], origin='reviewed_core_connector_bluetooth')
    plan['bluetooth_mapping'] = mapping
    plan['identity'] += '_native_ble_v1'
    constraints = workstation_pinout.render_constraints(plan)
    plan['constraints_sha256'] = workstation_pinout.digest(constraints.encode())
    (pinout_output / 'pinout.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    (pinout_output / 'custom_138k.locations.cst').write_text(constraints)
    result = stage_business(root, stage, relative_rom_paths=relative_rom_paths)
    result['mapping'] = mapping
    return result


def stage_business(root, stage, *, relative_rom_paths=False, resource_optimized=False):
    """Stage the existing business source policy without replacing its recorder.

    The teammate short-store backend is not the task3 single CPU/BLE object.
    Keep this selection explicit until its address, drain, reset and object
    integration have separate evidence; default staging remains byte-identical.
    """
    if resource_optimized:
        raise ValueError('short BLE DDR store is not integrated with the single recording owner')
    repository = root.parents[3]
    protocol = repository / 'projects/25k/example/RTL8723DS_PROTOCOL'
    vendor = repository / 'example/RTL8723DS/vendor/rtl8723ds_ble'
    sources = [protocol / name for name in (
        'prepare_adapted.py', 'adaptations/bt_hci_init.v', 'adaptations/bt_verilog_core.v',
        'adaptations/bt_gatt.v', 'adaptations/bt_h5_transport.v', 'adaptations/bt_uart_fast.v',
        'adaptations/bt_acl_bridge.v', 'rtl/ble_protocol_command.v', 'rtl/ble_recording.v',
        )]
    sources += [vendor / name for name in ('MANIFEST.json', 'rtl8723ds_patch.mem',
                                           'rtl/bt_uart.v', 'rtl/reset_release_sync.v')]
    identities = {source.relative_to(repository).as_posix():sha(source) for source in sources}
    manifest = json.loads((vendor / 'MANIFEST.json').read_text())['files']
    business_manifest = json.loads((protocol / 'vendor/rtl8723ds_ble/MANIFEST.json').read_text())['files']
    if manifest != business_manifest:
        raise ValueError('remote 138K transport and BLE business vendor identities differ')
    for name in ('rtl/bt_uart.v', 'rtl/reset_release_sync.v', 'rtl8723ds_patch.mem'):
        if sha(vendor / name) != manifest[name]['sha256']:
            raise ValueError('BLE frozen input changed: ' + name)
    destination = stage / 'native_bluetooth'
    destination.mkdir()
    result = subprocess.run([sys.executable, str(protocol / 'prepare_adapted.py'), '--output', str(destination)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('BLE checked storage adaptation failed: ' + result.stdout + result.stderr)
    for source in sources:
        if source.suffix in ('.v', '.mem') and source.name not in ('bt_gatt.v', 'bt_h5_transport.v'):
            shutil.copyfile(source, destination / source.name)
    patch_relative = 'native_bluetooth/rtl8723ds_patch.mem'
    patch_path = patch_relative if relative_rom_paths else (destination / 'rtl8723ds_patch.mem').as_posix()
    (destination / 'patch_path.vh').write_text('`define WORKSTATION_BLE_PATCH_FILE '+json.dumps(patch_path)+'\n')
    patch_source = (vendor / 'rtl8723ds_patch.mem').relative_to(repository).as_posix()
    generated_inputs = {
        'native_bluetooth/patch_path.vh': dict(origin='checked_ble_rom_path_header',
            generator='tools/workstation_bluetooth.py', generator_sha256=sha(Path(__file__)),
            sha256=sha(destination / 'patch_path.vh'), target=patch_relative, target_path=patch_path),
        patch_relative: dict(origin='locked_ble_vendor_patch', source=patch_source,
            source_sha256=identities[patch_source], sha256=sha(destination / 'rtl8723ds_patch.mem')),
    }
    for relative, expected in identities.items():
        if sha(repository / relative) != expected:
            raise ValueError('BLE source changed during preparation: ' + relative)
    return dict(source_snapshot_sha256=identities, capacity_frames=16384,
                rom_path_policy='stage_relative' if relative_rom_paths else 'absolute_original_candidate',
                generated_input_provenance=generated_inputs,
                transport_source='example/RTL8723DS/vendor/rtl8723ds_ble',
                business_source='projects/25k/example/RTL8723DS_PROTOCOL',
                source_policy='remote_138k_transport_with_existing_second40_business_adaptations',
                capture_source='post_fpc_i2s_48k_stereo_pcm16', sources=[str(path.relative_to(stage))
                    for path in sorted(destination.glob('*.v'))],
                external_seal_protocol=dict(parameter='EXTERNAL_SEAL_PROTOCOL', default=0,
                    clock='clk_50m', wire_contract_changed=False,
                    source_policy='shared_first_party_default_off_ports; native_top_must_explicitly_enable'))
