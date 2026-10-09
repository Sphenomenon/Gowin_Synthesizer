"""Bounded full85 shared-DDR bus boundary patch; no raster/effect/CNN changes."""
HDMI='src/video/hdmi_display.v'
ARBITER='src/ae350/gw138k_ddr_arbiter.sv'
PIPELINE='rtl/music/basic_pitch_ddr_arbiter_pipeline.sv'

CLIENT_QUEUES="rtl/music/basic_pitch_ddr_client_queues.sv"

def patch_hdmi(text,buffered_clients=False):
    assert text.count('    input wire [255:0] app_rdata,')==1
    text=text.replace('    input wire [255:0] app_rdata,','    input wire [255:0] app_rdata,\n    output wire [255:0] client_rdata,')
    # All consumer uses follow the BIST declaration; retain the native input.
    start=text.index('    ddr3_bist u_bist (')
    text=text[:start]+text[start:].replace('app_rdata','client_rdata')
    assert text.count('    gw138k_ddr_arbiter u_arbiter')==1
    module='basic_pitch_ddr_client_queues' if buffered_clients else 'basic_pitch_ddr_arbiter_pipeline'
    text=text.replace('    gw138k_ddr_arbiter u_arbiter','    '+module+' u_arbiter',1)
    anchor='.app_response(app_rvalid),.response_fault(arbiter_fault)'
    assert text.count(anchor)==1
    return text.replace(anchor,'.app_response(app_rvalid),.app_response_data(app_rdata),\n        .response_data(client_rdata),.response_fault(arbiter_fault)')

def patch_top(text):
    # Exactly the two native endpoint connections retain app_rdata: the PHY
    # output and new arbiter input. CPU, TF, CNN and P10 consume client_rdata.
    text=text.replace('app_rdata','client_rdata').replace('.client_rdata(','.app_rdata(')
    declaration='    wire [255:0] app_wdata,client_rdata;'
    assert text.count(declaration)==1
    text=text.replace(declaration,'    wire [255:0] app_wdata,app_rdata,client_rdata;')
    start=text.index('    ddr3_platform u_memory (');end=text.index('    );',start)
    block=text[start:end];assert block.count('.app_rdata(client_rdata)')==1
    text=text[:start]+block.replace('.app_rdata(client_rdata)','.app_rdata(app_rdata)')+text[end:]
    start=text.index('    hdmi_display u_video (');end=text.index('    );',start)
    block=text[start:end];assert block.count('.app_rdata(client_rdata)')==1
    text=text[:start]+block.replace('.app_rdata(client_rdata)','.app_rdata(app_rdata),.client_rdata(client_rdata)')+text[end:]
    return text

DELAY='rtl/audio/delay_ddr/serial_delay_effect_ddr.sv'
SYNC_FIFO='rtl/music/basic_pitch_ddr_sync_fifo.sv'

def patch_delay_fifo(text,both=False):
    anchor='  music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) u_write_fifo('
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor.replace('music_async_fifo','basic_pitch_ddr_sync_fifo'))
    if both:
        read=anchor.replace('u_write_fifo','u_read_fifo')
        assert text.count(read)==1
        text=text.replace(read,read.replace('music_async_fifo','basic_pitch_ddr_sync_fifo'))
    return text

TF_DMA='src/storage/tf_audio_ddr_dma.v'

def retime_tf_write_buffer(text):
    """Local data writes plus delayed zeroing in the no-request idle bubble.

    The original write-accept cycle issues no new capture read (write_pending
    is high). Clear one cycle later, before that capture request can return.
    Byte data/valid use only local capture state; command contents stay exact.
    """
    declaration='    reg [255:0] write_buf, read_buf;'
    assert text.count(declaration)==1
    text=text.replace(declaration,declaration+'\n    reg write_clear_pending;')
    lines=text.splitlines()
    clears=[line for line in lines if line.strip()=="write_buf <= 256'd0;"]
    assert len(clears)==4,clears
    text='\n'.join(line for line in lines if line not in clears)+'\n'
    byte='                        write_buf[write_count*8 +: 8] <= fifo_in_rd_data;'
    assert text.count(byte)==1;text=text.replace(byte,'')
    anchor='    always @(posedge clk or negedge rst_n) begin'
    assert text.count(anchor)==1
    data='''    wire epoch_clear=restart_event || (state==S_DONE && capture_finished);
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin write_buf<=0;write_clear_pending<=0;end
        else if(epoch_clear)begin write_buf<=0;write_clear_pending<=0;end
        else begin
            write_clear_pending<=write_accept;
            if(write_clear_pending)write_buf<=0;
            else if(state==S_STREAM && fifo_in_rd_valid && capture_byte_count!=32'hffff_ffff)
                write_buf[write_count*8 +:8]<=fifo_in_rd_data;
        end
    end
'''
    return text.replace(anchor,data+anchor,1)

