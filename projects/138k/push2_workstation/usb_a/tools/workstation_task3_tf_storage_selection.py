"""Explicit DIRECT CRC/cache selection and exact inverse provenance.

The native top is the product input. Inversion only feeds older strict source
validators; it never generates, installs or selects a historical product top.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

TOOL='tools/workstation_task3_tf_storage_selection.py'
TOP='rtl/workstation/gw138k_push_workstation_top.v'
REFERENCE='rtl/workstation/workstation_task3_tf_storage_top_reference.json'
POLICY='direct_sd_crc16_validated_fat_cache_v1'
PARENT_SHA256='9377948d17aa8fed710744827cc4c4e18b7414d88cdfd5f5ca28a86978b04615'
SELECTED_SHA256='4b4a99f674a7033b032a3e82b98e553d7d7675689627ca4fb0cebf9746738d0f'
REFERENCE_SHA256='7aa28c3bdcf90dd1eaa08912ac0a33229b3e577276c433f9a52f3d1b34b97a53'
MARKER='    // Explicit task3 M DIRECT storage selection; component defaults stay off.\n'

def digest(raw):
    return hashlib.sha256(raw.encode() if isinstance(raw,str) else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('DIRECT TF storage selection: '+message)

def inverse_top(root,text):
    """Restore exact a070 input before the separate unchanged W inverse."""
    if MARKER not in text and '.FAT_SECTOR_CACHE(1)) u_tf_audio' not in text:
        return text
    raw=(Path(root)/REFERENCE).read_bytes()
    require(digest(raw)==REFERENCE_SHA256,'reference identity drift')
    record=json.loads(raw)
    require(record.get('schema')==1 and
            record.get('policy')=='task3_direct_crc16_fat_cache_exact_top_selection_v1' and
            record.get('source')==TOP and record.get('parent_sha256')==PARENT_SHA256 and
            record.get('selected_sha256')==SELECTED_SHA256 and
            record.get('selected_only_in_direct_branch') is True and
            record.get('reconstruction_used_only_for_verification') is True and
            len(record.get('edits',[]))==1,'reference contract drift')
    require(digest(text)==SELECTED_SHA256,'native selected top identity drift')
    result=text
    for row in reversed(record['edits']):
        require(result.count(row['selected'])==1,'inverse anchor drift')
        result=result.replace(row['selected'],row['parent'],1)
    require(digest(result)==PARENT_SHA256,'inverse parent identity drift')
    forward=result
    for row in record['edits']:
        require(forward.count(row['parent'])==1,'forward anchor drift')
        forward=forward.replace(row['parent'],row['selected'],1)
    require(forward==text,'inverse forward round trip drift')
    return result

def configuration_selection(configuration):
    require(configuration.get('tf_policy')=='task3_m_native_direct_tf_v1' and
            configuration.get('tf_storage_policy')==POLICY and
            type(configuration.get('tf_sdc_revision')) is int and
            configuration['tf_sdc_revision']==3,
            'explicit DIRECT CRC1/cache1/r3 configuration required')
    return dict(policy=POLICY,VERIFY_DATA_CRC=1,FAT_SECTOR_CACHE=1,sdc_revision=3)

def prepared_selection(root,stage,configuration):
    """Check the actual selected inputs, independently of inverse validators."""
    root,stage=Path(root),Path(stage)
    selection=configuration_selection(configuration)
    from tools.workstation_profile import PROFILE_REGISTRY
    providers={s['provider'] for s in PROFILE_REGISTRY.values() if s.get('tf_direct_enabled',False)}
    selected=[r.get('path') for r in ET.parse(stage/'Prj1.gprj').find('FileList') if r.get('enable')=='1']
    actual=providers.intersection(selected)
    require(len(actual)==1,'registered DIRECT provider must be unique')
    provider=next(iter(actual))
    require(all(s['provider'] not in selected or s['provider']==provider
                for s in PROFILE_REGISTRY.values()),'another profile provider is selected')
    from tools.workstation_task3_tf_direct import SOURCES,UNSELECTED_WORKER_SOURCES
    require(all(selected.count(p)==1 for p in SOURCES),'complete DIRECT compilation inputs required')
    require(not set(selected).intersection(UNSELECTED_WORKER_SOURCES),'M cannot compile W CNN tasks')
    raw_top=(stage/TOP).read_text()
    require(digest(raw_top)==SELECTED_SHA256 and (root/TOP).read_text()==raw_top,
            'actual native top must be the new maintained input')
    inverse_top(stage,raw_top)
    # This check deliberately reads the actual native branch, not its inverse.
    parameters=re.findall(r'workstation_tf_direct_runtime_service\s*#\((.*?)\)\s*u_tf_audio\s*\(',raw_top,re.S)
    require(len(parameters)==1,'native TF owner instance must be unique')
    require(re.findall(r'\.(\w+)\s*\(\s*([^()]+)\s*\)',parameters[0])==[
        ('SEPARATE_COMMON_RESET','1'),('VERIFY_DATA_CRC','1'),('FAT_SECTOR_CACHE','1')],
        'actual native instance must select explicit CRC1/cache1')
    provider_text=(stage/provider).read_text().splitlines()
    require(provider_text.count('`define WORKSTATION_TF_DIRECT_NATIVE')==1 and
            provider_text.count('`define WORKSTATION_NO_CNN')==1 and
            '`define WORKSTATION_DEMO_NO_TF' not in provider_text,'provider DIRECT/no-CNN selection drift')
    from tools.workstation_tf_fat_cache_provenance import validate_adaptation
    chain,_=validate_adaptation(stage)
    source_sha256={p:digest((stage/p).read_bytes()) for p in SOURCES}
    require(all((root/p).read_bytes()==(stage/p).read_bytes() for p in SOURCES),
            'staged DIRECT sources differ from maintained bytes')
    return dict(selection,provider=provider,provider_sha256=digest((stage/provider).read_bytes()),
        native_top_sha256=digest(raw_top),source_sha256=source_sha256,
        reference_sha256=REFERENCE_SHA256,source_chain=chain,
        product_uses_native_source=True,reconstruction_used_only_for_verification=True,
        compiler_preprocessing_verified=False,synthesis_verified=False,physical_cdc_verified=False,
        hardware_tested=False)
