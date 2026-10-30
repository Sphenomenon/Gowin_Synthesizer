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
