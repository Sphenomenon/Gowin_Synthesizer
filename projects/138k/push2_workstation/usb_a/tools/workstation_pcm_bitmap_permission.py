"""Exact inverse of COMMIT bitmap permission factoring; no changed edge."""
import hashlib
SOURCE='rtl/audio/workstation_ae350_pcm_owner.sv'
PARENT_SHA256='0b9f1287fb1c68a9b6e72db65533b2d0e325e3f7feba02667fbef03582beb417'
SELECTED_SHA256='7bfca96c9f4f5d665fe433e6a3700a6b9bc1f326c02b2263d75a77eb2008f02f'
REMOVED='        if(bitmap_rejected_without_context && bitmap_usable_without_context && key_matches && !owned[tail_slot])bitmap_clear_without_context=1;\n'
ANCHOR='    reg [3:0] bitmap_clear_by_slot /* synthesis syn_keep=1 */;'
BLOCK="    // Once usability/key/free-slot permission is true, the matching COMMIT\n    // rejection reasons reduce to descriptor/format/ID only. Compute these\n    // independently of late physical/key qualification, then gate once.\n    wire bitmap_commit_attempt=write_command && command_address_i==12'h040 && command_data_i==32'd2;\n    wire bitmap_commit_permission=bitmap_usable_without_context && key_matches && !owned[tail_slot];\n    wire bitmap_descriptor_error=staged_slot!={30'd0,tail_slot} || !descriptor_frames_valid ||\n        staged_sequence!=expected_sequence || &expected_sequence || descriptor_missing_frames;\n"
OLD="                if(bitmap_commit_without_context)bitmap_clear_by_slot[tail_slot]=1;\n                if(bitmap_clear_without_context)bitmap_clear_by_slot=4'hf;"
NEW="                case(bitmap_commit_error)\n                    1'b0,1'b1:begin\n                        if(bitmap_commit_attempt && bitmap_commit_permission)begin\n                            if(!control_format_ok || !control_id_ok || bitmap_descriptor_error)\n                                bitmap_clear_by_slot=4'hf;\n                            else bitmap_clear_by_slot[tail_slot]=1;\n                        end\n                    end\n                    default:begin\n                        // Preserve procedural unknown-guard behavior in RTL\n                        // simulation; binary hardware uses the factored arm.\n                        if(bitmap_commit_without_context)bitmap_clear_by_slot[tail_slot]=1;\n                        if(bitmap_rejected_without_context && bitmap_commit_permission)\n                            bitmap_clear_by_slot=4'hf;\n                    end\n                endcase\n                if(bitmap_clear_without_context)bitmap_clear_by_slot=4'hf;"

PARALLEL_SHA256='6433efb8afcefc9026bbaf1ec0bd6d2e243182d559e009c9c34f0d7f1e2a6ef9'
PARALLEL_OLD='    always @* begin\n        bitmap_clear_without_context=0;\n        if(accepted_stop)bitmap_clear_without_context=1;\n        if(accepted_cancel)bitmap_clear_without_context=1;\n        if(armed)begin\n            if(cpu_previous && !cpu_ready_i)bitmap_clear_without_context=1;\n            else if(!live_matches)bitmap_clear_without_context=1;\n            else if(!bitmap_physical_without_context)bitmap_clear_without_context=1;\n            else if(tf_busy_i)bitmap_clear_without_context=1;\n            else if(sample_take_i && selected && !hold_serial && !cache_current)bitmap_clear_without_context=1;\n        end\n    end\n'
PARALLEL_NEW='    // Every revoke writes the same value. Resolve them as parallel OR terms\n    // instead of a priority chain behind the command acceptance cone. Retain\n    // the procedural if so X/Z-only guards still leave the result at zero.\n    always @* begin\n        bitmap_clear_without_context=0;\n        if(accepted_stop || accepted_cancel || (armed && (\n            (cpu_previous && !cpu_ready_i) || !live_matches ||\n            !bitmap_physical_without_context || tf_busy_i ||\n            (sample_take_i && selected && !hold_serial && !cache_current))))\n            bitmap_clear_without_context=1;\n    end\n'
PARALLEL_EDITS=[('    wire accepted_stop=', '    (* syn_keep=1 *) wire accepted_stop='), ('    wire accepted_cancel=', '    (* syn_keep=1 *) wire accepted_cancel=')]

