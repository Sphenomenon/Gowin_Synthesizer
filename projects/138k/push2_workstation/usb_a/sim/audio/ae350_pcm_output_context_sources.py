"""Bind the PCM output-context cofactor to the complete preceding owner."""
from pathlib import Path
import hashlib
import re
import ae350_pcm_bitmap_context_sources as bitmap_context

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'workstation_ae350_pcm_owner_before_output_context_gate.sv'
REFERENCE_SHA256='574c6e268e952a2d72063db5296e781528f47158f4c63ad8cc2968a767d1b71e'
OLD='''    assign pcm_left_o=selected ? (usable && !hold_serial && cache_current ? {interpolated_l,16'd0}:32'd0):legacy_left_i;
    assign pcm_right_o=selected ? (usable && !hold_serial && cache_current ? {interpolated_r,16'd0}:32'd0):legacy_right_i;'''
NEW='''    // Context can be revoked by an immediate upstream DSP fault. Compute
    // every other permission independently so that revoke remains the final
    // PCM zero gate, before the caller's gain/DSP path, without a new cycle.
    wire pcm_output_without_context /* synthesis syn_keep=1 */;
    assign pcm_output_without_context=armed && !failed && live_matches &&
        physical_epoch_match_0 && physical_epoch_match_1 && physical_epoch_match_2 && physical_epoch_match_3 &&
        active_rate==(rate_44100_i ? 32'd44100:32'd48000) && !switch_busy_i &&
        cpu_ready_i && !tf_busy_i && !hold_serial && cache_current;
    assign pcm_left_o=selected ? (context_ready_i && pcm_output_without_context ? {interpolated_l,16'd0}:32'd0):legacy_left_i;
    assign pcm_right_o=selected ? (context_ready_i && pcm_output_without_context ? {interpolated_r,16'd0}:32'd0):legacy_right_i;'''

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inputs():return list(dict.fromkeys([SOURCE,REFERENCE,Path(__file__).resolve()]+bitmap_context.inputs()))

def reference_view(text=None):
    text=SOURCE.read_text() if text is None else text
    # Remove the later reviewed bitmap change before checking this output-only
    # stage. The complete 290d... -> 1c575... inverse fails on any byte drift.
    text=bitmap_context.reference_view(text)
    assert sha(REFERENCE)==REFERENCE_SHA256,'PCM pre-output-context fixture drift'
    assert text.count(NEW)==1,'PCM output-context exact hunk drift'
    previous=text.replace(NEW,OLD,1)
    assert previous==REFERENCE.read_text(),'PCM output-context changed unrelated owner bytes'
    assignments=lambda s:re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',s)
    assert assignments(text)==assignments(previous),'PCM output-context changed NBA targets/RHS/order'
    return previous

def contract():
    reference_view()
    return dict(reference_sha256=REFERENCE_SHA256,source_sha256=sha(SOURCE),
        exact_whole_source_inverse=True,all_NBA_targets_RHS_and_order_unchanged=True,
        NBA_identity_scope='output-context stage after exact later bitmap inverse',
        later_bitmap_context_inverse=bitmap_context.contract(),
        kept_context_free_cofactor=True,immediate_context_output_zero_gate=True,
        new_registers=False,new_sample_latency=False)
