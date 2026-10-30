`timescale 1ns/1ps
// Exercise the maintained extraction through the real predecoded APB mailbox.
module tb_workstation_controlled_services;
    reg pclk=0,clk=0,reset_n=0;
    always #10 pclk=~pclk;
    always #6.510416667 clk=~clk;
    reg psel=0,penable=0,pwrite=0;
    reg [11:0] paddr=0;
    reg [31:0] pwdata=0;
    reg [3:0] pstrb=15;
    wire pready,pslverr; wire [31:0] prdata;
    wire command_reset_n,command_valid,command_ready,command_write,response_error;
    wire [11:0] command_address; wire [31:0] command_data,response_data;
    wire [3:0] command_strobes;
    gw138k_apb_cdc bridge(.reset_n,.pclk,.audio_clk(clk),.psel,.penable,.pwrite,
        .paddr,.pwdata,.pstrb,.pready,.pslverr,.prdata,.command_reset_n,
        .command_valid,.command_ready,.command_write,.command_address,.command_data,
        .command_strobes,.response_data,.response_error);
    reg event_ready=1,panel_event_valid=0;
    reg [6:0] panel_command=0;
    reg sample_run=0;
    reg [2:0] sample_divider=0;
    always @(posedge clk or negedge reset_n)
        if(!reset_n)sample_divider<=0;else sample_divider<=sample_divider+1'b1;
    wire sample_valid=sample_run && sample_divider==0;
    wire cpu_event_valid,panel_event_ready,record_enable,record_valid,record_ready;
    wire [17:0] cpu_event;
    wire [95:0] record_packet;
    wire [31:0] record_drop;
    wire score_write,score_start,score_stop,score_running,score_done;
    wire [7:0] score_address; wire [63:0] score_data; wire [8:0] score_length;
    wire [31:0] led_mask,score_frame,snap_status,snap_left,snap_right,snap_sequence;
    gw138k_controlled_services services(.clk,.reset_n(command_reset_n),
        .command_valid,.command_write,.command_address,.command_data,.command_strobes,
        .command_ready,.response_data,.response_error,.cpu_event_valid,.cpu_event,
        .cpu_event_ready(event_ready),.panel_event_valid,.panel_command,.panel_event_ready,
        .control_state(32'h12345678),.control_pitch(32'hcafef00d),
        .control_options(32'h89abcdef),.applied_events(32'd73),.pc_health(32'd5),
        .held_notes(128'h11112222_33334444_55556666_77778888),.sample_valid,
        .active_mask(32'h55aa),.deadline_miss(32'd2),.midi_overflow(32'd3),
        .note_drop(32'd4),.underrun_count(32'd5),.midi_cdc_drop(32'd6),
        .observation_drop(32'd7),.record_drop,.record_enable,.record_valid,.record_packet,
        .record_ready,.snap_status,.snap_left,.snap_right,.snap_sequence,
        .score_write,.score_start,.score_stop,.score_address,.score_data,.score_length,
        .score_running,.score_done,.led_mask,.score_frame,
        .media_stop_request_i(1'b0),.media_stop_hold_i(1'b0),.record_storage_reset_ni(reset_n),.record_seal_request_o(),
        .record_seal_done_i(1'b0),.record_seal_failed_i(1'b0),.record_start_ready_i(1'b1),
        .record_object_id_i(32'd0),.record_object_rate_i(32'd0),.record_object_epoch_i(32'd0),.record_object_frames_i(32'd0),
        .record_object_status_i(6'd0),.record_object_failure_i(3'd0),.record_seal_status_i(3'd0),.record_seal_count_i(32'd0),
        .score_cancelled_i(1'b0),.score_failed_i(1'b0),.media_stop_done_o(),.media_stop_failed_o());
    audio_capture_fifo #(.ADDRESS_BITS(2)) recorder(.clk_i(clk),.rst_ni(command_reset_n),
        .enable_i(record_enable),.sample_valid_i(sample_valid),
        .left_i(32'sh12340000),.right_i(32'sh89ab0000),.valid_o(record_valid),
        .ready_i(record_ready),.packet_o(record_packet),.drop_count_o(record_drop));
    score_led_player player(.clk_i(clk),.rst_ni(command_reset_n),.sample_ce_i(sample_valid),
        .write_i(score_write),.write_address_i(score_address),.write_data_i(score_data),
        .start_i(score_start),.stop_i(score_stop),.length_i(score_length),
        .running_o(score_running),.done_o(score_done),.leds_o(led_mask),.frame_o(score_frame));
    integer transactions=0,commits=0,event_commits=0,cue_commits=0,sample_frames=0;
    integer last_wait=0;
    always @(posedge clk)if(command_reset_n)begin
        if(command_valid && command_ready)commits<=commits+1;
        if(cpu_event_valid && event_ready)event_commits<=event_commits+1;
        if(score_write)cue_commits<=cue_commits+1;
        if(sample_valid)sample_frames<=sample_frames+1;
    end
    task transact(input bit wr,input [11:0] addr,input [31:0] data,
                  input [3:0] strobes,input bit expect_error,output [31:0] value);
        integer cycles;
        begin
            @(negedge pclk);paddr=addr;pwdata=data;pwrite=wr;pstrb=strobes;psel=1;penable=0;
            @(negedge pclk);penable=1;cycles=0;
            @(posedge pclk);
            while(!pready)begin
                @(posedge pclk);cycles=cycles+1;
                if(cycles>1000)$fatal(1,"APB timeout addr=%h",addr);
            end
            if(pslverr!==expect_error)$fatal(1,"APB error addr=%h write=%b got=%b expected=%b",addr,wr,pslverr,expect_error);
            value=prdata;last_wait=cycles;
            @(negedge pclk);psel=0;penable=0;
            repeat(2)@(negedge pclk);transactions=transactions+1;
            if(commits!=transactions)$fatal(1,"APB duplicate/lost commit got=%0d expected=%0d",commits,transactions);
        end
    endtask
    reg [31:0] value,saved_sequence,saved_samples;
    task write_reg(input [11:0] addr,input [31:0] data,input bit error);
        begin transact(1,addr,data,15,error,value);end
    endtask
    task read_reg(input [11:0] addr,input [31:0] expected,input bit error);
        begin
            transact(0,addr,0,15,error,value);
            if(!error && value!==expected)$fatal(1,"APB data addr=%h got=%h expected=%h",addr,value,expected);
        end
    endtask
    task panel(input [6:0] command);
        begin
            @(negedge clk);panel_command=command;panel_event_valid=1;
            @(posedge clk);if(!panel_event_ready)$fatal(1,"panel backpressure");
            @(negedge clk);panel_event_valid=0;repeat(2)@(negedge clk);
        end
    endtask
    initial begin
        repeat(5)@(negedge pclk);reset_n=1;repeat(6)@(negedge pclk);
        read_reg(12'h000,32'h41313338,0);read_reg(12'h004,32'h00010000,0);
        read_reg(12'h008,63,0);read_reg(12'h184,32'h12345678,0);
        read_reg(12'h188,32'hcafef00d,0);read_reg(12'h18c,32'h89abcdef,0);
        read_reg(12'h190,32'h77778888,0);read_reg(12'h194,32'h55556666,0);
        read_reg(12'h198,32'h33334444,0);read_reg(12'h19c,32'h11112222,0);
        read_reg(12'h1a0,73,0);read_reg(12'h1a4,5,0);
        read_reg(12'h020,0,1);read_reg(12'h014,0,0);
        // Invalid writes are acknowledged with an error and have no side effect.
        write_reg(12'h081,1,1);write_reg(12'h080,2,1);
        transact(1,12'h080,1,4'b0011,1,value);read_reg(12'h080,0,0);
        write_reg(12'h180,32'h00040000,1); // bits outside the 18-bit event
        write_reg(12'h180,{14'd0,4'd7,14'd0},1);
        write_reg(12'h180,{14'd0,4'd1,7'd60,7'd0},1);
        write_reg(12'h180,{14'd0,4'd6,7'd2,7'd0},1);
        if(event_commits)$fatal(1,"malformed event escaped");
        event_ready=0;
        fork
            begin
                write_reg(12'h180,{14'd0,4'd1,7'd60,7'd100},0);
                if(last_wait<25)$fatal(1,"CPU event ignored backpressure");
            end
            begin
                repeat(100)@(negedge clk);
                if(!cpu_event_valid || cpu_event!={4'd1,7'd60,7'd100})$fatal(1,"stalled CPU event not held");
                if(command_ready)$fatal(1,"legal event completed early");
                event_ready=1;
            end
        join
        if(event_commits!=1)$fatal(1,"CPU event not committed once");
        // A snapshot remains atomic while real samples continue.
        sample_run=1;repeat(80)@(negedge clk);write_reg(12'h010,1,0);
        read_reg(12'h020,32'h55aa,0);
        transact(0,12'h024,0,15,0,saved_samples);
        repeat(80)@(negedge clk);read_reg(12'h024,saved_samples,0);
        read_reg(12'h028,2,0);read_reg(12'h02c,3,0);read_reg(12'h030,4,0);
        read_reg(12'h034,5,0);read_reg(12'h038,6,0);read_reg(12'h03c,7,0);
        // Real bounded capture overflows while sample scheduling continues.
        write_reg(12'h080,1,0);repeat(120)@(negedge clk);write_reg(12'h080,0,0);
        if(record_drop==0 || sample_frames<30)$fatal(1,"recorder overflow did not preserve sample progress");
        read_reg(12'h084,2,0);write_reg(12'h088,1,0);
        read_reg(12'h084,3,0);transact(0,12'h08c,0,15,0,saved_sequence);
        read_reg(12'h090,32'h12340000,0);read_reg(12'h094,32'h89ab0000,0);
        write_reg(12'h088,1,1);read_reg(12'h08c,saved_sequence,0);
        write_reg(12'h098,1,0);read_reg(12'h08c,0,1);
        repeat(3)begin write_reg(12'h088,1,0);write_reg(12'h098,1,0);end
        read_reg(12'h084,0,0);write_reg(12'h088,1,1);write_reg(12'h098,1,1);
        panel(1);if(!record_enable)$fatal(1,"record panel start failed");
        panel(1);if(record_enable)$fatal(1,"record panel stop failed");
        sample_run=0;
        write_reg(12'h1a8,32'hdeadbeef,0);write_reg(12'h1ac,32'h12345678,0);
        write_reg(12'h1b0,32'h87654321,0);write_reg(12'h1b4,32'haabbccdd,0);
        read_reg(12'h1a8,32'hdeadbeef,0);read_reg(12'h1ac,32'h12345678,0);
        read_reg(12'h1b0,32'h87654321,0);read_reg(12'h1b4,32'haabbccdd,0);
        // Upload all 256 actual cue-RAM entries, with sequential/monotonic guards.
        write_reg(12'h120,1,0);write_reg(12'h114,1,1);
        for(integer cue=0;cue<256;cue=cue+1)begin
            write_reg(12'h100,32'(cue),0);write_reg(12'h104,32'((cue+1)*64),0);
            write_reg(12'h108,cue==255 ? 0 : 32'(cue+1),0);write_reg(12'h10c,1,0);
            if(cue==5)begin
                write_reg(12'h100,6,0);write_reg(12'h104,1,0);write_reg(12'h10c,1,1);
            end
        end
        if(cue_commits!=256)$fatal(1,"cue write count=%0d",cue_commits);
        read_reg(12'h12c,256,0);write_reg(12'h10c,1,1);
        write_reg(12'h110,257,1);write_reg(12'h110,256,0);write_reg(12'h114,1,0);
        if(!score_running)$fatal(1,"score did not start");
        write_reg(12'h100,0,1);write_reg(12'h104,0,1);write_reg(12'h108,0,1);
        write_reg(12'h10c,1,1);write_reg(12'h110,1,1);write_reg(12'h120,1,1);
        panel(0);if(score_running || led_mask)$fatal(1,"score panel stop failed");
        panel(0);if(!score_running)$fatal(1,"score panel restart failed");
        sample_run=1;wait(led_mask==1);wait(score_done);repeat(3)@(negedge clk);
        if(score_running || led_mask || score_frame!=16384)$fatal(1,"actual score timebase/completion mismatch frame=%0d",score_frame);
        read_reg(12'h11c,2,0);write_reg(12'h118,1,0);write_reg(12'h120,1,0);
        read_reg(12'h12c,0,0);
        if(event_commits!=1)$fatal(1,"score/record created a note event");
        $display("PASS controlled_services: transactions=%0d commits=%0d cpu_events=%0d cue_writes=%0d sample_frames=%0d record_drops=%0d score_frames=%0d",transactions,commits,event_commits,cue_commits,sample_frames,record_drop,score_frame);
        $finish;
    end
    initial begin #30000000;$fatal(1,"global timeout");end
endmodule
