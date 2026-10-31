`timescale 1ns/1ps
// Actual native owner, bootstrap, decoder, ledgers, packet RAMs and BLE bridge.
// The external H5 fixture retains the real registered read/two-clock copy ABI.
module tb_workstation_hci_native_transport #(parameter bit SESSION_ONLY_PAIRING=0,SESSION_CONTRACT_ONLY=0);
    reg clk=0,resetn=0,observer_reset=1,initialized=0;
    reg [63:0] boot_id=64'h8877665544332211;
    always #5 clk=~clk;
    wire boot_ready,fault,fenced,classic_active,classic_ready;
    wire [31:0] epoch,generation;
    wire [15:0] ble_limit;
    wire tx_start,tx_ready,tx_done;
    wire [3:0] tx_type;
    wire [8:0] tx_length,rx_address;
    wire [7:0] tx_data;
    reg [8:0] tx_address=0;
    reg model_pending=0,model_copy=0,model_wait=1,hold_transport=0,model_done=0;
    reg [3:0] model_type;
    reg [8:0] model_length;
    reg [7:0] sent [0:279],incoming [0:279];
    reg rx_valid=0;
    reg [3:0] rx_type=4;
    reg [8:0] rx_length=0;
    reg [7:0] rx_data;
    wire rx_consume;
    integer commands=0,boot_commands=0,le_packets=0,br_packets=0,returns=0,disconnects=0,le_payload_offset=0;
    reg [15:0] auto_opcode=0;
    reg auto_pending=0,controller_busy=0;
    wire ble_tx_start,ble_tx_ready,ble_tx_done,ble_tx_error;
    wire [3:0] ble_tx_type,ble_rx_type;
    wire [8:0] ble_tx_length,ble_tx_address,ble_rx_length,ble_rx_address;
    wire [7:0] ble_tx_data,ble_rx_data;
    wire ble_rx_valid,ble_rx_consume;
    reg app_tx_start=0,app_rx_consume=0;
    reg [3:0] app_tx_type=2;
    reg [8:0] app_tx_length=0,app_rx_address=0;
    wire [8:0] app_tx_address,app_rx_length;
    reg [7:0] app_tx_data;
    reg [7:0] app_bytes [0:263];
    wire app_tx_ready,app_tx_done,app_tx_error,app_rx_valid;
    wire [3:0] app_rx_type;
    wire [7:0] app_rx_data;
    reg bus_valid=0,bus_write=0;
    reg [11:0] bus_address=0;
    reg [31:0] bus_data=0;
    wire bus_ready,bus_error;
    wire [31:0] bus_read;
    integer checks=0,logical_done=0;
    always @(posedge clk)if(app_tx_done)logical_done=logical_done+1;
    workstation_hci_native_transport #(.SESSION_ONLY_PAIRING(SESSION_ONLY_PAIRING),.CLK_HZ(1000),.BOOTSTRAP_TIMEOUT_CYCLES(2000),.COMMAND_TIMEOUT_CYCLES(20000)) dut (
        .clk_i(clk),.reset_ni(resetn),.enable_i(1'b1),.observer_reset_ni(observer_reset),
        .link_up_i(1'b1),.physical_fault_i(1'b0),.boot_id_i(boot_id),
        .initializer_handoff_i(1'b1),.initialized_i(initialized),.host_flow_ready_o(boot_ready),
        .controller_epoch_o(epoch),.classic_generation_o(generation),.classic_active_o(classic_active),.classic_ready_o(classic_ready),
        .fault_o(fault),.classic_fenced_o(fenced),.ble_acl_limit_o(ble_limit),
        .init_tx_start_i(1'b0),.init_tx_type_i(4'd1),.init_tx_length_i(9'd3),.init_tx_address_o(),
        .init_tx_data_i(8'd0),.init_tx_ready_o(),.init_tx_done_o(),.init_tx_error_o(),
        .init_rx_valid_o(),.init_rx_type_o(),.init_rx_length_o(),.init_rx_address_i(9'd0),.init_rx_data_o(),.init_rx_consume_i(1'b0),
        .ble_tx_start_i(ble_tx_start),.ble_tx_type_i(ble_tx_type),.ble_tx_length_i(ble_tx_length),
        .ble_tx_address_o(ble_tx_address),.ble_tx_data_i(ble_tx_data),.ble_tx_ready_o(ble_tx_ready),
        .ble_tx_done_o(ble_tx_done),.ble_tx_error_o(ble_tx_error),.ble_rx_valid_o(ble_rx_valid),
        .ble_rx_type_o(ble_rx_type),.ble_rx_length_o(ble_rx_length),.ble_rx_address_i(ble_rx_address),
        .ble_rx_data_o(ble_rx_data),.ble_rx_consume_i(ble_rx_consume),
        .h5_tx_start_o(tx_start),.h5_tx_type_o(tx_type),.h5_tx_length_o(tx_length),.h5_tx_address_i(tx_address),
        .h5_tx_data_o(tx_data),.h5_tx_ready_i(tx_ready),.h5_tx_done_i(tx_done),.h5_tx_error_i(1'b0),
        .h5_rx_valid_i(rx_valid),.h5_rx_type_i(rx_type),.h5_rx_length_i(rx_length),.h5_rx_address_o(rx_address),
        .h5_rx_data_i(rx_data),.h5_rx_consume_o(rx_consume),
        .command_valid_i(bus_valid),.command_write_i(bus_write),.command_address_i(bus_address),
        .command_data_i(bus_data),.command_strobes_i(4'hf),.command_ready_o(bus_ready),
        .response_error_o(bus_error),.response_data_o(bus_read)
    );
    workstation_hci_ble_bridge #(.CLK_HZ(1000)) bridge (
        .clk(clk),.resetn(resetn),.enable(initialized),.connected(dut.known_active[0]),
        .connection_handle(12'd16),.acl_data_limit_i(ble_limit),
        .app_tx_start(app_tx_start),.app_tx_type(app_tx_type),.app_tx_length(app_tx_length),
        .app_tx_addr(app_tx_address),.app_tx_data(app_tx_data),.app_tx_ready(app_tx_ready),
        .app_tx_done(app_tx_done),.app_tx_error(app_tx_error),.app_rx_valid(app_rx_valid),
        .app_rx_type(app_rx_type),.app_rx_length(app_rx_length),.app_rx_addr(app_rx_address),
        .app_rx_data(app_rx_data),.app_rx_consume(app_rx_consume),
        .h5_tx_start(ble_tx_start),.h5_tx_type(ble_tx_type),.h5_tx_length(ble_tx_length),
        .h5_tx_addr(ble_tx_address),.h5_tx_data(ble_tx_data),.h5_tx_ready(ble_tx_ready),
        .h5_tx_done(ble_tx_done),.h5_tx_error(ble_tx_error),.h5_rx_valid(ble_rx_valid),
        .h5_rx_type(ble_rx_type),.h5_rx_length(ble_rx_length),.h5_rx_addr(ble_rx_address),
        .h5_rx_data(ble_rx_data),.h5_rx_consume(ble_rx_consume),.errors()
    );
    reg [1:0] sink_state=0;
    reg [8:0] sink_index=0;
    reg [7:0] sink_bytes[0:263];
    integer received_le_pdus=0;
    always @(posedge clk)begin
        app_rx_consume<=0;
        if(!resetn)begin sink_state<=0;sink_index<=0;app_rx_address<=0;end
        else case(sink_state)
            0:if(app_rx_valid)begin sink_index<=0;app_rx_address<=0;sink_state<=1;end
            1:sink_state<=2;
            2:begin
                sink_bytes[sink_index]=app_rx_data;
                if(sink_index+1==app_rx_length)begin
                    if(app_rx_type==2)received_le_pdus=received_le_pdus+1;
                    app_rx_consume<=1;sink_state<=3;
                end else begin sink_index<=sink_index+1'b1;app_rx_address<=app_rx_address+1'b1;sink_state<=1;end
            end
            3:if(!app_rx_valid)sink_state<=0;
        endcase
    end
    assign tx_ready=!model_pending;
    assign tx_done=model_done;
    always @(posedge clk)begin
        rx_data<=incoming[rx_address];app_tx_data<=app_bytes[app_tx_address];
        model_done<=0;
        if(resetn)begin
            if(tx_start)begin
                if(!tx_ready)$fatal(1,"FAIL duplicate H5 acceptance");
                model_pending<=1;model_copy<=1;model_wait<=1;tx_address<=0;model_type<=tx_type;model_length<=tx_length;
            end
            if(model_copy)begin
                if(model_wait)model_wait<=0;
                else begin
                    sent[tx_address]=tx_data;model_wait<=1;
                    if(tx_address+1==model_length)begin
                        model_copy<=0;
                        if(model_type==1)begin
                            if({sent[1],sent[0]}==16'h0c35)begin
                                if(model_length!=8 || sent[2]!=5 || sent[3]!=1 || sent[6]==0)$fatal(1,"FAIL host return bytes");
                                returns=returns+sent[6];
                            end else begin
                                commands=commands+1;auto_opcode={sent[1],sent[0]};auto_pending=1;
                                if(auto_opcode==16'h0406)disconnects=disconnects+1;
                                if(!initialized)begin
                                    case(boot_commands)
                                        0:if(auto_opcode!=16'h1005)$fatal(1,"FAIL boot BR");
                                        1:if(auto_opcode!=16'h2002)$fatal(1,"FAIL boot LE");
                                        2:if(auto_opcode!=16'h0c33 || sent[3]!=8'h14 || sent[4]!=1 || sent[6]!=4 || sent[8]!=0 || sent[9]!=0)$fatal(1,"FAIL boot geometry");
                                        3:if(auto_opcode!=16'h0c31 || sent[3]!=1)$fatal(1,"FAIL boot flow");
                                        default:$fatal(1,"FAIL extra boot command");
                                    endcase
                                    boot_commands=boot_commands+1;
                                end
                            end
                        end else begin
                            if({sent[1][3:0],sent[0]}==12'd16)begin
                                if(model_length>31 || sent[1][5:4]!=(le_packets==0 ? 0 : 1))$fatal(1,"FAIL physical BLE fragment shape");
                                for(integer at=4;at<model_length;at=at+1)
                                    if(sent[at]!==app_bytes[4+le_payload_offset+at-4])$fatal(1,"FAIL BLE fragment RAM byte");
                                le_payload_offset=le_payload_offset+model_length-4;le_packets=le_packets+1;
                            end
                            else if({sent[1][3:0],sent[0]}==12'd32)br_packets=br_packets+1;
                            else $fatal(1,"FAIL wrong physical ACL handle");
                        end
                    end else tx_address<=tx_address+1'b1;
                end
            end else if(model_pending && !hold_transport)begin model_pending<=0;model_done<=1;end
        end
    end
    task automatic check(input condition,input [8*100-1:0] message);
        begin checks=checks+1;if(!condition)$fatal(1,"FAIL %0s t=%0t tx=%0d rx=%0d flow=%0d host=%0d boot=%0d",message,$time,dut.tx_state,dut.rx_state,dut.flow_reason,dut.host_reason,dut.bootstrap_reason);end
    endtask
    task automatic cycles(input integer count);repeat(count)@(negedge clk);endtask
    task automatic send_packet(input [3:0] kind,input integer length,input [2239:0] bytes);
        begin
            wait(!controller_busy);controller_busy=1;
            @(negedge clk);for(integer at=0;at<length;at=at+1)incoming[at]=bytes[8*at+:8];
            rx_type=kind;rx_length=9'(length);rx_valid=1;
            wait(rx_consume);@(negedge clk);rx_valid=0;cycles(2);controller_busy=0;
        end
    endtask
    initial forever begin: automatic_command_responses
        reg [2239:0] bytes;
        integer length;
        wait(auto_pending);bytes=0;length=6;bytes[7:0]=8'h0e;bytes[15:8]=4;bytes[23:16]=1;
        bytes[39:24]=auto_opcode;
        if(auto_opcode==16'h1005)begin length=13;bytes[15:8]=11;bytes[63:48]=64;bytes[87:72]=4;end
        if(auto_opcode==16'h2002)begin length=9;bytes[15:8]=7;bytes[63:48]=27;bytes[71:64]=1;end
        auto_pending=0;send_packet(4,length,bytes);
    end
    task automatic transaction(input wr,input [11:0] address,input [31:0] value,input expect_error,output [31:0] readback);
        integer timeout;
        begin
            @(negedge clk);bus_valid=1;bus_write=wr;bus_address=address;bus_data=value;timeout=0;
            #1;while(!bus_ready && timeout<10)begin @(negedge clk);timeout=timeout+1;#1;end
            check(bus_ready,"MMIO bounded RAM pipeline");check(bus_error===expect_error,"MMIO error semantics");readback=bus_read;
            @(negedge clk);bus_valid=0;bus_write=0;cycles(1);
        end
    endtask
    reg [31:0] value,discard,ticket;
    task automatic write_reg(input [11:0] address,input [31:0] data);transaction(1,address,data,0,discard);endtask
    task automatic read_reg(input [11:0] address,output [31:0] data);transaction(0,address,0,0,data);endtask
    task automatic submit(input [3:0] kind,input integer length,input [31:0] gen,input [31:0] token,input [2239:0] bytes);
        begin
            write_reg('h220,1);write_reg('h210,32'h44332211);write_reg('h214,gen);write_reg('h218,token);
            write_reg('h21c,(32'(length)<<16)|kind);
            for(integer at=0;at<length;at=at+1)write_reg('h228,{24'd0,bytes[8*at+:8]});
            write_reg('h224,1);
        end
    endtask
    task automatic release_head;
        begin read_reg('h24c,ticket);write_reg('h23c,32'h44332211);write_reg('h264,ticket);end
    endtask
    task automatic connection(input le,input [11:0] handle);
        reg [2239:0] bytes;
        begin
            bytes=0;
            if(le)begin bytes[7:0]='h3e;bytes[15:8]=19;bytes[23:16]=1;bytes[47:32]={4'd0,handle};send_packet(4,21,bytes);end
            else begin bytes[7:0]=3;bytes[15:8]=11;bytes[39:24]={4'd0,handle};bytes[95:88]=1;send_packet(4,13,bytes);end
            cycles(300);
        end
    endtask
    task automatic completion(input [11:0] handle,input [15:0] amount);
        reg [2239:0] bytes;
        begin bytes=0;bytes[7:0]='h13;bytes[15:8]=5;bytes[23:16]=1;bytes[39:24]={4'd0,handle};bytes[55:40]=amount;send_packet(4,7,bytes);cycles(200);end
    endtask
    integer session_cases=0,session_accepts=0,session_rejects=0;
    task automatic session_command(input integer length,input [2239:0] bytes,input bit accept);
        integer before_commands,waited;
        reg [31:0] token;
        begin
            token=32'(100+session_cases);before_commands=commands;
            check(dut.command_credits==1 && !dut.command_pending && !fault,"session pre-command credit");
            submit(1,length,0,token,bytes);waited=0;
            while(!(dut.cpu.tx_state==5 || (dut.cpu.tx_state==4 && dut.cpu.response_done)) && waited<1000)begin
                cycles(1);waited=waited+1;
            end
            check(waited<1000 && !fault,"session command bounded completion");
            read_reg('h22c,value);
            if(accept)begin
                if(!(value[3:0]==4 && value[10:8]==7 && commands==before_commands+1))
                    $display("session case=%0d opcode=%04x state=%08x commands=%0d/%0d generation=%0d reject=%0d epoch=%08x/%08x generation=%0d/%0d type=%0d length=%0d header=%02x %02x %02x %02x schema=%b context=%b shape=%b initialized=%b boot=%b",session_cases,bytes[15:0],value,commands,before_commands,dut.current_br_generation,dut.cpu.reject_reason,dut.cpu_tx_epoch,dut.epoch,dut.tx_generation,dut.current_br_generation,dut.tx_type,dut.tx_length,dut.tx_header[0],dut.tx_header[1],dut.tx_header[2],dut.tx_header[3],dut.tx_schema,dut.cpu_context,dut.cpu_command_shape(dut.selected_opcode,dut.tx_length,dut.tx_header[3],dut.tx_header[4],dut.tx_header[5]),initialized,boot_ready);
                check(value[3:0]==4 && value[10:8]==7 && commands==before_commands+1,"exact W/default command reaches physical H5 once");
                check(model_length==length,"physical command length");
                for(integer at=0;at<length;at=at+1)check(sent[at]===bytes[at*8+:8],"exact physical command bytes");
                waited=0;
                while(dut.cpu.count==0 && waited<1000)begin cycles(1);waited=waited+1;end
                check(waited<1000,"raw response publication remains bounded independently of command completion");
                read_reg('h258,value);check(value==token,"response token retained for session policy");
                release_head();session_accepts=session_accepts+1;
            end else begin
                check(value[3:0]==5 && value[10:8]==0 && commands==before_commands,"invalid session command never takes physical slot");
                check(dut.cpu.reject_reason==4 && dut.cpu.count==0,"invalid command has schema rejection and no raw response");
                session_rejects=session_rejects+1;
            end
            check(dut.command_credits==1 && !dut.command_pending,"validation cannot mint or lose command credit");
            write_reg('h230,token);cycles(5);session_cases=session_cases+1;
        end
    endtask
    task automatic session_contract;
        reg [2239:0] bytes,exact;
        begin
            exact=0;exact[15:0]=16'h0c24;exact[23:16]=3;
            exact[31:24]=8'h14;exact[39:32]=8'h04;exact[47:40]=8'h24;
            session_command(6,exact,SESSION_ONLY_PAIRING);
            for(integer byte_index=3;byte_index<6;byte_index=byte_index+1)
                for(integer candidate=0;candidate<256;candidate=candidate+1)
                    if(8'(candidate)!=exact[8*byte_index+:8])begin
                        bytes=exact;bytes[8*byte_index+:8]=8'(candidate);session_command(6,bytes,0);
                    end
            for(integer length=3;length<=8;length=length+1)if(length!=6)begin
                bytes=exact;bytes[23:16]=8'(length-3);session_command(length,bytes,0);
            end
            for(integer declared=0;declared<=6;declared=declared+1)if(declared!=3)begin
                bytes=exact;bytes[23:16]=8'(declared);session_command(6,bytes,0);
            end
            for(integer scan=0;scan<256;scan=scan+1)begin
                bytes=0;bytes[15:0]=16'h0c1a;bytes[23:16]=1;bytes[31:24]=8'(scan);
                session_command(4,bytes,scan==2 || (SESSION_ONLY_PAIRING && scan==3));
            end
            for(integer length=3;length<=6;length=length+1)if(length!=4)begin
                bytes=0;bytes[15:0]=16'h0c1a;bytes[23:16]=8'(length-3);bytes[31:24]=3;
                session_command(length,bytes,0);
            end
            // Existing SSP/GeneralBonding prerequisites stay constrained, and
            // CPU cannot take controller reset/initializer ownership.
            for(integer value=0;value<256;value=value+1)begin
                bytes=0;bytes[15:0]=16'h0c56;bytes[23:16]=1;bytes[31:24]=8'(value);
                session_command(4,bytes,value==1);
            end
            bytes=0;bytes[15:0]=16'h0c03;session_command(3,bytes,0);
            $display("PASS native session policy=%0d cases=%0d accepted=%0d rejected=%0d checks=%0d physical_bytes=1 command_credit=1",SESSION_ONLY_PAIRING,session_cases,session_accepts,session_rejects,checks);
            $finish;
        end
    endtask
    initial begin: exercise
        reg [2239:0] bytes;
        integer before_le,before_br,before_returns;
        cycles(3);resetn=1;wait(boot_ready);cycles(10);initialized=1;cycles(10);
        check(boot_commands==4 && !fault,"real four-command host bootstrap");
        read_reg('h200,value);check(value==32'h48434931,"native MMIO ID");
        read_reg('h204,value);check(value==32'h01040114,"exact ABI geometry");
        if(SESSION_CONTRACT_ONLY)session_contract();
        connection(1,16);check(dut.known_active==1 && !fault,"LE authoritative generation");
        // The bridge's app receives copied LE event; consume that whole packet.
        cycles(5);
        connection(0,32);check(generation==2 && classic_ready && !fault,"BR authoritative live bundle");
        read_reg('h248,value);check(value==2,"CPU raw connection generation");
        write_reg('h25c,0);read_reg('h260,value);check(value==3,"first synchronous event RAM byte");
        release_head();
        // CPU command response before its actual transport retirement.
        hold_transport=1;bytes=0;bytes[15:0]=16'h1003;
        submit(1,3,2,1,bytes);wait(dut.cpu.response_done);cycles(2);
        read_reg('h22c,value);check(value[3:0]==3 && value[8] && !value[10],"early CC cannot forge H5 retirement");
        transaction(1,'h230,1,1,discard);
        transaction(1,'h228,8'h55,1,discard);
        hold_transport=0;wait(dut.cpu.transport_done);cycles(40);
        read_reg('h22c,value);check(value[3:0]==4 && value[8] && value[10],"exact token retires both independent boundaries");
        read_reg('h258,value);check(value==1,"owner2 response original transport token");
        read_reg('h250,value);check(value[10] && value[9:8]==2 && value[3:0]==4,"raw CC owner route");
        release_head();write_reg('h230,1);
        // Opcode0 can arrive after a CPU response while its old owner/token
        // are still in routing registers. It updates quota without publishing
        // a second CPU response or recycling that completed token.
        bytes=0;bytes[7:0]=8'h0e;bytes[15:8]=3;bytes[23:16]=1;
        send_packet(4,5,bytes);cycles(100);
        check(dut.command_credits==1 && dut.cpu.count==0 && !dut.cpu.response_done && !fault,
            "quota-only event cannot inherit the last CPU owner/token");
        // A BLE advertising result never becomes a CPU response or credit.
        app_bytes[0]=8'h0a;app_bytes[1]=8'h20;app_bytes[2]=1;app_bytes[3]=1;
        wait(app_tx_ready);app_tx_type=1;app_tx_length=4;app_tx_start=1;cycles(1);app_tx_start=0;
        wait(logical_done==1);cycles(150);
        check(dut.cpu.count==0 && !dut.cpu.response_done && !fault,"BLE command response cannot satisfy a retired CPU token");
        app_tx_type=2;
        // Opcode0 CC updates command quota only, never an ordinary response.
        bytes=0;bytes[7:0]=8'h0e;bytes[15:8]=3;send_packet(4,5,bytes);cycles(100);
        check(dut.command_credits==0 && dut.cpu.count==0 && !fault,"quota-only event never inherits a stale CPU owner");
        // BR physical ACL copy retires its real hardware lease while CPU stalls.
        bytes=0;bytes[15:0]=16'h2020;bytes[31:16]=4;bytes[63:32]=32'hdbc0a55a;before_returns=returns;
        send_packet(2,8,bytes);cycles(350);
        check(returns==before_returns+1 && dut.host_budget==4 && dut.host_leases==0,"CPU slow copy never holds controller RX credit");
        read_reg('h24c,ticket);
        // Physical LE continuations and an intervening hardware event preserve
        // the BLE logical PDU while the CPU still owns its independent BR copy.
        begin
            reg [2239:0] le_bytes;
            le_bytes=0;le_bytes[15:0]=16'h2010;le_bytes[31:16]=6;
            le_bytes[47:32]=4;le_bytes[63:48]=4;le_bytes[79:64]=16'hdbc0;
            send_packet(2,10,le_bytes);cycles(170);
            completion(16,0);
            le_bytes=0;le_bytes[15:0]=16'h1010;le_bytes[31:16]=2;le_bytes[47:32]=16'h5aa5;
            send_packet(2,6,le_bytes);cycles(240);
            check(received_le_pdus==1 && sink_bytes[2]==8 && sink_bytes[8]==8'hc0 &&
                sink_bytes[9]==8'hdb && sink_bytes[10]==8'ha5 && sink_bytes[11]==8'h5a,"physical LE fragments reassemble through synchronous private queues");
            check(returns==before_returns+3 && dut.host_leases==0,"all three real RX packets return independently of CPU");
        end
        read_reg('h24c,value);check(value==ticket,"BLE traffic never overwrites a slow CPU copy");
        read_reg('h250,value);check(value[3:0]==2 && value[24:16]==8,"physical raw ACL descriptor");
        for(integer at=0;at<8;at=at+1)begin write_reg('h25c,at);read_reg('h260,value);check(value[7:0]==bytes[8*at+:8],"registered host slot to immutable CPU byte");end
        release_head();
        check(dut.command_credits==0 && returns==before_returns+3,"dedicated host return bypasses zero ordinary quota");
        bytes=0;bytes[7:0]=8'h0e;bytes[15:8]=3;bytes[23:16]=1;send_packet(4,5,bytes);cycles(100);
        check(dut.command_credits==1 && dut.cpu.count==0,"quota-only restoration stays outside CPU queue");
        // One logical BLE PDU needs three independently debited HCI fragments.
        for(integer at=0;at<68;at=at+1)app_bytes[at]=8'(at^8'hb9);
        app_bytes[0]=16;app_bytes[1]=0;app_bytes[2]=64;app_bytes[3]=0;
        app_bytes[4]=60;app_bytes[5]=0;app_bytes[6]=4;app_bytes[7]=0;
        wait(app_tx_ready);app_tx_length=68;app_tx_start=1;cycles(1);app_tx_start=0;
        wait(le_packets==1);cycles(100);
        check(dut.le_available==0 && le_packets==1,"one physical LE credit cannot authorize next fragment");
        // An independent BR pool still progresses while LE waits for NCP.
        before_br=br_packets;bytes=0;bytes[15:0]=16'h2020;bytes[31:16]=4;bytes[63:32]=32'h04030201;
        submit(2,8,2,2,bytes);wait(br_packets==before_br+1);wait(dut.cpu.transport_done);
        check(le_packets==1 && dut.br_available==3 && !fault,"blocked LE does not steal sole TX slot from BR");
        write_reg('h230,2);completion(16,1);wait(le_packets==2);cycles(80);
        check(le_packets==2 && dut.le_available==0,"second physical fragment separately debited");
        completion(16,1);wait(le_packets==3);wait(logical_done==2);cycles(5);
        check(!app_tx_error && !fault,"logical BLE completion after all actual fragments");completion(16,1);
        // Queue a generation2 packet, then close/reuse handle32 without changing its bytes.
        bytes=0;bytes[7:0]=8'h22;bytes[15:8]=1;bytes[23:16]=8'had;send_packet(4,3,bytes);cycles(100);
        read_reg('h24c,ticket);bytes=0;bytes[7:0]=5;bytes[15:8]=4;bytes[39:24]=32;bytes[47:40]=8'h13;
        send_packet(4,6,bytes);cycles(150);check(!classic_ready && !classic_active,"actual disconnect revokes live audio immediately");
        connection(0,32);check(generation==3 && classic_ready,"same HCI handle gets strictly newer generation");
        read_reg('h24c,value);check(value==ticket,"disconnect never reuses a live CPU reader slot");
        read_reg('h254,value);check(value[16],"old generation CPU copy explicitly retired");
        write_reg('h25c,2);read_reg('h260,value);check(value[7:0]==8'had,"retired bytes immutable across handle reuse");
        release_head();release_head();release_head();
        bytes=0;bytes[15:0]=16'h1003;submit(1,3,2,3,bytes);cycles(120);
        read_reg('h22c,value);check(value[3:0]==5,"stale generation command rejected before acceptance");write_reg('h230,3);
        bytes=0;bytes[15:0]=16'h1408;bytes[23:16]=2;bytes[39:24]=16;
        submit(1,5,3,4,bytes);cycles(120);read_reg('h22c,value);
        check(value[3:0]==5 && dut.known_active[0],"CPU BR command cannot address a LE handle");write_reg('h230,4);
        transaction(1,'h27c,32'h44332212,1,discard);check(!fenced,"stale CPU fence key consumes no current authority");
        // Fill all CPU copies. Lifecycle/NCP/BLE and hardware credit paths continue.
        bytes=0;bytes[7:0]=8'h22;send_packet(4,2,bytes);cycles(100);send_packet(4,2,bytes);cycles(100);
        send_packet(4,2,bytes);cycles(100);send_packet(4,2,bytes);cycles(100);send_packet(4,2,bytes);cycles(200);
        check(fenced && !fault && !classic_ready,"bounded CPU overflow fences only Classic");
        wait(disconnects==1);cycles(100);check(!fault && dut.known_active[0],"bounded hardware BR disconnect preserves LE");
        completion(32,0);check(!fault,"NCP decoder never waits on full CPU queue");
        read_reg('h278,value);check(value>1000,"independent reference time advances without CPU polling");
        // Observer reset cannot refund either controller ledger or mutate BLE.
        before_le=le_packets;observer_reset=0;cycles(4);observer_reset=1;cycles(4);
        check(dut.known_active[0] && dut.le_available==1 && le_packets==before_le && !fault,"observer reset retains shared controller ownership");
        // A real common reset establishes a different external epoch and
        // clears every real reader/queue/ledger. Old ticket numbers alone can
        // collide after reset; the exact release epoch must still reject them.
        initialized=0;resetn=0;boot_id=64'h8877665544332212;boot_commands=0;cycles(4);resetn=1;
        wait(boot_ready);initialized=1;cycles(10);connection(0,32);
        read_reg('h24c,ticket);write_reg('h23c,32'h44332211);
        transaction(1,'h264,ticket,1,discard);check(epoch==32'h44332212 && classic_ready,"old epoch release cannot retire a new reader");
        transaction(1,'h27c,32'h44332211,1,discard);check(!fenced,"old epoch fence rejected after common reset");
        write_reg('h27c,32'h44332212);cycles(4);check(fenced && !classic_ready && !fault,"exact CPU fault request revokes the live bundle without resetting controller");
        wait(disconnects==2);cycles(20);check(!fault,"CPU requested BR disconnect uses sole owner");
        $display("PASS native integration checks=%0d commands=%0d fragments=%0d BR=%0d hostreturns=%0d",checks,commands,le_packets,br_packets,returns);
        $finish;
    end
    initial begin cycles(100000);$display("DETAIL bridgeT=%0d kind=%0d len=%0d chunk=%0d err=%0d connected=%0d ready=%0d start=%0d grantsource=%0d app_len=%0d app_ready=%0d known=%b",bridge.t_state,bridge.t_type,bridge.t_length,bridge.t_chunk,bridge.errors,bridge.connected,ble_tx_ready,ble_tx_start,dut.tx_origin,app_tx_length,app_tx_ready,dut.known_active);$fatal(1,"FAIL native integration watchdog tx=%0d rx=%0d fault=%0d flow=%0d host=%0d boot=%0d cpu=%0d checks=%0d commands=%0d le=%0d br=%0d cpuvalid=%b eligible=%b credits=%d pending=%b grant=%d",dut.tx_state,dut.rx_state,fault,dut.flow_reason,dut.host_reason,dut.bootstrap_reason,dut.cpu.tx_state,checks,commands,le_packets,br_packets,dut.cpu_tx_valid,dut.cpu_schedulable,dut.command_credits,dut.command_pending,dut.grant_age);end
endmodule
