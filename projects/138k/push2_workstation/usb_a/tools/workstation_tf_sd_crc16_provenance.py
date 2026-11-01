"""Strict opt-in CRC adaptation chain; reconstruction is verification only.

Original manifests and vendor bytes remain immutable. Product builders consume
the maintained sources directly; this module never writes or selects RTL.
"""
from pathlib import Path
import hashlib
import json

POLICY='task3-direct-opt-in-sd-data-crc16-v1'
MANIFEST='rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.adaptation.json'
MANIFEST_SHA256='230b9436cab1b56311ef757f548ccf12705ff94ca7381b0e718aedfa7b0d17f4'
BASIS={
    'rtl/tf_audio/storage/workstation_tf_sd_sector_reader.sv':'8f1961c951f3622ed6253bf0b1c42879f5b1950bc6a9e4a5ef40b5a01b546110',
    'rtl/tf_audio/storage/workstation_tf_file_reader.sv':'13495665a2c01dc3b2d129790e570a21122850e8664743efa44fa7d8d36c236b',
    'rtl/tf_audio/workstation_tf_direct_native_v1.sv':'48c4df2eea55652e1d2a684dd14f42dbdd63bd589fb8ed915a602068fac368c4',
    'rtl/tf_audio/workstation_tf_direct_runtime_service.sv':'a09810740bb94416d17c7d2b66d69937cb43ed62d2b62da91df417d64093056d',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(ok,message):
    if not ok:
        raise ValueError('SD CRC16 adaptation provenance: '+message)


def validate_adaptation(root):
    root=Path(root)
    data=(root/MANIFEST).read_bytes()
    require(digest(data)==MANIFEST_SHA256,'explicit adaptation manifest identity changed')
    m=json.loads(data)
    require(m['policy']==POLICY and m['schema']==1 and m['default']==0 and
            m['parameter']=='VERIFY_DATA_CRC' and m['DIRECT_selection_requires_explicit_value']==1,
            'explicit opt-in CRC selection contract changed')
    original={p:digest((root/p).read_bytes()) for p in m['unchanged_original_sha256']}
    require(original==m['unchanged_original_sha256'],'original manifest/vendor bytes changed')
    checker=m['new_checker'];require(digest((root/checker['path']).read_bytes())==checker['sha256'],
                                   'maintained first-party checker identity changed')
    require({r['path']:r['basis_sha256'] for r in m['adaptations']}==BASIS and
            len(m['adaptations'])==len(BASIS),'exact four source/basis identities changed')
    restored={};rows=[]
    for row in m['adaptations']:
        raw=(root/row['path']).read_bytes()
        require(digest(raw)==row['adapted_sha256'],'maintained adapted source changed: '+row['path'])
        text=raw.decode()
        for e in reversed(row['edits']):
            require(e['count']==1 and text.count(e['after'])==1,'exact reverse anchor drift: '+row['path'])
            text=text.replace(e['after'],e['before'])
        basis=text.encode()
        require(digest(basis)==BASIS[row['path']],'inverse did not recover original source identity: '+row['path'])
        for e in row['edits']:
            require(text.count(e['before'])==1,'exact forward anchor drift: '+row['path'])
            text=text.replace(e['before'],e['after'])
        require(text.encode()==raw,'forward verification changed maintained bytes')
        restored[row['path']]=basis
        rows.append(dict(path=row['path'],basis_sha256=digest(basis),
                         adapted_sha256=digest(raw),exact_forward_reverse=True))
    # The unchanged older manifests must still validate their own exact bytes.
    prefix='rtl/tf_audio/storage/'
    sector=json.loads((root/(prefix+'workstation_tf_sd_sector_reader.provenance.json')).read_text())
    require(digest(restored[prefix+'workstation_tf_sd_sector_reader.sv'])==sector['native_sector_sha256'] and
            digest((root/sector['native_session']).read_bytes())==sector['native_session_sha256'],
            'restored native sector/session not bound to original manifest')
    file=json.loads((root/(prefix+'workstation_tf_file_reader.provenance.json')).read_text())
    original_file=(root/file['origin']).read_bytes()
    require(digest(original_file)==file['origin_sha256'] and
            digest(restored[file['native']])==file['native_sha256'],
            'restored native file not bound to original manifest')
    text=original_file.decode()
    for edit in file['forward_edits']:
        require(text.count(edit['before'])==edit['count'],'original file forward anchor drift')
        text=text.replace(edit['before'],edit['after'])
    require((file['header']+text+file['suffix']).encode()==restored[file['native']],
            'original file derivation no longer exact')
    return dict(policy=POLICY,manifest_sha256=MANIFEST_SHA256,source_chain=rows,
                unchanged_original_sha256=original,checker=checker,
                original_manifests_and_vendor_bytes_unchanged=True,
                original_file_forward_derivation_exact=True,
                default_CRC_verification_enabled=False,
                reconstruction_used_only_for_verification=True,hardware_tested=False),restored


def restored_basis(root,relative):
    """For explicit DIRECT source validation; never a product fallback."""
    result,restored=validate_adaptation(root)
    require(relative in restored,'unknown explicit adaptation source')
    return restored[relative],result
