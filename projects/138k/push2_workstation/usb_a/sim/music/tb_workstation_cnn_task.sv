`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
module tb_workstation_cnn_task #(
    parameter integer CLIP_FRAMES=4096,
    parameter integer MAX_CYCLES=120000000,
    parameter integer IO_TIMEOUT_CYCLES=4096,
    parameter [31:0] TASK_TIMEOUT_CYCLES=32'd400000000,
    parameter bit REQUIRE_SELECTED_W=0,
    parameter bit CNN_USE_DDR_SIGNAL=1,
    parameter bit CNN_USE_DDR_CQT_COEFF=1
);
    localparam integer MODEL_BYTES=104510;
    reg clk=0,mclk=0,reset_n=0,memory_reset_n=0,calibrated=0;
    always #10 clk=~clk;
    always #7 mclk=~mclk;
    reg start=0,frame_valid=0,cancel=0,ingress_fault=0,terminal_ready=0,score_ready=1;
    reg [31:0] start_id=0,start_generation=0,start_frames=0,start_crc=0;
    reg [7:0] format=1;
    reg [31:0] frame_id=0,frame_generation=0,frame_index=0,frame_pcm=0,cancel_id=0,cancel_generation=0;
    wire start_ready,start_accepted,start_rejected,frame_ready,seal,terminal,fatal;
    wire [3:0] rejection,terminal_code,model_status;
    wire [31:0] id,generation,sealed_crc,accepted,committed,replayed,score_index;
    wire score_valid,first_valid;
    wire [6:0] score_note,first_note;
    wire [15:0] first_frame;
    wire flash_cs,flash_clk,flash_mosi;
    reg flash_miso=1;
    wire media_reset,media_ready,media_fault,req,wr,local_ready,response;
    wire [28:0] address;
    wire [255:0] wdata,rdata;
    wire [31:0] mask;
    wire [8:0] native_accept;
    wire [2:0] app_cmd;
    wire app_en,app_wren,app_wend;
    wire [28:0] app_address;
    wire [255:0] app_data;
    wire [31:0] app_mask;
    reg app_response=0;
    reg [255:0] app_rdata=0;
    wire app_ready,app_write_ready;
    reg allow_native=1,allow_response=1,corrupt_stage=0,inject_unowned_return=0,expect_fatal=0;
    reg delay_valid=0,recording_valid=0;
    wire delay_ready,recording_ready;
    workstation_cnn_task_service #(.IO_TIMEOUT_CYCLES(IO_TIMEOUT_CYCLES),.TASK_TIMEOUT_CYCLES(TASK_TIMEOUT_CYCLES)
`ifdef TB_CONFIGURABLE_CNN_STORAGE
        ,.CNN_USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL),.CNN_USE_DDR_CQT_COEFF(CNN_USE_DDR_CQT_COEFF)
