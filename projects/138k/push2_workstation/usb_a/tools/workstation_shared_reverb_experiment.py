"""Checked source-only reverb seam; no production profile selects this view.

Expose the original instance ports, preserve every DSP and DDR owner, and
disable only the private rate-consistency check while another owner leases
that physical engine. The physical rate is still visible. Exit: explicit
native profile integration after transport/physical qualification.
"""
import hashlib
import json
import re
from pathlib import Path

SOURCE='rtl/audio/workstation_runtime_stereo_effects.sv'
ADAPTATION='rtl/audio/workstation_runtime_stereo_effects.remote_reverb_partition.json'
CURRENT='50d18332d820f8bc11f272726b6ed51190cd3ec4acde666c9ef4d0c511ab4e13'
PARENT='99095afee6425a42fab993575a09f6e1c6b8beb05619b9b46fc0a311bdcdc2c9'
PORTS='''    input wire rv_away_i,
    output wire rv_valid_o,rv_enabled_o,
    output wire signed [31:0] rv_left_o,rv_right_o,
    input wire rv_ready_i,rv_active_i,rv_valid_i,rv_clip_i,
    input wire signed [31:0] rv_left_i,rv_right_i,
    output wire rv_config_valid_o,rv_history_clear_o,rv_rate_o,
    input wire rv_config_ready_i,rv_history_ready_i,rv_history_done_i,
    input wire rv_quiescent_i,rv_applied_rate_i,
'''
SEAM='''  assign rv_valid_o=state==SEND && work_id==2,rv_enabled_o=work_enabled;
  assign rv_left_o=work_l,rv_right_o=work_r;
  assign reverb_ready=rv_ready_i,reverb_active=rv_active_i,reverb_valid=rv_valid_i;
  assign reverb_l=rv_left_i,reverb_r=rv_right_i,reverb_clip=rv_clip_i;
  assign rv_config_valid_o=config_accept,rv_history_clear_o=history_accept,rv_rate_o=rate_44100_i;
  assign stage_config_ready[2]=rv_config_ready_i,stage_history_ready[2]=rv_history_ready_i;
  assign stage_done[2]=rv_history_done_i,stage_quiet[2]=rv_quiescent_i,stage_rate[2]=rv_applied_rate_i;
  // The original composition consumes the real history ACK for both operations.
'''


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def project(root, text=None):
    root=Path(root)
    current=(root/SOURCE).read_text() if text is None else text
    if sha(current)!=CURRENT:
        raise ValueError('shared reverb maintained source identity drift')
    adaptation=json.loads((root/ADAPTATION).read_text())
    if adaptation['current_source_sha256']!=CURRENT or adaptation['parent_source_sha256']!=PARENT:
        raise ValueError('shared reverb prior adaptation identity drift')
    parent=current
    for row in reversed(adaptation['exact_changes']):
        if parent.count(row['after'])!=1:
            raise ValueError('shared reverb prior inverse anchor drift')
        parent=parent.replace(row['after'],row['before'],1)
    if sha(parent)!=PARENT:
        raise ValueError('shared reverb parent identity drift')
    instances=re.findall(r'  workstation_runtime_spatial_reverb reverb_stage\(.*?\);',parent,re.S)
    if len(instances)!=1:
        raise ValueError('shared reverb instance must be unique')
    edits=[('module workstation_runtime_stereo_effects #(',
            'module workstation_runtime_stereo_effects_reverb_port #('),
           ('    input logic clk_i,rst_ni,clear_i,valid_i,',PORTS+'    input logic clk_i,rst_ni,clear_i,valid_i,'),
           (instances[0],SEAM.rstrip()),
           ('if(!barrier_busy && stage_rate!={3{stage_rate[0]}})',
            'if(!rv_away_i && !barrier_busy && stage_rate!={3{stage_rate[0]}})')]
    selected=parent
    for before,after in edits:
        if selected.count(before)!=1:
            raise ValueError('shared reverb forward anchor drift')
        selected=selected.replace(before,after,1)
    restored=selected
    for before,after in reversed(edits):
        if restored.count(after)!=1:
            raise ValueError('shared reverb inverse anchor drift')
        restored=restored.replace(after,before,1)
    if restored!=parent:
        raise ValueError('shared reverb parent roundtrip drift')
    for row in adaptation['exact_changes']:
        if restored.count(row['before'])!=1:
            raise ValueError('shared reverb prior forward anchor drift')
        restored=restored.replace(row['before'],row['after'],1)
    if restored!=current:
        raise ValueError('shared reverb maintained source roundtrip drift')
    return selected,dict(policy='source_only_shared_reverb_seam_v1',maintained_sha256=CURRENT,
        canonical_parent_sha256=PARENT,selected_sha256=sha(selected),
        exact_edits=[dict(before=a,after=b) for a,b in edits],full_roundtrip=True,
        production_profile_selected=False,other_DSP_DDR_owners_unchanged=True)
