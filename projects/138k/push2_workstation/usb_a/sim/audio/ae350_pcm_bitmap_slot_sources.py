"""Strict source inverse for the PCM private per-slot bitmap clear permissions."""
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv'
BASELINE_SHA256='290d3fbab8de519772d2be44f7ded6a7a94d5ff8e00781b37d4d2680d8aff1f0'
MAINTAINED_SHA256='7dd8a51d5fc6d847b638f12c42c54684682f66a0950312683481f70f64efb4f1'
OLD="    integer bitmap_slot;\n    always @(posedge clk_i or negedge reset_ni)begin\n        if(!reset_ni)begin\n            for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;\n        end else begin\n            case(context_ready_i)\n                1'b0:begin\n                    if(accepted_stop || accepted_cancel || armed)\n                        for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;\n                end\n                1'b1:begin\n            if(accepted_window_write)written[write_slot][write_index]<=1;\n            if(bitmap_start_without_context)begin\n                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;\n            end\n            if(bitmap_commit_without_context)written[tail_slot]<=0;\n            if(bitmap_clear_without_context)begin\n                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;\n            end\n                end\n                default:begin\n            if(accepted_window_write)written[write_slot][write_index]<=1;\n            if(accepted_start)begin\n                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;\n            end\n            if(accepted_commit)written[tail_slot]<=0;\n            if(bitmap_clear_late)begin\n                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;\n            end\n                end\n            endcase\n        end\n    end\n"
NEW="    // Resolve the original ordered bitmap clears once for each slot. Keep\n    // this final permission separate from the wide data update mux. Partial\n    // writes lose to START, COMMIT and revoke exactly as before, including\n    // unknown guards and unknown dynamic slot/index values.\n    reg [3:0] bitmap_clear_by_slot /* synthesis syn_keep=1 */;\n    reg bitmap_allow_write;\n    always @* begin\n        bitmap_clear_by_slot=0;bitmap_allow_write=0;\n        case(context_ready_i)\n            1'b0:begin\n                if(accepted_stop || accepted_cancel || armed)bitmap_clear_by_slot=4'hf;\n            end\n            1'b1:begin\n                if(accepted_window_write)bitmap_allow_write=1;\n                if(bitmap_start_without_context)bitmap_clear_by_slot=4'hf;\n                if(bitmap_commit_without_context)bitmap_clear_by_slot[tail_slot]=1;\n                if(bitmap_clear_without_context)bitmap_clear_by_slot=4'hf;\n            end\n            default:begin\n                if(accepted_window_write)bitmap_allow_write=1;\n                if(accepted_start)bitmap_clear_by_slot=4'hf;\n                if(accepted_commit)bitmap_clear_by_slot[tail_slot]=1;\n                if(bitmap_clear_late)bitmap_clear_by_slot=4'hf;\n            end\n        endcase\n    end\n    for(genvar bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)begin:g_bitmap_slot\n        always @(posedge clk_i or negedge reset_ni)begin\n            if(!reset_ni)written[bitmap_slot]<=0;\n            else if(bitmap_clear_by_slot[bitmap_slot])written[bitmap_slot]<=0;\n            else if(bitmap_allow_write && write_slot==2'(bitmap_slot))\n                written[bitmap_slot][write_index]<=1;\n        end\n    end\n"

def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def inputs():return [SOURCE,Path(__file__).resolve()]
def restore_before_bitmap_slots(text):
    if sha(text)!=MAINTAINED_SHA256:raise ValueError('PCM bitmap slot source identity changed')
    if text.count(NEW)!=1:raise ValueError('PCM bitmap slot exact region changed')
    text=text.replace(NEW,OLD,1)
    if sha(text)!=BASELINE_SHA256:raise ValueError('PCM bitmap slot source inverse changed')
    return text

def apply_bitmap_slots(text):
    if sha(text)!=BASELINE_SHA256:raise ValueError('PCM bitmap slot baseline identity changed')
    if text.count(OLD)!=1:raise ValueError('PCM bitmap slot baseline region changed')
    text=text.replace(OLD,NEW,1)
    if sha(text)!=MAINTAINED_SHA256:raise ValueError('PCM bitmap slot source application changed')
    return text
