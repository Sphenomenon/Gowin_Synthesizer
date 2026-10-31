"""Checked inverse of the explicit runtime-only storage generate adapter."""
import re

def before_runtime_clear_adapter(text):
    pattern=(r'    generate if\(NATIVE_RUNTIME_PROTOCOL\)begin: g_runtime_(capture|playback|dma)\n'
             r'.*?    end else begin: g_legacy_\1\n(.*?)    end endgenerate')
    def legacy(match):
        return re.sub(r'^        assign runtime_.*;\n','',match[2],flags=re.M).rstrip('\n')
    text,count=re.subn(pattern,legacy,text,flags=re.S)
    if count!=3:raise ValueError('Runtime storage generate identity drift')
    edits=[
        ('    parameter integer NATIVE_RESTART_HOLD = 0,\n    parameter integer NATIVE_RUNTIME_PROTOCOL = 0',
         '    parameter integer NATIVE_RESTART_HOLD = 0'),
        ('    input  wire        native_memory_hold_i,\n    input wire native_source_hold_i,\n    input wire runtime_clear_toggle_i,\n    output wire runtime_clear_done_o\n',
         '    input  wire        native_memory_hold_i\n'),
        ("    wire native_source_hold=NATIVE_RUNTIME_PROTOCOL ? native_source_hold_i:1'b0;\n"
         '    wire soft_restart = (restart && !restart_q) |\n'
         '        (!NATIVE_RUNTIME_PROTOCOL && (track_change | reader_fault));',
         '    wire soft_restart = (restart && !restart_q) | track_change | reader_fault;'),
        ('    wire runtime_capture_wr_ack,runtime_capture_rd_ack,runtime_playback_wr_ack,runtime_playback_rd_ack,runtime_dma_ack;\n','')]
    edits.extend([('    wire native_memory_hold;\n',''),
        ("    assign native_memory_hold=NATIVE_RESTART_HOLD ? native_memory_hold_i:1'b0;",
         "    wire native_memory_hold=NATIVE_RESTART_HOLD ? native_memory_hold_i:1'b0;")])
    edits.extend([
        ('    reg file_size_valid_settled;\n'
         '    // Native DMA publishes length and valid together, then holds both until\n'
         '    // restart. Give the continuously sampled word one extra destination edge\n'
         '    // before it may change a playback threshold or become public metadata.\n'
         '    wire file_size_ready=NATIVE_RUNTIME_PROTOCOL ?\n'
         '        (file_size_valid_settled && !native_source_hold && !soft_restart):file_size_valid_sync;\n',''),
        ("    assign audio_file_size = NATIVE_RUNTIME_PROTOCOL && !file_size_ready ? 32'd0:file_size_sync_ui;\n"
         '    always @(posedge clk_50m or negedge reset_n)begin\n'
         '        if(!reset_n)file_size_valid_settled<=0;\n'
         '        else if(soft_restart || native_source_hold)file_size_valid_settled<=0;\n'
         '        else file_size_valid_settled<=file_size_valid_sync;\n'
         '    end',
         '    assign audio_file_size = file_size_sync_ui;'),
        ("            if(NATIVE_RUNTIME_PROTOCOL && (soft_restart || native_source_hold))begin\n"
         "                file_size_valid_meta <= 1'b0;\n"
         "                file_size_valid_sync <= 1'b0;\n"
         '            end\n',''),
        ("        (file_size_ready && file_size_sync_ui < 32'd1024) ?",
         "        (file_size_valid_sync && file_size_sync_ui < 32'd1024) ?")])
    for changed,original in edits:
        if text.count(changed)!=1:raise ValueError('Runtime clear inverse anchor drift: '+changed[:60])
        text=text.replace(changed,original)
    if text.count(' && !native_source_hold')!=5:raise ValueError('Runtime source hold anchors drift')
    text=text.replace(' && !native_source_hold','')
    pattern=(r'    \(\* ASYNC_REG="TRUE",syn_preserve=1 \*\) reg \[4:0\] runtime_ack_meta,runtime_ack_sync;\n'
             r'.*?    assign runtime_clear_done_o=.*?;\n\n')
    text,count=re.subn(pattern,'',text,flags=re.S)
    if count!=1:raise ValueError('Runtime clear ACK inverse anchor drift')
    text=text.replace('    );\n\n\n    // Status is produced','    );\n\n    // Status is produced')
    return text
