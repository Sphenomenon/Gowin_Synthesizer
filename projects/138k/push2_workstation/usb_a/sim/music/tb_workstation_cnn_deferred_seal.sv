`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
// Storage/lifecycle test only: the CNN boundary below is a deterministic sink.
// The actual broker, staging FIFOs, CRC/commit/readback task service are used.
module tb_workstation_cnn_deferred_seal;
    reg clk=0,mclk=0,rst=0;
    always #10 clk=~clk;
    always #7 mclk=~mclk;
    reg start=0,frame=0,seal=0,cancel=0;
    reg [31:0] generation=0,budget=0,index=0,pcm=0,seal_frames=0,seal_crc=0;
    wire sr,fr,zr,accepted,rejected,tv,sv,fatal;
    wire [3:0] tc;
    wire [31:0] af,cf,rf,si;
    wire mv,mw;
    wire [28:0] ma;
    wire [255:0] md;
    wire [31:0] mm;
    reg nr=0,rsp=0;
    reg [255:0] rd=0;
    integer checks=0,notes=0;
    workstation_cnn_task_service #(.DEFERRED_SEAL_ENABLE(1),.IO_TIMEOUT_CYCLES(1000),.TASK_TIMEOUT_CYCLES(20000)) dut(
        .clk_i(clk),.reset_ni(rst),.memory_clk_i(mclk),.memory_reset_ni(rst),.backend_ready_i(rst),.transport_fault_i(1'b0),
        .start_valid_i(start),.start_ready_o(sr),.start_task_id_i(32'd5),.start_generation_i(generation),
        .start_frames_i(budget),.start_crc_i(32'd0),.start_format_i(8'd1),.start_accepted_o(accepted),.start_rejected_o(rejected),.rejection_code_o(),
        .frame_valid_i(frame),.frame_ready_o(fr),.frame_task_id_i(32'd5),.frame_generation_i(generation),.frame_index_i(index),.frame_pcm_i(pcm),
        .ingress_fault_i(1'b0),.seal_valid_i(seal),.seal_ready_o(zr),.seal_task_id_i(32'd5),.seal_generation_i(generation),
        .seal_frames_i(seal_frames),.seal_crc_i(seal_crc),.cancel_valid_i(cancel),.cancel_task_id_i(32'd5),.cancel_generation_i(generation),
        .seal_valid_o(),.seal_crc_o(),.accepted_frames_o(af),.committed_frames_o(cf),.replayed_frames_o(rf),
        .score_valid_o(sv),.score_ready_i(1'b1),.score_note_o(),.score_index_o(si),.task_id_o(),.generation_o(),
        .terminal_valid_o(tv),.terminal_ready_i(1'b0),.terminal_code_o(tc),.first_result_valid_o(),.first_result_note_o(),.first_result_frame_o(),
        .fatal_o(fatal),.model_status_o(),.model_serial_i(1'b1),.flash_miso_i(1'b1),.flash_cs_n_o(),.flash_clk_o(),.flash_mosi_o(),
        .memory_valid_o(mv),.memory_write_o(mw),.memory_address_o(ma),.memory_data_o(md),.memory_mask_o(mm),
        .memory_slot_ready_i(1'b1),.memory_native_accept_i(nr),.memory_response_i(rsp),.memory_read_data_i(rd));
    // Old callers omit all new seal inputs with the default parameter. They
    // must remain ready and may not enter a deferred-seal state by X leakage.
    wire old_ready,old_seal_ready,old_fatal;
    workstation_cnn_task_service #(.IO_TIMEOUT_CYCLES(1000)) old_default(
        .clk_i(clk),.reset_ni(rst),.memory_clk_i(mclk),.memory_reset_ni(rst),.backend_ready_i(rst),.transport_fault_i(1'b0),
        .start_valid_i(1'b0),.start_ready_o(old_ready),.frame_valid_i(1'b0),.ingress_fault_i(1'b0),.cancel_valid_i(1'b0),
        .seal_ready_o(old_seal_ready),.terminal_ready_i(1'b0),.score_ready_i(1'b1),.fatal_o(old_fatal),
        .model_serial_i(1'b1),.flash_miso_i(1'b1),.memory_slot_ready_i(1'b0),.memory_native_accept_i(1'b0),.memory_response_i(1'b0),.memory_read_data_i(256'd0));
    reg race_desc=0,race_cancel=0;
    wire race_ready;
    workstation_task3_cnn_stream_w race(
        .clk_i(clk),.reset_ni(rst),.memory_clk_i(mclk),.memory_reset_ni(rst),.backend_ready_i(rst),
        .link_ready_i(1'b1),.transport_fault_i(1'b0),.panic_i(1'b0),.peer_boot_i(32'd1),.session_i(32'd2),
        .desc_valid_i(race_desc),.desc_ready_o(race_ready),.desc_i({32'd1,32'd2,32'd3,32'd4,32'd16,32'd0,8'd1}),
        .frame_valid_i(1'b0),.frame_i(192'd0),.seal_valid_i(1'b0),.seal_i(192'd0),
        .cancel_valid_i(race_cancel),.cancel_i({32'd1,32'd2,32'd3,32'd4}),
        .score_ready_i(1'b1),.terminal_ready_i(1'b1),.model_serial_i(1'b1),.flash_miso_i(1'b1),
        .memory_slot_ready_i(1'b0),.memory_native_accept_i(1'b0),.memory_response_i(1'b0),.memory_read_data_i(256'd0));
    reg [255:0] mem[0:31];
    reg [28:0] held_addr;
    reg [255:0] held_data;
    reg [31:0] held_mask;
    reg held_write;
    integer mstate=0,waits=0,beat,lane;
    always @(posedge mclk)begin
        nr<=0;rsp<=0;
        if(!rst)begin mstate<=0;waits<=0;end
        else case(mstate)
            0:if(mv)begin held_addr<=ma;held_data<=md;held_mask<=mm;held_write<=mw;waits<=3;mstate<=1;end
            1:if(waits!=0)waits<=waits-1;
              else begin
                  nr<=1;beat=integer'((held_addr-`PRJ1_DDR_TASK3_W_CNN_PCM_APP_BASE)>>3);
                  if(beat<0 || beat>=32)$fatal(1,"outside clip memory");
                  if(held_write)begin for(lane=0;lane<32;lane=lane+1)if(!held_mask[lane])mem[beat][lane*8+:8]<=held_data[lane*8+:8];end
                  else rd<=mem[beat];
                  waits<=4;mstate<=2;
              end
            2:if(held_write)mstate<=0;
              else if(waits!=0)waits<=waits-1;
              else begin rsp<=1;mstate<=0;end
        endcase
    end
    always @(posedge clk)if(rst && sv)notes<=notes+1;
    task automatic check(input bit ok,input string label_text);
        begin checks=checks+1;if(!ok)$fatal(1,"check failed %s",label_text);end
    endtask
    function automatic [31:0] cb(input [31:0] old_crc,input [7:0] data);
        reg [31:0] c;integer j;begin c=old_crc^{24'd0,data};for(j=0;j<8;j=j+1)c=c[0]?((c>>1)^32'hedb88320):(c>>1);cb=c;end
    endfunction
    task automatic reset_all;
        begin @(negedge clk);rst=0;start=0;frame=0;seal=0;cancel=0;notes=0;repeat(5)@(negedge clk);rst=1;
            repeat(10)@(negedge clk);check(old_ready && !old_seal_ready && !old_fatal,"old default omitted ports safe");end
    endtask
    task automatic launch(input integer frames);
        begin generation=generation+1;budget=frames;@(negedge clk);while(!sr)@(negedge clk);start=1;@(negedge clk);start=0;
            while(!fr)@(negedge clk);end
    endtask
    task automatic feed(input integer frames,output reg [31:0] sum);
        integer j,k;reg [31:0] value,c;
        begin c=32'hffffffff;
            for(j=0;j<frames;j=j+1)begin
                @(negedge clk);index=32'(j);value=32'h5ac30000^32'(j*1237);pcm=value;frame=1;
                while(!fr)@(negedge clk);
                @(negedge clk);frame=0;
                for(k=0;k<4;k=k+1)c=cb(c,value[k*8+:8]);
            end
            sum=~c;
        end
    endtask
    task automatic send_seal(input integer frames,input [31:0] crc_value);
        begin @(negedge clk);seal_frames=32'(frames);seal_crc=crc_value;seal=1;while(!zr)@(negedge clk);@(negedge clk);seal=0;end
    endtask
    task automatic terminal(input [3:0] code);
        begin while(!tv)@(negedge clk);check(tc==code && !fatal,"expected bounded terminal");end
    endtask
    reg [31:0] crc_value;
    initial begin
        reset_all();launch(32);feed(13,crc_value);
        repeat(50)@(negedge clk);check(rf==0 && dut.cnn.received==0,"no inference before partial seal");
        send_seal(13,crc_value);terminal(0);
        check(af==13 && cf==13 && rf==13 && notes==2,"partial finite clip commits/verifies/replays");
        reset_all();launch(16);feed(16,crc_value);repeat(50)@(negedge clk);
        check(dut.state==13 && rf==0,"exact budget waits for seal");send_seal(16,crc_value);terminal(0);
        check(cf==16 && rf==16,"exact-budget clip success");
        reset_all();launch(32);feed(9,crc_value);send_seal(9,crc_value^1);terminal(4);check(rf==0,"bad input seal CRC rejected");
        reset_all();launch(32);feed(9,crc_value);send_seal(8,crc_value);terminal(4);check(rf==0,"bad seal length rejected");
        reset_all();launch(32);feed(8,crc_value);
        while(cf!=8)@(negedge clk);@(negedge mclk);mem[0][0]=!mem[0][0];
        send_seal(8,crc_value);terminal(5);check(rf==0,"real DDR readback corruption rejects before inference");
        reset_all();launch(32);feed(5,crc_value);@(negedge clk);cancel=1;@(negedge clk);cancel=0;terminal(1);
        check(rf==0,"cancel before seal prevents inference");
        reset_all();launch(32);feed(2,crc_value);terminal(6);check(rf==0,"missing seal has bounded timeout");
        reset_all();while(!race_ready)@(negedge clk);race_desc=1;@(negedge clk);race_desc=0;race_cancel=1;
        @(negedge clk);race_cancel=0;repeat(4)@(negedge clk);
        check(race.state==0 && race.task_service.state==0 && !race.task_service.start_accepted_o,"START same-cycle cancel cannot leave hidden accepted task");
        check(race.task_service.cnn.WIN_LEN==44100 && race.task_service.cnn.FRAME_LIMIT==8 &&
            race.task_service.cnn.CQT_HOP_NUMERATOR==22050 && race.task_service.cnn.CQT_HOP_DENOMINATOR==4 &&
            race.task_service.cnn.FEATURE_TILE_COLS==16 && race.task_service.cnn.COARSE_GUIDANCE==1,
            "explicit native W4Hz parameter chain");
        $display("PASS deferred_seal_storage_lifecycle checks=%0d scenarios=8 real_cnn=0",checks);$finish;
    end
    initial begin #30000000;$fatal(1,"test timeout");end
