`timescale 1ns/1ps
module tb_interaction_latency;
    reg usb_clk=0,clk_50m=0,audio_clk=0,reset_n=0,pc_rx=1,g1_rx=1;
    always #(1000.0/96)usb_clk=~usb_clk;
    always #10 clk_50m=~clk_50m;
    always #(1000.0/153.6)audio_clk=~audio_clk;
    reg select=0,write=0;reg [7:0]address=0;reg [31:0]wdata=0;
    wire ready;wire [31:0]rdata;
    wire push_valid,push_ready;wire [17:0]push_event;
    wire [447:0]performance;
    push2_usb_a_control push(.clk(usb_clk),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(reset_n),
        .feedback_clk(audio_clk),.feedback_reset_n(reset_n),.performance_words(performance),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),
        .select(select),.write(write),.address(address),.wdata(wdata),.ready(ready),.rdata(rdata),
        .audio_valid(push_valid),.audio_ready(push_ready),.audio_event(push_event),.telemetry());
    wire sample_ce,sample_valid,display_valid;
    wire signed [31:0]left,right;
    wire [31:0]display_pcm,active,deadline,overflow,drops,underruns,cdc_drop,observation_drop;
    gw138k_usb_controlled_audio dut(.usb_event_valid(push_valid),.usb_event_data(push_event),.usb_event_ready(push_ready),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(reset_n),.midi_rx_i(g1_rx),.pc_uart_rx_i(pc_rx),
        .performance_words_o(performance),.pclk(1'b0),.preset_n(reset_n),.psel(1'b0),.penable(1'b0),
        .pwrite(1'b0),.paddr(12'd0),.pwdata(32'd0),.pstrb(4'd0),
        .sample_ce_o(sample_ce),.sample_valid_o(sample_valid),.audio_left_o(left),.audio_right_o(right),
        .display_valid_o(display_valid),.display_pcm_o(display_pcm),.active_mask_o(active),
        .deadline_miss_o(deadline),.midi_overflow_o(overflow),.note_drop_o(drops),
        .underrun_count_o(underruns),.midi_cdc_drop_o(cdc_drop),.observation_drop_o(observation_drop));

    integer source,offset_ns;
    realtime source_start,source_complete,core_accept_time,pcm32_time,dac16_time;
    reg armed=0,core_seen=0,pcm_seen=0,dac_seen=0;
    always @(posedge audio_clk) if(reset_n && armed) begin
        if(!core_seen && dut.u_audio.u_workstation.core_event_valid &&
           dut.u_audio.u_workstation.core_event_ready && dut.u_audio.u_workstation.core_note_on) begin
            core_seen=1;core_accept_time=$realtime;
        end
        if(!pcm_seen && sample_valid && (left || right))begin pcm_seen=1;pcm32_time=$realtime;end
        if(deadline || overflow || drops || underruns || cdc_drop)$fatal(1,"audio health fault");
    end
    always @(posedge clk_50m) if(reset_n && armed && !dac_seen && display_valid && display_pcm!=0) begin
        dac_seen=1;dac16_time=$realtime;
    end

    task mmio_write(input [7:0]a,input [31:0]d);
        begin
            @(negedge usb_clk);select=1;write=1;address=a;wdata=d;
            do @(posedge usb_clk);while(!ready);
            @(negedge usb_clk);select=0;write=0;
        end
    endtask
    task pc_byte(input [7:0]data);
        begin
            pc_rx=0; #(1000000000.0/115200);
            for(integer j=0;j<8;j++)begin pc_rx=data[j];#(1000000000.0/115200);end
            pc_rx=1;#(1000000000.0/115200);
        end
    endtask
    task g1_byte(input [7:0]data);
        begin
            g1_rx=0;#32000;
            for(integer j=0;j<8;j++)begin g1_rx=data[j];#32000;end
            g1_rx=1;#32000;
        end
    endtask
    initial begin
        if(!$value$plusargs("SOURCE=%d",source))$fatal(1,"missing SOURCE");
        offset_ns=0;void'($value$plusargs("OFFSET_NS=%d",offset_ns));
        #250;reset_n=1;repeat(8)@(posedge audio_clk);
        // Exclude PT8211 power-up mute/initial zero frames.  The physical
        // workstation is already running when a user presses a key or pad.
        repeat(200)@(posedge sample_ce);
        if(source==0)mmio_write(8'h00,1);
        wait(sample_ce);#1;#(offset_ns);armed=1;source_start=$realtime;
        case(source)
            0:begin
                mmio_write(8'h04,32'h643c9009);
                source_complete=$realtime;
            end
            1:begin
                pc_byte(8'h90);pc_byte(8'd60);pc_byte(8'd100);
                source_complete=$realtime;
            end
            default:begin
                g1_byte(8'h90);g1_byte(8'd60);g1_byte(8'd100);
                source_complete=$realtime;
            end
        endcase
        wait(core_seen && pcm_seen && dac_seen);
        if(!active[0])$fatal(1,"voice not active");
        $display("LATENCY source=%0d offset_ns=%0d wire_us=%0.3f source_to_core_us=%0.3f complete_to_core_us=%0.3f source_to_pcm32_us=%0.3f source_to_dac16_us=%0.3f",
            source,offset_ns,(source_complete-source_start)/1000.0,
            (core_accept_time-source_start)/1000.0,(core_accept_time-source_complete)/1000.0,
            (pcm32_time-source_start)/1000.0,(dac16_time-source_start)/1000.0);
        $finish;
    end
    initial begin #10000000;$fatal(1,"latency timeout source=%0d",source);end
endmodule
