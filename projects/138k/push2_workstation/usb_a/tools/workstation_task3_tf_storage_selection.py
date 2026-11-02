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

def unwrap_paired_top(root,text):
    """Unwrap only an explicitly selected, fully identity-checked pair role.

    Existing callers have the stage directory, including its exact references
    and GPRJ. No historical source or private maintenance checkout is read.
    """
    common='`include "rtl/workstation/workstation_task3_paired_link_board.svh"'
    markers=('`include "rtl/workstation/workstation_task3_m_paired_board.svh"',
             '`include "rtl/workstation/workstation_task3_w_paired_board.svh"')
    if common not in text and not any(marker in text for marker in markers):
        return text,None
    from tools.workstation_profile import PROFILE_REGISTRY
    project=Path(root)/'Prj1.gprj'
    require(project.is_file(),'paired inverse requires actual compilation manifest')
    selected=[r.get('path') for r in ET.parse(project).find('FileList') if r.get('enable')=='1']
    # Multiple capacity configurations may reuse one exact role provider; the
    # compiled provider/role must still be unique, irrespective of config name.
    pairs={(s['paired_role'],s['provider']) for s in PROFILE_REGISTRY.values()
           if s.get('paired_board',False) and s['provider'] in selected}
    require(len(pairs)==1,'paired inverse requires unique registered role provider')
    selected_role,selected_provider=next(iter(pairs))
    pair=dict(paired_role=selected_role,provider=selected_provider)
    require(all(s['provider'] not in selected or s['provider']==pair['provider']
                for s in PROFILE_REGISTRY.values()),'paired inverse mixed profile providers')
    from tools.workstation_task3_paired_board import inverse_top as inverse_common,role_helper
    role=pair['paired_role']
    if common in text:text=inverse_common(root,text,role)
    return role_helper(role).inverse_top(root,text),role

def inverse_top(root,text):
    """Restore exact a070 input before the separate unchanged W inverse."""
    text,_=unwrap_paired_top(root,text)
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

def prepared_selection(root,stage,configuration,*,captured_source_sha256=None):
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
    maintained_top,paired_role=unwrap_paired_top(stage,raw_top)
    require(paired_role in (None,'M'),'DIRECT selected a non-M paired role')
    require(digest(maintained_top)==SELECTED_SHA256,
            'actual native top must be the new maintained input')
    if captured_source_sha256 is None:
        require((root/TOP).read_text()==maintained_top,
                'actual native top must be the new maintained input')
    else:
        # Immutable paired synthesis review has no second maintained checkout.
        # Its caller first verifies the mutually bound full candidate manifests.
        require(root.resolve()==stage.resolve() and paired_role=='M' and
                captured_source_sha256.get(TOP)==digest(maintained_top),
                'captured paired parent must match exact maintained identity')
    inverse_top(stage,raw_top)
    # This check deliberately reads the actual native branch, not its inverse.
    parameters=re.findall(r'workstation_tf_direct_runtime_service\s*#\((.*?)\)\s*u_tf_audio\s*\(',raw_top,re.S)
    require(len(parameters)==1,'native TF owner instance must be unique')
    expected_parameters=[('SEPARATE_COMMON_RESET','1')]
    if paired_role=='M':expected_parameters.append(('REMOTE_ANALYSIS_ENABLE','1'))
    expected_parameters.extend([('VERIFY_DATA_CRC','1'),('FAT_SECTOR_CACHE','1')])
    require(re.findall(r'\.(\w+)\s*\(\s*([^()]+)\s*\)',parameters[0])==expected_parameters,
        'actual native instance must select explicit CRC1/cache1')
    provider_text=(stage/provider).read_text().splitlines()
    require(provider_text.count('`define WORKSTATION_TF_DIRECT_NATIVE')==1 and
            provider_text.count('`define WORKSTATION_NO_CNN')==1 and
            '`define WORKSTATION_DEMO_NO_TF' not in provider_text,'provider DIRECT/no-CNN selection drift')
    from tools.workstation_tf_fat_cache_provenance import validate_adaptation
    chain,_=validate_adaptation(stage)
    source_sha256={p:digest((stage/p).read_bytes()) for p in SOURCES}
    if captured_source_sha256 is None:
        require(all((root/p).read_bytes()==(stage/p).read_bytes() for p in SOURCES),
                'staged DIRECT sources differ from maintained bytes')
    else:
        require(all(captured_source_sha256.get(p)==value for p,value in source_sha256.items()) and
                captured_source_sha256.get(provider)==digest((stage/provider).read_bytes()),
                'staged DIRECT sources differ from captured maintained bytes')
    return dict(selection,provider=provider,provider_sha256=digest((stage/provider).read_bytes()),
        native_top_sha256=digest(raw_top),source_sha256=source_sha256,
        **({'paired_role':paired_role,'maintained_parent_top_sha256':digest(maintained_top)}if paired_role is not None else{}),
        reference_sha256=REFERENCE_SHA256,source_chain=chain,
        product_uses_native_source=True,reconstruction_used_only_for_verification=True,
        compiler_preprocessing_verified=False,synthesis_verified=False,physical_cdc_verified=False,
        hardware_tested=False)
