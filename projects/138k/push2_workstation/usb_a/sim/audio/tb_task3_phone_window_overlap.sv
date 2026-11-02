`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
// Real M endpoint, deterministic held-command owner fixture. Bad overlap must
// revoke the stream, never transfer an in-flight command to another producer.
module tb_task3_phone_window_overlap;
    reg clk=0,reset_n=0,link=0,panic=0;
    always #10 clk=~clk;
    reg rx_valid=0;
    reg [3:0] rx_channel=0;
    reg [255:0] rx_payload=0;
    reg [5:0] rx_length=0;
    wire rx_ready,tx_valid;
    reg tx_ready=1,owner_allow=0;
    wire [3:0] tx_channel;
    wire [255:0] tx_payload;
    wire [5:0] tx_length;
    wire owner_live,command_valid,command_target,command_write,hci_ready;
    wire [11:0] command_address;
    wire [31:0] command_data;
    wire [3:0] command_strobes;
    wire command_ready=owner_allow && command_valid;
    integer checks=0,cycles=0,samples=0,cases=0;
    integer applied=0,normal_applied=0,window_applied=0,responses=0,response_errors=0;
    integer total_applied=0,total_response=0;
    reg command_seen=0,previous_valid=0;
    reg [49:0] previous_command;
    workstation_task3_m_bus_endpoint #(.BLOCK_PCM(1),.PHONE_WINDOW_BLOCK(1)) m(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),
        .local_boot_i(32'd11),.peer_boot_i(32'd22),.session_i(32'd33),.generation_i(32'd1),
        .rx_valid_i(rx_valid),.rx_ready_o(rx_ready),.rx_channel_i(rx_channel),.rx_payload_i(rx_payload),.rx_length_i(rx_length),
        .tx_valid_o(tx_valid),.tx_ready_i(tx_ready),.tx_channel_o(tx_channel),.tx_payload_o(tx_payload),.tx_length_o(tx_length),
        .analysis_start_i(1'b0),.analysis_ready_o(),.analysis_cancel_i(1'b0),.analysis_pcm_valid_i(1'b0),
        .analysis_pcm_last_i(1'b0),.analysis_pcm_ready_o(),.analysis_pcm_i(32'd0),.analysis_failed_o(),.analysis_busy_o(),.analysis_done_o(),
        .push_score_valid_o(),.push_score_ready_i(1'b1),.push_score_note_o(),.record_arm_i(1'b0),.record_cancel_i(1'b0),
        .frame_valid_i(1'b0),.frame_44k1_i(1'b0),.frame_error_i(1'b0),.frame_epoch_i(32'd7),.frame_sequence_i(32'd0),.frame_pcm_i(32'd0),
        .record_armed_o(),.record_fault_o(),.phone_owner_idle_i(1'b1),.phone_owner_live_o(owner_live),
        .phone_command_valid_o(command_valid),.phone_command_ready_i(command_ready),
        .phone_command_target_o(command_target),.phone_command_write_o(command_write),.phone_command_address_o(command_address),
        .phone_command_data_o(command_data),.phone_command_strobes_o(command_strobes),
        .phone_response_data_i(32'h12345678),.phone_response_error_i(1'b0),
        .hci_ready_o(hci_ready),.hci_epoch_o(),.hci_generation_o(),.model_status_o(),.malformed_packets_o(),.stale_packets_o());
    task automatic check(input reg condition,input [511:0] description);
        begin checks=checks+1;if(!condition)$fatal(1,"overlap: %0s",description);end
    endtask
    task automatic ticks(input integer count);
        begin repeat(count)begin @(posedge clk);#1;end end
    endtask
    // Called at a negedge; adjacent offers may remain valid continuously.
    task automatic send_now(input [3:0] channel,input [255:0] payload,input [5:0] length);
        begin
            rx_channel=channel;rx_payload=payload;rx_length=length;rx_valid=1;
            #1;check(rx_ready,"offered protocol packet consumed");ticks(1);
            @(negedge clk);rx_valid=0;
        end
    endtask
    task automatic send(input [3:0] channel,input [255:0] payload,input [5:0] length);
        begin @(negedge clk);send_now(channel,payload,length);end
    endtask
    function automatic [255:0] rpc(input [31:0] seq,input reg target,input [11:0] address,input [31:0] data);
        rpc={76'd0,`TASK3_PAIR_KIND_DATA,32'd11,32'd33,32'd1,seq,target,1'b1,address,data,4'hf};
    endfunction
    function automatic [255:0] window(input [2:0] count);
        begin
            window={160'h0000000500000004000000030000000200000001,32'h800,32'd0,32'd1};
            if(count==1)window[255:128]=0;
        end
    endfunction
    task automatic fresh(input reg hold_arm_ack);
        begin
            @(negedge clk);reset_n=0;link=0;panic=0;rx_valid=0;tx_ready=1;owner_allow=0;
            applied=0;normal_applied=0;window_applied=0;responses=0;response_errors=0;
            ticks(3);@(negedge clk);reset_n=1;link=1;ticks(4);
            send(`TASK3_PAIR_CH_STATUS,{58'd0,32'd22,32'd11,32'd33,32'd1,32'd44,32'd55,1'b1,1'b1,4'd9},`TASK3_PAIR_STATUS_BYTES);
            send(`TASK3_PAIR_CH_MEDIA_CAPS,{32'd0,32'd22,32'd11,32'd33,32'd1,`TASK3_PAIR_MEDIA_MAGIC,`TASK3_PAIR_PHONE_WINDOW_VERSION,`TASK3_PAIR_PHONE_WINDOW_FEATURES},`TASK3_PAIR_MEDIA_CAPS_BYTES);
            ticks(5);check(hci_ready&&m.media_current,"negotiated current HCI and media");
            if(hold_arm_ack)begin @(negedge clk);tx_ready=0;end
            send(`TASK3_PAIR_CH_PHONE,{76'd0,`TASK3_PAIR_KIND_ARM,32'd11,32'd33,32'd1,82'd0},`TASK3_PAIR_PHONE_BYTES);
            ticks(5);check(owner_live,"logical phone owner armed");
            if(hold_arm_ack)check(tx_valid,"ARM ACK held in shared TX slot");
        end
    endtask
    task automatic fenced(input integer expected_applied,input integer expected_errors);
        begin
            ticks(3);check(m.phone_window_protocol_fault,"overlap faults are sticky");
            check(!owner_live&&!command_valid&&!m.phone_window_busy,"overlap revokes owner without replaying window");
            tx_ready=1;ticks(12);
            check(applied==expected_applied&&window_applied==0,"overlap cannot apply or misattribute an extra command");
            check(response_errors==expected_errors,"held normal response drained with correct scope");
            cases=cases+1;
        end
    endtask
    always @(posedge clk)begin
        cycles<=cycles+1;if(cycles>10000)$fatal(1,"overlap test timeout");
        // A physical sample tick is deliberately independent of all fixtures.
        if(cycles%8==0)samples<=samples+1;
        if(!reset_n)begin command_seen<=0;previous_valid<=0;previous_command<=0;end
        else begin
            if(previous_valid&&command_valid&&owner_live)
                check({command_target,command_write,command_address,command_data,command_strobes}==previous_command,"held owner request never switches producers");
            previous_valid<=command_valid;
            previous_command<={command_target,command_write,command_address,command_data,command_strobes};
            if(!command_valid)command_seen<=0;
            if(command_valid&&command_ready&&!command_seen)begin
                check(owner_live,"only current logical owner applies");
                command_seen<=1;applied<=applied+1;total_applied<=total_applied+1;
                if(command_address>=12'h800)window_applied<=window_applied+1;
                else normal_applied<=normal_applied+1;
            end
            if(tx_valid&&tx_ready&&tx_channel==`TASK3_PAIR_CH_PHONE_ACK&&tx_payload[162:161]==`TASK3_PAIR_KIND_DATA)begin
                check(tx_length==`TASK3_PAIR_PHONE_ACK_BYTES&&tx_payload[160:65]=={32'd11,32'd33,32'd1},"normal response retains full common identity");
                responses<=responses+1;total_response<=total_response+1;
                if(tx_payload[32])response_errors<=response_errors+1;
            end
        end
    end
    integer before_samples;
    initial begin
        // PREPARE: the original command has not reached the owner yet.
        fresh(0);send(`TASK3_PAIR_CH_PHONE,rpc(0,1,12'h02c,32'haabbccdd),`TASK3_PAIR_PHONE_BYTES);
        check(m.phone.state==3,"normal PREPARE reached");
        send_now(`TASK3_PAIR_CH_PHONE_WINDOW,window(1),16);fenced(0,1);
        check(responses==1,"PREPARE command returns explicit cancellation error");
        // WAIT_OWNER: one held request must never be replaced by window data.
        fresh(0);send(`TASK3_PAIR_CH_PHONE,rpc(0,0,12'h02c,32'h11),`TASK3_PAIR_PHONE_BYTES);ticks(2);
        check(command_valid&&m.phone.state==1,"normal WAIT_OWNER reached");
        before_samples=samples;send(`TASK3_PAIR_CH_PHONE_WINDOW,window(1),16);fenced(0,1);
        check(samples>before_samples,"sample schedule continues through overlap fault");
        // RESPONSE: real completion remains successful; later overlap revokes
        // ownership without changing the already completed command's result.
        fresh(1);owner_allow=1;send(`TASK3_PAIR_CH_PHONE,rpc(0,1,12'h02c,32'h22),`TASK3_PAIR_PHONE_BYTES);ticks(3);
        check(m.phone.state==2&&normal_applied==1,"normal RESPONSE held behind TX");
        send(`TASK3_PAIR_CH_PHONE_WINDOW,window(1),16);fenced(1,0);
        check(responses==1,"already applied response preserved exactly once");
        // Opposite overlap: ordinary RPC arriving during a window is consumed
        // as a protocol fault and never accepted into the normal ingress FSM.
        fresh(0);send(`TASK3_PAIR_CH_PHONE_WINDOW,window(5),32);ticks(3);
        check(command_valid&&m.phone_window_busy,"window WAIT_OWNER reached");
        send(`TASK3_PAIR_CH_PHONE,rpc(0,1,12'h02c,32'h33),`TASK3_PAIR_PHONE_BYTES);
        ticks(5);check(m.phone_window_protocol_fault&&!owner_live&&!command_valid,"RPC over window revokes immediately");
        check(m.phone.accepted_commands_o==0&&applied==0,"overlapping RPC was never accepted or applied");cases=cases+1;
        // PANIC dominates an offered overlapping block in the same cycle.
        fresh(0);send(`TASK3_PAIR_CH_PHONE,rpc(0,0,12'h02c,32'h44),`TASK3_PAIR_PHONE_BYTES);ticks(2);
        @(negedge clk);panic=1;owner_allow=1;rx_valid=1;rx_channel=`TASK3_PAIR_CH_PHONE_WINDOW;rx_payload=window(1);rx_length=16;
        #1;check(!owner_live&&!command_valid,"same-cycle PANIC suppresses command before edge");ticks(3);
        check(applied==0&&!m.phone_window_busy,"PANIC cannot leak ordinary/window application");cases=cases+1;
        // Matched cancel similarly withdraws a window command before ready.
        fresh(0);send(`TASK3_PAIR_CH_PHONE_WINDOW,window(5),32);ticks(3);check(command_valid,"cancel test window held");
        @(negedge clk);owner_allow=1;rx_valid=1;rx_channel=`TASK3_PAIR_CH_PHONE;rx_length=`TASK3_PAIR_PHONE_BYTES;
        rx_payload={76'd0,`TASK3_PAIR_KIND_CANCEL,32'd11,32'd33,32'd1,82'd0};
        #1;check(!owner_live&&!command_valid,"same-cycle matched cancel suppresses window before edge");ticks(3);
        check(applied==0&&!m.phone_window_busy&&!m.phone_window_protocol_fault,"cancel flushes without false overlap");cases=cases+1;
        $display("PASS phone window overlap checks=%0d cases=%0d applied=%0d responses=%0d samples=%0d",checks,cases,total_applied,total_response,samples);$finish;
    end
endmodule
