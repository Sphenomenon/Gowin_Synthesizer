"""Exact source lineage for the private PCM bitmap context cofactor.

This simulation-only inverse reconstructs the complete preceding owner. It is
never consumed by a production build and has no external cache dependency.
"""
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv'
PREVIOUS_SHA256='1c575c3fd39d73c795cb7e49c075a1b5848be90d3cccd57e24db991a9071649b'
SOURCE_SHA256='290d3fbab8de519772d2be44f7ded6a7a94d5ff8e00781b37d4d2680d8aff1f0'
OLD='''    // Private bitmap writes retain the original ordering. The revocation
    // clear needs no failure-code or unrelated command-response selection.
    reg bitmap_clear_late /* synthesis syn_keep=1 */;
    always @* begin
        bitmap_clear_late=0;
        if(accepted_stop)bitmap_clear_late=1;
        if(accepted_cancel)bitmap_clear_late=1;
        if(rejected_commit && usable && key_matches && !owned[tail_slot])bitmap_clear_late=1;
        if(armed)begin
            if(cpu_previous && !cpu_ready_i)bitmap_clear_late=1;
            else if(!live_matches)bitmap_clear_late=1;
            else if(!physical_matches)bitmap_clear_late=1;
            else if(tf_busy_i)bitmap_clear_late=1;
            else if(sample_take_i && selected && !hold_serial && !cache_current)bitmap_clear_late=1;
        end
    end
    integer bitmap_slot;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
        end else begin
            if(accepted_window_write)written[write_slot][write_index]<=1;
            if(accepted_start)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
            if(accepted_commit)written[tail_slot]<=0;
            if(bitmap_clear_late)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
        end
    end
'''
NEW='''    // Context revoke is the final private bitmap decision. All other
    // predicates are computed without that late DSP-fault qualification.
    (* syn_keep=1 *) wire bitmap_physical_without_context=physical_epoch_match_0 && physical_epoch_match_1 &&
        physical_epoch_match_2 && physical_epoch_match_3 &&
        active_rate==(rate_44100_i ? 32'd44100:32'd48000) && !switch_busy_i;
    wire bitmap_usable_without_context=armed && !failed && live_matches && bitmap_physical_without_context && cpu_ready_i && !tf_busy_i;
    wire bitmap_staging_without_context=session_live_i && staged_controller==controller_epoch_i && staged_generation==transport_generation_i &&
        staged_physical==physical_epoch_i && staged_rate==(rate_44100_i ? 32'd44100:32'd48000) && !switch_busy_i && !tf_busy_i;
    wire bitmap_start_error=armed || selected || history_state!=H_IDLE || !bitmap_staging_without_context || !new_stream || &cancel_epoch_o;
    wire bitmap_commit_error=!bitmap_usable_without_context || !key_matches || staged_slot!={30'd0,tail_slot} || owned[tail_slot] ||
        !descriptor_frames_valid || staged_sequence!=expected_sequence || &expected_sequence || descriptor_missing_frames;
    wire bitmap_start_without_context=control_write && command_data_i==32'd1 && !bitmap_start_error;
    wire bitmap_commit_without_context=control_write && command_data_i==32'd2 && !bitmap_commit_error;
    wire bitmap_rejected_without_context=write_command && command_address_i==12'h040 && command_data_i==32'd2 &&
        (!control_format_ok || !control_id_ok || bitmap_commit_error);
    // Private bitmap writes retain the original ordering. The revocation
    // clear needs no failure-code or unrelated command-response selection.
    reg bitmap_clear_late /* synthesis syn_keep=1 */;
    always @* begin
        bitmap_clear_late=0;
        if(accepted_stop)bitmap_clear_late=1;
        if(accepted_cancel)bitmap_clear_late=1;
        if(rejected_commit && usable && key_matches && !owned[tail_slot])bitmap_clear_late=1;
        if(armed)begin
            if(cpu_previous && !cpu_ready_i)bitmap_clear_late=1;
            else if(!live_matches)bitmap_clear_late=1;
            else if(!physical_matches)bitmap_clear_late=1;
            else if(tf_busy_i)bitmap_clear_late=1;
            else if(sample_take_i && selected && !hold_serial && !cache_current)bitmap_clear_late=1;
        end
    end
    reg bitmap_clear_without_context /* synthesis syn_keep=1 */;
    always @* begin
        bitmap_clear_without_context=0;
        if(accepted_stop)bitmap_clear_without_context=1;
        if(accepted_cancel)bitmap_clear_without_context=1;
        if(bitmap_rejected_without_context && bitmap_usable_without_context && key_matches && !owned[tail_slot])bitmap_clear_without_context=1;
        if(armed)begin
            if(cpu_previous && !cpu_ready_i)bitmap_clear_without_context=1;
            else if(!live_matches)bitmap_clear_without_context=1;
            else if(!bitmap_physical_without_context)bitmap_clear_without_context=1;
            else if(tf_busy_i)bitmap_clear_without_context=1;
            else if(sample_take_i && selected && !hold_serial && !cache_current)bitmap_clear_without_context=1;
        end
    end
    integer bitmap_slot;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
        end else begin
            case(context_ready_i)
                1'b0:begin
                    if(accepted_stop || accepted_cancel || armed)
                        for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
                end
                1'b1:begin
            if(accepted_window_write)written[write_slot][write_index]<=1;
            if(bitmap_start_without_context)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
            if(bitmap_commit_without_context)written[tail_slot]<=0;
            if(bitmap_clear_without_context)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
                end
                default:begin
            if(accepted_window_write)written[write_slot][write_index]<=1;
            if(accepted_start)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
            if(accepted_commit)written[tail_slot]<=0;
            if(bitmap_clear_late)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
                end
            endcase
        end
    end
'''

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def inputs():return [SOURCE,Path(__file__).resolve()]
def require(ok,message):
    if not ok:raise ValueError('PCM bitmap context: '+message)

def reference_view(text=None):
    text=SOURCE.read_text() if text is None else text
    require(text.count(NEW)==1,'exact reviewed bitmap region drift')
    previous=text.replace(NEW,OLD,1)
    require(hashlib.sha256(previous.encode()).hexdigest()==PREVIOUS_SHA256,'change outside bitmap boundary')
    require(hashlib.sha256(text.encode()).hexdigest()==SOURCE_SHA256,'complete current owner identity drift')
    return previous

def contract():
    reference_view()
    return dict(source_sha256=SOURCE_SHA256,reference_sha256=PREVIOUS_SHA256,
        exact_whole_source_inverse=True,only_private_bitmap_region_changed=True,
        known_zero_context_clears_on_armed_stop_or_cancel=True,
        unknown_context_uses_original_ordered_NBA_body=True,
        new_registers=False,new_sample_latency=False)
