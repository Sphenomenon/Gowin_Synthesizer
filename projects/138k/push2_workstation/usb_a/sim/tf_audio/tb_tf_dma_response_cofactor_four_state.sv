`timescale 1ns/1ps
module tf_response_four;
    parameter [31:0] BANK_BYTES = 64;
    localparam [31:0] TEST_CAPACITY = BANK_BYTES + BANK_BYTES;
    reg clk=0;

    reg rst_n=0,mem_ready=0,capture_done_toggle=0,restart_toggle=0;
    reg [31:0] file_size_bytes=0;
    reg fifo_in_empty=1,fifo_in_rd_valid=0,fifo_out_full=0;
    reg [7:0] fifo_in_rd_data=0;
    reg app_rdy=0,app_wrdy=0,app_rvalid=0,runtime_hold_i=0;
    reg [255:0] app_rdata=0;
    wire fifo_in_rd_en,playback_start_toggle,playback_done_toggle;
    wire fifo_out_wr_en,app_en,app_wren,app_wend,capacity_error;
    wire bank0_valid,bank1_valid,file_size_valid,runtime_restart_ack_o;
    wire [7:0] fifo_out_wr_data;
    wire [2:0] app_cmd;
    wire [28:0] app_addr;
    wire [255:0] app_wdata;
    wire [31:0] staged_file_size;
    wire r_fifo_in_rd_en,r_playback_start_toggle,r_playback_done_toggle;
    wire r_fifo_out_wr_en,r_app_en,r_app_wren,r_app_wend,r_capacity_error;
    wire r_bank0_valid,r_bank1_valid,r_file_size_valid,r_runtime_restart_ack_o;
    wire [7:0] r_fifo_out_wr_data;
    wire [2:0] r_app_cmd;
    wire [28:0] r_app_addr;
    wire [255:0] r_app_wdata;
    wire [31:0] r_staged_file_size;
    workstation_tf_runtime_dma #(.AUDIO_BANK_BYTES(BANK_BYTES),.AUDIO_STREAM_START_BYTES(32)) dut(.*);
    reference_workstation_tf_runtime_dma #(.AUDIO_BANK_BYTES(BANK_BYTES),.AUDIO_STREAM_START_BYTES(32)) reference(
        .clk(clk),.rst_n(rst_n),.mem_ready(mem_ready),.capture_done_toggle(capture_done_toggle),
        .restart_toggle(restart_toggle),.file_size_bytes(file_size_bytes),.fifo_in_empty(fifo_in_empty),
        .fifo_in_rd_valid(fifo_in_rd_valid),.fifo_in_rd_data(fifo_in_rd_data),
        .fifo_out_full(fifo_out_full),.app_rdy(app_rdy),.app_wrdy(app_wrdy),
        .app_rvalid(app_rvalid),.app_rdata(app_rdata),.runtime_hold_i(runtime_hold_i),
        .fifo_in_rd_en(r_fifo_in_rd_en),.playback_start_toggle(r_playback_start_toggle),
        .playback_done_toggle(r_playback_done_toggle),.fifo_out_wr_en(r_fifo_out_wr_en),
        .fifo_out_wr_data(r_fifo_out_wr_data),.app_cmd(r_app_cmd),.app_en(r_app_en),
        .app_addr(r_app_addr),.app_wdata(r_app_wdata),.app_wren(r_app_wren),.app_wend(r_app_wend),
        .capacity_error(r_capacity_error),.bank0_valid(r_bank0_valid),.bank1_valid(r_bank1_valid),
        .file_size_valid(r_file_size_valid),.staged_file_size(r_staged_file_size),
        .runtime_restart_ack_o(r_runtime_restart_ack_o));

    integer control,pattern,checks=0;
    reg [31:0] rng=32'h71c539ad;
    reg [31:0] probe_available,probe_accepted;
    reg [5:0] probe_pending,probe_response;
    reg probe_selected,probe_read_pending,probe_read_buf,probe_stream,probe_write;
    reg [1:0] probe_state;
    function quad(input integer v);begin case(v&3)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase end endfunction
    function [31:0] random_word(input [31:0] v);reg[31:0]t;begin t=v^(v<<13);t=t^(t>>17);random_word=t^(t<<5);end endfunction
    initial begin
force dut.available_bytes=probe_available;
force dut.accepted_used=probe_accepted;
force dut.pending_bytes=probe_pending;
force dut.read_pending_bytes=probe_response;
force dut.read_pending=probe_read_pending;
force dut.write_selected=probe_selected;
force dut.write_pending=probe_write;
force dut.stream_started=probe_stream;
force dut.read_buf_valid=probe_read_buf;
force dut.state=probe_state;
force dut.eof_finalized=1;
force dut.capture_byte_count=0;
force reference.available_bytes=probe_available;
force reference.accepted_used=probe_accepted;
force reference.pending_bytes=probe_pending;
force reference.read_pending_bytes=probe_response;
force reference.read_pending=probe_read_pending;
force reference.write_selected=probe_selected;
force reference.write_pending=probe_write;
force reference.stream_started=probe_stream;
force reference.read_buf_valid=probe_read_buf;
force reference.state=probe_state;
force reference.eof_finalized=1;
force reference.capture_byte_count=0;

    for(pattern=0;pattern<16;pattern=pattern+1)begin
      probe_available=32'(pattern*31);probe_accepted=32'hfffffff0+32'(pattern);
      probe_pending=6'(pattern*3);probe_response=6'(pattern*2);
      case(pattern)
        1:probe_available=32'hffffffff;
        2:probe_available=32'h0000000x;
        3:probe_available=32'hxxxxxx80;
        4:probe_accepted=32'h0000000x;
        5:probe_accepted=32'hxxxxxx80;
        6:probe_pending=6'b00000x;
        7:probe_pending=6'bx00000;
        8:probe_response=6'b00000x;
        9:probe_response=6'bx00000;
        10:probe_available=32'hzzzzzzzz;
        11:probe_accepted=32'hzzzzzzzz;
        12:probe_pending=6'bzzzzzz;
        13:probe_response=6'bzzzzzz;
        14:begin probe_available=32'hxxxxxxxx;probe_accepted=32'hxxxxxxxx;end
        15:begin probe_pending=6'bxxxxxx;probe_response=6'bxxxxxx;end
      endcase
      for(control=0;control<65536;control=control+1)begin
        probe_selected=quad(control);probe_read_pending=quad(control>>2);
        app_rdy=quad(control>>4);app_rvalid=quad(control>>6);
        fifo_in_rd_valid=quad(control>>8);mem_ready=quad(control>>10);
        runtime_hold_i=quad(control>>12);probe_read_buf=quad(control>>14);
        rng=random_word(rng);fifo_out_full=0;probe_stream=1;
        probe_write=1;probe_state=0;app_wrdy=quad(rng>>10);
        #0.001;
        if(dut.next_available_bytes !== reference.next_available_bytes ||
           dut.next_accepted_used !== reference.next_accepted_used)
           $fatal(1,"cofactor four-state differs pattern=%0d control=%0d old=%h new=%h selected=%b read_pending=%b",pattern,control,reference.next_accepted_used,dut.next_accepted_used,probe_selected,probe_read_pending);
        checks=checks+1;
      end
    end
    $display("PASS actual DMA cofactor four-state vectors=%0d",checks);$finish;
    end
endmodule