REDUCTION_SHA256='aa21dfd1f4c1ca1486a22de1a0efcf26fa21b0ac77763df53e650994ce9eefcd'
REDUCTION_BLOCK='    // A9 mapped the full32 command-ID saturation reduction as eight serial\n    // LUT levels. Keep four independent byte reductions, then combine once.\n    // No state, acceptance edge or procedural X/Z treatment changes.\n    (* syn_keep=1 *) wire [3:0] command_id_full_bytes;\n    for(genvar id_byte=0;id_byte<4;id_byte=id_byte+1)begin:g_command_id_full\n        assign command_id_full_bytes[id_byte]=&command_id[id_byte*8+:8];\n    end\n'

def restore_reduction(payload):
    text=payload.decode()if isinstance(payload,bytes)else payload
    digest=lambda t:hashlib.sha256(t.encode()).hexdigest()
    if digest(text)==PARALLEL_SHA256:return text.encode()
    if digest(text)!=REDUCTION_SHA256 or text.count(REDUCTION_BLOCK)!=1 or text.count('if(&command_id_full_bytes)')!=2:
        raise ValueError('PCM command-ID byte reduction source drift')
    text=text.replace(REDUCTION_BLOCK,'',1).replace('if(&command_id_full_bytes)','if(&command_id)')
    if digest(text)!=PARALLEL_SHA256:raise ValueError('PCM command-ID reduction inverse drift')
    return text.encode()

def restore_parallel(payload):
    text=payload.decode()if isinstance(payload,bytes)else payload
    if hashlib.sha256(text.encode()).hexdigest()==REDUCTION_SHA256:text=restore_reduction(text).decode()
    digest=lambda t:hashlib.sha256(t.encode()).hexdigest()
    if digest(text)==SELECTED_SHA256:return text.encode()
    if digest(text)!=PARALLEL_SHA256 or text.count(PARALLEL_NEW)!=1:
        raise ValueError('PCM parallel bitmap source drift')
    text=text.replace(PARALLEL_NEW,PARALLEL_OLD,1)
    for old,new in PARALLEL_EDITS:
        if text.count(new)!=1:raise ValueError('PCM parallel bitmap kept guard drift')
        text=text.replace(new,old,1)
    if digest(text)!=SELECTED_SHA256:raise ValueError('PCM parallel bitmap inverse drift')
    return text.encode()

def normalize(payload):
    text=payload.decode()if isinstance(payload,bytes)else payload
    from tools.workstation_m_pcm_overflow import restore as restore_overflow
    text=restore_overflow(text)
    digest=lambda t:hashlib.sha256(t.encode()).hexdigest()
    if digest(text)in (PARALLEL_SHA256,REDUCTION_SHA256):text=restore_parallel(text).decode()
    if digest(text)==PARENT_SHA256:return text.encode()
    if digest(text)!=SELECTED_SHA256 or text.count(BLOCK)!=1 or text.count(NEW)!=1:
        raise ValueError('PCM bitmap permission source drift')
    text=text.replace(BLOCK,'',1).replace(NEW,OLD,1)
    anchor='        if(accepted_cancel)bitmap_clear_without_context=1;\n'
    if text.count(anchor)!=1:raise ValueError('PCM bitmap inverse anchor drift')
    text=text.replace(anchor,anchor+REMOVED,1)
    if digest(text)!=PARENT_SHA256:raise ValueError('PCM bitmap permission inverse drift')
    return text.encode()
