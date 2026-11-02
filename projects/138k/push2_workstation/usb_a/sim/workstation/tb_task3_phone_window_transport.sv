`timescale 1ns/1ps
// Local-clock transport contract test. The owner model deliberately holds
// ready after valid drops; this is not a physical LCD or real PCM-owner test.
module tb_task3_phone_window_transport;
    reg clk=0,reset_n=0,session_live=0,armed=0;
    always #5 clk=~clk;
    reg [31:0] token=32'h18;
    reg local_valid=0,local_target=0,local_write=0;
    reg [11:0] local_address=0;
    reg [31:0] local_data=0;
    reg [3:0] local_strobes=0;
    wire local_ready,local_error;
    wire [31:0] local_result;
    wire proxy_valid,proxy_target,proxy_write;
    wire [11:0] proxy_address;
    wire [31:0] proxy_data;
    wire [3:0] proxy_strobes;
    reg proxy_enable=1,send_enable=1,ack_enable=1,manual_rx=0;
    wire proxy_ready=proxy_valid && proxy_enable;
    wire tx_block_valid,tx_block_ready,rx_ack_valid,rx_ack_ready;
    wire [255:0] tx_payload;
    wire [5:0] tx_length;
    wire [31:0] rx_ack_first,rx_ack_next;
    wire rx_ack_error,tx_busy,tx_fault,rx_busy,rx_fault;
    reg inject_block=0,inject_ack=0;
    reg [255:0] injected_payload=0;
    reg [5:0] injected_length=0;
    reg [31:0] injected_ack_first=0,injected_ack_next=0;
    reg injected_ack_error=0;
    assign tx_block_ready=send_enable;
    assign rx_ack_ready=ack_enable;
    wire receive_block=inject_block || (!manual_rx && tx_block_valid && tx_block_ready);
    wire [255:0] receive_payload=inject_block?injected_payload:tx_payload;
    wire [5:0] receive_length=inject_block?injected_length:tx_length;
    wire receive_ack=inject_ack || (rx_ack_valid && rx_ack_ready);
    wire command_valid;
    wire [11:0] command_address;
    wire [31:0] command_data;
    reg owner_ready=0,owner_error=0,owner_enable=1,hold_ready_forever=0;
    reg owner_busy=0;
    integer owner_delay=0,release_delay=0;
    reg [11:0] owner_address;
    reg [31:0] owner_data;
    reg [11:0] expected_addresses[0:127];
    reg [31:0] expected_words[0:127];
    integer expected=0,applied=0,checks=0,blocks=0,proxies=0,cycles=0;
    integer total_words=0,total_blocks=0,total_proxies=0,negative_cases=0;
    reg check_owner=1;
    workstation_task3_phone_window_tx #(.TIMEOUT_CYCLES(256),.PARTIAL_FLUSH_CYCLES(16)) tx(
        .flush_i(1'b0),
        .clk_i(clk),.reset_ni(reset_n),.session_live_i(session_live),.armed_i(armed),.token_i(token),
        .local_valid_i(local_valid),.local_target_i(local_target),.local_write_i(local_write),
        .local_address_i(local_address),.local_data_i(local_data),.local_strobes_i(local_strobes),
        .local_ready_o(local_ready),.local_response_error_o(local_error),.local_response_data_o(local_result),
        .proxy_valid_o(proxy_valid),.proxy_target_o(proxy_target),.proxy_write_o(proxy_write),
        .proxy_address_o(proxy_address),.proxy_data_o(proxy_data),.proxy_strobes_o(proxy_strobes),
        .proxy_ready_i(proxy_ready),.proxy_response_error_i(1'b0),.proxy_response_data_i(32'h7eadbeef),
        .block_valid_o(tx_block_valid),.block_ready_i(tx_block_ready),.block_payload_o(tx_payload),.block_length_o(tx_length),
        .ack_valid_i(receive_ack),.ack_first_sequence_i(inject_ack?injected_ack_first:rx_ack_first),
        .ack_next_sequence_i(inject_ack?injected_ack_next:rx_ack_next),
        .ack_error_i(inject_ack?injected_ack_error:rx_ack_error),.busy_o(tx_busy),.fault_o(tx_fault));
    workstation_task3_phone_window_rx #(.TIMEOUT_CYCLES(256)) rx(
        .clk_i(clk),.reset_ni(reset_n),.session_live_i(session_live),.armed_i(armed),.token_i(token),
        .block_valid_i(receive_block),.block_payload_i(receive_payload),.block_length_i(receive_length),
        .command_valid_o(command_valid),.command_ready_i(owner_ready),
        .command_address_o(command_address),.command_data_o(command_data),.command_response_error_i(owner_error),
        .ack_valid_o(rx_ack_valid),.ack_ready_i(rx_ack_ready),.ack_first_sequence_o(rx_ack_first),
        .ack_next_sequence_o(rx_ack_next),.ack_error_o(rx_ack_error),.busy_o(rx_busy),.fault_o(rx_fault));
    task automatic check(input reg condition,input [255:0] description);
        begin checks=checks+1;if(!condition)$fatal(1,"contract: %0s",description);end
    endtask
    task automatic ticks(input integer n);
        begin repeat(n)begin @(posedge clk);#1;end end
    endtask
    task automatic restart;
        begin
            @(negedge clk);reset_n=0;session_live=0;armed=0;local_valid=0;
            inject_block=0;inject_ack=0;send_enable=1;ack_enable=1;manual_rx=0;
            proxy_enable=1;owner_enable=1;hold_ready_forever=0;owner_error=0;check_owner=1;
            expected=0;applied=0;blocks=0;proxies=0;token=32'h18;
            ticks(3);@(negedge clk);reset_n=1;session_live=1;ticks(3);
        end
    endtask
    task automatic arm;
        begin @(negedge clk);armed=1;ticks(3);check(!tx_fault&&!rx_fault,"fresh arm");end
    endtask
    task automatic begin_command(input reg target,input reg write,input [11:0] address,input [31:0] data,input [3:0] strobes);
        begin
            @(negedge clk);local_valid=1;local_target=target;local_write=write;
            local_address=address;local_data=data;local_strobes=strobes;
        end
    endtask
    task automatic finish_command(input reg error);
        integer t;reg [31:0] result;
        begin
            t=0;while(!local_ready && t<1000)begin ticks(1);t=t+1;end
            check(local_ready,"bounded local completion");check(local_error==error,"local completion scope/error");
            result=local_result;ticks(3);check(local_ready&&local_error==error&&local_result==result,"held local response stable");
            @(negedge clk);local_valid=0;ticks(3);check(!local_ready,"local response released");
        end
    endtask
    task automatic post(input [11:0] address,input [31:0] word);
        begin
            expected_addresses[expected]=address;expected_words[expected]=word;expected=expected+1;
            begin_command(0,1,address,word,4'hf);finish_command(0);
        end
    endtask
    task automatic drain;
        begin begin_command(0,0,12'h014,0,0);finish_command(0);check(applied==expected,"barrier waits every owner write");check(local_result==32'h7eadbeef,"real proxy result");end
    endtask
    function automatic [255:0] packet(input [31:0] base,input [31:0] seq,input [31:0] context_token,input [159:0] data);
        packet={data,base,seq,context_token};
    endfunction
    task automatic offer(input [255:0] payload,input [5:0] length);
        begin @(negedge clk);inject_block=1;injected_payload=payload;injected_length=length;ticks(1);@(negedge clk);inject_block=0;end
    endtask
    task automatic rejected(input [255:0] payload,input [5:0] length);
        begin
            restart();arm();manual_rx=1;offer(payload,length);ticks(2);
            check(rx_fault,"malformed block faults");negative_cases=negative_cases+1;
        end
    endtask
    always @(posedge clk)begin
        cycles<=cycles+1;
        if(cycles>50000)$fatal(1,"global test timeout");
        if(!reset_n)begin owner_ready<=0;owner_busy<=0;owner_delay<=0;release_delay<=0;end
        else begin
            if(tx_block_valid && tx_block_ready)begin blocks<=blocks+1;total_blocks<=total_blocks+1;end
            if(proxy_valid && proxy_ready)begin
                proxies<=proxies+1;total_proxies<=total_proxies+1;
                if(check_owner)check(applied==expected,"proxy cannot overtake queued words");
            end
            if(!owner_ready && !owner_busy && command_valid && owner_enable)begin
                owner_busy<=1;owner_delay<=3;owner_address<=command_address;owner_data<=command_data;
            end else if(owner_busy && !owner_ready)begin
                check(command_valid&&command_address==owner_address&&command_data==owner_data,"owner request stable");
                if(owner_delay==0)begin
                    owner_ready<=1;release_delay<=3;
                    if(check_owner)begin
                        check(applied<expected,"no duplicate or unsolicited write");
                        check(owner_address==expected_addresses[applied]&&owner_data==expected_words[applied],"exact owner write order/address/data");
                    end
                    applied<=applied+1;total_words<=total_words+1;
                end else owner_delay<=owner_delay-1;
            end else if(owner_ready && !command_valid && !hold_ready_forever)begin
                if(release_delay==0)begin owner_ready<=0;owner_busy<=0;end
                else release_delay<=release_delay-1;
            end
        end
    end
    integer i,t;
    initial begin
        // A first command may be captured on the very edge that qualifies
        // the link as absent. Both a one-cycle offer and held APB valid must
        // drain locally with an error, without waiting for remote service.
        restart();@(negedge clk);session_live=0;
        begin_command(0,0,12'h000,0,0);ticks(1);
        @(negedge clk);local_valid=0;ticks(1);
        check(local_ready&&local_error,"offline one-cycle command drains");
        ticks(3);check(!local_ready&&!tx_busy&&!tx_fault,"offline one-cycle response releases");
        begin_command(1,1,12'h02c,32'h11,4'hf);finish_command(1);
        check(!tx_busy&&!tx_fault&&!proxy_valid,"offline held valid drains without proxy");
        restart();arm();
        @(negedge clk);session_live=0;local_valid=1;local_target=0;local_write=1;
        local_address=12'h800;local_data=32'h12345678;local_strobes=4'hf;
        finish_command(1);check(!tx_busy&&!tx_block_valid&&!tx_fault,"same-edge disconnect and first posted write drains");
        restart();
        begin_command(1,1,12'h02c,32'h11,4'hf);finish_command(0);
        begin_command(0,1,12'h800,32'h22,4'hf);finish_command(0);
        begin_command(0,0,12'h000,0,0);finish_command(0);
        check(proxies==3&&!tx_fault&&!tx_block_valid,"unarmed reads and writes remain original RPC");
        arm();send_enable=0;
        for(i=0;i<10;i=i+1)post(12'h800+12'(i*4),32'h1000+32'(i));
        check(applied==0&&tx_busy,"ten bounded admissions before owner");
        expected_addresses[expected]=12'h900;expected_words[expected]=32'h7000;expected=expected+1;
        begin_command(0,1,12'h900,32'h7000,4'hf);ticks(8);check(!local_ready,"eleventh admission backpressured");
        send_enable=1;finish_command(0);
        post(12'hffc,32'h7fffffff);post(12'h808,32'h01802033);drain();
        check(!tx_fault&&!rx_fault,"sequential and discontinuous runs");check(blocks>=4,"partial discontinuity flush exercised");
        // Clock, partial-strobe and unaligned window writes retain barriers.
        post(12'h920,32'h11223344);begin_command(1,1,12'h014,32'h42,4'hf);finish_command(0);
        post(12'h924,32'h55667788);begin_command(0,1,12'h928,32'h42,4'h3);finish_command(0);
        post(12'h928,32'habcdef01);begin_command(0,1,12'h92a,32'h42,4'hf);finish_command(0);
        check(applied==expected&&!tx_fault&&!rx_fault,"all nonposted classes barrier");
        // No COMMIT is needed to flush the final short idle aggregate.
        post(12'h930,32'h43);ticks(80);check(applied==expected&&!tx_busy&&!rx_busy,"partial idle flush");
        // Link loss clears both partial and in-flight state; a new arm uses sequence zero.
        send_enable=0;post(12'h934,32'h44);@(negedge clk);session_live=0;armed=0;ticks(3);
        check(!tx_busy&&!rx_busy&&!tx_fault&&!rx_fault,"link cancellation flushes state");
        @(negedge clk);session_live=1;token=32'h19;send_enable=1;expected=applied;arm();post(12'h938,32'h45);drain();

        rejected(packet(32'h800,0,32'h18,160'h1),6'd12);
        rejected(packet(32'h800,0,32'h18,160'h1),6'd17);
        rejected(packet(32'h800,0,32'h18,160'h1),6'd36);
        rejected(packet(32'h801,0,32'h18,160'h1),6'd16);
        rejected(packet(32'h7fc,0,32'h18,160'h1),6'd16);
        rejected(packet(32'h10000800,0,32'h18,160'h1),6'd16);
        rejected(packet(32'hffc,0,32'h18,160'h1),6'd20);
        rejected(packet(32'h800,1,32'h18,160'h1),6'd16);
        rejected(packet(32'h800,0,32'h17,160'h1),6'd16);
        rejected(packet(32'h800,0,32'h18,160'h100000001),6'd16);
        restart();arm();manual_rx=1;check_owner=0;owner_enable=0;
        offer(packet(32'h800,0,32'h18,160'h1),16);offer(packet(32'h804,1,32'h18,160'h2),16);
        ticks(2);check(rx_fault,"busy packet consumed and faults");negative_cases=negative_cases+1;
        restart();arm();manual_rx=1;owner_enable=0;check_owner=0;
        offer(packet(32'h800,0,32'h18,160'h1),16);ticks(270);check(rx_fault&&!command_valid,"owner timeout bounded");negative_cases=negative_cases+1;
        restart();arm();owner_error=1;post(12'h800,32'hf0);ticks(80);
        check(rx_fault&&tx_fault,"real owner error propagates");negative_cases=negative_cases+1;
        restart();arm();send_enable=0;for(i=0;i<5;i=i+1)post(12'h800+12'(i*4),32'(i));
        ticks(270);check(tx_fault&&!tx_block_valid,"send timeout bounded");negative_cases=negative_cases+1;
        restart();arm();manual_rx=1;for(i=0;i<5;i=i+1)post(12'h800+12'(i*4),32'(i));
        ticks(270);check(tx_fault,"ACK timeout bounded");negative_cases=negative_cases+1;
        restart();arm();manual_rx=1;for(i=0;i<5;i=i+1)post(12'h800+12'(i*4),32'(i));
        t=0;while(blocks==0&&t<100)begin ticks(1);t=t+1;end
        @(negedge clk);inject_ack=1;injected_ack_first=1;injected_ack_next=5;ticks(1);
        @(negedge clk);inject_ack=0;ticks(2);check(tx_fault,"wrong ACK sequence faults");negative_cases=negative_cases+1;
        restart();arm();proxy_enable=0;begin_command(0,0,12'h014,0,0);finish_command(1);
        check(tx_fault,"proxy barrier timeout bounded");negative_cases=negative_cases+1;
        @(negedge clk);armed=0;ticks(3);check(tx_fault,"fault sticks across dearm");
        @(negedge clk);armed=1;token=32'h20;ticks(3);check(!tx_fault&&!rx_fault,"new arm clears fault");
        @(negedge clk);token=32'h21;ticks(2);check(tx_fault&&rx_fault,"live token change faults");negative_cases=negative_cases+1;
        restart();token=0;@(negedge clk);armed=1;ticks(3);check(tx_fault&&rx_fault,"zero arm token rejected");negative_cases=negative_cases+1;
        $display("PHONE_WINDOWS checks=%0d words=%0d blocks=%0d proxies=%0d negative_cases=%0d",checks,total_words,total_blocks,total_proxies,negative_cases);
        $display("PASS task3_phone_window_transport");$finish;
    end
endmodule
