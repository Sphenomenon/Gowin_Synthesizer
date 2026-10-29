`timescale 1ns/1ps
module tb_workstation_pcm_observation_bridge;
    reg source_clk=0,destination_clk=0,run_source=1,reset_n=1;
    realtime source_half=40.690104,destination_half=6.510417,source_phase=7.3,destination_phase=1.1;
    integer ignored;
    initial begin ignored=$value$plusargs("SOURCE_PHASE=%f",source_phase);#(source_phase);forever begin #(source_half);if(run_source)source_clk=!source_clk;end end
    initial begin ignored=$value$plusargs("DESTINATION_PHASE=%f",destination_phase);#(destination_phase);forever begin #(destination_half);destination_clk=!destination_clk;end end
    reg valid_i=0,rate_i=0,error_i=0,ready_i=1;
    reg [31:0] epoch_i=0,sequence_i=0,pcm_i=0;
    wire [31:0] source_drops,destination_drops;
    wire drop_event,loss_seen,valid_o,rate_o,error_o,stream_change,sequence_gap;
    wire [31:0] epoch_o,sequence_o,pcm_o;
    wire signed [31:0] qleft,qright;
    workstation_pcm_observation_bridge #(.FIFO_ADDRESS_BITS(2),.DROP_COUNTER_BITS(3)) dut(
        .reset_ni(reset_n),.source_clk_i(source_clk),.destination_clk_i(destination_clk),
        .frame_valid_i(valid_i),.frame_44k1_i(rate_i),.frame_error_i(error_i),
        .frame_epoch_i(epoch_i),.frame_sequence_i(sequence_i),.frame_pcm_i(pcm_i),
        .source_drop_count_o(source_drops),.destination_drop_count_o(destination_drops),
        .destination_drop_event_o(drop_event),.destination_loss_seen_o(loss_seen),
        .frame_valid_o(valid_o),.frame_ready_i(ready_i),.frame_44k1_o(rate_o),.frame_error_o(error_o),
        .frame_epoch_o(epoch_o),.frame_sequence_o(sequence_o),.frame_pcm_o(pcm_o),
        .left_q31_o(qleft),.right_q31_o(qright),.stream_change_o(stream_change),.sequence_gap_o(sequence_gap));
    wire default_valid;
    wire [97:0] default_payload;
    wire [31:0] default_source_drops,default_destination_drops;
    workstation_pcm_observation_bridge default_dut(
        .reset_ni(reset_n),.source_clk_i(source_clk),.destination_clk_i(destination_clk),
        .frame_valid_i(valid_i),.frame_44k1_i(rate_i),.frame_error_i(error_i),
        .frame_epoch_i(epoch_i),.frame_sequence_i(sequence_i),.frame_pcm_i(pcm_i),
        .source_drop_count_o(default_source_drops),.destination_drop_count_o(default_destination_drops),
        .destination_drop_event_o(),.destination_loss_seen_o(),.frame_valid_o(default_valid),.frame_ready_i(ready_i),
        .frame_44k1_o(default_payload[97]),.frame_epoch_o(default_payload[96:65]),.frame_sequence_o(default_payload[64:33]),
        .frame_error_o(default_payload[32]),.frame_pcm_o(default_payload[31:0]),
        .left_q31_o(),.right_q31_o(),.stream_change_o(),.sequence_gap_o());
    reg [97:0] default_expected[0:1023];
    integer default_tail=0,default_head=0,default_expected_drops=0,default_checked=0;
    reg default_past_seven=0;
    always @(negedge reset_n)begin default_tail=0;default_head=0;default_expected_drops=0;end
    always @(posedge source_clk)if(reset_n && default_dut.source_reset_n && valid_i)begin
        if(default_dut.write_ready)begin
            default_expected[default_tail]={rate_i,epoch_i,sequence_i,error_i,pcm_i};default_tail=default_tail+1;
        end else default_expected_drops=default_expected_drops+1;
        #0.01;
        if(default_source_drops!=32'(default_expected_drops))$fatal(1,"default32bit counter mismatch");
        if(default_source_drops>7)default_past_seven=1;
    end
    always @(posedge destination_clk)if(reset_n && default_valid && ready_i)begin
        if(default_head>=default_tail || default_payload!==default_expected[default_head])$fatal(1,"default16depth atomicity/order");
        default_head=default_head+1;default_checked=default_checked+1;
    end
    reg [97:0] expected[0:1023];
    integer tail=0,head=0,expected_drops=0,offered=0,accepted=0,checked=0,drop_events=0,changes=0,gaps=0,errors=0;
    integer totals_checked=0,totals_offered=0,totals_accepted=0,totals_dropped=0;
    reg previous_valid=0,previous_rate=0;
    reg [31:0] previous_epoch=0,previous_sequence=0;
    reg stalled=0;
    reg [99:0] stalled_payload;
    always @(negedge reset_n)begin
        head=0;tail=0;expected_drops=0;offered=0;accepted=0;checked=0;
        previous_valid=0;stalled=0;
    end
    always @(posedge source_clk)if(reset_n && dut.source_reset_n && valid_i)begin
        offered=offered+1;totals_offered=totals_offered+1;
        if(dut.write_ready)begin
            if(tail>=1024)$fatal(1,"fixture queue capacity");
            expected[tail]={rate_i,epoch_i,sequence_i,error_i,pcm_i};tail=tail+1;
            accepted=accepted+1;totals_accepted=totals_accepted+1;
        end else begin
            if(expected_drops<7)expected_drops=expected_drops+1;
            totals_dropped=totals_dropped+1;
        end
        #0.01;
        if(source_drops!=32'(expected_drops))$fatal(1,"source counter not saturating/last-edge current");
    end
    always @(posedge destination_clk)if(reset_n && dut.destination_reset_n)begin
        if(drop_event)drop_events=drop_events+1;
        if(loss_seen!==(destination_drops!=0))$fatal(1,"loss visibility independent of payload");
        if(stalled && (!valid_o || {stream_change,sequence_gap,rate_o,epoch_o,sequence_o,error_o,pcm_o}!==stalled_payload))
            $fatal(1,"stalled destination payload changed");
        stalled=valid_o && !ready_i;
        if(stalled)stalled_payload={stream_change,sequence_gap,rate_o,epoch_o,sequence_o,error_o,pcm_o};
        if(valid_o && ready_i)begin
            if(head>=tail || {rate_o,epoch_o,sequence_o,error_o,pcm_o}!==expected[head])
                $fatal(1,"torn/duplicate/reordered PCM or metadata");
            if(qleft!==$signed({pcm_o[31:16],16'd0}) || qright!==$signed({pcm_o[15:0],16'd0}))
                $fatal(1,"Q31 sign-preserving conversion");
            if(stream_change!==(!previous_valid || rate_o!=previous_rate || epoch_o!=previous_epoch))
                $fatal(1,"stream change lost/false");
            if(sequence_gap!==(previous_valid && rate_o==previous_rate && epoch_o==previous_epoch && sequence_o!=previous_sequence+1'b1))
                $fatal(1,"sequence gap/wrap lost/false");
            if(stream_change)changes=changes+1;if(sequence_gap)gaps=gaps+1;if(error_o)errors=errors+1;
            previous_valid=1;previous_rate=rate_o;previous_epoch=epoch_o;previous_sequence=sequence_o;
            head=head+1;checked=checked+1;totals_checked=totals_checked+1;
        end
    end
    task send(input bit rate,input [31:0] epoch,seq_value,pcm,input bit error);
        begin
            @(negedge source_clk);rate_i=rate;epoch_i=epoch;sequence_i=seq_value;pcm_i=pcm;error_i=error;valid_i=1;
            @(posedge source_clk);#0.1;
            @(negedge source_clk);valid_i=0;
        end
    endtask
    task drained;
        integer n;
        begin
            n=0;while((head!=tail || valid_o) && n<1000)begin @(negedge destination_clk);n=n+1;end
            if(head!=tail || valid_o)$fatal(1,"destination drain failed");
            repeat(6)@(negedge destination_clk);
        end
    endtask
    task source_release;
        begin repeat(6)@(negedge source_clk);repeat(6)@(negedge destination_clk);end
    endtask
    task check_drops(input integer count);
        integer n;
        begin
            n=0;while(destination_drops!=32'(count) && n<20)begin @(negedge destination_clk);n=n+1;end
            if(destination_drops!=32'(count) || (count!=0 && !loss_seen))$fatal(1,"drop invisible without next frame/source edge");
        end
    endtask
    task reset_common;
        begin
            reset_n=0;valid_i=0;#11;
            if(valid_o || source_drops || destination_drops || loss_seen)$fatal(1,"coordinated async reset needs source edge");
            reset_n=1;
        end
    endtask
    integer old_drop_events;
    initial begin
        #2;reset_n=0;#200;reset_n=1;source_release();
        // Real source clocks/cadences, actual compute clock, extrema and errors.
        for(integer rate=0;rate<2;rate=rate+1)begin
            source_half=rate ? 29.525699:40.690104;
            for(integer n=0;n<16;n=n+1)begin
                send(1'(rate),32'(rate),32'(n),n%4==0 ? 32'h80007fff:n%4==1 ? 32'hffff0001:n%4==2 ? 32'h00008000:32'h7fff0000,n%5==0);
                repeat(rate ? 382:254)@(negedge source_clk);
            end
            drained();
        end
        // Wrap must be consecutive; deliberate hole is exactly one gap.
        send(1,2,32'hfffffffe,32'h12345678,0);send(1,2,32'hffffffff,32'h87654321,1);
        send(1,2,0,32'h80008000,0);send(1,2,1,32'h7fff7fff,0);send(1,2,3,32'hffffffff,0);drained();
        if(gaps!=1)$fatal(1,"sequence wrap incorrectly counted gaps=%0d checked=%0d offered=%0d accepted=%0d dropped=%0d tail=%0d head=%0d lastseq=%h",gaps,checked,offered,accepted,expected_drops,tail,head,previous_sequence);
        // Fill exactly four slots with stalled destination. The fifth frame
        // drops. Stop high immediately after that SAME edge; no next edge/frame.
        ready_i=0;for(integer n=0;n<4;n=n+1)send(1,3,32'(n),32'h13572468^32'(n),0);
        @(negedge source_clk);valid_i=1;sequence_i=4;pcm_i=32'hdeadbeef;
        @(posedge source_clk);run_source=0;#0.1;valid_i=0;
        check_drops(1);
        if(source_clk!==1'b1 || offered!=accepted+1)$fatal(1,"no-backpressure/stopped-high fixture");
        ready_i=1;drained();
        if(checked!=accepted)$fatal(1,"source stop blocked existing queued frames");
        run_source=1;repeat(4)@(negedge source_clk);
        send(1,3,5,32'h8000ffff,1);drained();
        if(gaps!=2)$fatal(1,"whole dropped frame not visible as sequence gap");
        // Stop low while queued; destination can still consume and loss persists.
        ready_i=0;send(0,4,0,32'h7fff8000,0);@(negedge source_clk);run_source=0;
        ready_i=1;drained();check_drops(1);
        if(source_clk!==1'b0)$fatal(1,"low stop fixture");
        // Common reset with stopped source: queue and telemetry clear together.
        reset_common();repeat(10)@(negedge destination_clk);
        if(valid_o || source_drops || destination_drops)$fatal(1,"reset resurrected old frame/drop");
        run_source=1;source_release();
        // A slower destination and bursts cross unrelated phase/clock ratios.
        destination_half=91.7;ready_i=0;
        for(integer n=0;n<24;n=n+1)send(0,8,32'(n),32'h10008000+32'(n),n[0]);
        check_drops(7);
        if(source_drops!=7 || offered!=24 || accepted!=4 || expected_drops!=7)$fatal(1,"bounded full capacity/saturation");
        if(default_tail!=16 || default_expected_drops!=8 || default_source_drops!=8)$fatal(1,"default16-frame capacity");
        repeat(6)@(negedge destination_clk);
        if(default_destination_drops!=8)$fatal(1,"default32bit drop telemetry");
        old_drop_events=drop_events;ready_i=1;drained();
        send(1,9,32'hffffffff,32'hffffffff,1);drained();send(1,9,0,32'h00008000,0);drained();
        check_drops(7);
        if(drop_events!=old_drop_events || !loss_seen)$fatal(1,"stream switch cleared saturated loss or false drop");
        // Reset a nonempty stalled queue; release while source remains stopped.
        ready_i=0;send(0,10,0,32'h01020304,0);@(negedge source_clk);run_source=0;
        reset_common();repeat(10)@(negedge destination_clk);
        run_source=1;destination_half=6.510417;ready_i=1;source_release();
        send(0,20,0,32'h80007fff,1);drained();
        if(destination_drops || source_drops || loss_seen || checked!=1)$fatal(1,"global reset did not start a clean lifetime");
        if(totals_dropped!=21 || gaps<2 || changes<8 || errors<4 || drop_events==0 || !default_past_seven || default_checked<=totals_checked)$fatal(1,"coverage missing");
        $display("PASS pcm_observation: offered=%0d accepted=%0d dropped=%0d checked=%0d stream_changes=%0d sequence_gaps=%0d errors=%0d drop_events=%0d default_checked=%0d capacity=4 saturation=7",totals_offered,totals_accepted,totals_dropped,totals_checked,changes,gaps,errors,drop_events,default_checked);
        $finish;
    end
    initial begin #5000000;$fatal(1,"observation watchdog");end
endmodule
