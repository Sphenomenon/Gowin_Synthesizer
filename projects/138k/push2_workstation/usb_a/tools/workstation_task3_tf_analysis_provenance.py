"""Strict inverse proof for a default-off native TF analysis aperture.

No RTL is generated or installed. Original CRC/cache manifests and strict
checks remain unchanged; only this exact newer identity may precede them.
"""
from pathlib import Path
import hashlib,json
POLICY='task3_default_off_remote_analysis_runtime_extension_v1'
SOURCE='rtl/tf_audio/workstation_tf_direct_runtime_service.sv'
REFERENCE='rtl/tf_audio/workstation_tf_remote_analysis_v1.adaptation.json'
REFERENCE_SHA256='528961ca7fb7c74903f1782a315f2df8a8865a7fcaa44a7f5d3e9ef5c26e7ae0'
PARENT_SHA256='2f92cd3a008df79b291667094d8aee82acaeab2470278446647c269a485f6b07'
SELECTED_SHA256='9195f5a23fb3317f99861cd4c39875f2658f8f4d328cbb1250a4301e8ccd708d'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def restore(root,raw):
 from tools.workstation_tf_failure_path import normalize
 raw=normalize(raw)
 payload=(Path(root)/REFERENCE).read_bytes()
 if digest(payload)!=REFERENCE_SHA256:raise ValueError('remote TF analysis reference identity drift')
 d=json.loads(payload)
 if (d.get('schema')!=1 or d.get('policy')!=POLICY or d.get('source')!=SOURCE or
     d.get('parent_sha256')!=PARENT_SHA256 or d.get('selected_sha256')!=SELECTED_SHA256 or
     d.get('parameter')!='REMOTE_ANALYSIS_ENABLE' or d.get('default')!=0 or
     d.get('reconstruction_used_only_for_verification') is not True):raise ValueError('remote TF analysis reference contract drift')
 if digest(raw)!=SELECTED_SHA256:raise ValueError('remote TF analysis selected source identity drift')
 selected=raw.decode();text=selected
 for row in reversed(d['edits']):
  if text.count(row['selected'])!=1:raise ValueError('remote TF analysis reverse anchor drift')
  text=text.replace(row['selected'],row['parent'],1)
 prior=text.encode()
 if digest(prior)!=PARENT_SHA256:raise ValueError('remote TF analysis parent identity drift')
 for row in d['edits']:
  if text.count(row['parent'])!=1:raise ValueError('remote TF analysis forward anchor drift')
  text=text.replace(row['parent'],row['selected'],1)
 if text!=selected:raise ValueError('remote TF analysis exact roundtrip drift')
 return prior,dict(policy=POLICY,source=SOURCE,parent_sha256=PARENT_SHA256,
  selected_sha256=SELECTED_SHA256,reference_sha256=REFERENCE_SHA256,default_enabled=False,
  exact_forward_reverse=True,reconstruction_used_only_for_verification=True,hardware_tested=False)
