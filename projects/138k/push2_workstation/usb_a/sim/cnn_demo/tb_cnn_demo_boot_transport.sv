`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
// Real model startup, CDC, DDR16 adapter, client slots, arbiter and BIST.
// Only the native DDR device is behavioral. No model memory is preloaded.
module tb_cnn_demo_boot_transport #(parameter EXPECT_REJECT=0);
    reg clk=0,mclk=0,rstn=0,mrstn=0,calibrated=0;
    always #10 clk=~clk;
    always #5 mclk=~mclk;
    wire req,wr,ready,rsp,done;
    wire [31:0] addr,crc;
    wire [15:0] data,rdata;
    wire [3:0] status;
    wire [1:0] error;
    workstation_cnn_demo_model_loader #(.WAIT_CYCLES(100000)) loader(
        .clk_i(clk),.rst_ni(rstn),.serial_i(1'b1),.done_o(done),.status_o(status),
        .debug_expected_crc_o(),.debug_actual_crc_o(crc),.debug_error_stage_o(error),
        .mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(data),
        .mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(rdata));
    wire qvalid,qready,cvalid,cready;
    wire [48:0] qdata,cdata;
    music_async_fifo #(.WIDTH(49),.ADDRESS_BITS(4)) requests(
        .write_clk_i(clk),.write_rst_ni(rstn),.write_valid_i(req),.write_ready_o(ready),
        .write_data_i({wr,addr,data}),.read_clk_i(mclk),.read_rst_ni(mrstn),
        .read_valid_o(qvalid),.read_ready_i(qready),.read_data_o(qdata));
    basic_pitch_ddr_command_buffer commands(.clk_i(mclk),.rst_ni(mrstn),
        .in_valid_i(qvalid),.in_data_i(qdata),.in_ready_o(qready),
        .out_valid_o(cvalid),.out_data_o(cdata),.out_ready_i(cready));
    wire drsp,drspready;wire [15:0] drdata;
    music_async_fifo #(.WIDTH(16),.ADDRESS_BITS(2)) replies(
        .write_clk_i(mclk),.write_rst_ni(mrstn),.write_valid_i(drsp),
        .write_ready_o(drspready),.write_data_i(drdata),.read_clk_i(clk),
        .read_rst_ni(rstn),.read_valid_o(rsp),.read_ready_i(1'b1),.read_data_o(rdata));
    wire dreq,dwr,dready,dresponse;
    wire [28:0] daddr;wire [255:0] ddata,response_data;wire [31:0] dmask;
    basic_pitch_ddr16_port port16(.clk_i(mclk),.rst_ni(mrstn),
        .req_valid_i(cvalid && calibrated && (cdata[48] || drspready)),
        .req_write_i(cdata[48]),.req_byte_addr_i(cdata[47:16]),.req_wdata_i(cdata[15:0]),
        .req_ready_o(cready),.rsp_valid_o(drsp),.rsp_rdata_o(drdata),
        .ddr_req_o(dreq),.ddr_write_o(dwr),.ddr_address_o(daddr),.ddr_data_o(ddata),
        .ddr_mask_o(dmask),.ddr_ready_i(dready),.ddr_response_i(dresponse),
        .ddr_read_data_i(response_data));
    wire client_ready,client_reset,aready;
    reg audio_pending=1;
    wire [2:0] cmd;wire en,wren,wend;
    wire [28:0] app_addr;wire [255:0] app_data;wire [31:0] mask;
    reg [31:0] cycle=0;
    wire app_ready=cycle%7!=0,app_wrdy=cycle%5!=0;
    reg [3:0] rsp_pipe=0;
    reg [255:0] rsp_data[0:3];
    wire [7:0] flags;
    workstation_cnn_demo_memory #(.BIST_BURSTS(32)) memory_owner(
        .reset_ni(rstn),.clk_50m_i(clk),.memory_clk_i(mclk),.memory_reset_ni(mrstn),
        .memory_calibrated_i(calibrated),.memory_pll_locked_i(mrstn),
        .client_reset_no(client_reset),.client_ready_o(client_ready),
        .audio_valid_i(audio_pending),.audio_write_i(1'b1),.audio_address_i(29'd512),
        .audio_data_i(256'hdeadbeef),.audio_ready_o(aready),.audio_response_o(),
        .music_valid_i(dreq),.music_write_i(dwr),.music_address_i(daddr),
        .music_data_i(ddata),.music_mask_i(dmask),.music_ready_o(dready),.music_response_o(dresponse),
        .app_cmd_o(cmd),.app_en_o(en),.app_wren_o(wren),.app_wend_o(wend),
        .app_address_o(app_addr),.app_data_o(app_data),.app_mask_o(mask),
        .app_ready_i(app_ready),.app_write_ready_i(app_wrdy),.app_response_i(rsp_pipe[3]),
        .app_response_data_i(rsp_data[3]),.response_data_o(response_data),.memory_flags_o(flags));
    localparam [28:0] MODEL_BASE=`BP_DDR_NN_MODEL_BYTE_BASE>>2;
    reg [255:0] native_memory[0:3399];
    reg [15:0] oracle[0:52238];
    integer i,lane,index,model_writes=0,model_reads=0,false_ready=0;
    always @(posedge mclk)begin
        cycle<=cycle+1;
        if(aready && audio_pending)audio_pending<=0;
        if(client_reset && !client_ready && (aready || dready))false_ready<=false_ready+1;
        rsp_pipe<={rsp_pipe[2:0],1'b0};
        for(i=3;i>0;i=i-1)rsp_data[i]<=rsp_data[i-1];
        if(en)begin
            if(!app_ready || (wren && !app_wrdy))$fatal(1,"bad native handshake");
            index=app_addr>=MODEL_BASE ? 128+int'((app_addr-MODEL_BASE)>>3) : int'(app_addr>>3);
            if(index>=3400)$fatal(1,"unexpected native address %h",app_addr);
            if(wren)begin
                for(lane=0;lane<32;lane=lane+1)
                    if(!mask[lane])native_memory[index][lane*8+:8]<=app_data[lane*8+:8];
                if(app_addr>=MODEL_BASE)model_writes<=model_writes+1;
            end else begin
                rsp_pipe[0]<=1;rsp_data[0]<=native_memory[index];
                if(app_addr>=MODEL_BASE)model_reads<=model_reads+1;
            end
        end
    end
    initial begin
        for(i=0;i<3400;i=i+1)native_memory[i]=0;
        $readmemh("rtl/music/weights/cnn_ddr_blob.mem",oracle);
        repeat(8)@(negedge clk);rstn=1;
        repeat(20)@(negedge mclk);mrstn=1;
        repeat(20)@(negedge mclk);calibrated=1;
        wait(done || status==15);@(negedge clk);
        if(EXPECT_REJECT)begin
            if(done || false_ready==0 || model_writes==52239)$fatal(1,"D7 negative did not expose lost startup requests");
            $display("PASS D7 negative reproduced: status=%h error=%d false_ready=%d model_writes=%d CRC=%h",status,error,false_ready,model_writes,crc);
        end else begin
            if(!done || crc!=32'hAF01A61B || error || false_ready ||
               model_writes!=52239 || model_reads!=52239 || !flags[1] || flags[2])
                $fatal(1,"joined boot failed status=%h error=%d false_ready=%d writes=%d reads=%d CRC=%h flags=%h",status,error,false_ready,model_writes,model_reads,crc,flags);
            for(i=0;i<52239;i=i+1)
                if(native_memory[128+i/16][(i%16)*16+:16]!==oracle[i])$fatal(1,"model word %d corrupted",i);
            $display("PASS joined automatic boot: real BIST/CDC/DDR16/slots/arbiter, 52239 native writes and reads, AF01A61B, no false acceptance");
        end
        $finish;
    end
    initial begin #100000000;$fatal(1,"joined boot hung");end
endmodule
