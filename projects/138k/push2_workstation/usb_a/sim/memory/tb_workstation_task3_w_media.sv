`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
module tb_workstation_task3_w_media;
    localparam integer MODEL_BYTES=104510;
    reg clk=0,mclk=0,reset_n=0,memory_reset_n=0,calibrated=0;
    always #10 clk=~clk;
    always #7 mclk=~mclk;
    reg raw_start=0,raw_clear=0,raw_capture=0,raw_close=0,raw_fetch=0;
    reg [31:0] raw_index=0,raw_pcm=0,raw_addr=0;
    wire raw_start_ready,raw_start_done,raw_clear_ready,raw_clear_done,raw_capture_ready,raw_close_ready;
    wire raw_drained,raw_fault,raw_fetch_ready,raw_fetch_done,raw_fetch_fault,raw_cache,raw_protocol_fault;
    wire [31:0] raw_accepted,raw_committed,raw_word;
    wire media_reset,media_ready,control_ready,media_fault,cnn_ready,cnn_fatal;
    wire [3:0] model_status;
    wire flash_cs,flash_clk,flash_mosi;
    reg flash_miso=1;
    wire [8:0] native_accept;
    wire [2:0] app_cmd;
    wire app_en,app_wren,app_wend;
    wire [28:0] app_address;
    wire [255:0] app_data,rdata;
    wire [31:0] app_mask;
    reg app_response=0,allow_native=1,inject_unowned_return=0,expect_fault=0;
    reg [255:0] app_rdata=0;
    wire app_ready,app_write_ready;
    reg delay_valid=0;
    wire delay_ready;
    workstation_task3_w_media #(.BIST_BURSTS(4),.CNN_IO_TIMEOUT_CYCLES(100000)) dut(
        .clk_i(clk),.reset_ni(reset_n),.memory_clk_i(mclk),.memory_reset_ni(memory_reset_n),
        .memory_calibrated_i(calibrated),.memory_pll_locked_i(calibrated),
        .client_reset_no(media_reset),.client_ready_o(media_ready),.control_ready_o(control_ready),
        .memory_flags_o(),.slot_accept_o(),.core_accept_o(),.native_accept_o(native_accept),.transport_fault_o(media_fault),
        .delay_valid_i(delay_valid),.delay_write_i(1'b1),.delay_address_i(`PRJ1_DDR_DELAY_RING_APP_BASE),
        .delay_data_i(256'hd311aabb),.delay_ready_o(delay_ready),.delay_response_o(),.response_data_o(rdata),
        .raw_start_valid_i(raw_start),.raw_start_ready_o(raw_start_ready),.raw_start_done_o(raw_start_done),
        .raw_clear_valid_i(raw_clear),.raw_clear_ready_o(raw_clear_ready),.raw_clear_done_o(raw_clear_done),
        .raw_capture_valid_i(raw_capture),.raw_capture_index_i(raw_index),.raw_capture_pcm_i(raw_pcm),
        .raw_capture_ready_o(raw_capture_ready),.raw_close_valid_i(raw_close),.raw_close_ready_o(raw_close_ready),
        .raw_drained_o(raw_drained),.raw_fault_o(raw_fault),.raw_object_fault_o(),.raw_channel_fault_o(),.raw_failure_code_o(),
        .raw_accepted_frames_o(raw_accepted),.raw_committed_frames_o(raw_committed),
        .raw_fetch_valid_i(raw_fetch),.raw_fetch_ready_o(raw_fetch_ready),.raw_fetch_offset_i(32'd0),.raw_fetch_length_i(14'd96),
        .raw_fetch_done_o(raw_fetch_done),.raw_fetch_fault_o(raw_fetch_fault),.raw_cache_valid_o(raw_cache),
        .raw_sample_addr_i(raw_addr),.raw_sample_word_o(raw_word),.raw_native_protocol_fault_o(raw_protocol_fault),
        .cnn_start_valid_i(1'b0),.cnn_start_ready_o(cnn_ready),.cnn_start_task_id_i(32'd0),.cnn_start_generation_i(32'd0),
        .cnn_start_frames_i(32'd0),.cnn_start_crc_i(32'd0),.cnn_start_format_i(8'd1),.cnn_start_accepted_o(),
        .cnn_start_rejected_o(),.cnn_rejection_code_o(),.cnn_frame_valid_i(1'b0),.cnn_frame_ready_o(),
        .cnn_frame_task_id_i(32'd0),.cnn_frame_generation_i(32'd0),.cnn_frame_index_i(32'd0),.cnn_frame_pcm_i(32'd0),
        .cnn_ingress_fault_i(1'b0),.cnn_cancel_valid_i(1'b0),.cnn_cancel_task_id_i(32'd0),.cnn_cancel_generation_i(32'd0),
        .cnn_seal_valid_o(),.cnn_seal_crc_o(),.cnn_accepted_frames_o(),.cnn_committed_frames_o(),.cnn_replayed_frames_o(),
        .cnn_score_valid_o(),.cnn_score_ready_i(1'b1),.cnn_score_note_o(),.cnn_score_index_o(),.cnn_task_id_o(),.cnn_generation_o(),
        .cnn_terminal_valid_o(),.cnn_terminal_ready_i(1'b0),.cnn_terminal_code_o(),.cnn_first_result_valid_o(),
        .cnn_first_result_note_o(),.cnn_first_result_frame_o(),.cnn_fatal_o(cnn_fatal),.cnn_model_status_o(model_status),
        .model_serial_i(1'b1),.model_flash_miso_i(flash_miso),.model_flash_cs_no(flash_cs),
        .model_flash_clk_o(flash_clk),.model_flash_mosi_o(flash_mosi),
        .app_cmd_o(app_cmd),.app_en_o(app_en),.app_wren_o(app_wren),.app_wend_o(app_wend),
        .app_address_o(app_address),.app_data_o(app_data),.app_mask_o(app_mask),
        .app_ready_i(app_ready),.app_write_ready_i(app_write_ready),.app_response_i(app_response || inject_unowned_return),
        .app_response_data_i(app_rdata));
    reg [7:0] image[0:MODEL_BYTES-1];
    string image_path;
    integer flash_bits=0,flash_byte=0,flash_bit=7,flash_commands=0;
    reg [31:0] flash_command=0;
    reg flash_reading=0;
    always @(negedge flash_cs)if(reset_n)begin
        flash_bits=0;flash_byte=0;flash_bit=7;flash_command=0;flash_reading=0;flash_miso=1;flash_commands=flash_commands+1;
    end
    always @(posedge flash_clk)if(!flash_cs)begin
        if(!flash_reading)begin
            flash_command={flash_command[30:0],flash_mosi};flash_bits=flash_bits+1;
            if(flash_bits==32)begin
                if(flash_command!=32'h03600000)$fatal(1,"unexpected model SPI command/address");
                flash_reading=1;
            end
        end else begin
            if(flash_byte>=MODEL_BYTES)$fatal(1,"SPI read exceeds complete real image");
            if(flash_bit==0)begin flash_bit=7;flash_byte=flash_byte+1;end else flash_bit=flash_bit-1;
        end
    end
    always @(negedge flash_clk)if(!flash_cs && flash_reading)
        flash_miso=flash_byte<MODEL_BYTES?image[flash_byte][flash_bit]:1'b1;
    function automatic integer gmap(input [11:0] g);
        case(g)
            12'h100:gmap=0;12'h101:gmap=1;12'h102:gmap=2;12'h103:gmap=3;
            12'h104:gmap=4;12'h105:gmap=5;12'h106:gmap=6;12'h107:gmap=7;
            12'h108:gmap=8;12'h304:gmap=9;12'h301:gmap=10;12'h302:gmap=11;
            12'h303:gmap=12;12'h311:gmap=13;12'h000:gmap=14;12'h300:gmap=15;12'h306:gmap=16;
            default:gmap=-1;
        endcase
    endfunction
    reg [15:0] mem[0:17*524288-1];
    reg pending_read=0;
    integer native_cycle=0,pending_index=0,read_timer=0,reads=0,writes=0,index,lane;
    integer owner5_commits=0,owner6_commits=0,owner8_commits=0;
    assign app_ready=reset_n && memory_reset_n && calibrated && allow_native && !pending_read && !app_response && native_cycle%11!=0;
    assign app_write_ready=allow_native && native_cycle%13>=3;
    always @(posedge mclk)begin
        native_cycle<=native_cycle+1;app_response<=0;
        if(!reset_n || !memory_reset_n)begin pending_read<=0;delay_valid<=0;end
        else begin
            if(media_ready && !expect_fault && native_cycle%257==0)delay_valid<=1;
            else if(delay_valid && delay_ready)delay_valid<=0;
            if(app_en)begin
                if(!app_ready || (app_wren && !app_write_ready))$fatal(1,"native joint acceptance violated");
                index=gmap({1'b0,app_address[28:18]})*524288+{app_address[17:3],4'b0000};
                if(gmap({1'b0,app_address[28:18]})<0)$fatal(1,"invalid actual native address %h",app_address);
                if(native_accept[5])owner5_commits<=owner5_commits+1;
                if(native_accept[6])owner6_commits<=owner6_commits+1;
                if(native_accept[8])begin
                    owner8_commits<=owner8_commits+1;
                    if(app_address<`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE || app_address>`PRJ1_DDR_TASK3_W_RECORDING_LAST_BEAT)
                        $fatal(1,"recording escaped task3 W object");
                end
                if(app_wren)begin
                    writes<=writes+1;
                    for(lane=0;lane<16;lane=lane+1)begin
                        if(!app_mask[2*lane])mem[index+lane][7:0]<=app_data[lane*16+:8];
                        if(!app_mask[2*lane+1])mem[index+lane][15:8]<=app_data[lane*16+8+:8];
                    end
                end else begin reads<=reads+1;pending_read<=1;pending_index<=index;read_timer<=3+native_cycle%7;end
            end
            if(pending_read)begin
                if(read_timer>0)read_timer<=read_timer-1;
                else begin
                    for(lane=0;lane<16;lane=lane+1)app_rdata[lane*16+:16]<=mem[pending_index+lane];
                    app_response<=1;pending_read<=0;
                end
            end
        end
    end
    integer clocks=0,checks=0;
    always @(posedge clk)if(reset_n)begin
        clocks<=clocks+1;
        if(!expect_fault && (media_fault || raw_fault || raw_protocol_fault || cnn_fatal))$fatal(1,"unexpected W-media fault");
        if(clocks>40000000)$fatal(1,"actual W-media model boot deadline status=%0d",model_status);
        if(clocks%10000000==0)begin $display("PROGRESS clocks=%0d model=%0d owner5=%0d owner8=%0d",clocks,model_status,owner5_commits,owner8_commits);$fflush();end
    end
    task automatic ticks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task automatic check(input bit ok,input [767:0] message);
        begin checks=checks+1;if(!ok)$fatal(1,"%0s clock=%0d",message,clocks);end
    endtask
    initial begin
        if(!$value$plusargs("IMAGE=%s",image_path))$fatal(1,"full real IMAGE required");
        $readmemh(image_path,image);
        ticks(10);reset_n=1;memory_reset_n=1;ticks(20);
        check(!raw_start_ready && !cnn_ready && flash_commands==0,"all clients wait for calibration and actual BIST");
        calibrated=1;wait(control_ready);ticks(10);
        check(dut.raw_store.CAPACITY_FRAMES==2880000,"actual raw store binds 60s capacity");
        check(dut.raw_store.BASE_APP==`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE,"actual raw store binds W map");
        wait(raw_start_ready);@(negedge clk);raw_start=1;
        @(negedge clk);raw_start=0;wait(raw_start_done);ticks(3);
        allow_native=0;ticks(10);
        for(integer k=0;k<24;k=k+1)begin
            check(raw_capture_ready,"bounded raw capture available during native stall");
            raw_capture=1;raw_index=32'(k);raw_pcm=32'h72630000+32'(k);ticks(1);raw_capture=0;ticks(1);
        end
        wait(raw_close_ready);raw_close=1;ticks(1);raw_close=0;ticks(100);
        check(raw_accepted==24 && raw_committed==0 && !raw_drained,"local queue admission never seals recording");
        allow_native=1;wait(raw_drained);ticks(5);
        check(raw_committed==24 && owner8_commits==3,"only actual owner8 native BL8 commits finish recording");
        wait(raw_fetch_ready);raw_fetch=1;ticks(1);raw_fetch=0;wait(raw_fetch_done);ticks(3);
        check(raw_cache && !raw_fetch_fault,"owner8 actual DDR readback populates fetch cache");
        for(integer k=0;k<24;k=k+1)begin
            raw_addr=32'(k);ticks(3);check(raw_word==32'h72630000+32'(k),"recording download exact PCM from actual DDR");
        end
        wait(raw_clear_ready);raw_clear=1;ticks(1);raw_clear=0;wait(raw_clear_done);ticks(3);
        check(!raw_cache && raw_committed==0,"same raw store clear invalidates download");
        wait(cnn_ready);ticks(2);
        check(model_status==14 && flash_commands==1 && dut.cnn_task.cnn.u_basic_pitch.model_done,"actual full SPI model boot completes through owner5");
        check(dut.cnn_task.cnn.model_expected_crc==32'haf01a61b && dut.cnn_task.cnn.model_actual_crc==32'haf01a61b,
            "actual model payload and owner5 DDR readback CRC match");
        check(owner5_commits>100000 && owner6_commits>0 && owner8_commits==6,"all real native owners5/6/8 exercised");
        expect_fault=1;wait(!pending_read && !app_response);@(negedge mclk);inject_unowned_return=1;
        @(negedge mclk);inject_unowned_return=0;ticks(30);
        check(media_fault && raw_fault && cnn_fatal && !control_ready,"unowned native return quarantines all clients");
        check(!raw_start_ready && !cnn_ready && !delay_ready,"fault cannot reopen client admission");
        $display("PASS actual_task3_W_media checks=%0d clocks=%0d owner5=%0d owner6=%0d owner8=%0d model_crc=%h",checks,clocks,owner5_commits,owner6_commits,owner8_commits,dut.cnn_task.cnn.model_actual_crc);
        $finish;
    end
endmodule
