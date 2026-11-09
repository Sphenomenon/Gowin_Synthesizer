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
SELECTED_SHA256='f57b5ef4ef4fe7d4722657cc7fe5fe4b1edbf3c5c216d29da0f3895df4ea2cab'
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


# Capture the unchanged metadata checks at their existing read edges. Only
# publication values that are not already held elsewhere need new storage.
EDITS.extend([('    reg [255:0] global_q,meta_lo_q,meta_hi_q;',
  '    reg [31:0] snapshot_rate_q,snapshot_epoch_q;\n'
  '    reg [255:0] global_q;\n'
  '    reg [127:0] meta_body_q;\n'
  '    reg [31:0] meta_tail_q,meta_peaks_q;\n'
  '    reg meta_low_ok_q,meta_high_ok_q;\n'
  '    wire [255:0] '
  "meta_lo_q={32'h44495350,meta_body_q,descriptor_source[0],global_q[223:192],meta_tail_q};\n"
  "    wire [255:0] meta_hi_q={32'd0,(METADATA_MINOR==0 ? 32'd0:snapshot_epoch_q),\n"
  '        (METADATA_MINOR==0 ? SAMPLE_RATE_HZ:snapshot_rate_q),global_q[191:160],\n'
  '        descriptor_gain[1],meta_peaks_q,global_q[255:224],descriptor_source[1]};'),
 ('    reg [31:0] snapshot_rate_q,snapshot_epoch_q;\n    // This profile',
  '    // Snapshot tags are declared above the derived metadata wires.\n    // This profile'),
 ('global_q<=0;meta_lo_q<=0;meta_hi_q<=0;',
  'global_q<=0;meta_body_q<=0;meta_tail_q<=0;meta_peaks_q<=0;meta_low_ok_q<=0;meta_high_ok_q<=0;'),
 ('                        if(payload_beat==0)meta_lo_q<=rsp_q;else meta_hi_q<=rsp_q;',
  '                        if(payload_beat==0)begin\n'
  '                            meta_body_q<=rsp_q[223:96];meta_tail_q<=rsp_q[31:0];\n'
  "                            meta_low_ok_q<=rsp_q[255:224]==32'h44495350 &&\n"
  '                                rsp_q[63:32]==global_q[223:192] && '
  'rsp_q[95:64]==descriptor_source[0] &&\n'
  '                                (METADATA_MINOR==0 || rsp_q[223:201]==0);\n'
  '                        end else begin\n'
  '                            meta_peaks_q<=rsp_q[95:64];\n'
  '                            meta_high_ok_q<=meta_low_ok_q && '
  'descriptor_source[1]==descriptor_source[2] &&\n'
  '                                descriptor_source[3]==global_q[95:64] &&\n'
  '                                rsp_q[31:0]==descriptor_source[1] && '
  'rsp_q[63:32]==global_q[255:224] &&\n'
  '                                rsp_q[127:96]==descriptor_gain[1] && '
  'rsp_q[159:128]==global_q[191:160] &&\n'
  '                                (METADATA_MINOR==0 ? rsp_q[191:160]==SAMPLE_RATE_HZ && '
  'rsp_q[255:192]==0 :\n'
  '                                 rsp_q[191:160]==snapshot_rate_q && '
  'rsp_q[223:192]==snapshot_epoch_q && rsp_q[255:224]==0);\n'
  '                        end'),
 ('    wire meta_ok=\n'
  "        meta_lo_q[255:224]==32'h44495350 &&\n"
  '        meta_lo_q[63:32]==global_q[223:192] &&\n'
  '        meta_lo_q[95:64]==descriptor_source[0] &&\n'
  '        meta_hi_q[31:0]==descriptor_source[1] &&\n'
  '        descriptor_source[1]==descriptor_source[2] &&\n'
  '        descriptor_source[3]==global_q[95:64] &&\n'
  '        meta_hi_q[63:32]==global_q[255:224] &&\n'
  '        meta_hi_q[127:96]==descriptor_gain[1] &&\n'
  '        meta_hi_q[159:128]==global_q[191:160] &&\n'
  '        (METADATA_MINOR==0 ? meta_hi_q[191:160]==SAMPLE_RATE_HZ && meta_hi_q[255:192]==0 :\n'
  '         meta_hi_q[191:160]==snapshot_rate_q && meta_hi_q[223:192]==snapshot_epoch_q &&\n'
  '         meta_hi_q[255:224]==0 && meta_lo_q[223:201]==0);\n',
  '    wire meta_ok=meta_high_ok_q;\n')])

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
        metadata_checks_capture_at_original_read_edges=True,
        redundant_metadata_reuses_existing_held_tags=True,
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
    require(not any(p.rsplit('/',1)[-1].startswith(('meta_lo_q_', 'meta_hi_q_'))
                    for p in registers), 'redundant metadata storage remains')
    checks=[graph.register(scope,stem)for stem in ('meta_low_ok_q','meta_high_ok_q')]
    for p in checks:
        cell=netlist.cells[p]
        require(cell['kind']=='DFFCE' and netlist.pin(p,'CLK')=='memory_clk' and
                cell['parameters'].get('INIT',"1'b0")=="1'b0" and
                netlist.pin(p,'CLEAR')==netlist.pin(canonical[0],'CLEAR'),
                'metadata validation register clock/reset mapping changed')
    return dict(policy=POLICY,canonical_global_registers=len(canonical),
        captured_metadata_validation_registers=checks,
        retired_storage_absent=True,scope='selected_storage_mapping_only',
        functional_equivalence_evidence='actual legacy/minor1 all-public-output twins',
        routed_timing_verified=False,hardware_tested=False)
