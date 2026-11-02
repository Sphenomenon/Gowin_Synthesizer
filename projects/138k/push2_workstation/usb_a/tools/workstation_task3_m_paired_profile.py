"""Exact reversible paired M stage selection; no historical provider changes."""
from pathlib import Path
import hashlib,json
POLICY='task3_m_paired_exact_top_composition_v1'
NAME='custom138k-workstation-task3-m-paired-v1'
PROVIDER='rtl/workstation/workstation_profile_task3_m_paired.sv'
REFERENCE='rtl/workstation/workstation_task3_m_paired_top_reference.json'
BOARD='rtl/workstation/workstation_task3_m_paired_board.svh'
PARENT_TOP_SHA256='4b4a99f674a7033b032a3e82b98e553d7d7675689627ca4fb0cebf9746738d0f'
REFERENCE_SHA256='e1af8daa488fbb704a7fd3fdc04b4b0fae89bdbcbe531643d3f2f97cbcd5e473'
SOURCES=('rtl/workstation/workstation_task3_m_bus_endpoint.sv',
 'rtl/music/workstation_task3_tf_analysis_source.sv','rtl/music/workstation_task3_score_commit_m.sv',
 'rtl/workstation/workstation_task3_final_tap_export.sv','rtl/workstation/workstation_task3_phone_command_ingress.sv',
 'rtl/workstation/workstation_task3_phone_command_mux.sv',
 'rtl/workstation/workstation_task3_phone_window_rx.sv')
MAINTAINED_UPDATES=('rtl/workstation/workstation_runtime_controlled.sv',
 'rtl/workstation/workstation_runtime_audio.sv','rtl/audio/workstation_ae350_pcm_owner.sv',
 'rtl/tf_audio/workstation_tf_direct_runtime_service.sv')
DEPENDENCIES=('tools/workstation_task3_m_paired_profile.py',PROVIDER,REFERENCE,BOARD,
 'rtl/workstation/task3_paired_channels.vh','rtl/workstation/workstation_runtime_controlled.sv',
 'rtl/workstation/workstation_runtime_audio.sv','rtl/audio/workstation_ae350_pcm_owner.sv',
 'rtl/tf_audio/workstation_tf_direct_runtime_service.sv','rtl/workstation/WORKSTATION_TASK3_M_PAIRED_CONTRACT.md')
def digest(s):return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
def reference(root):
 payload=(Path(root)/REFERENCE).read_bytes()
 if digest(payload)!=REFERENCE_SHA256:raise ValueError('M paired reference identity drift')
 d=json.loads(payload)
 if d.get('schema')!=1 or d.get('policy')!=POLICY or d.get('parent_sha256')!=PARENT_TOP_SHA256:raise ValueError('M paired reference schema/parent drift')
 return d
def apply_top(root,text):
 d=reference(root)
 if digest(text)!=d['parent_sha256']:raise ValueError('M paired input top identity drift')
 for row in d['edits']:
  if text.count(row['parent'])!=1:raise ValueError('M paired forward anchor drift')
  text=text.replace(row['parent'],row['selected'],1)
 if digest(text)!=d['selected_sha256']:raise ValueError('M paired selected top identity drift')
 return text
def inverse_top(root,text):
 if 'WORKSTATION_TASK3_M_PAIRED' not in text:return text
 if '`include "'+BOARD+'"' not in text:raise ValueError('M paired board include missing')
 selected=text
 d=reference(root)
 if digest(text)!=d['selected_sha256']:raise ValueError('M paired selected identity drift')
 for row in reversed(d['edits']):
  if text.count(row['selected'])!=1:raise ValueError('M paired inverse anchor drift')
  text=text.replace(row['selected'],row['parent'],1)
 if digest(text)!=d['parent_sha256'] or apply_top(root,text)!=selected:raise ValueError('M paired inverse identity drift')
 return text