TF_BUFFER='src/memory/tf_audio_ddr_command_buffer.sv'
TMDS='vendor/sipeed_dvi/dvi_tx_tmds_enc.v'

def retime_tf_buffer_enable(text):
    old="""        end else if(full && out_ready) full<=0;
        else if(!full && in_valid) begin
            full<=1;
            write_q<=in_write;
            address_q<=in_address;
            data_q<=in_data;
        end"""
    new="""        end else begin
            if(full)begin if(out_ready)full<=0;end
            else begin
                full<=in_valid;
                write_q<=in_write;
                address_q<=in_address;
                data_q<=in_data;
            end
        end"""
    assert text.count(old)==1
    return text.replace(old,new)

def retime_tf_capture_limit(text):
    declaration='    reg capture_overflow;'
    assert text.count(declaration)==1
    text=text.replace(declaration,declaration+'\n    reg capture_limit_hit;')
    anchor='    wire epoch_clear='
    assert text.count(anchor)==1
    text=text.replace(anchor,"""    // The saturating byte count changes only at a capture acceptance. Predict
    // its terminal value on the same edge, so the wide buffer never decodes
    // the 32-bit count in its per-byte write-enable cones.
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)capture_limit_hit<=0;
        else if(restart_event || (state==S_DONE && capture_finished))capture_limit_hit<=0;
        else if(state==S_STREAM && fifo_in_rd_valid && capture_byte_count==32'hffff_fffe)
            capture_limit_hit<=1;
    end
"""+anchor)
    return text.replace("state==S_STREAM && fifo_in_rd_valid && capture_byte_count!=32'hffff_ffff",
                        'state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit')

def retime_display_enable(text):
    anchor='    wire display_enabled=bist_done && !bist_failed && !fetch_fault && !arbiter_fault;'
    assert text.count(anchor)==1
    return text.replace(anchor,"""    reg display_enabled;
    always @(posedge memory_clk or negedge ui_rst_n)begin
        if(!ui_rst_n)display_enabled<=0;
        else display_enabled<=bist_done && !bist_failed && !fetch_fault && !arbiter_fault;
    end""")

def retime_tmds_statistics(text):
    assert text.count('data_reg<=0;input_ones<=0;den_reg<=0;ctrl_reg<=0;')==1
    assert text.count('data_reg<=data;input_ones<=count_ones(data);den_reg<=den;ctrl_reg<=ctrl;')==1
    text=text.replace('data_reg<=0;input_ones<=0;den_reg<=0;ctrl_reg<=0;',
                      'data_reg<=0;den_reg<=0;ctrl_reg<=0;')
    text=text.replace('data_reg<=data;input_ones<=count_ones(data);den_reg<=den;ctrl_reg<=ctrl;',
                      'data_reg<=data;den_reg<=den;ctrl_reg<=ctrl;')
    anchor='    always @(posedge clock) begin'
    assert text.count(anchor)==1
    # Statistics are masked by den_reg/den_stats during reset pipeline drain.
    return text.replace(anchor,'    always @(posedge clock) input_ones<=count_ones(data);\n'+anchor)

DASHBOARD='src/video/feedback_dashboard.v'
RENDERER='src/video/feedback_renderer.v'

