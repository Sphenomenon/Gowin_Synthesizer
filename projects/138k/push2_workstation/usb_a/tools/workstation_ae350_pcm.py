"""Explicit candidate PCM source inventory; no accepted profile is modified.

A fresh profile must opt in, merge HCI wrapper ports, lock these inputs and
supply audited physical CDC constraints. This module does not generate RTL.
"""
from pathlib import Path
import hashlib,json
POLICY='ae350_decoded_pcm_source_v1'
MACRO='WORKSTATION_AE350_PCM'
SOURCES=('rtl/audio/workstation_ae350_pcm_owner.sv','rtl/audio/workstation_ae350_pcm_session.sv')
DEPENDENCIES=('rtl/audio/AE350_PCM_INGRESS_CONTRACT.md','tools/workstation_ae350_pcm.py')
COMPOSITION=('rtl/workstation/gw138k_push_workstation_top.v',
    'rtl/workstation/workstation_runtime_controlled.sv','rtl/workstation/workstation_runtime_audio.sv',
    'rtl/audio/workstation_i2s_serializer.sv')
def source_bundle(root):
    root=Path(root).resolve();hashes={}
    for name in (*SOURCES,*DEPENDENCIES,*COMPOSITION):
        p=root/name
        if not p.is_file() or not p.resolve().is_relative_to(root):raise FileNotFoundError(name)
        hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return dict(policy=POLICY,source_set_sha256=identity,source_sha256=hashes,
        sources=list(SOURCES),dependencies=list(DEPENDENCIES),composition=list(COMPOSITION),
        required_macros=['WORKSTATION_RUNTIME_NATIVE','WORKSTATION_CPU_BLE_BUSINESS',MACRO],
        apb_base=0xf8060000,slot_bytes=512,slots=4,prefill_frames=256,
        caps=0x67,sustained_verified=False,measured_total_delay_valid=False,
        profile_selected=False,rtl_text_generation=False,synthesis_verified=False,
        physical_cdc_accepted=False,hardware_accepted=False,deployment_allowed=False)
