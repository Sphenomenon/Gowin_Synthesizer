"""Strict inverse for the reviewed private final memory_failure write cofactor."""
import hashlib

BASELINE_SHA256 = 'd2e39654e16fde55c13b231ef672162fb2b2b6bdfa3740d4b7ac25bb95f8c38d'
MAINTAINED_SHA256 = '5262395f5031a14aa6cf18b359852590d3dcab33ee3fde9ce5f4e069b6fb9739'
FAILURE_BLOCK = "    // Private failure-code writes keep the original edge and first-fault rule.\n    // A known immediate fault suppresses every protocol write, so it reaches\n    // the final write enable directly. Its zero cofactor has no fault feedback;\n    // unknown fault values retain the exact original procedural projection.\n    wire failure_fifo_without_fault=fifo_read_valid && memory_reset_n && !memory_channel_fault &&\n        !memory_command_start && (clear_fifo_pop || (!memory_clear_pending && normal_fifo_pop));\n    reg memory_failure_protocol_write /* synthesis syn_keep=1 */;\n    always @* begin\n        memory_failure_protocol_write=0;\n        if(failure_fifo_without_fault)begin\n            if(!memory_clear_pending)begin\n                if(fifo_read_data[63:32]!=memory_next_index ||\n                   (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin\n                    memory_failure_protocol_write=1;\n                end\n            end\n        end\n        if(memory_command_start)begin\n            if(memory_channel_fault)begin end\n            else case(command_kind)\n                CMD_START:begin if(start_context_bad)memory_failure_protocol_write=1;end\n                CMD_CLEAR:begin\n                    if(command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)\n                        memory_failure_protocol_write=1;\n                end\n                CMD_FETCH:begin end\n                default:memory_failure_protocol_write=1;\n            endcase\n        end\n    end\n    always @(posedge memory_clk_i or negedge memory_reset_n)begin\n        if(!memory_reset_n)memory_failure<=0;\n        else case(memory_fault_now)\n            1'b1:begin\n                if(!memory_channel_fault)memory_failure<=global_failure_value;\n            end\n            1'b0:begin\n                if(memory_failure_protocol_write)memory_failure<=F_PROTOCOL;\n            end\n            default:begin\n                if(fifo_pop)begin\n                    if(!memory_clear_pending)begin\n                        if(fifo_read_data[63:32]!=memory_next_index ||\n                           (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin\n                            memory_failure<=F_PROTOCOL;\n                        end\n                    end\n                end\n                if(memory_command_start)begin\n                    if(memory_channel_fault || memory_fault_now)begin end\n                    else case(command_kind)\n                        CMD_START:begin if(start_context_bad)memory_failure<=F_PROTOCOL;end\n                        CMD_CLEAR:begin\n                            if(command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)\n                                memory_failure<=F_PROTOCOL;\n                        end\n                        CMD_FETCH:begin end\n                        default:memory_failure<=F_PROTOCOL;\n                    endcase\n                end\n                if(global_failure_write)memory_failure<=global_failure_value;\n            end\n        endcase\n    end\n\n"
MAIN_ANCHOR = '    always @(posedge memory_clk_i or negedge memory_reset_n)begin\n        if(!memory_reset_n)begin\n            command_req_meta<=0;'
GLOBAL_ANCHOR = '            if(memory_fault_now)begin\n                memory_channel_fault<=1;memory_fetch_cancel<=1;\n            end\n'
GLOBAL_WRITE = '            if(global_failure_write)memory_failure<=global_failure_value;\n'


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError('reviewed final failure CE source anchor changed: ' + old[:100])
    return text.replace(old, new)


def restore_before_failure_final_ce(text):
    """Restore the exact consumed W17 owner, rejecting any complete-source drift."""
    if _sha(text) != MAINTAINED_SHA256:
        raise ValueError('maintained final failure CE source identity changed')
    text = _replace(text, FAILURE_BLOCK, '')
    text = _replace(text, 'memory_channel_fault<=0;pack_frames<=0;',
                    'memory_channel_fault<=0;memory_failure<=0;pack_frames<=0;')
    text = _replace(text, 'memory_channel_fault<=1;\n',
                    'memory_channel_fault<=1;memory_failure<=F_PROTOCOL;\n', 3)
    text = _replace(text, 'memory_channel_fault<=1;completion_code<=F_PROTOCOL;',
                    'memory_channel_fault<=1;memory_failure<=F_PROTOCOL;completion_code<=F_PROTOCOL;')
    text = _replace(text, GLOBAL_ANCHOR, GLOBAL_ANCHOR + GLOBAL_WRITE)
    if _sha(text) != BASELINE_SHA256:
        raise ValueError('exact pre-final-failure-CE source reconstruction changed')
    return text


def apply_failure_final_ce(text):
    """Apply only the reviewed W17 change; no fallback for a different owner."""
    if _sha(text) != BASELINE_SHA256:
        raise ValueError('baseline final failure CE source identity changed')
    text = _replace(text, 'memory_channel_fault<=0;memory_failure<=0;pack_frames<=0;',
                    'memory_channel_fault<=0;pack_frames<=0;')
    text = _replace(text, 'memory_channel_fault<=1;memory_failure<=F_PROTOCOL;\n',
                    'memory_channel_fault<=1;\n', 3)
    text = _replace(text, 'memory_channel_fault<=1;memory_failure<=F_PROTOCOL;completion_code<=F_PROTOCOL;',
                    'memory_channel_fault<=1;completion_code<=F_PROTOCOL;')
    text = _replace(text, GLOBAL_WRITE, '')
    text = _replace(text, MAIN_ANCHOR, FAILURE_BLOCK + MAIN_ANCHOR)
    if _sha(text) != MAINTAINED_SHA256:
        raise ValueError('reviewed final failure CE candidate reconstruction changed')
    return text