def predecode_dashboard(text):
    """One enabled predecode stage; same pixel content after one extra enable."""
    import re
    header_end=text.index('    localparam [255:0] TITLE')
    header=text[:header_end];body=text[header_end:]
    inputs=[]
    for declaration in re.findall(r'input wire\s+([^\n]+)',header):
        width=re.search(r'\[[^]]+\]',declaration)
        width=width[0] if width else ''
        for name in declaration.replace(width,'').strip().strip(',').split(','):
            name=name.strip()
            if name not in ('clk','reset_n','enable','frame_start'):inputs.append((width,name))
    assert len(inputs)==23,len(inputs)
    # Frame animation and frame-gain freeze consume the original raw inputs;
    # they must not move one cycle relative to frame_start.
    preserves=[]
    patterns=[r'    always @\(posedge clk or negedge reset_n\) begin.*?\n    end\n',
              r'    always @\* begin\n        computed_wave_gain=.*?\n    end\n',
              r'    always @\(posedge clk or negedge reset_n\)\n        if\(!reset_n\)wave_gain.*?: 0;\n']
    for pattern in patterns:
        match=re.search(pattern,body,re.S);assert match,pattern
        preserves.append(match[0]);body=body[:match.start()]+f'    // PRESERVED_RAW_{len(preserves)-1}\n'+body[match.end():]
    # Pure coordinate predicates are inexpensive in stage0 and no longer
    # travel through all text priority muxes before reaching stageA.
    start=body.index('    always @* begin\n        text_line = 0;');end=body.index('    always @* begin\n        next_character',start)
    block=body[start:end];conditions=[]
    def condition(match):
        expr=match[1]
        names=set(re.findall(r'\b[A-Za-z_]\w*\b',expr))
        if ('pixel_x' in names or 'pixel_y' in names) and names <= {'pixel_x','pixel_y','d','h'}:
            index=len(conditions);conditions.append(expr)
            return 'if (coordinate_predicate_q['+str(index)+'])'
        return match[0]
    block=re.sub(r'if\s*\(([^()]*)\)',condition,block)
    assert len(conditions)>30,len(conditions)
    body=body[:start]+block+body[end:]
    # Every remaining input is carried with the same enable; animated local
    # state is carried too so frame boundaries cannot skew label/card data.
    extras=[('[2:0]','visible_mask'),('[1:0]','front_effect'),('[10:0]','effect_x0'),('[10:0]','effect_x1'),('[10:0]','effect_x2'),('[2:0]','wave_gain')]
    carried=inputs+extras
    for width,name in carried:body=re.sub(r'\b'+name+r'\b',name+'_q',body)
    for index,original in enumerate(preserves):body=body.replace(f'    // PRESERVED_RAW_{index}\n',original)
    # Destination is animation control too and uses the current raw frame mask.
    start=body.index('    function [10:0] destination(');end=body.index('    endfunction',start)
    raw=body[start:end].replace('effect_mask_q','effect_mask').replace('effect_order_q','effect_order')
    body=body[:start]+raw+body[end:]
    declarations='\n'.join('    reg '+width+' '+name+'_q;' for width,name in carried)+'\n'
    declarations+=f'    reg [{len(conditions)-1}:0] coordinate_predicate_q;\n'
    # Expressions are evaluated from raw coordinates, on the same edge as the
    # raw payload capture. Both hold during every renderer DDR stall.
    sequential='    always @(posedge clk or negedge reset_n)begin\n        if(!reset_n)begin\n'
    sequential+=''.join('            '+name+'_q<=0;\n' for _,name in carried)
    sequential+='            coordinate_predicate_q<=0;\n        end else if(enable)begin\n'
    sequential+=''.join('            '+name+'_q<='+name+';\n' for _,name in carried)
    sequential+=''.join(f'            coordinate_predicate_q[{i}]<=({expr});\n' for i,expr in enumerate(conditions))
    sequential+='        end\n    end\n'
    # Declarations of animated state were renamed along with consumers;
    # restore those declarations (raw blocks assign them).
    for width,name in extras:
        body=body.replace('reg '+width+' '+name+'_q;', 'reg '+width+' '+name+';')
    body=body.replace('reg [10:0] effect_x0_q, effect_x1_q, effect_x2_q;', 'reg [10:0] effect_x0, effect_x1, effect_x2;')
    body=body.replace('reg [2:0] wave_gain_q,computed_wave_gain;', 'reg [2:0] wave_gain,computed_wave_gain;')
    return header+declarations+body.replace('endmodule',sequential+'endmodule')

def align_renderer_predecode(text):
    assert text.count('reg [4:0] valid_pipe, last_pipe;')==1
    text=text.replace('reg [4:0] valid_pipe, last_pipe;','reg [5:0] valid_pipe, last_pipe;')
    text=text.replace('c_x, c_y, output_x, output_y;', 'c_x, c_y, d_x, d_y, output_x, output_y;')
    text=text.replace('last_pipe[4]','last_pipe[5]').replace('valid_pipe[4]','valid_pipe[5]')
    text=text.replace('valid_pipe[3:0]','valid_pipe[4:0]').replace('last_pipe[3:0]','last_pipe[4:0]')
    assert text.count('output_x <= c_x; output_y <= c_y;')==1
    text=text.replace('output_x <= c_x; output_y <= c_y;', 'd_x <= c_x; d_y <= c_y;\n                output_x <= d_x; output_y <= d_y;')
    anchor='c_x <= 0; c_y <= 0;'
    assert text.count(anchor)==1
    return text.replace(anchor,anchor+' d_x <= 0; d_y <= 0;')
