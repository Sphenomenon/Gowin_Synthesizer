"""Select versioned 138K business sources; no RTL text generation or fallback."""
from pathlib import Path
import hashlib,json,shutil
from tools import workstation_bluetooth_ddr as legacy
from tools.workstation_ble_recording_policy import metadata as raw_metadata
POLICY='ae350_ble_business_owner_v2'
PROVIDER='rtl/workstation/workstation_profile_ae350_business_v1.sv'
DIRECTORY='rtl/bluetooth/cpu_owner'
COPIES={
    'native_bluetooth/ble_protocol_command.v':DIRECTORY+'/ble_protocol_command.v',
    'native_bluetooth/bt_gatt.v':DIRECTORY+'/bt_gatt.v',
    'native_bluetooth/bt_verilog_core.v':DIRECTORY+'/bt_verilog_core.v',
    'rtl/bluetooth/workstation_bluetooth.sv':DIRECTORY+'/workstation_bluetooth.sv',
}
SOURCES=(DIRECTORY+'/workstation_ble_record_data_engine.sv',
    DIRECTORY+'/workstation_ble_record_data_service.sv','rtl/services/workstation_business_mailbox.sv')
DEPENDENCIES=(*COPIES.values(),DIRECTORY+'/provenance.json',
    DIRECTORY+'/CONTRACT.md','rtl/services/BUSINESS_MAILBOX_CONTRACT.md',
    'rtl/workstation/workstation_profile_r00_no_local_panel.sv','tools/workstation_cpu_business.py',
    'tools/ae350_ble_business_indirect_review.json')
HCI_POLICY='native_shared_hci_owner_v1'
HCI_DIRECTORY='rtl/bluetooth/hci_owner'
HCI_COPIES=dict(COPIES,**{
    'native_bluetooth/bt_verilog_core.v':HCI_DIRECTORY+'/workstation_hci_native_core.v',
    'rtl/bluetooth/workstation_bluetooth.sv':HCI_DIRECTORY+'/workstation_hci_bluetooth.sv'})
HCI_SOURCES=tuple(HCI_DIRECTORY+'/'+name for name in (
    'workstation_hci_flow_owner.sv','workstation_hci_event_decoder.sv',
    'workstation_hci_host_rx_owner.sv','workstation_hci_host_bootstrap.sv',
    'workstation_hci_native_transport.sv','workstation_hci_cpu_mailbox.sv',
    'workstation_hci_ble_queue.sv','workstation_hci_ble_bridge.v','workstation_hci_initializer.v'))
HCI_DEPENDENCIES=(*HCI_COPIES.values(),HCI_DIRECTORY+'/NATIVE_TRANSPORT_CONTRACT.md',
    'rtl/workstation/workstation_profile_ae350_business_v1.sv',
    'rtl/workstation/workstation_profile_hci_owner_v1.sv')
def selection(shared_hci=False):
    return (HCI_COPIES,(*SOURCES,*HCI_SOURCES),(*DEPENDENCIES,*HCI_DEPENDENCIES)) if shared_hci else (COPIES,SOURCES,DEPENDENCIES)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def metadata():
    m=raw_metadata()
    m.update(policy='native_raw_ddr_ae350_business_v2',
        business_owner='AE350 ble_business_owner.c',object_ids_tasks_crc_codec_transfer_owned_by_ble=False,
        software_owned=['task_table','operation_ids','object_id_allocation','transfer_id_allocation','record_commands','open_close_cancel_commands','read_ack_combined_policy','resume_offsets','transfer_timeout_policy'],
        hardware_owned=['capture_crc','raw_storage','native_commit','media_seal','block_fetch','rice_codec','wire_bytes'],
        remaining_software_migration=[])
    return m
def prepare(root,stage,*,shared_hci=False):
    root,stage=Path(root),Path(stage)
    # Verify exactly the original stage being replaced, without generating the
    # legacy raw recorder. Stable native sources already contain the raw ports.
    before={}
    for name,relative in legacy.STAGED_PATHS.items():
        p=stage/relative
        if sha(p)!=legacy.INPUT_SHA256[name]:raise ValueError('CPU business original stage drift: '+relative)
        before[relative]=sha(p)
    copies,sources,dependencies=selection(shared_hci)
    for destination,source in copies.items():
        shutil.copyfile(root/source,stage/destination)
    retired='native_bluetooth/ble_recording.v'
    (stage/retired).unlink()
    evidence=dict(policy=HCI_POLICY if shared_hci else POLICY,source_sha256={p:sha(root/p) for p in (*sources,*dependencies)},
        copied={d:dict(source=s,sha256=sha(root/s)) for d,s in copies.items()},
        replaced_input_sha256=before,retired=[retired],rtl_text_generation=False,
        hardware_tested=False,synthesis=False,pnr=False,deployment_allowed=False)
    verify_prepared(root,stage,evidence,shared_hci=shared_hci)
    return evidence
def verify_prepared(root,stage,evidence,*,shared_hci=False):
    root,stage=Path(root),Path(stage)
    copies,sources,dependencies=selection(shared_hci)
    expected_sources={p:sha(root/p) for p in (*sources,*dependencies)}
    expected_copies={d:dict(source=s,sha256=sha(root/s)) for d,s in copies.items()}
    expected_before={legacy.STAGED_PATHS[n]:h for n,h in legacy.INPUT_SHA256.items()}
    if evidence.get('policy')!=(HCI_POLICY if shared_hci else POLICY) or evidence.get('source_sha256')!=expected_sources or evidence.get('copied')!=expected_copies or evidence.get('replaced_input_sha256')!=expected_before or evidence.get('retired')!=['native_bluetooth/ble_recording.v'] or evidence.get('rtl_text_generation') is not False:
        raise ValueError('CPU business source policy/evidence drift')
    for destination,source in copies.items():
        if sha(stage/destination)!=sha(root/source):raise ValueError('CPU business staged source drift: '+destination)
    if (stage/'native_bluetooth/ble_recording.v').exists():raise ValueError('retired RTL business owner remains staged')
    engine=(root/SOURCES[0]).read_text()
    for token in ('operation_counter','object_counter','transfer_counter','task_id[','task_valid','allocate_task',
        'transfer_open','confirmed_offset','pending_offset','pending_crc','last_ack',
        'transfer_time','extended_limit','block_pending'):
        if token in engine:raise ValueError('retired RTL identity/task owner returned: '+token)
    # The codec and wire builder are retained bytes. Banks only differ in the
    # wrapper's new command/result ports, outside these protected regions.
    for marker,ending,key in [('module ble_rice_encoder',None,'encoder'),
        ('    // Four explicit','    function [7:0] le32;','transfer_banks'),
        ('    function [7:0] transfer_message_byte;','    task reject;','wire_message_bytes')]:
        data=engine.encode();start=data.index(marker.encode());end=data.index(ending.encode(),start) if ending else len(data)
        if hashlib.sha256(data[start:end]).hexdigest()!=legacy.PROTECTED_SHA256[key]:
            raise ValueError('retained data-plane bytes drift: '+key)
    return evidence
