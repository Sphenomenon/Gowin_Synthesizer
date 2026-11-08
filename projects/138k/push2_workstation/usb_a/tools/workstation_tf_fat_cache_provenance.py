"""Strict newer FAT-cache chain; invert to the unchanged CRC stage first.

Reconstruction verifies provenance only and never selects/writes product RTL.
"""
from pathlib import Path
import hashlib,json

POLICY='task3-direct-opt-in-validated-FAT-sector-cache-v1'
MANIFEST='rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.adaptation.json'
MANIFEST_SHA256='4a19c32642279a05deef72d6795d47dc4d79c4f623b8733cc7e69dcebb4f0e65'
BASIS={
    'rtl/tf_audio/storage/workstation_tf_file_reader.sv':'3d20a0d1cbe0475c958114f77e7a61dc94cabc3f0981c0ff8e77b023cf561ce8',
    'rtl/tf_audio/workstation_tf_direct_native_v1.sv':'5a54f4515b51a85638503ce849ef45c973fe88295403ad53906468db28f377af',
    'rtl/tf_audio/workstation_tf_direct_runtime_service.sv':'82f77d9b4dfcda27a3dc87ebde91a4f2876a7dab75879e1a10bbd0a971bf0428',
    'tools/workstation_tf_sd_crc16_provenance.py':'5a5ecace8234c700876debf219a2d5bf2c5aa8ede48bf0d51367d14777a10c11',
}
PRIOR_MANIFEST='rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.adaptation.json'
PRIOR_MANIFEST_SHA256='230b9436cab1b56311ef757f548ccf12705ff94ca7381b0e718aedfa7b0d17f4'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('FAT cache adaptation provenance: '+message)

def restore_crc_basis(root):
    root=Path(root);raw=(root/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'new manifest identity changed')
    m=json.loads(raw)
    require(m['schema']==1 and m['policy']==POLICY and m['parameter']=='FAT_SECTOR_CACHE' and
            m['default']==0 and m['requires_VERIFY_DATA_CRC']==1 and m['storage_bytes']==512 and
            m['metadata_only'] is True,'explicit validated metadata cache contract changed')
    require(m['prior_CRC_manifest']==dict(path=PRIOR_MANIFEST,sha256=PRIOR_MANIFEST_SHA256) and
            digest((root/PRIOR_MANIFEST).read_bytes())==PRIOR_MANIFEST_SHA256,
            'original CRC manifest bytes changed')
    require({r['path']:r['basis_sha256'] for r in m['adaptations']}==BASIS and
            len(m['adaptations'])==len(BASIS),'exact prior CRC-stage source identities changed')
    cache=m['new_cache']
    require(cache['path']=='rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv' and
            digest((root/cache['path']).read_bytes())==cache['sha256'],'cache source identity changed')
    restored={};rows=[];analysis_extension=None
    for row in m['adaptations']:
        actual=(root/row['path']).read_bytes()
        if row['path']=='rtl/tf_audio/storage/workstation_tf_file_reader.sv' and b'boot_geometry_step' in actual:
            from tools.workstation_tf_boot_geometry import restore as restore_geometry
            actual,_=restore_geometry(root,actual)
        if (row['path']=='rtl/tf_audio/workstation_tf_direct_runtime_service.sv' and
                b'parameter bit REMOTE_ANALYSIS_ENABLE=0' in actual):
            from tools.workstation_task3_tf_analysis_provenance import restore as restore_analysis
            actual,analysis_extension=restore_analysis(root,actual)
        require(digest(actual)==row['adapted_sha256'],'adapted source changed: '+row['path'])
        text=actual.decode()
        for e in reversed(row['edits']):
            require(e['count']==1 and text.count(e['after'])==1,'reverse anchor drift: '+row['path'])
            text=text.replace(e['after'],e['before'])
        prior=text.encode()
        require(digest(prior)==BASIS[row['path']],'inverse did not restore prior CRC source: '+row['path'])
        for e in row['edits']:
            require(text.count(e['before'])==1,'forward anchor drift: '+row['path'])
            text=text.replace(e['before'],e['after'])
        require(text.encode()==actual,'forward source mismatch: '+row['path'])
        restored[row['path']]=prior
        rows.append(dict(path=row['path'],basis_sha256=digest(prior),adapted_sha256=digest(actual),
                         exact_forward_reverse=True))
    return dict(policy=POLICY,manifest_sha256=MANIFEST_SHA256,source_chain=rows,cache=cache,
                **({'explicit_remote_analysis_extension':analysis_extension}if analysis_extension is not None else{}),
                prior_CRC_manifest_bytes_unchanged=True,default_cache_enabled=False,
                enabled_cache_requires_CRC=True,reconstruction_used_only_for_verification=True,
                hardware_tested=False),restored

def validate_adaptation(root):
    report,crc_basis=restore_crc_basis(root)
    # This is the old verifier's original strict body, now fed ONLY the exact
    # inverse-restored CRC-stage identities proven above. Immutable manifests,
    # vendor bytes, anchors and basis hashes retain their original checks.
    from tools.workstation_tf_sd_crc16_provenance import _validate_adaptation
    prior,_=_validate_adaptation(root,crc_basis)
    report['prior_CRC_chain']=prior
    return report,crc_basis
