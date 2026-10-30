`timescale 1ns/1ps
module tb_workstation_hci_event_decoder;
    reg clk_i=0;always #5 clk_i=~clk_i;
    reg reset_ni=0,packet_valid_i=0,packet_release_i=0;
    reg [8:0] packet_length_i=0;
    wire [8:0] packet_read_address_o;
    reg [7:0] packet_read_data_i=0;
    reg [7:0] memory [0:511];
    always @(posedge clk_i)packet_read_data_i<=memory[packet_read_address_o];
    wire packet_consume_o,packet_done_o,fault_o;
    wire [7:0] packet_event_o;
    wire [3:0] fault_reason_o;
    wire handle_open_o,handle_close_o,handle_is_le_o,handle_open_ready_i,handle_admitted_o;
    wire [11:0] handle_o;
    wire [31:0] handle_open_generation_i,handle_generation_o;
    wire completion_start_o,completion_pair_valid_o,completion_commit_o;
    wire [11:0] completion_handle_o;
    wire [15:0] completion_count_o;
    wire command_response_o;
    wire [7:0] response_credits_o,response_status_o;
    wire [15:0] response_opcode_o;
    wire buffer_info_valid_o,buffer_info_is_le_o;
    wire [15:0] buffer_info_length_o,buffer_info_count_o;
    workstation_hci_event_decoder decoder(.*);
    reg config_valid=0;
    wire configured,owner_fault;
    wire [3:0] owner_fault_reason;
    wire [15:0] br_available,le_available;
    wire [1:0] active;
    wire [31:0] outstanding;
    reg acl_valid=0,acl_send=0;
    reg [11:0] acl_handle=0;
    reg [31:0] acl_generation=0;
    reg [15:0] acl_length=1;
    wire acl_ready;
    reg command_valid=0,command_send=0;
    reg [1:0] command_owner=0;
    reg [15:0] command_opcode=0;
    wire command_ready,owner_response;
    wire [1:0] response_owner;
    wire [7:0] owner_status;
    workstation_hci_flow_owner owner(
        .clk_i(clk_i),.reset_ni(reset_ni),.transport_fault_i(fault_o),
        .config_valid_i(config_valid),.br_acl_length_i(16'd1021),.br_acl_count_i(16'd3),
        .le_acl_length_i(16'd27),.le_acl_count_i(16'd2),.configured_o(configured),
        .fault_o(owner_fault),.fault_reason_o(owner_fault_reason),
        .br_available_o(br_available),.le_available_o(le_available),
        .handle_open_i(handle_open_o),.handle_close_i(handle_close_o),.handle_is_le_i(handle_is_le_o),
        .handle_i(handle_o),.handle_open_ready_o(handle_open_ready_i),
        .handle_open_generation_o(handle_open_generation_i),.handle_active_o(active),.handle_outstanding_o(outstanding),
        .acl_valid_i(acl_valid),.acl_send_i(acl_send),.acl_handle_i(acl_handle),
        .acl_generation_i(acl_generation),.acl_data_length_i(acl_length),.acl_ready_o(acl_ready),
        .completion_start_i(completion_start_o),.completion_pair_valid_i(completion_pair_valid_o),
        .completion_handle_i(completion_handle_o),.completion_count_i(completion_count_o),
        .completion_commit_i(completion_commit_o),.completion_abort_i(1'b0),
        .command_valid_i(command_valid),.command_send_i(command_send),.command_owner_i(command_owner),
        .command_opcode_i(command_opcode),.command_ready_o(command_ready),
        .command_response_i(command_response_o),.command_timeout_i(1'b0),
        .response_credits_i(response_credits_o),.response_status_i(response_status_o),
        .response_opcode_i(response_opcode_o),.response_valid_o(owner_response),
        .response_owner_o(response_owner),.response_status_o(owner_status)
    );
    integer checks=0,events=0,responses=0,opens=0,closes=0,pairs=0,commits=0,buffer_infos=0;
    reg [31:0] br_generation,le_generation;
    reg [15:0] seen_buffer_length,seen_buffer_count;
    reg seen_buffer_le;
    always @(posedge clk_i)begin
        if(reset_ni)begin
            if(owner_response)responses=responses+1;
            if(handle_open_o)opens=opens+1;
            if(handle_close_o)closes=closes+1;
            if(completion_pair_valid_o)pairs=pairs+1;
            if(completion_commit_o)commits=commits+1;
            if(buffer_info_valid_o)begin
                buffer_infos=buffer_infos+1;seen_buffer_length=buffer_info_length_o;
                seen_buffer_count=buffer_info_count_o;seen_buffer_le=buffer_info_is_le_o;
            end
        end
    end
    task check;input condition;input [767:0] text;
        begin checks=checks+1;if(condition!==1'b1)begin $display("FAIL %0s event=%0d t=%0t",text,events,$time);$fatal(1);end end
    endtask
    task tick;begin @(posedge clk_i);#1;end endtask
    task reset_all;
        begin
            reset_ni=0;packet_valid_i=0;packet_release_i=0;config_valid=0;
            acl_valid=0;acl_send=0;command_valid=0;command_send=0;tick();tick();reset_ni=1;tick();
            config_valid=1;tick();config_valid=0;#1;
            check(configured&&!fault_o&&!owner_fault&&active==0,"fresh isolated controller ledger");
            responses=0;opens=0;closes=0;pairs=0;commits=0;buffer_infos=0;
        end
    endtask
    task packet;input [7:0] event_code;input integer bytes;
        begin
            for(integer at=0;at<512;at=at+1)memory[at]=0;
            memory[0]=event_code;memory[1]=bytes-2;packet_length_i=bytes;
        end
    endtask
    task receive;input good;
        integer waited;
        begin
            events=events+1;packet_valid_i=1;waited=0;
            while(!packet_done_o&&!fault_o&&waited<1100)begin tick();waited=waited+1;end
            check(waited<1100,"bounded event parser service");
            if(good)begin
                check(packet_done_o&&!fault_o,"valid event fully checked before external release");
                check(!packet_consume_o,"packet RAM retained until bounded router releases");
                tick();
            end else begin
                check(fault_o&&!packet_done_o,"bad event never published as validated");tick();
                check(owner_fault&&owner_fault_reason==1,"malformed critical event fences accounting instead of guessed refund");
            end
        end
    endtask
    task release_packet;
        begin
            packet_release_i=1;tick();packet_release_i=0;packet_valid_i=0;
            check(packet_consume_o&&!packet_done_o,"explicit router release consumes once");tick();
            check(!packet_consume_o,"consume pulse does not repeat");
        end
    endtask
    task br_connect;input [11:0] number;
        begin packet(8'h03,13);memory[3]=number[7:0];memory[4]={4'd0,number[11:8]};memory[11]=1;
            receive(1);check(handle_admitted_o&&handle_generation_o!=0,"BR ACL admitted with exact PL generation");
            br_generation=handle_generation_o;release_packet();end
    endtask
    task send_acl;input [11:0] number;input [31:0] generation;
        begin acl_handle=number;acl_generation=generation;acl_valid=1;#1;check(acl_ready,"physical fragment gets one shared owner grant");
            acl_send=1;tick();acl_send=0;acl_valid=0;end
    endtask
    task send_command;input [15:0] opcode;input [1:0] who;
        begin command_opcode=opcode;command_owner=who;command_valid=1;#1;check(command_ready,"command serialization accepts exact owner");
            command_send=1;tick();command_send=0;command_valid=0;end
    endtask
    initial begin
        reset_all();br_connect(12'h042);
        packet(8'h3e,21);memory[2]=1;memory[4]=8'h31;receive(1);
        check(handle_admitted_o&&handle_generation_o>br_generation&&active==3,"LE creation uses separate monotonic generation");
        le_generation=handle_generation_o;release_packet();
        send_acl(12'h042,br_generation);send_acl(12'h031,le_generation);
        check(br_available==2&&le_available==1,"dedicated physical pool debit");
        packet(8'h13,11);memory[2]=2;memory[3]=8'h42;memory[5]=1;memory[7]=8'h31;memory[9]=1;
        receive(1);check(br_available==3&&le_available==2&&pairs==2&&commits==1,"raw NCP refunds exact two handles atomically");release_packet();
        send_acl(12'h042,br_generation);packet(8'h05,6);memory[3]=8'h42;memory[5]=8'h13;
        receive(1);check(active==2&&br_available==3&&closes==1,"raw successful disconnect reclaims outstanding controller buffers");release_packet();
        packet(8'h05,6);memory[2]=1;memory[3]=8'h31;receive(1);
        check(active==2&&closes==1,"failed disconnect response does not close live LE");release_packet();

        reset_all();send_command(16'h1005,0);packet(8'h0e,13);memory[2]=1;memory[3]=5;memory[4]=8'h10;
        memory[6]=8'hfd;memory[7]=3;memory[9]=7;receive(1);
        check(responses==1&&response_owner==0&&buffer_infos==1&&!seen_buffer_le&&seen_buffer_length==1021&&seen_buffer_count==7,"BR ReadBufferSize parsed in native little endian");release_packet();
        send_command(16'h2002,0);packet(8'h0e,9);memory[2]=1;memory[3]=2;memory[4]=8'h20;memory[6]=27;
        receive(1);check(responses==2&&buffer_infos==2&&seen_buffer_le&&seen_buffer_length==27&&seen_buffer_count==0,"LE zero packet count preserved for shared BR pool policy");release_packet();
        send_command(16'h0409,2);packet(8'h0f,6);memory[2]=8'h0c;memory[3]=1;memory[4]=9;memory[5]=4;
        receive(1);check(responses==3&&response_owner==2&&owner_status==8'h0c,"raw CommandStatus failure routed to CPU owner");release_packet();
        packet(8'h0e,5);memory[2]=1;receive(1);check(responses==3,"opcode-zero quota event never retires pending transaction");release_packet();

        reset_all();packet(8'h3e,33);memory[2]=10;memory[4]=8'h42;receive(1);
        check(handle_admitted_o&&handle_is_le_o,"LE enhanced v1 connection event supported");release_packet();
        packet(8'hff,257);receive(1);check(packet_event_o==8'hff&&opens==1,"max sized vendor event preserves bounded raw routing");release_packet();
        packet(8'h13,3);memory[2]=0;receive(1);check(pairs==0&&commits==1,"empty NCP batch is legal");release_packet();
        packet(8'h13,255);memory[2]=63;
        for(integer p=0;p<63;p=p+1)memory[3+p*4]=8'h42;
        receive(1);check(pairs==63&&commits==2&&!owner_fault,"63-pair maximum event validated");release_packet();

        // Every alternative outer-consistent length for these fixed schemas.
        for(integer kind=0;kind<7;kind=kind+1)begin
            for(integer n=0;n<259;n=n+1)begin
                if(!((kind==0&&n==13)||(kind==1&&n==6)||(kind==2&&n==6)||
                    (kind==3&&n==21)||(kind==4&&n==33)||(kind==5&&n==13)||(kind==6&&n==9)))begin
                    reset_all();
                    case(kind)
                        0: begin packet(8'h03,n);memory[11]=1;end
                        1: packet(8'h05,n);
                        2: packet(8'h0f,n);
                        3: begin packet(8'h3e,n);memory[2]=1;end
                        4: begin packet(8'h3e,n);memory[2]=10;end
                        5: begin packet(8'h0e,n);memory[3]=5;memory[4]=8'h10;end
                        6: begin packet(8'h0e,n);memory[3]=2;memory[4]=8'h20;end
                    endcase
                    receive(0);check(opens==0&&closes==0&&responses==0&&commits==0,"invalid schema has no lifecycle or completion side effect");
                end
            end
        end
        reset_all();br_connect(12'h042);send_acl(12'h042,br_generation);
        packet(8'h13,11);memory[2]=2;memory[3]=8'h42;memory[5]=1;memory[7]=8'h31;memory[8]=8'hf0;
        receive(0);check(br_available==2&&commits==0&&pairs==1,"late reserved handle rejects whole batch without partial refund");
        reset_all();packet(8'h13,7);memory[2]=2;receive(0);check(commits==0,"NCP count and event length must agree");
        reset_all();packet(8'h13,259);memory[2]=64;receive(0);
        reset_all();packet(8'h03,13);memory[11]=1;memory[4]=8'h0f;receive(0);
        reset_all();packet(8'h03,13);memory[11]=1;memory[4]=8'h10;receive(0);
        reset_all();packet(8'hff,3);memory[1]=0;receive(0);check(fault_reason_o==1,"wire parameter length must match immutable packet length");
        reset_all();packet(8'h00,2);receive(0);
        reset_all();packet(8'h03,13);memory[2]=8'h3e;memory[11]=1;receive(1);check(opens==0,"failed connection does not open arbitrary returned handle");release_packet();
        reset_all();packet(8'h10,3);receive(0);check(fault_reason_o==5,"controller hardware error is a fail closed boundary");
        reset_all();packet(8'h1a,3);receive(0);
        reset_all();packet(8'h03,13);packet_valid_i=1;tick();tick();packet_length_i=12;tick();
        check(fault_o&&fault_reason_o==4,"packet memory lifetime cannot change during validation");
        $display("PASS checks=%0d events=%0d exhaustive_schema_lengths=1806",checks,events);$finish;
    end
    initial begin #100000000;$fatal(1,"watchdog");end
endmodule
