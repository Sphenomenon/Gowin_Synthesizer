"""Compact validated M display metadata; retire the adaptation into its owner.

Only the explicit M preboard profile selects this checked temporary adapter.
The unchanged global/header/descriptor checks dominate every derived consumer.
Actual legacy/minor1 twins must preserve all public outputs and cycle timing.
"""
from pathlib import Path
import hashlib
KEY='display_reader_validated_policy'
POLICY='task3_M_validated_display_metadata_storage_v1'
SOURCE='rtl/display_data/display_data_reader.v'
TOOL='tools/workstation_reader_validated_metadata.py'
PARENT_SHA256='ed0772cfcdbb916ecd4e3ebaddf447597aff33af7703c8c4e39914a3215bc580'
SELECTED_SHA256='79da5ed21cba81ed4451cbeef39262760b852de0ffef2d7c2b350c56ab83a48f'
EDITS=[('    reg [28:0] header_addr,descriptor_base;',
  '    wire [28:0] header_addr=bank ? BANK1_HEADER_WORD:BANK0_HEADER_WORD;\n'
  '    wire [28:0] descriptor_base=bank ? DESC_BANK1_WORD:DESC_BANK0_WORD;'),
 ('    reg [28:0] payload_base[0:3];',
  '    wire [28:0] payload_base[0:3];\n'
  '    for(genvar '
  'payload_index=0;payload_index<4;payload_index=payload_index+1)begin:validated_payload_base\n'
  '        assign payload_base[payload_index]=(bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+\n'
  '            (payload_index==0 ? WAVEFORM_OFFSET_WORD:payload_index==1 ? LISSAJOUS_OFFSET_WORD:\n'
  '             payload_index==2 ? SPECTRUM_OFFSET_WORD:EFFECT_META_OFFSET_WORD);\n'
  '    end'),
 ('    reg [255:0] global_q,header_q,meta_lo_q,meta_hi_q;',
  '    reg [255:0] global_q,meta_lo_q,meta_hi_q;'),
 ('            '
  'descriptor_beat<=0;payload_kind<=0;payload_beat<=0;header_addr<=0;descriptor_base<=0;',
  '            descriptor_beat<=0;payload_kind<=0;payload_beat<=0;'),
 ('global_q<=0;header_q<=0;', 'global_q<=0;'),
 ('                    global_q<=rsp_q;',
  '                    // Later consumers are admitted only after the unchanged\n'
  '                    // full global check. Store its accepted canonical form.\n'
  "                    global_q<={rsp_q[255:192],(rsp_q[161] ? 32'hf:32'h9),\n"
  "                        (rsp_q[48] ? {3'd0,DESC_BANK1_WORD}:{3'd0,DESC_BANK0_WORD}),\n"
  '                        (rsp_q[95:64]<<1),rsp_q[95:64],\n'
  "                        {8'd4,7'd0,rsp_q[48],VERSION_MAJOR,SELECTED_MINOR},DISPLAY_MAGIC};"),
 ('                        header_addr<=rsp_q[48] ? BANK1_HEADER_WORD:BANK0_HEADER_WORD;\n'
  '                        descriptor_base<=rsp_q[156:128];state<=REQ_HEADER;',
  '                        state<=REQ_HEADER;'),
 ('                PARSE_HEADER:begin\n'
  '                    header_q<=rsp_q;\n'
  '                    header_bad_q',
  '                PARSE_HEADER:begin\n                    header_bad_q'),
 ('                            '
  'payload_base[descriptor]<=rsp_q[28:0];descriptor_gain[descriptor]<=rsp_q[127:96];',
  '                            descriptor_gain[descriptor]<=rsp_q[127:96];'),
 ('                    final_bad_q<=rsp_q[63:0]!=header_q[63:0];state<=FINAL_CMP1;',
  '                    final_bad_q<=rsp_q[63:0]!=global_q[63:0];state<=FINAL_CMP1;'),
 ('                FINAL_CMP1:begin final_bad_q<=final_bad_q || '
  '(rsp_q[127:64]!=header_q[127:64]);state<=FINAL_CMP2;end',
  '                FINAL_CMP1:begin final_bad_q<=final_bad_q || '
  '(rsp_q[127:64]!=global_q[127:64]);state<=FINAL_CMP2;end'),
 ('                FINAL_CMP2:begin final_bad_q<=final_bad_q || '
  '(rsp_q[191:128]!=header_q[191:128]);state<=FINAL_CMP3;end',
  '                FINAL_CMP2:begin final_bad_q<=final_bad_q || '
  '(rsp_q[191:128]!=global_q[191:128]);state<=FINAL_CMP3;end'),
 ('                    final_bad_q<=final_bad_q || (rsp_q[255:192]!=header_q[255:192]);',
  '                    final_bad_q<=final_bad_q || (rsp_q[255:192]!=global_q[255:192]);')]


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError('M validated metadata: '+message)


def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown policy')
    if value:
        require(configuration.get('demo_role')=='M' and
                configuration.get('display_metadata_minor')==1 and
                configuration.get('display_reader_storage_policy')==
                'task3_M_display_reader_held_response_reuse_v1',
                'requires explicit paired M minor1 response reuse')
    return bool(value)


def adapt(text):
    require(digest(text)==PARENT_SHA256,'composed parent drift')
    for before,after in EDITS:
        require(text.count(before)==1,'forward anchor drift')
        text=text.replace(before,after,1)
    require(digest(text)==SELECTED_SHA256,'selected identity drift')
    return text


def restore(text):
    if digest(text)!=SELECTED_SHA256:return text
    for before,after in reversed(EDITS):
        require(text.count(after)==1,'inverse anchor drift')
        text=text.replace(after,before,1)
    require(digest(text)==PARENT_SHA256,'parent inverse drift')
    return text


def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/SOURCE
    path.write_text(adapt(path.read_text()))
    return evidence(stage,configuration)


def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text()
    require(digest(text)==SELECTED_SHA256 and digest(restore(text))==PARENT_SHA256,
            'selection absent or inverse drift')
    return dict(policy=POLICY,parent_sha256=PARENT_SHA256,selected_sha256=SELECTED_SHA256,
        accepted_header_reuses_equal_global=True,validated_addresses_derived=True,
        global_storage_uses_accepted_canonical_form=True,added_cycles=0,
        all_original_validation_and_failure_states_retained=True,
        routed_timing_verified=False,hardware_tested=False)


def audit_mapped(netlist):
    """Check the actual selected storage, without claiming whole-chip equivalence."""
    from tools.workstation_runtime_pcm_cdc import Graph
    graph=Graph(netlist)
    scope='u_video/u_runtime_display/reader'
    registers=[p for p in graph.regs if netlist.scopes[p]==scope]
    retired=('header_q_','payload_base[','header_addr_','descriptor_base_')
    require(not any(p.rsplit('/',1)[-1].startswith(retired) for p in registers),
            'redundant validated storage remains')
    canonical=[p for p in registers if p.rsplit('/',1)[-1].startswith('global_q_')]
    require(len(canonical)==99,'canonical global storage inventory changed')
    for p in canonical:
        cell=netlist.cells[p]
        require(cell['kind']=='DFFCE' and netlist.pin(p,'CLK')=='memory_clk' and
                cell['parameters'].get('INIT',"1'b0")=="1'b0",
                'canonical global register clock/reset mapping changed')
    return dict(policy=POLICY,canonical_global_registers=len(canonical),
        retired_storage_absent=True,scope='selected_storage_mapping_only',
        functional_equivalence_evidence='actual legacy/minor1 all-public-output twins',
        routed_timing_verified=False,hardware_tested=False)