endmodule

// Deliberately explicit test sink: this does not prove model/CQT/CNN quality.
module basic_pitch_workstation_link #(
    parameter bit USE_FLASH_WEIGHTS=0,USE_DDR_SIGNAL=1,USE_DDR_CQT_COEFF=1,DRAIN_RESTART_ENABLE=0,BOUNDED_EOF_PADDING=0,
    parameter integer WIN_LEN=43844,FRAME_LIMIT=172,OCTAVE_LIMIT=9,CQT_HOP_NUMERATOR=256,CQT_HOP_DENOMINATOR=1,FEATURE_TILE_COLS=0,
    parameter bit COARSE_GUIDANCE=0,
    parameter integer RESTART_TIMEOUT_CYCLES=50000000
)(
    input wire clk_50m,reset_n,memory_clk,memory_reset_n,memory_calibrated,model_serial,flash_miso,
    output wire flash_cs_n,flash_clk,flash_mosi,
    input wire analysis_enable,analysis_restart,pcm_valid,pcm_end,
    input wire signed [15:0] pcm_left,pcm_right,
    input wire [19:0] sample_rate,
    input wire format_ready,source_active,
    input wire [10:0] hotplug_debug,
    output wire pcm_ready,
    output wire [3:0] model_status,
    output wire result_valid,
    output wire [6:0] result_note,
    output wire [15:0] result_frame,
    output wire score_valid,
    input wire score_ready,
    output wire [6:0] score_note,
    output wire analysis_done,report_sending,report_serial,ddr_req,ddr_write,
    output wire [28:0] ddr_address,
    output wire [255:0] ddr_data,
    output wire [31:0] ddr_mask,
    input wire ddr_ready,ddr_response,
    input wire [255:0] ddr_read_data,
    output wire restart_ready_o,restart_busy_o,restart_done_o,restart_fault_o,
    output wire [1:0] restart_failure_code_o
);
    reg restart_q;
    integer received,phase;
    assign flash_cs_n=1,flash_clk=0,flash_mosi=0,pcm_ready=1,model_status=14;
    assign result_valid=0,result_note=0,result_frame=0;
    assign score_valid=analysis_enable && (phase==1 || phase==2),score_note=phase==1?7'd60:7'd64;
    assign analysis_done=phase==3,report_sending=0,report_serial=1,ddr_req=0,ddr_write=0,ddr_address=0,ddr_data=0,ddr_mask=0;
    assign restart_ready_o=1,restart_busy_o=0,restart_done_o=restart_q,restart_fault_o=0,restart_failure_code_o=0;
    always @(posedge clk_50m or negedge reset_n)begin
        if(!reset_n)begin restart_q<=0;received<=0;phase<=0;end
        else begin
            restart_q<=analysis_restart;
            if(analysis_restart)begin received<=0;phase<=0;end
            else begin
                if(pcm_valid && analysis_enable)received<=received+1;
                if(pcm_end && analysis_enable && phase==0)phase<=1;
                else if(score_valid && score_ready)phase<=phase+1;
            end
        end
    end
endmodule
