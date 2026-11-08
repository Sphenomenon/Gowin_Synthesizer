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

def normalize(payload):
    text=payload.decode()if isinstance(payload,bytes)else payload
    digest=lambda t:hashlib.sha256(t.encode()).hexdigest()
    if digest(text)==PARENT_SHA256:return text.encode()
    if digest(text)!=SELECTED_SHA256 or text.count(BLOCK)!=1 or text.count(NEW)!=1:
        raise ValueError('PCM bitmap permission source drift')
    text=text.replace(BLOCK,'',1).replace(NEW,OLD,1)
    anchor='        if(accepted_cancel)bitmap_clear_without_context=1;\n'
    if text.count(anchor)!=1:raise ValueError('PCM bitmap inverse anchor drift')
    text=text.replace(anchor,anchor+REMOVED,1)
    if digest(text)!=PARENT_SHA256:raise ValueError('PCM bitmap permission inverse drift')
    return text.encode()
