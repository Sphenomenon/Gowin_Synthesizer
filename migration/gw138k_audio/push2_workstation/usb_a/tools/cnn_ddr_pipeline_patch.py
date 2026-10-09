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
