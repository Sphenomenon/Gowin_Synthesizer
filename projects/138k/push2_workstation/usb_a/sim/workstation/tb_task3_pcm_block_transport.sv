`timescale 1ns/1ps
// Ideal wires only: actual PCM codecs and unmodified LCD transport/PHY.
// This bench grants a MODEL budget; it never qualifies a physical link.
module tb_task3_pcm_block_transport #(
    parameter integer FRAMES=4099,
    parameter integer W_HALF_NS=11
);
    reg mc=0,wc=0,reset_n=0,enable=0,budget=0,run=0;
    always #10 mc=~mc;
    initial begin #3;forever #(W_HALF_NS) wc=~wc;end
    wire [1:0] clocks={wc,mc},live,business,link_fault,transport_tx_ready,transport_rx_valid;
    wire [1:0] req,ack,panic;
    wire [3:0] phy_data[2],rx_channel[2],link_failure[2];
    wire [255:0] rx_payload[2];
    wire [5:0] rx_length[2];
    wire [31:0] tx_packets[2],rx_packets[2],crc_errors[2],sequence_errors[2];
    wire [31:0] overflows[2],probes[2],max_rtt[2];
    reg transport_tx_valid[2];
    reg [3:0] tx_channel[2];
    reg [255:0] tx_payload[2];
    reg [5:0] tx_length[2];
    integer mcycles=0,wcycles=0;
    reg m_started=0,w_started=0;
    wire m_start=run && !m_started;
    wire w_start=run && !w_started;
    time begin_ns,finish_ns;
    for(genvar i=0;i<2;i=i+1)begin:g_link
        workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(1)) link(
            .clk_i(clocks[i]),.reset_ni(reset_n),.enable_i(enable),.panic_i(1'b0),.budget_validated_i(budget),
            .local_boot_i(32'(i+1)),.peer_boot_i(32'(2-i)),.session_i(32'hb106),
            .tx_valid_i(transport_tx_valid[i]),.tx_ready_o(transport_tx_ready[i]),
            .tx_channel_i(tx_channel[i]),.tx_payload_i(tx_payload[i]),.tx_length_i(tx_length[i]),
            .rx_valid_o(transport_rx_valid[i]),.rx_ready_i(1'b1),.rx_channel_o(rx_channel[i]),
            .rx_payload_o(rx_payload[i]),.rx_length_o(rx_length[i]),
            .link_ready_o(live[i]),.business_ready_o(business[i]),.pad_drive_o(),
            .fault_o(link_fault[i]),.failure_code_o(link_failure[i]),.peer_panic_o(),
            .phy_tx_data_o(phy_data[i]),.phy_tx_req_o(req[i]),.phy_rx_ack_o(ack[i]),.phy_panic_o(panic[i]),
            .phy_rx_data_i(phy_data[1-i]),.phy_rx_req_i(req[1-i]),.phy_tx_ack_i(ack[1-i]),.phy_peer_panic_i(panic[1-i]),
            .tx_packets_o(tx_packets[i]),.rx_packets_o(rx_packets[i]),.crc_errors_o(crc_errors[i]),
            .sequence_errors_o(sequence_errors[i]),.rejected_packets_o(),.overflow_count_o(overflows[i]),
            .congestion_cycles_o(),.last_rtt_cycles_o(),.max_rtt_cycles_o(max_rtt[i]),
            .probe_results_o(probes[i]),.link_timeouts_o());
        always @(posedge clocks[i])if(run && link_fault[i])
            $fatal(1,"actual transport fault endpoint=%0d code=%0d",i,link_failure[i]);
    end
    function automatic [31:0] pcm(input integer stream,input integer index);
        pcm=32'hb1090401 ^ (32'(index)*32'h10497) ^ (32'(stream)*32'h5a390181);
    endfunction
    wire [1:0] tx_frame_ready,block_valid,block_ready,tx_empty,tx_active,tx_fault;
    wire [255:0] block_payload[2];
    wire [5:0] block_length[2];
    wire [31:0] sent_blocks[2];
    wire [1:0] frame_valid,frame_ready,rx_empty,rx_active,rx_fault,credit_valid,credit_ready;
    wire [31:0] frame_index[2],frame_pcm[2],credit_token[2],credit_limit[2];
    wire [31:0] accepted_blocks[2],delivered_frames[2];
    wire source_pending[2];
    integer generated[2],submitted[2],received[2],max_source_queue[2];
    wire [31:0] pending_index[2];
    integer phase[2];
    wire [1:0] source_fire;
    integer analysis_wait_credit=0;
    reg stall_started=0,stall_complete=0;
    integer stall_remaining=0,record_at_stall=0,control_at_stall=0;
    integer record_during_stall=0,control_during_stall=0;
    integer control_sent=0,control_received=0,control_echoed=0;
    reg control_pending=0,echo_pending=0;
    reg [31:0] echo_sequence=0;
    reg media_rr=0,credit_rr=0;
    reg [1:0] media_choice,credit_choice;
    time record_last_ns=0,max_record_gap_ns=0;
    for(genvar s=0;s<2;s=s+1)begin:g_stream
        wire credit_packet=transport_rx_valid[0] && rx_channel[0]==12 && rx_length[0]==9 &&
            rx_payload[0][255:65]==0 && rx_payload[0][64]==1'(s);
        workstation_task3_pcm_block_tx sender(
            .clk_i(mc),.reset_ni(reset_n),.live_i(run && business[0]),.start_i(m_start),.cancel_i(1'b0),
            .flush_i(generated[s]==FRAMES && !source_pending[s]),.token_i(32'h100+32'(s)),.first_index_i(32'd0),
            .frame_valid_i(source_pending[s]),.frame_ready_o(tx_frame_ready[s]),
            .frame_index_i(pending_index[s]),.frame_pcm_i(pcm(s,integer'(pending_index[s]))),
            .credit_valid_i(credit_packet),.credit_token_i(rx_payload[0][31:0]),.credit_limit_i(rx_payload[0][63:32]),
            .block_valid_o(block_valid[s]),.block_ready_i(block_ready[s]),.block_payload_o(block_payload[s]),.block_length_o(block_length[s]),
            .empty_o(tx_empty[s]),.active_o(tx_active[s]),.fault_o(tx_fault[s]),.sent_blocks_o(sent_blocks[s]));
        workstation_task3_pcm_block_rx receiver(
            .clk_i(wc),.reset_ni(reset_n),.live_i(run && business[1]),.start_i(w_start),.cancel_i(1'b0),
            .token_i(32'h100+32'(s)),.first_index_i(32'd0),
            .block_valid_i(transport_rx_valid[1] && rx_channel[1]==4'(10+s)),
            .block_payload_i(rx_payload[1]),.block_length_i(rx_length[1]),
            .frame_valid_o(frame_valid[s]),.frame_ready_i(frame_ready[s]),.frame_index_o(frame_index[s]),.frame_pcm_o(frame_pcm[s]),
            .credit_valid_o(credit_valid[s]),.credit_ready_i(credit_ready[s]),.credit_token_o(credit_token[s]),.credit_limit_o(credit_limit[s]),
            .empty_o(rx_empty[s]),.active_o(rx_active[s]),.fault_o(rx_fault[s]),
            .accepted_blocks_o(accepted_blocks[s]),.delivered_frames_o(delivered_frames[s]));
        assign source_pending[s]=generated[s]!=submitted[s];
        assign pending_index[s]=32'(submitted[s]);
        assign source_fire[s]=source_pending[s] && tx_frame_ready[s];
        assign frame_ready[s]=s==0 ? stall_remaining==0 && wcycles%3==0 : wcycles%7==0;
        initial begin generated[s]=0;submitted[s]=0;received[s]=0;phase[s]=0;max_source_queue[s]=0;end
        always @(posedge mc)if(run)begin
            if(source_fire[s])submitted[s]<=submitted[s]+1;
            if(generated[s]-submitted[s]>max_source_queue[s])max_source_queue[s]<=generated[s]-submitted[s];
            if(generated[s]<FRAMES)begin
                if(phase[s]+48000>=50000000)begin
                    phase[s]<=phase[s]+48000-50000000;
                    // Both real source adapters have bounded 256-frame queues.
                    // Deterministic indices model their queued PCM values here.
                    // TF pauses when full; the recording tick may never wait.
                    if(generated[s]-submitted[s]<256 || source_fire[s])generated[s]<=generated[s]+1;
                    else if(s==1)$fatal(1,"recording source queue overflow index=%0d",generated[s]);
                end else phase[s]<=phase[s]+48000;
            end
            if(tx_fault[s])$fatal(1,"block TX fault stream=%0d",s);
        end
        always @(posedge wc)if(run)begin
            if(frame_valid[s] && frame_ready[s])begin
                if(frame_index[s]!=32'(received[s]) || frame_pcm[s]!=pcm(s,received[s]) || received[s]>=FRAMES)
                    $fatal(1,"PCM/order mismatch stream=%0d index=%0d",s,received[s]);
                received[s]<=received[s]+1;
                if(s==1)begin
                    if(record_last_ns!=0 && $time-record_last_ns>max_record_gap_ns)max_record_gap_ns<=$time-record_last_ns;
                    record_last_ns<=$time;
                end
            end
            if(rx_fault[s])$fatal(1,"block RX fault stream=%0d",s);
        end
    end
    always @*begin
        // Bounded synthetic control traffic has its own slot. Media RR cannot
        // starve a ready recording block when analysis resumes with backlog.
        media_choice=2;
        if(block_valid[media_rr])media_choice={1'b0,media_rr};
        else if(block_valid[!media_rr])media_choice={1'b0,!media_rr};
        transport_tx_valid[0]=run && (control_pending || media_choice<2);
        tx_channel[0]=control_pending ? 4'd15 : 4'd10+4'(media_choice);
        tx_payload[0]=control_pending ? {224'd0,32'(control_sent)} : media_choice<2 ? block_payload[media_choice[0]] : 256'd0;
        tx_length[0]=control_pending ? 6'd4 : media_choice<2 ? block_length[media_choice[0]] : 6'd0;
        credit_choice=2;
        if(credit_valid[credit_rr])credit_choice={1'b0,credit_rr};
        else if(credit_valid[!credit_rr])credit_choice={1'b0,!credit_rr};
        transport_tx_valid[1]=run && (echo_pending || credit_choice<2);
        tx_channel[1]=echo_pending ? 4'd15 : 4'd12;
        tx_payload[1]=echo_pending ? {224'd0,echo_sequence} : credit_choice<2 ?
            {191'd0,credit_choice[0],credit_limit[credit_choice[0]],credit_token[credit_choice[0]]} : 256'd0;
        tx_length[1]=echo_pending ? 6'd4 : 6'd9;
    end
    assign block_ready[0]=transport_tx_ready[0] && !control_pending && media_choice==0;
    assign block_ready[1]=transport_tx_ready[0] && !control_pending && media_choice==1;
    assign credit_ready[0]=transport_tx_ready[1] && !echo_pending && credit_choice==0;
    assign credit_ready[1]=transport_tx_ready[1] && !echo_pending && credit_choice==1;
    always @(posedge mc)begin
        mcycles<=mcycles+1;
        if(run)begin
            m_started<=1;
            if(mcycles%10000==0)begin
                if(control_pending)$fatal(1,"bounded control source overflow");
                control_pending<=1;
            end
            if(transport_tx_valid[0] && transport_tx_ready[0])begin
                if(control_pending)begin control_pending<=0;control_sent<=control_sent+1;end
                else media_rr<=!media_choice[0];
            end
            if(tx_active[0] && !tx_empty[0] && !tx_frame_ready[0] && !block_valid[0])analysis_wait_credit<=analysis_wait_credit+1;
            if(transport_rx_valid[0])begin
                if(rx_channel[0]==15)begin
                    if(rx_length[0]!=4 || rx_payload[0]!={224'd0,32'(control_echoed)})$fatal(1,"control echo mismatch");
                    control_echoed<=control_echoed+1;
                end else if(rx_channel[0]!=12)$fatal(1,"unexpected M business channel");
            end
        end
    end
    always @(posedge wc)begin
        wcycles<=wcycles+1;
        if(run)begin
            w_started<=1;
            if(transport_tx_valid[1] && transport_tx_ready[1])begin
                if(echo_pending)echo_pending<=0;
                else credit_rr<=!credit_choice[0];
            end
            if(transport_rx_valid[1] && rx_channel[1]==15)begin
                if(rx_length[1]!=4 || rx_payload[1]!={224'd0,32'(control_received)} || echo_pending)
                    $fatal(1,"control delivery mismatch/overflow");
                control_received<=control_received+1;echo_pending<=1;echo_sequence<=rx_payload[1][31:0];
            end
            if(!stall_started && received[0]>=300)begin
                stall_started<=1;stall_remaining<=180000;record_at_stall<=received[1];control_at_stall<=control_received;
            end else if(stall_remaining!=0)begin
                stall_remaining<=stall_remaining-1;
                if(stall_remaining==1)begin
                    record_during_stall<=received[1]-record_at_stall;
                    control_during_stall<=control_received-control_at_stall;
                    if(received[1]-record_at_stall<100 || control_received-control_at_stall<10)
                        $fatal(1,"analysis HOL blocked recording/control");
                    stall_complete<=1;
                end
            end
        end
    end
    initial begin
        repeat(5)@(negedge mc);reset_n=1;enable=1;
        wait(&live);@(negedge mc);budget=1;
        wait(&business);@(negedge mc);begin_ns=$time;run=1;
        wait(received[0]==FRAMES && received[1]==FRAMES);
        wait(control_sent==control_received && control_sent==control_echoed && !control_pending && !echo_pending);
        @(negedge mc);finish_ns=$time;
        if(!stall_complete || analysis_wait_credit==0 || max_record_gap_ns>500000)
            $fatal(1,"missing bounded concurrency coverage or excessive recording service gap");
        for(integer i=0;i<2;i=i+1)begin
            if(crc_errors[i]!=0 || sequence_errors[i]!=0 || overflows[i]!=0 || probes[i]==0)
                $fatal(1,"transport counters not clean endpoint=%0d",i);
            if(sent_blocks[i]!=accepted_blocks[i] || delivered_frames[i]!=FRAMES || !tx_empty[i] || !rx_empty[i])
                $fatal(1,"block counters/queues not drained stream=%0d",i);
        end
        $display("PCM_BLOCK_MODEL frames_per_stream=%0d elapsed_ns=%0t record_max_gap_ns=%0t analysis_credit_stall_M_cycles=%0d record_frames_during_analysis_stall=%0d controls_during_analysis_stall=%0d controls=%0d max_source_queue_analysis=%0d max_source_queue_record=%0d blocks_analysis=%0d blocks_record=%0d M_probe_results=%0d W_probe_results=%0d M_probe_max_RTT_cycles=%0d W_probe_max_RTT_cycles=%0d",
            FRAMES,finish_ns-begin_ns,max_record_gap_ns,analysis_wait_credit,record_during_stall,control_during_stall,
            control_received,max_source_queue[0],max_source_queue[1],sent_blocks[0],sent_blocks[1],probes[0],probes[1],max_rtt[0],max_rtt[1]);
        $display("PASS task3_pcm_block_transport W_half_ns=%0d physical_acceptance=0",W_HALF_NS);
        $finish;
    end
    initial begin #200000000;$fatal(1,"PCM block transport model timeout");end
endmodule
