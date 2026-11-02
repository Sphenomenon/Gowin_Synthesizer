`timescale 1ns/1ps
// Real batch adapter + real posted-window TX/RX. The delayed local-clock owner
// is a transport model, not proof of the physical LCD or production PCM owner.
module tb_task3_phone_batch_w;
    reg clk=0,reset_n=0,live=0,capability=0;
    always #5 clk=~clk;
    reg [31:0] token=32'h11223344,local_boot=1,peer_boot=2,session=3,generation=4;
    reg local_valid=0,local_write=0;
    reg [11:0] local_address=0;
    reg [31:0] local_data=0;
    reg [3:0] local_strobes=0;
    wire local_ready,local_error;
    wire [31:0] local_result;
    wire legacy_valid,legacy_write,legacy_ready,legacy_error;
    wire [11:0] legacy_address;
    wire [31:0] legacy_data,legacy_result;
    wire [3:0] legacy_strobes;
    wire request_valid,flush,batch_busy,batch_fault;
    reg request_ready=1,response_valid=0,force_window_busy=0;
    wire [255:0] request_payload;
    wire [5:0] request_length;
    reg [255:0] response_payload=0;
    reg [5:0] response_length=32;
    wire window_busy,window_fault,rx_fault,rx_busy;
    wire proxy_valid,proxy_write,proxy_target;
    wire [11:0] proxy_address;
    wire [31:0] proxy_data;
    wire [3:0] proxy_strobes;
    reg proxy_enable=1,send_enable=1,ack_enable=1,owner_enable=1;
    wire block_valid,ack_valid,ack_error;
    wire [255:0] block_payload;
    wire [5:0] block_length;
    wire [31:0] ack_first,ack_next;
    wire owner_valid;
    wire [11:0] owner_address;
    wire [31:0] owner_data;
    reg owner_ready=0,owner_held=0;
    integer owner_timer=0;
    reg [11:0] held_owner_address;
    reg [31:0] held_owner_data;
    integer checks=0,negative_cases=0,requests=0,proxies=0,applied=0,blocks=0;
    integer total_requests=0,total_proxies=0,total_applied=0,total_blocks=0;
    reg [255:0] last_request,last_reply;
    reg [11:0] last_proxy_address;
    reg [31:0] last_proxy_data;
    reg [3:0] last_proxy_strobes;
    reg last_proxy_write;
    workstation_task3_phone_batch_w #(.TIMEOUT_CYCLES(160)) dut(
        .clk_i(clk),.reset_ni(reset_n),.live_i(live),.capability_i(capability),
        .token_i(token),.local_boot_i(local_boot),.peer_boot_i(peer_boot),.session_i(session),.generation_i(generation),
        .local_valid_i(local_valid),.local_write_i(local_write),.local_address_i(local_address),
        .local_data_i(local_data),.local_strobes_i(local_strobes),
        .local_ready_o(local_ready),.local_response_error_o(local_error),.local_response_data_o(local_result),
        .legacy_valid_o(legacy_valid),.legacy_write_o(legacy_write),.legacy_address_o(legacy_address),
        .legacy_data_o(legacy_data),.legacy_strobes_o(legacy_strobes),.legacy_ready_i(legacy_ready),
        .legacy_response_error_i(legacy_error),.legacy_response_data_i(legacy_result),
        .request_valid_o(request_valid),.request_ready_i(request_ready),.request_payload_o(request_payload),
        .request_length_o(request_length),.response_valid_i(response_valid),.response_payload_i(response_payload),
        .response_length_i(response_length),.window_busy_i(window_busy || force_window_busy),
        .window_flush_o(flush),.busy_o(batch_busy),.fault_o(batch_fault));
    workstation_task3_phone_window_tx #(.TIMEOUT_CYCLES(512),.PARTIAL_FLUSH_CYCLES(100000),.EXTERNAL_FLUSH_ENABLE(1)) tx(
        .clk_i(clk),.reset_ni(reset_n),.session_live_i(live),.armed_i(live&&capability),.flush_i(flush),.token_i(token),
        .local_valid_i(legacy_valid),.local_target_i(1'b0),.local_write_i(legacy_write),
        .local_address_i(legacy_address),.local_data_i(legacy_data),.local_strobes_i(legacy_strobes),
        .local_ready_o(legacy_ready),.local_response_error_o(legacy_error),.local_response_data_o(legacy_result),
        .proxy_valid_o(proxy_valid),.proxy_target_o(proxy_target),.proxy_write_o(proxy_write),
        .proxy_address_o(proxy_address),.proxy_data_o(proxy_data),.proxy_strobes_o(proxy_strobes),
        .proxy_ready_i(proxy_enable),.proxy_response_error_i(proxy_address==12'h03c),.proxy_response_data_i(32'h7eadbeef),
        .block_valid_o(block_valid),.block_ready_i(send_enable),.block_payload_o(block_payload),.block_length_o(block_length),
        .ack_valid_i(ack_valid&&ack_enable),.ack_first_sequence_i(ack_first),.ack_next_sequence_i(ack_next),
        .ack_error_i(ack_error),.busy_o(window_busy),.fault_o(window_fault));
    workstation_task3_phone_window_rx #(.TIMEOUT_CYCLES(512)) rx(
        .clk_i(clk),.reset_ni(reset_n),.session_live_i(live),.armed_i(live&&capability),.token_i(token),
        .block_valid_i(block_valid&&send_enable),.block_payload_i(block_payload),.block_length_i(block_length),
        .command_valid_o(owner_valid),.command_ready_i(owner_ready),.command_address_o(owner_address),
        .command_data_o(owner_data),.command_response_error_i(1'b0),.ack_valid_o(ack_valid),.ack_ready_i(ack_enable),
        .ack_first_sequence_o(ack_first),.ack_next_sequence_o(ack_next),.ack_error_o(ack_error),.busy_o(rx_busy),.fault_o(rx_fault));
    task automatic check(input reg condition,input [511:0] description);
        begin checks=checks+1;if(!condition)$fatal(1,"batch W: %0s",description);end
    endtask
    task automatic ticks(input integer n);
        begin repeat(n)begin @(posedge clk);#1;end end
    endtask
    always @(posedge clk)begin
        if(!reset_n)begin owner_ready<=0;owner_held<=0;owner_timer<=0;end
        else begin
            if(!owner_held && owner_valid && owner_enable)begin
                owner_held<=1;owner_timer<=4;held_owner_address<=owner_address;held_owner_data<=owner_data;
            end else if(owner_held && !owner_ready)begin
                check(owner_valid && owner_address==held_owner_address && owner_data==held_owner_data,"real RX keeps held write");
                if(owner_timer==0)begin owner_ready<=1;applied=applied+1;total_applied=total_applied+1;end
                else owner_timer<=owner_timer-1;
            end else if(owner_ready && !owner_valid)begin
                if(owner_timer==3)begin owner_ready<=0;owner_held<=0;owner_timer<=0;end
                else owner_timer<=owner_timer+1;
            end
            if(request_valid&&request_ready)begin
                check(!window_busy && !force_window_busy,"batch cannot overtake real applied ACK");
                check(request_length==30,"exact batch request length");
                requests=requests+1;total_requests=total_requests+1;last_request=request_payload;
            end
            if(proxy_valid&&proxy_enable)begin
                check(!proxy_target,"only PCM1 target reaches batch");
                proxies=proxies+1;total_proxies=total_proxies+1;
                last_proxy_address=proxy_address;last_proxy_data=proxy_data;last_proxy_strobes=proxy_strobes;last_proxy_write=proxy_write;
            end
            if(block_valid&&send_enable)begin blocks=blocks+1;total_blocks=total_blocks+1;end
        end
    end
    task automatic restart;
        begin
            @(negedge clk);reset_n=0;live=0;capability=0;local_valid=0;response_valid=0;
            token=32'h11223344;local_boot=1;peer_boot=2;session=3;generation=4;
            request_ready=1;force_window_busy=0;proxy_enable=1;send_enable=1;ack_enable=1;owner_enable=1;
            requests=0;proxies=0;applied=0;blocks=0;last_request=0;last_reply=0;
            ticks(3);@(negedge clk);reset_n=1;live=1;capability=1;ticks(4);
            check(!batch_fault&&!window_fault&&!rx_fault,"fresh context");
        end
    endtask
    task automatic begin_local(input reg write,input [11:0] address,input [31:0] data,input [3:0] strobes);
        begin @(negedge clk);local_valid=1;local_write=write;local_address=address;local_data=data;local_strobes=strobes;end
    endtask
    task automatic finish_local(input reg error,input reg verify_data,input [31:0] data);
        integer t;
        begin
            t=0;while(!local_ready && t<700)begin ticks(1);t=t+1;end
            if(!local_ready)$display("missing completion addr=%h write=%b data=%h state=%0d fault=%b requests=%0d",local_address,local_write,local_data,dut.state,batch_fault,requests);
            check(local_ready,"bounded local completion");check(local_error==error,"real completion error preserved");
            if(verify_data)check(local_result==data,"local response data");
            @(negedge clk);local_valid=0;ticks(3);check(!local_ready,"completion released");
        end
    endtask
    task automatic access(input reg write,input [11:0] address,input [31:0] data,input [3:0] strobes,input reg error,input reg verify_data,input [31:0] expected);
        begin begin_local(write,address,data,strobes);finish_local(error,verify_data,expected);end
    endtask
    task automatic write_intent(input [11:0] address,input [31:0] data);
        begin access(1,address,data,4'hf,0,0,0);end
    endtask
    task automatic wait_request(input integer count);
        integer t;
        begin t=0;while(requests<count && t<300)begin ticks(1);t=t+1;end check(requests==count,"single bounded request");end
    endtask
    function automatic [255:0] reply_for(input [31:0] capture);
        reg [31:0] flags;
        begin flags=32'h2c004f00;reply_for={flags,32'h12345678,capture,32'h90000001,32'h34567890,32'h456789ab,last_request[63:32],token};end
    endfunction
    task automatic deliver_reply(input [255:0] payload,input [5:0] length);
        begin @(negedge clk);response_payload=payload;response_length=length;response_valid=1;ticks(1);@(negedge clk);response_valid=0;end
    endtask
    task automatic start_batch(input [31:0] opcode);
        begin begin_local(1,12'h130,opcode,4'hf);wait_request(requests+1);end
    endtask
    task automatic expect_fault;
        begin check(batch_fault && !request_valid && !flush,"failed branch stops traffic");check(!dut.reply_valid && dut.reply==0,"failed branch clears complete reply");negative_cases=negative_cases+1;end
    endtask
    integer i,j,k;
    reg [255:0] changed;
    initial begin
        restart();
        access(0,12'h100,0,0,0,1,32'h50434d42);access(0,12'h104,0,0,0,1,32'h00010000);
        access(0,12'h108,0,0,0,1,1);
        @(negedge clk);capability=0;ticks(2);
        access(0,12'h108,0,0,0,1,0);access(0,12'h100,0,0,0,1,32'h50434d42);
        restart();
        for(i=0;i<8;i=i+1)begin
            access(1,12'h020+12'(i*4),32'hfedc0000+i,4'(i+1),i==7,1,32'h7eadbeef);
            check(last_proxy_address==12'h020+12'(i*4) && last_proxy_data==32'hfedc0000+i && last_proxy_strobes==4'(i+1)&&last_proxy_write,"legacy staging unchanged");
        end
        access(0,12'h024,0,0,0,1,32'h7eadbeef);check(!last_proxy_write,"legacy read unchanged");
        write_intent(12'h110,32'h10203040);write_intent(12'h114,32'h50607080);write_intent(12'h118,32'h90abcdef);
        write_intent(12'h11c,44100);write_intent(12'h120,32'hdeadbeef);write_intent(12'h124,3);
        write_intent(12'h128,128);write_intent(12'h12c,32'hf1234567);
        check(proxies==9,"new intent page never masquerades as legacy staging");
        owner_enable=0;ack_enable=0;
        access(1,12'h800,32'h01234567,4'hf,0,1,0);ticks(8);
        check(window_busy && blocks==0 && applied==0,"one posted word remains pending before explicit flush");
        begin_local(1,12'h130,2,4'hf);ticks(14);
        check(flush && blocks==1 && requests==0 && applied==0,"batch flush waits for actual remote owner");
        owner_enable=1;j=0;while(!ack_valid && j<80)begin ticks(1);j=j+1;end
        check(ack_valid && applied==1 && requests==0 && window_busy,"remote owner completion alone is not ACK receipt");
        ticks(5);check(requests==0,"delayed ACK still fences batch");
        ack_enable=1;wait_request(1);
        check(last_request=={18'd0,8'd128,2'd3,1'b1,3'd2,32'hf1234567,32'hdeadbeef,32'h90abcdef,32'h50607080,32'h10203040,32'd0,32'h11223344},"all frozen full-width request fields");
        last_reply=reply_for(1);deliver_reply(last_reply,32);finish_local(0,1,0);
        check(last_reply[235:232]==15 && !batch_fault,"free field preserves all four unowned slot bits");
        for(i=0;i<8;i=i+1)access(0,12'h140+12'(i*4),0,0,0,1,last_reply[i*32+:32]);
        start_batch(0);check(last_request[63:32]==1,"strict request sequence advances once");
        check(last_request[237:228]==0 && last_request[223:192]==0,"snapshot clears reserved COMMIT descriptor fields");
        last_reply=reply_for(2);last_reply[235:232]=14;last_reply[251:250]=0;deliver_reply(last_reply,32);finish_local(0,0,0);
        check(!batch_fault,"free mask14 means slot0 owned, not an impossible count");
        check(!batch_fault,"actual key mismatch is returned as a fact");
        for(i=0;i<8;i=i+1)access(0,12'h140+12'(i*4),0,0,0,1,last_reply[i*32+:32]);
        for(i=1;i<=5;i=i+1)begin
            if(i!=2)begin
                start_batch(i);check(last_request[237:228]==0 && last_request[223:192]==0,"non-COMMIT clears descriptor without clearing shadow intent");
                changed=reply_for(32'(i+2));changed[235:232]=0;deliver_reply(changed,32);finish_local(0,0,0);
                check(!batch_fault && dut.reply[235:232]==0,"free mask0 means all slots owned");
            end
        end
        start_batch(2);check(last_request[237:230]==128 && last_request[229:228]==3 && last_request[223:192]==32'hf1234567,"later COMMIT retains shadow intent");
        deliver_reply(reply_for(8),32);finish_local(0,0,0);
        // Every malformed response must revoke the cache and never retry.
        for(i=0;i<9;i=i+1)begin
            restart();start_batch(0);changed=reply_for(1);
            case(i)
                0:changed[31:0]=token+1;
                1:changed[63:32]=1;
                2:changed[191:160]=0;
                3:changed[253]=0;
                4:changed[252]=1;
                5:changed=reply_for(1);
                6:changed[245:236]=513;
                7:changed[63:32]=32'hffffffff;
                default:changed=reply_for(1);
            endcase
            deliver_reply(changed,i==8?31:i==5?33:32);finish_local(1,1,0);expect_fault();ticks(10);check(requests==1,"invalid reply has no replay");
        end
        restart();start_batch(0);last_reply=reply_for(5);deliver_reply(last_reply,32);finish_local(0,0,0);
        start_batch(0);deliver_reply(reply_for(5),32);finish_local(1,0,0);expect_fault();
        restart();start_batch(0);last_reply=reply_for(1);deliver_reply(last_reply,32);finish_local(0,0,0);
        deliver_reply(last_reply,32);ticks(1);expect_fault();
        restart();deliver_reply(reply_for(1),32);ticks(1);expect_fault();
        // FLUSH, SEND and WAIT_RESPONSE each share the same bounded budget.
        for(i=0;i<3;i=i+1)begin
            restart();force_window_busy=i==0;request_ready=i!=1;
            begin_local(1,12'h130,0,4'hf);finish_local(1,1,0);expect_fault();
            check(requests==(i==2?1:0),"timeout cannot fabricate or retry request");
        end
        restart();request_ready=0;begin_local(1,12'h130,0,4'hf);ticks(3);
        check(request_valid,"SEND is held until ready");deliver_reply(reply_for(1),32);finish_local(1,0,0);expect_fault();
        // Context and PANIC fences are immediate and cannot reopen on same ID.
        for(i=0;i<7;i=i+1)begin
            restart();start_batch(0);@(negedge clk);
            case(i)
                0:live=0;
                1:capability=0;
                2:token=token+1;
                3:local_boot=local_boot+1;
                4:peer_boot=peer_boot+1;
                5:session=session+1;
                6:generation=generation+1;
            endcase
            #1;check(!request_valid&&!flush,"same-edge context output fence");ticks(1);finish_local(1,0,0);expect_fault();
        end
        restart();start_batch(0);@(negedge clk);live=0;ticks(1);finish_local(1,0,0);
        @(negedge clk);live=1;ticks(4);access(0,12'h108,0,0,0,1,0);
        check(batch_fault,"same identity cannot restart sequence zero");
        @(negedge clk);live=0;ticks(2);@(negedge clk);token=token+1;session=session+1;live=1;ticks(4);
        access(0,12'h108,0,0,0,1,1);start_batch(0);check(last_request[63:32]==0,"new paired identity starts fresh sequence");
        deliver_reply(reply_for(1),32);finish_local(0,0,0);
        // Changing or withdrawing the held command cannot produce a second op.
        for(i=0;i<6;i=i+1)begin
            restart();request_ready=0;begin_local(1,12'h130,0,4'hf);ticks(3);@(negedge clk);
            case(i)
                0:local_valid=0;
                1:local_write=0;
                2:local_address=12'h12c;
                3:local_data=1;
                4:local_strobes=1;
                5:local_address=12'h020;
            endcase
            #1;check(!request_valid,"held command overlap blocks SEND immediately");ticks(1);
            if(i!=0)finish_local(1,0,0);else ticks(3);
            expect_fault();check(requests==0,"overlap has no request");
        end
        restart();proxy_enable=0;begin_local(1,12'h020,1,4'hf);ticks(3);@(negedge clk);local_address=12'h024;
        #1;check(!legacy_valid,"changed held legacy command cannot escape");ticks(1);finish_local(1,0,0);expect_fault();
        // Illegal virtual writes do not become legacy traffic or stale state.
        for(i=0;i<9;i=i+1)begin
            restart();
            case(i)
                0:begin_local(1,12'h110,1,1);
                1:begin_local(1,12'h111,1,4'hf);
                2:begin_local(1,12'h124,4,4'hf);
                3:begin_local(1,12'h128,129,4'hf);
                4:begin_local(1,12'h11c,32000,4'hf);
                5:begin_local(1,12'h130,6,4'hf);
                6:begin_local(1,12'h130,2,4'hf);
                7:begin_local(0,12'h140,0,0);
                8:begin_local(0,12'h10c,0,0);
            endcase
            finish_local(1,0,0);expect_fault();check(proxies==0&&requests==0,"invalid virtual command cannot leak");
        end
        // Sequence exhaustion cannot wrap or replay an old accepted sequence.
        restart();dut.next_sequence=32'hffffffff;begin_local(1,12'h130,0,4'hf);finish_local(1,0,0);expect_fault();
        check(total_applied==1 && total_blocks==1,"real explicit flush coverage");
        $display("PHONE_BATCH_W checks=%0d requests=%0d proxies=%0d applied=%0d blocks=%0d negative_cases=%0d",checks,total_requests,total_proxies,total_applied,total_blocks,negative_cases);
        $display("PASS task3_phone_batch_w");$finish;
    end
    initial begin #2000000;$fatal(1,"batch W test timeout");end
endmodule
