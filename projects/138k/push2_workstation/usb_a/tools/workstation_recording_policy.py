"""Explicit R00 production source selection; no EDA, acceptance or deployment."""
from pathlib import Path
import hashlib
import re
from tools.workstation_baselines import load_baseline

NAME='custom138k-workstation-r00-v1'
CONFIG='boards/custom_138k/workstation_profile_r00_v1.json'
PROVIDER='rtl/workstation/workstation_profile_r00_runtime.sv'
POLICY='native_owner8_pcm_ddr_r00_v1'
SOURCES=(
    'rtl/workstation/workstation_recording_runtime.sv',
    'rtl/services/workstation_recording_ddr_service.sv',
    'rtl/services/workstation_recording_seal_bridge.sv',
    'rtl/audio/workstation_pcm_ddr_backend.sv',
    'rtl/memory/workstation_recording_ddr_client_queues.sv',
    'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
    'rtl/memory/workstation_recording_ddr_native_bridge.sv',
)
DEPENDENCIES=(
    'rtl/workstation/workstation_profile_no_cnn_runtime.sv',
    'rtl/ddr_address_map.vh',
    'rtl/services/RECORDING_DDR_SERVICE_CONTRACT.md',
    'rtl/audio/PCM_DDR_BACKEND_CONTRACT.md',
    'rtl/memory/RECORDING_DDR_NATIVE_CONTRACT.md',
)
MAP_SOURCE='rtl/ddr_address_map.vh'
MAP_DESTINATION='src/memory/ddr_address_map.vh'

def digest(data):return hashlib.sha256(data).hexdigest()
def macros(data):return dict(re.findall(rb'^`define[ \t]+(\w+)[ \t]+([^\r\n]+)',data,re.M))
def address_map_inputs(root):
    root=Path(root);baseline=load_baseline(root,'resource_rework_route0')
    original=baseline.read_bytes(MAP_DESTINATION);selected=(root/MAP_SOURCE).read_bytes()
    old,new=macros(original),macros(selected)
    if not old or any(new.get(key)!=value for key,value in old.items()):
        raise ValueError('R00 address-map adaptation changes an existing allocation')
    if new.get(b'PRJ1_DDR_RECORDING_BYTE_BASE')!=b"32'h3050_0000" or new.get(b'PRJ1_DDR_RECORDING_APP_BASE')!=b"29'h0c14_0000":
        raise ValueError('R00 recording allocation changed')
    return original,selected

def install_address_map(root,stage):
    original,selected=address_map_inputs(root);target=Path(stage)/MAP_DESTINATION
    if target.read_bytes()!=original:raise ValueError('R00 parent address-map identity changed')
    target.write_bytes(selected)
    return dict(source=MAP_SOURCE,destination=MAP_DESTINATION,
        parent_sha256=digest(original),selected_sha256=digest(selected),
        original_macros_preserved=True,policy='versioned_allocation_authority_no_text_overlay')

def verify_address_map(root,stage,evidence):
    original,selected=address_map_inputs(root)
    expected=dict(source=MAP_SOURCE,destination=MAP_DESTINATION,parent_sha256=digest(original),
        selected_sha256=digest(selected),original_macros_preserved=True,
        policy='versioned_allocation_authority_no_text_overlay')
    if evidence!=expected or (Path(stage)/MAP_DESTINATION).read_bytes()!=selected:
        raise ValueError('R00 selected address-map provenance changed')

def metadata():
    return dict(policy=POLICY,production_owner8_selected=True,owner_bits=4,owner=8,
        final_pcm_source='u_managed/runtime/serializer completed physical frame',
        frame_order='physical high16=left; backend/download low16=left, high16=right',
        sample_rates_hz=[48000,44100],stage_capacity_frames=16384,stage_capacity_bytes=65536,
        apb_base='0xf8040000',backend='u_recording/service/backend',
        pcm_cdc='u_recording/pcm_cdc',native_commit='u_recording/native_commit',
        arbiter='u_video/u_arbiter/g_recording/u_core',
        default_ble_backend_replaced=False,ble_format_extended=False,
        normal_seal_before_rate_switch=True,physical_resource_saving_proven=False,
        source_cdc_complete=False,physical_cdc_accepted=False,r00_complete=False,
        hardware_tested=False,deployment_allowed=False)
