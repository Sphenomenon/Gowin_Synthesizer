"""Task3 W-media native component policy; not yet a board-build profile.

The versioned DDR map is the capacity/allocation authority. No W21 trim, source
overlay, private input fallback, physical pin claim or accepted-profile switch.
"""
from pathlib import Path
import hashlib
import re

POLICY='task3_w_native_media_cnn_single_recording_v1'
TOP='rtl/workstation/workstation_task3_w_media.sv'
INGRESS='rtl/workstation/workstation_task3_record_ingress.sv'
MAP='rtl/ddr_address_map.vh'
SOURCES=(TOP,INGRESS,'rtl/memory/workstation_media_memory.sv',
    'rtl/memory/workstation_ble_raw_ddr_store.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv',
    'rtl/memory/workstation_recording_ddr_client_queues.sv','rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
    'rtl/music/workstation_cnn_task_service.sv','rtl/music/workstation_cnn_ddr_broker.sv')

def recording_geometry(root):
    text=(Path(root)/MAP).read_text()
    values={}
    for name,width,radix,value in re.findall(r"^`define\s+(\w+)\s+(\d+)'([dh])([0-9a-fA-F_]+)\s*$",text,re.M):
        number=int(value.replace('_',''),16 if radix=='h'else 10)
        if number>=1<<int(width):raise ValueError('DDR map literal overflows declared width')
        values[name]=number
    prefix='PRJ1_DDR_TASK3_W_RECORDING_'
    def val(name):return values[prefix+name]
    frames,byte_count=val('CAPACITY_FRAMES'),val('BYTES')
    if frames!=2880000 or byte_count!=frames*4 or frames%8 or val('APP_BASE')%8:
        raise ValueError('task3 W recording format/capacity/alignment drift')
    if (val('BYTE_BASE')!=val('APP_BASE')*4 or val('BYTE_LAST')!=(val('APP_LAST')+1)*4-1 or
        val('BYTE_LAST')-val('BYTE_BASE')+1!=byte_count or val('LAST_BEAT')!=val('APP_LAST')-7 or
        not val('POOL_BYTE_BASE')<=val('BYTE_BASE')<=val('BYTE_LAST')<=val('POOL_BYTE_LAST')):
        raise ValueError('task3 W recording byte/native geometry drift')
    cnn_prefix='PRJ1_DDR_TASK3_W_CNN_PCM_'
    if values[cnn_prefix+'POOL_BYTE_BASE']<=val('POOL_BYTE_LAST'):
        raise ValueError('task3 CNN task overlaps recording reservation')
    return dict(capacity_frames=frames,capacity_bytes=byte_count,sample_rate_hz=48000,format=1,
        byte_base=val('BYTE_BASE'),byte_last=val('BYTE_LAST'),native_word_base=val('APP_BASE'),
        native_word_last=val('APP_LAST'),last_native_BL8=val('LAST_BEAT'),
        pool_padding_bytes=val('POOL_BYTE_LAST')-val('BYTE_LAST'))

def firmware_capacity_flag(root):
    return '-DA138_BLE_RECORD_CAPACITY_FRAMES='+str(recording_geometry(root)['capacity_frames'])+'u'

def metadata(root):
    root=Path(root)
    return dict(policy=POLICY,stage='native_component_not_board_profile',
        source_sha256={rel:hashlib.sha256((root/rel).read_bytes()).hexdigest()for rel in(*SOURCES,MAP)},
        recording=recording_geometry(root),firmware_capacity_flag=firmware_capacity_flag(root),
        native_owners=dict(CNN=5,delay=6,single_recording_raw=8),
        recording_object_owner='existing unique ble_business_owner firmware_owner and physical engine',
        raw_storage_is_second_object=False,R00_backend_selected=False,headless=True,
        full_HCI_Classic_GATT_required=True,W21_audio_only_policy_reused=False,
        board_shell_integrated=False,LCD_electrical_and_transport_verified=False,
        native_LCD_pin_driving=False,M_final_tap_connected=False,
        communication_may_backpressure_M_sample_schedule=False,
        synthesis=False,place_and_route=False,hardware_acceptance=False)