`endif
    ) dut(
        .clk_i(clk),.reset_ni(reset_n),.memory_clk_i(mclk),.memory_reset_ni(media_reset),
        .backend_ready_i(media_ready),.transport_fault_i(media_fault),
        .start_valid_i(start),.start_ready_o(start_ready),.start_task_id_i(start_id),.start_generation_i(start_generation),
        .start_frames_i(start_frames),.start_crc_i(start_crc),.start_format_i(format),
        .start_accepted_o(start_accepted),.start_rejected_o(start_rejected),.rejection_code_o(rejection),
        .frame_valid_i(frame_valid),.frame_ready_o(frame_ready),.frame_task_id_i(frame_id),
        .frame_generation_i(frame_generation),.frame_index_i(frame_index),.frame_pcm_i(frame_pcm),.ingress_fault_i(ingress_fault),
        .cancel_valid_i(cancel),.cancel_task_id_i(cancel_id),.cancel_generation_i(cancel_generation),
        .seal_valid_o(seal),.seal_crc_o(sealed_crc),.accepted_frames_o(accepted),.committed_frames_o(committed),
        .replayed_frames_o(replayed),.score_valid_o(score_valid),.score_ready_i(score_ready),.score_note_o(score_note),
        .score_index_o(score_index),.task_id_o(id),.generation_o(generation),
        .terminal_valid_o(terminal),.terminal_ready_i(terminal_ready),.terminal_code_o(terminal_code),
        .first_result_valid_o(first_valid),.first_result_note_o(first_note),.first_result_frame_o(first_frame),.fatal_o(fatal),
        .model_status_o(model_status),.model_serial_i(1'b1),.flash_miso_i(flash_miso),
        .flash_cs_n_o(flash_cs),.flash_clk_o(flash_clk),.flash_mosi_o(flash_mosi),
        .memory_valid_o(req),.memory_write_o(wr),.memory_address_o(address),.memory_data_o(wdata),.memory_mask_o(mask),
        .memory_slot_ready_i(local_ready),.memory_native_accept_i(native_accept[5]),
        .memory_response_i(response),.memory_read_data_i(rdata));
    workstation_media_memory #(.BIST_BURSTS(4)) memory_boundary(
        .reset_ni(reset_n),.clk_50m_i(clk),.memory_clk_i(mclk),.memory_reset_ni(memory_reset_n),
        .memory_calibrated_i(calibrated),.memory_pll_locked_i(calibrated),
        .client_reset_no(media_reset),.client_ready_o(media_ready),
        .music_valid_i(req),.music_write_i(wr),.music_address_i(address),.music_data_i(wdata),.music_mask_i(mask),
        .music_ready_o(local_ready),.music_response_o(response),
        .delay_valid_i(delay_valid),.delay_write_i(1'b1),.delay_address_i(`PRJ1_DDR_DELAY_RING_APP_BASE),
        .delay_data_i(256'hd311aabb),.delay_ready_o(delay_ready),.delay_response_o(),
        .recording_valid_i(recording_valid),.recording_write_i(1'b1),.recording_address_i(`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE),
        .recording_data_i(256'h8c991122),.recording_mask_i(32'd0),.recording_ready_o(recording_ready),.recording_response_o(),
        .app_cmd_o(app_cmd),.app_en_o(app_en),.app_wren_o(app_wren),.app_wend_o(app_wend),
        .app_address_o(app_address),.app_data_o(app_data),.app_mask_o(app_mask),
        .app_ready_i(app_ready),.app_write_ready_i(app_write_ready),.app_response_i(app_response || inject_unowned_return),
        .app_response_data_i(app_rdata),.response_data_o(rdata),.memory_flags_o(),
        .slot_accept_o(),.core_accept_o(),.native_accept_o(native_accept),.transport_fault_o(media_fault));

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
            if(flash_byte>=MODEL_BYTES)$fatal(1,"SPI read exceeds complete real model image");
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
    reg pending_read=0,pending_stage=0;
    integer native_cycle=0,pending_index=0,read_timer=0,reads=0,writes=0;
    integer owner5_commits=0,delay_commits=0,recording_commits=0,stage_writes=0,stage_reads=0;
    integer owner5_reads=0,owner5_writes=0;
    integer index,lane;
    assign app_ready=reset_n && memory_reset_n && calibrated && allow_native && !pending_read && !app_response && native_cycle%11!=0;
    assign app_write_ready=allow_native && native_cycle%13>=3;
    always @(posedge mclk)begin
        native_cycle<=native_cycle+1;app_response<=0;
        if(!reset_n || !memory_reset_n)begin pending_read<=0;delay_valid<=0;recording_valid<=0;end
        else begin
            if(media_ready && native_cycle%257==0)delay_valid<=1;
            else if(delay_valid && delay_ready)delay_valid<=0;
            if(media_ready && native_cycle%521==0)recording_valid<=1;
            else if(recording_valid && recording_ready)recording_valid<=0;
            if(dut.cnn_ddr_ready && !native_accept[5])$fatal(1,"CNN ack was only a local-slot admission");
            if(app_en)begin
                if(!app_ready || (app_wren && !app_write_ready))$fatal(1,"native joint acceptance violated");
                index=gmap({1'b0,app_address[28:18]})*524288+{app_address[17:3],4'b0000};
                if(gmap({1'b0,app_address[28:18]})<0)$fatal(1,"invalid actual native address %h",app_address);
                if(native_accept[5])begin
                    owner5_commits<=owner5_commits+1;
                    if(app_wren)owner5_writes<=owner5_writes+1;
                    else owner5_reads<=owner5_reads+1;
                end
                if(native_accept[6])delay_commits<=delay_commits+1;
                if(native_accept[8])recording_commits<=recording_commits+1;
                if(app_wren)begin
                    writes<=writes+1;
                    if(gmap({1'b0,app_address[28:18]})==13)stage_writes<=stage_writes+1;
                    for(lane=0;lane<16;lane=lane+1)begin
                        if(!app_mask[2*lane])mem[index+lane][7:0]<=app_data[lane*16+:8];
                        if(!app_mask[2*lane+1])mem[index+lane][15:8]<=app_data[lane*16+8+:8];
                    end
                end else begin
                    reads<=reads+1;pending_read<=1;pending_index<=index;read_timer<=3+native_cycle%7;
                    pending_stage<=gmap({1'b0,app_address[28:18]})==13;
                    if(gmap({1'b0,app_address[28:18]})==13)stage_reads<=stage_reads+1;
                end
            end
            if(pending_read && allow_response)begin
                if(read_timer>0)read_timer<=read_timer-1;
                else begin
                    for(lane=0;lane<16;lane=lane+1)app_rdata[lane*16+:16]<=mem[pending_index+lane]^((corrupt_stage && pending_stage && lane==0)?16'd1:16'd0);
                    app_response<=1;pending_read<=0;
                end
            end
        end
    end
    reg [31:0] pcm[0:CLIP_FRAMES-1];
    reg [15:0] lfsr=16'hbeef;
    function automatic [15:0] lfsr_next(input [15:0] value);
        lfsr_next={value[14:0],value[15]^value[12]^value[10]^value[8]};
    endfunction
    function automatic [31:0] crc_byte(input [31:0] c,input [7:0] b);
        reg [31:0] x;integer n;begin x=c^{24'd0,b};for(n=0;n<8;n=n+1)x=x[0]?(x>>1)^32'hedb88320:x>>1;crc_byte=x;end
    endfunction
    function automatic [31:0] clip_crc(input integer frames);
        reg [31:0] c;integer k,j;begin c=32'hffffffff;for(k=0;k<frames;k=k+1)for(j=0;j<4;j=j+1)c=crc_byte(c,pcm[k][j*8+:8]);clip_crc=~c;end
    endfunction
    integer clocks=0,checks=0,notes=0,layer_writes[0:5],analysis_count=0;
    integer reference_writes[0:5],reference_notes=0;
    integer launch_clock=0,first_score_clock=0;
    integer cnn_reads=0,cnn_writes=0;
    integer launch_cnn_reads=0,launch_cnn_writes=0,launch_owner_reads=0,launch_owner_writes=0;
    integer launch_stage_reads=0,launch_stage_writes=0;
    reg [191:0] reference_hashes;
    reg [6:0] observed_notes[0:511],reference_sequence[0:511];
    reg capture_layers=0;
    task automatic check(input bit ok,input [767:0] message);
        begin checks=checks+1;if(!ok)$fatal(1,"%0s clock=%0d task=%0d state=%0d",message,clocks,id,dut.state);end
    endtask
    always @(posedge clk)if(reset_n)begin
        clocks<=clocks+1;
        if(dut.cnn.bp_mem_req && dut.cnn.bp_mem_ready)begin
            if(dut.cnn.bp_mem_write)cnn_writes<=cnn_writes+1;
            else cnn_reads<=cnn_reads+1;
        end
        if(!expect_fatal && (fatal || media_fault))$fatal(1,"unexpected actual transport/restart fault task=%0d state=%0d model=%0d broker=%b broker_state=%0d broker_timer=%0d media=%b restart=%b restart_code=%0d stage=%b allow_response=%b pending=%b",id,dut.state,model_status,dut.broker_fault,dut.broker.state,dut.broker.timer,media_fault,dut.restart_fault,dut.restart_failure,dut.stage_inflight,allow_response,pending_read);
        if(clocks%10000000==0)begin
            $display("PROGRESS clocks=%0d task=%0d state=%0d cnn=%0d replayed=%0d reads=%0d writes=%0d front_started=%b full=%b drained=%b score=%b notes=%0d",clocks,id,dut.state,dut.cnn.u_basic_pitch.state,replayed,reads,writes,dut.cnn.u_basic_pitch.front_window_started,dut.cnn.u_basic_pitch.front_win_full,dut.cnn.u_basic_pitch.front_drained,score_valid,notes);$fflush();
        end
        if(clocks>MAX_CYCLES)$fatal(1,"task fixture deadline model=%0d state=%0d cnn=%0d frontend_n=%0d base=%0d busy=%b",model_status,dut.state,dut.cnn.u_basic_pitch.state,dut.cnn.u_basic_pitch.u_frontend.n_recv,dut.cnn.u_basic_pitch.u_frontend.base_val,dut.cnn.u_basic_pitch.u_frontend.busy);
        if(cancel && cancel_id==id && cancel_generation==generation && score_valid)$fatal(1,"old score escaped immediate cancellation");
        if(score_valid && score_ready)begin
            if(notes==0)first_score_clock=clocks;
            check(id==5 || id==7,"score belongs to current successful task");
            check(score_index==32'(notes),"score sequence ordinal is exact");
            $display("SCORE task=%0d index=%0d note=%0d",id,score_index,score_note);
            observed_notes[notes]=score_note;notes=notes+1;
        end
        if(capture_layers)begin
            if(dut.cnn.u_basic_pitch.contour_act_valid)layer_writes[0]=layer_writes[0]+1;
            if(dut.cnn.u_basic_pitch.reduce_act_valid)layer_writes[1]=layer_writes[1]+1;
            if(dut.cnn.u_basic_pitch.notes_act_valid)layer_writes[2]=layer_writes[2]+1;
            if(dut.cnn.u_basic_pitch.note_out_act_valid)layer_writes[3]=layer_writes[3]+1;
            if(dut.cnn.u_basic_pitch.onset_act_valid)layer_writes[4]=layer_writes[4]+1;
            if(dut.cnn.u_basic_pitch.onset_out_act_valid)layer_writes[5]=layer_writes[5]+1;
            if(dut.cnn_analysis_done)begin
                $display("TASK_METRICS task=%0d clip_frames=%0d launch_clock=%0d first_score_clock=%0d complete_clock=%0d task_cycles=%0d hashes=%h writes0=%0d writes1=%0d writes2=%0d writes3=%0d writes4=%0d writes5=%0d notes=%0d",id,CLIP_FRAMES,launch_clock,first_score_clock,clocks,clocks-launch_clock,dut.cnn.layer_hashes,layer_writes[0],layer_writes[1],layer_writes[2],layer_writes[3],layer_writes[4],layer_writes[5],notes);$fflush();
                $display("TASK_TRAFFIC task=%0d cnn_ddr16_reads=%0d cnn_ddr16_writes=%0d owner5_native_reads=%0d owner5_native_writes=%0d staging_native_reads=%0d staging_native_writes=%0d",id,cnn_reads-launch_cnn_reads,cnn_writes-launch_cnn_writes,owner5_reads-launch_owner_reads,owner5_writes-launch_owner_writes,stage_reads-launch_stage_reads,stage_writes-launch_stage_writes);$fflush();
                analysis_count=analysis_count+1;
                if(id==5)begin
                    reference_hashes=dut.cnn.layer_hashes;reference_notes=notes;
                    for(integer k=0;k<6;k=k+1)reference_writes[k]=layer_writes[k];
                    for(integer k=0;k<notes;k=k+1)reference_sequence[k]=observed_notes[k];
                end else if(id==7)begin
                    check(dut.cnn.layer_hashes===reference_hashes,"post-cancel real six-layer hashes match fresh task");
                    check(notes==reference_notes,"post-cancel real Viterbi score length matches");
                    for(integer k=0;k<6;k=k+1)check(layer_writes[k]==reference_writes[k] && layer_writes[k]>0,"every real layer write count matches");
                    for(integer k=0;k<notes;k=k+1)check(observed_notes[k]==reference_sequence[k],"post-cancel real score sequence matches");
                end
            end
        end
    end
    task automatic ticks(input integer count);begin repeat(count)@(negedge clk);end endtask
    task automatic launch(input integer task_number,input integer frames,input [31:0] crc_value);
        begin wait(start_ready);@(negedge clk);start_id=32'(task_number);start_generation=32'(task_number);start_frames=32'(frames);start_crc=crc_value;start=1;
            @(negedge clk);check(start_accepted,"valid bounded descriptor accepted");start=0;
            wait(frame_ready);launch_clock=clocks;first_score_clock=0;notes=0;for(integer k=0;k<6;k=k+1)layer_writes[k]=0;
            launch_cnn_reads=cnn_reads;launch_cnn_writes=cnn_writes;
            launch_owner_reads=owner5_reads;launch_owner_writes=owner5_writes;
            launch_stage_reads=stage_reads;launch_stage_writes=stage_writes;
        end
    endtask
    task automatic feed(input integer task_number,input integer frames);
        begin for(integer k=0;k<frames;k=k+1)begin
            @(negedge clk);frame_id=32'(task_number);frame_generation=32'(task_number);frame_index=32'(k);frame_pcm=pcm[k];frame_valid=1;
            do @(posedge clk);while(!frame_ready);
            @(negedge clk);frame_valid=0;
        end end
    endtask
    task automatic cancel_task(input integer task_number);
        begin @(negedge clk);cancel_id=32'(task_number);cancel_generation=32'(task_number);cancel=1;#1;
            check(!score_valid && !frame_ready,"cancel immediately fences task I/O");@(negedge clk);cancel=0;
        end
    endtask
    task automatic finish(input integer code);
        begin wait(terminal);check(terminal_code==4'(code) && !fatal,"terminal code and healthy transport");
            if(code==0 || code==1)check(!dut.stage_inflight && !dut.restart_pending,"terminal follows actual stage/CNN drain");
            @(negedge clk);terminal_ready=1;@(negedge clk);terminal_ready=0;ticks(4);
        end
    endtask
    initial begin
        if(REQUIRE_SELECTED_W)begin
            check(dut.cnn.u_basic_pitch.WIN_LEN==44100 && dut.cnn.u_basic_pitch.FRAME_LIMIT==8 &&
                  dut.cnn.u_basic_pitch.CQT_HOP_NUMERATOR==22050 && dut.cnn.u_basic_pitch.CQT_HOP_DENOMINATOR==4 &&
                  dut.cnn.u_basic_pitch.FEATURE_TILE_COLS==16 && dut.cnn.u_basic_pitch.COARSE_GUIDANCE==1,
                  "actual selected W4Hz dimensions, tile and guidance are elaborated");
            check(CLIP_FRAMES==96000 && IO_TIMEOUT_CYCLES==50000000 && TASK_TIMEOUT_CYCLES==32'd3600000000,
                  "selected W task budgets and maximum clip capacity are unchanged");
            check(dut.cnn.u_basic_pitch.USE_DDR_SIGNAL==CNN_USE_DDR_SIGNAL &&
                  dut.cnn.u_basic_pitch.USE_DDR_CQT_COEFF==CNN_USE_DDR_CQT_COEFF &&
                  dut.cnn.u_basic_pitch.USE_DDR_FRONT_COEFF==1 && dut.cnn.u_basic_pitch.USE_ALL_DDR==0 &&
                  dut.cnn.u_basic_pitch.USE_EXTERNAL_STATE && dut.cnn.u_basic_pitch.USE_EXTERNAL_PLANE &&
                  dut.cnn.u_basic_pitch.USE_EXTERNAL_WEIGHTS && dut.cnn.u_basic_pitch.USE_EXTERNAL_FEATURES,
                  "actual storage selection retains front coefficients and external graph stores");
        end
        if(!$value$plusargs("IMAGE=%s",image_path))$fatal(1,"full real IMAGE required");
        $readmemh(image_path,image);
        for(integer k=0;k<CLIP_FRAMES;k=k+1)begin
            pcm[k]={lfsr_next(lfsr_next(lfsr)),lfsr_next(lfsr)};lfsr=lfsr_next(lfsr_next(lfsr));
        end
        for(integer k=0;k<6;k=k+1)layer_writes[k]=0;
        ticks(10);reset_n=1;memory_reset_n=1;ticks(20);
        check(!start_ready && flash_commands==0,"boot waits for actual memory BIST/calibration");calibrated=1;
        wait(start_ready);
        check(model_status==14 && flash_commands==1 && dut.cnn.u_basic_pitch.model_done,"actual full SPI model boot completes");
        check(dut.cnn.model_expected_crc==32'haf01a61b && dut.cnn.model_actual_crc==32'haf01a61b,"actual payload and DDR readback CRC validated");
        $display("MODEL real_spi_crc=%h words=52239 native_reads=%0d native_writes=%0d",dut.cnn.model_actual_crc,reads,writes);$fflush();
        @(negedge clk);start=1;start_id=99;start_generation=99;start_frames=96001;start_crc=0;
        @(negedge clk);check(start_rejected && !start_accepted,"oversize descriptor rejected before allocation");start=0;
        launch(1,13,clip_crc(13));allow_native=0;feed(1,8);ticks(40);
        check(committed==0 && dut.stage_inflight,"local slot acceptance is not staged write commitment");
        cancel_task(1);ticks(64);check(!terminal,"cancel waits for accepted staged native write");allow_native=1;finish(1);
        $display("CASE staged_write_cancel PASS");$fflush();
        wait(start_ready);@(negedge clk);start=1;start_id=99;start_generation=1;start_frames=13;start_crc=clip_crc(13);
        @(negedge clk);check(start_rejected && !start_accepted && generation==1,"old generation descriptor cannot allocate new task");start=0;
        launch(2,13,clip_crc(13)^32'd1);feed(2,13);finish(4);check(replayed==0,"input CRC failure never feeds CNN");
        $display("CASE input_crc_reject PASS");$fflush();
        launch(3,13,clip_crc(13));corrupt_stage=1;feed(3,13);finish(5);corrupt_stage=0;
        check(replayed==0,"DDR readback CRC failure never feeds CNN");$display("CASE ddr_crc_reject PASS");$fflush();
        launch(4,13,clip_crc(13));allow_response=0;feed(4,13);wait(pending_read && pending_stage);
        cancel_task(4);ticks(64);check(!terminal,"cancel waits for real outstanding staging read return");allow_response=1;finish(1);
        $display("CASE delayed_staging_return_cancel PASS");$fflush();
        if(!$test$plusargs("CANCEL_ONLY"))begin
        launch(5,CLIP_FRAMES,clip_crc(CLIP_FRAMES));capture_layers=1;score_ready=0;feed(5,CLIP_FRAMES);
        wait(score_valid);begin reg [6:0] held_note;held_note=score_note;ticks(16);check(score_valid && score_note==held_note && id==5,"bounded score output holds under backpressure");end
        score_ready=1;finish(0);capture_layers=0;
        check(replayed==CLIP_FRAMES && accepted==CLIP_FRAMES && committed==CLIP_FRAMES && sealed_crc==clip_crc(CLIP_FRAMES),"actual staged/sealed/replayed frame identity");
        check(reference_notes>0 && first_valid,"real CNN/Viterbi produces guidance and first result");
        $display("INFERENCE fresh hashes=%h notes=%0d first=%0d",reference_hashes,reference_notes,first_note);$fflush();
        end
        launch(6,CLIP_FRAMES,clip_crc(CLIP_FRAMES));feed(6,CLIP_FRAMES);
        wait(replayed>0);wait(pending_read && !pending_stage);@(negedge mclk);allow_response=0;
        cancel_task(6);ticks(64);check(!terminal,"CNN cancellation waits for actual native read");allow_response=1;finish(1);
        $display("CASE delayed_cnn_return_cancel PASS");$fflush();
        if($test$plusargs("CANCEL_ONLY"))begin $display("PASS cancel_probe");$finish;end
        launch(7,CLIP_FRAMES,clip_crc(CLIP_FRAMES));capture_layers=1;
        @(negedge clk);cancel_id=6;cancel_generation=6;cancel=1;ticks(2);cancel=0;
        check(frame_ready && id==7 && generation==7,"late old cancellation cannot cancel new generation");
        feed(7,CLIP_FRAMES);finish(0);capture_layers=0;
        check(analysis_count==2 && delay_commits>0 && recording_commits>0,"two real inference completions share memory with owners6/8");
        launch(8,13,clip_crc(13));@(negedge clk);frame_id=7;frame_generation=7;frame_index=0;frame_pcm=pcm[0];frame_valid=1;
        @(negedge clk);frame_valid=0;finish(2);
        check(accepted==0 && committed==0 && replayed==0,"old ingress identity cannot contaminate next clip");
        $display("CASE stale_ingress_reject PASS");$fflush();
        launch(9,13,clip_crc(13));@(negedge mclk);expect_fatal=1;inject_unowned_return=1;
        @(negedge mclk);inject_unowned_return=0;wait(terminal);
        check(fatal && media_fault && terminal_code==15,"actual unowned native return quarantines active task");
        @(negedge clk);terminal_ready=1;@(negedge clk);terminal_ready=0;ticks(16);
        check(!terminal && !start_ready && !frame_ready && !score_valid,"fault terminal is consumed once without recovering native owner");
        $display("CASE unowned_native_return_quarantine PASS");$fflush();
        $display("PASS actual_W_CNN_task checks=%0d clocks=%0d model_commands=%0d reads=%0d writes=%0d owner5_native=%0d owner6_native=%0d owner8_native=%0d stage_writes=%0d stage_reads=%0d notes=%0d",checks,clocks,flash_commands,reads,writes,owner5_commits,delay_commits,recording_commits,stage_writes,stage_reads,notes);$finish;
    end
endmodule
