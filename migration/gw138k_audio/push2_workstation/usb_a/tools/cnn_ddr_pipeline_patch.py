"""Bounded full85 shared-DDR bus boundary patch; no raster/effect/CNN changes."""
HDMI='src/video/hdmi_display.v'
ARBITER='src/ae350/gw138k_ddr_arbiter.sv'
PIPELINE='rtl/music/basic_pitch_ddr_arbiter_pipeline.sv'

def patch_hdmi(text):
    assert text.count('    input wire [255:0] app_rdata,')==1
    text=text.replace('    input wire [255:0] app_rdata,','    input wire [255:0] app_rdata,\n    output wire [255:0] client_rdata,')
    # All consumer uses follow the BIST declaration; retain the native input.
    start=text.index('    ddr3_bist u_bist (')
    text=text[:start]+text[start:].replace('app_rdata','client_rdata')
    assert text.count('    gw138k_ddr_arbiter u_arbiter')==1
    text=text.replace('    gw138k_ddr_arbiter u_arbiter','    basic_pitch_ddr_arbiter_pipeline u_arbiter',1)
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

def patch_delay_fifo(text):
    anchor='  music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) u_write_fifo('
    assert text.count(anchor)==1
    return text.replace(anchor,anchor.replace('music_async_fifo','basic_pitch_ddr_sync_fifo'))
