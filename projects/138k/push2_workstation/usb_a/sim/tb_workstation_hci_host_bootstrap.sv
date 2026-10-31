`timescale 1ns/1ps
module tb_workstation_hci_host_bootstrap;
    reg clk_i=0;always #5 clk_i=~clk_i;
    reg reset_ni=0,start_i=0,initializer_handoff_i=1,links_idle_i=1,external_fault=0;
    reg [15:0] host_data_length_i=276,host_packet_count_i=4;
    wire fault_o,ready_o,activate_host_rx_o,command_valid_o,pool_config_valid_o;
    wire [3:0] fault_reason_o;
    wire [1:0] command_owner_o;
    wire [15:0] command_opcode_o;
    wire [8:0] command_length_o;
    reg [3:0] command_address_i=0;
    wire [7:0] command_data_o;
    reg command_accept_i=0,command_transport_done_i=0;
    wire response_valid_i;
    wire [1:0] response_owner_i;
    wire [15:0] response_opcode_i;
    wire [7:0] response_status_i;
    wire response_is_complete_i;
    reg [15:0] response_acl_length_i=0,response_acl_count_i=0;
    wire pool_config_ready_i;
    wire [15:0] br_acl_length_o,br_acl_count_o,le_acl_length_o,le_acl_count_o;
    wire flow_fault,rx_fault;
    wire controller_fault_i=external_fault||flow_fault||rx_fault;
    reg override_response=0;
    reg [1:0] override_owner=0;
    reg [15:0] override_opcode=0;
    reg override_complete=1;
    wire routed_valid;
    wire [1:0] routed_owner;
    wire [15:0] routed_opcode;
    wire [7:0] routed_status;
    wire routed_complete;
    assign response_is_complete_i=override_response ? override_complete : routed_complete;
    assign response_valid_i=override_response||routed_valid;
    assign response_owner_i=override_response ? override_owner : routed_owner;
    assign response_opcode_i=override_response ? override_opcode : routed_opcode;
    assign response_status_i=override_response ? 8'd0 : routed_status;
    workstation_hci_host_bootstrap #(.STEP_TIMEOUT_CYCLES(128)) dut(.*);
    reg ordinary_send=0,raw_response=0,allow_config=1,raw_complete=1;
    reg [15:0] raw_opcode=0;
    reg [7:0] raw_status=0,raw_credits=1;
    wire command_ready,config_ready,configured,le_shared;
    wire [7:0] command_credits;
    wire [15:0] br_limit,le_limit;
    wire [1:0] known_active,known_is_le;
    wire [23:0] known_handles;
    wire [63:0] known_generations;
    assign pool_config_ready_i=config_ready&&allow_config;
    workstation_hci_flow_owner flow(
        .clk_i(clk_i),.reset_ni(reset_ni),.transport_fault_i(external_fault||fault_o||rx_fault),
        .config_valid_i(pool_config_valid_o&&allow_config),.br_acl_length_i(br_acl_length_o),.br_acl_count_i(br_acl_count_o),
        .le_acl_length_i(le_acl_length_o),.le_acl_count_i(le_acl_count_o),.config_ready_o(config_ready),
        .configured_o(configured),.fault_o(flow_fault),.le_shared_o(le_shared),.br_acl_limit_o(br_limit),.le_acl_limit_o(le_limit),
        .handle_open_i(1'b0),.handle_close_i(1'b0),.handle_is_le_i(1'b0),.handle_i(12'd0),
        .handle_active_o(known_active),.handle_is_le_o(known_is_le),.handle_numbers_o(known_handles),.handle_generations_o(known_generations),
        .acl_valid_i(1'b0),.acl_send_i(1'b0),.acl_handle_i(12'd0),.acl_generation_i(32'd0),.acl_data_length_i(16'd0),
        .completion_start_i(1'b0),.completion_pair_valid_i(1'b0),.completion_handle_i(12'd0),.completion_count_i(16'd0),
        .completion_commit_i(1'b0),.completion_abort_i(1'b0),
        .command_valid_i(ordinary_send||command_valid_o),.command_send_i(ordinary_send||command_accept_i),
        .command_owner_i(ordinary_send ? 2'd2 : command_owner_o),.command_opcode_i(ordinary_send ? 16'h0409 : command_opcode_o),
        .command_ready_o(command_ready),.command_credits_o(command_credits),
        .command_response_i(raw_response),.command_timeout_i(1'b0),.response_credits_i(raw_credits),
        .response_is_complete_i(raw_complete),.response_is_complete_o(routed_complete),
        .response_opcode_i(raw_opcode),.response_status_i(raw_status),
        .response_valid_o(routed_valid),.response_owner_o(routed_owner),.response_opcode_o(routed_opcode),.response_status_o(routed_status)
    );
    wire rx_active;
    workstation_hci_host_rx_owner rx(
        .clk_i(clk_i),.reset_ni(reset_ni),.transport_fault_i(external_fault||fault_o||flow_fault),
        .activate_i(activate_host_rx_o),.active_o(rx_active),.fault_o(rx_fault),
        .known_active_i(known_active),.known_is_le_i(known_is_le),.known_handles_i(known_handles),.known_generations_i(known_generations),
        .rx_valid_i(1'b0),.rx_take_i(1'b0),.rx_want_lease_i(1'b0),.rx_handle_i(16'd0),.rx_data_length_i(16'd0),
        .release_valid_i(1'b0),.release_lease_i(32'd0),.disconnect_valid_i(1'b0),.disconnect_handle_i(12'd0),.disconnect_generation_i(32'd0),
        .return_address_i(4'd0),.return_send_i(1'b0),.return_transport_done_i(1'b0)
    );
    integer checks=0,scenarios=0,activations=0,commands=0;
    reg [79:0] held;
    task check;input condition;input [767:0] text;
        begin checks=checks+1;if(condition!==1'b1)begin $display("FAIL %0s t=%0t scenario=%0d state=%0d step=%0d",text,$time,scenarios,dut.state,dut.step);$fatal(1);end end
    endtask
    task tick;begin @(posedge clk_i);#1;end endtask
    always @(posedge clk_i)if(reset_ni&&activate_host_rx_o)activations=activations+1;
    task reset_all;
        begin
            reset_ni=0;start_i=0;external_fault=0;initializer_handoff_i=1;links_idle_i=1;
            host_data_length_i=276;host_packet_count_i=4;command_accept_i=0;command_transport_done_i=0;
            ordinary_send=0;raw_response=0;allow_config=1;override_response=0;raw_complete=1;override_complete=1;response_acl_length_i=0;response_acl_count_i=0;
            tick();tick();reset_ni=1;tick();activations=0;commands=0;scenarios=scenarios+1;
            check(!fault_o&&!ready_o&&!command_valid_o&&!rx_active&&!configured,"no implicit bootstrap or host RX enable after reset");
        end
    endtask
    task start;
        begin @(negedge clk_i);start_i=1;tick();start_i=0;check(!fault_o&&command_valid_o&&command_opcode_o==16'h1005,"explicit handoff begins BR buffer query");end
    endtask
    task bytes;output [79:0] packet;
        begin packet=0;for(integer at=0;at<10;at=at+1)begin command_address_i=at;#1;packet[8*at+:8]=command_data_o;end end
    endtask
    task accept;
        reg [79:0] packet,again;
        begin
            check(command_valid_o&&command_ready&&command_owner_o==0,"initializer uses sole ordinary-command quota");
            bytes(packet);
            case(commands)
                0:check(command_length_o==3&&packet[23:0]==24'h001005,"actual BR ReadBufferSize bytes");
                1:check(command_length_o==3&&packet[23:0]==24'h002002,"actual LE ReadBufferSize bytes");
                2:check(command_length_o==10&&packet==80'h00000004000114070c33,"actual HostBufferSize276/4/SCO0 bytes");
                3:check(command_length_o==4&&packet[31:0]==32'h01010c31,"actual ACL flow enable bytes");
                default:check(0,"no extra bootstrap command");
            endcase
            held=packet;@(negedge clk_i);command_accept_i=1;tick();command_accept_i=0;commands=commands+1;
            check(!command_valid_o&&!ready_o&&!rx_active,"transport acceptance alone never activates host RX");
            bytes(again);check(again==held,"transport retains identical builder bytes after irreversible acceptance");
        end
    endtask
    task transport_done;
        begin @(negedge clk_i);command_transport_done_i=1;tick();command_transport_done_i=0;end
    endtask
    task reply;input [15:0] opcode;input [7:0] status;input [15:0] data_length,count;
        begin
            @(negedge clk_i);raw_opcode=opcode;raw_status=status;raw_credits=1;response_acl_length_i=data_length;response_acl_count_i=count;raw_response=1;
            tick();raw_response=0;tick();
        end
    endtask
    task first_two;input shared;
        begin
            accept();transport_done();reply(16'h1005,0,1021,5);
            check(command_valid_o&&command_opcode_o==16'h2002&&!ready_o,"BR success advances to LE query only");
            accept();reply(16'h2002,0,shared ? 0 : 27,shared ? 0 : 3);
            check(!command_valid_o&&!pool_config_valid_o&&!ready_o,"successful LE result still waits for old packet retirement");
            transport_done();check(pool_config_valid_o&&!configured,"pool configuration is a separate accepted transaction");
            check(br_acl_length_o==1021&&br_acl_count_o==5&&le_acl_count_o==(shared ? 0 : 3),"raw reported controller capabilities preserved");
            tick();check(configured&&!pool_config_valid_o&&command_opcode_o==16'h0c33&&le_shared==shared,"shared flow owner is configured before host buffer command");
            check(br_limit==276&&le_limit==(shared ? 276 : 27),"shared owner enforces actual physical limits");
        end
    endtask
    task finish;
        begin
            accept();reply(16'h0c33,0,0,0);check(!command_valid_o&&!ready_o,"buffer success cannot mutate bytes still read by H5");
            transport_done();check(command_valid_o&&command_opcode_o==16'h0c31&&!rx_active,"enable occurs only after accepted size command finishes");
            accept();transport_done();reply(16'h0c31,0,0,0);
            check(ready_o&&activate_host_rx_o&&!fault_o&&!rx_active,"both confirmations publish one activation pulse");
            tick();check(rx_active&&!rx_fault&&activations==1&&!activate_host_rx_o,"real host RX owner activates once on the next edge");
            repeat(8)tick();check(ready_o&&rx_active&&activations==1&&!command_valid_o,"normal audio/CPU observers cannot retrigger bootstrap");
        end
    endtask
    task expect_timeout;
        begin repeat(132)tick();check(fault_o&&fault_reason_o==7&&!ready_o&&!activate_host_rx_o,"step deadline fails closed without automatic retry");end
    endtask
    initial begin
        reset_all();start();first_two(1);finish();
        reset_all();start();first_two(0);finish();

        reset_all();@(negedge clk_i);ordinary_send=1;tick();ordinary_send=0;
        check(command_credits==0,"another client holds ordinary command credit");start();
        bytes(held);repeat(12)tick();begin reg [79:0] packet;bytes(packet);check(packet==held&&command_valid_o&&!command_ready,"zero quota preserves an unaccepted stable offer");end
        reply(16'h0409,0,0,0);check(!fault_o&&command_opcode_o==16'h1005,"other owner's routed completion cannot finish bootstrap query");
        first_two(1);finish();

        reset_all();initializer_handoff_i=0;@(negedge clk_i);start_i=1;tick();start_i=0;
        check(fault_o&&fault_reason_o==2&&!command_valid_o,"no competing initializer before explicit handoff");
        reset_all();links_idle_i=0;@(negedge clk_i);start_i=1;tick();start_i=0;
        check(fault_o&&!ready_o,"host-flow bootstrap cannot begin with links already active");
        for(integer bad=0;bad<4;bad=bad+1)begin
            reset_all();if(bad==0)host_data_length_i=3;if(bad==1)host_data_length_i=277;
            if(bad==2)host_packet_count_i=1;if(bad==3)host_packet_count_i=17;
            @(negedge clk_i);start_i=1;tick();start_i=0;
            check(fault_o&&fault_reason_o==3&&!command_valid_o,"invalid advertised host buffer geometry rejected");
        end
        reset_all();start();host_packet_count_i=5;tick();check(fault_o&&fault_reason_o==3&&!command_valid_o,"configuration drift cannot change advertised capacity");
        reset_all();start();accept();transport_done();reply(16'h1005,1,1021,5);
        check(fault_o&&fault_reason_o==5&&!ready_o,"controller BR query failure never falls back to guessed buffers");
        reset_all();start();accept();transport_done();reply(16'h1005,0,1021,0);
        check(fault_o&&fault_reason_o==8&&!configured,"BR missing capacity rejected");
        reset_all();start();accept();transport_done();reply(16'h1005,0,1021,5);accept();transport_done();reply(16'h2002,0,0,3);
        check(fault_o&&fault_reason_o==8&&!configured,"dedicated LE capacity requires actual nonzero data length");
        reset_all();start();accept();transport_done();reply(16'h1005,0,1021,5);accept();transport_done();reply(16'h2002,0,27,256);
        check(fault_o&&fault_reason_o==8,"LE packet count remains its actual eight-bit wire value");
        for(integer phase=0;phase<4;phase=phase+1)begin
            reset_all();start();
            if(phase==1)begin accept();transport_done();reply(16'h1005,0,1021,5);end
            if(phase>=2)first_two(1);
            if(phase==3)begin accept();transport_done();reply(16'h0c33,0,0,0);end
            accept();transport_done();raw_complete=0;
            case(phase)
                0:reply(16'h1005,0,1021,5);
                1:reply(16'h2002,0,0,0);
                2:reply(16'h0c33,0,0,0);
                3:reply(16'h0c31,0,0,0);
            endcase
            check(fault_o&&fault_reason_o==4&&!ready_o&&!rx_active,"CommandStatus success cannot impersonate required CommandComplete");
        end
        for(integer which=0;which<2;which=which+1)begin
            reset_all();start();first_two(1);accept();transport_done();reply(16'h0c33,which==0 ? 1 : 0,0,0);
            if(which==1)begin accept();transport_done();reply(16'h0c31,1,0,0);end
            check(fault_o&&fault_reason_o==5&&!ready_o&&!rx_active,"host size/flow unsupported stops before RX activation");
        end
        reset_all();start();accept();override_response=1;override_owner=0;override_opcode=16'h1002;tick();override_response=0;
        check(fault_o&&fault_reason_o==4,"wrong routed initializer opcode cannot complete command");
        reset_all();start();accept();reply(16'h1005,0,1021,5);override_response=1;override_owner=0;override_opcode=16'h1005;tick();override_response=0;
        check(fault_o&&fault_reason_o==4,"duplicate success cannot release still-owned transport bytes");
        reset_all();start();accept();external_fault=1;command_transport_done_i=1;tick();external_fault=0;command_transport_done_i=0;
        check(fault_o&&fault_reason_o==1&&!ready_o,"transport uncertainty dominates simultaneous completion without replay");
        reset_all();start();expect_timeout();
        reset_all();@(negedge clk_i);ordinary_send=1;tick();ordinary_send=0;start();expect_timeout();
        reset_all();start();accept();expect_timeout();
        reset_all();start();accept();reply(16'h1005,0,1021,5);expect_timeout();
        reset_all();start();allow_config=0;accept();transport_done();reply(16'h1005,0,1021,5);accept();transport_done();reply(16'h2002,0,0,0);
        check(pool_config_valid_o,"pool config is genuinely backpressured");
        repeat(8)begin tick();check(pool_config_valid_o&&!command_valid_o&&!configured,"pool backpressure cannot publish host-size command or skip actual configuration acceptance");end
        expect_timeout();
        reset_all();start();first_two(1);accept();transport_done();reply(16'h0c33,0,0,0);accept();
        @(negedge clk_i);raw_opcode=16'h0c31;raw_status=0;raw_response=1;tick();raw_response=0;
        @(negedge clk_i);command_transport_done_i=1;tick();command_transport_done_i=0;
        check(ready_o&&activate_host_rx_o&&!fault_o,"response and transport retirement can safely commit on the same edge");
        tick();check(rx_active&&activations==1,"same-edge completion activates real RX exactly once");
        reset_all();start();first_two(1);accept();transport_done();reply(16'h0c33,0,0,0);accept();
        @(negedge clk_i);override_response=1;override_owner=0;override_opcode=16'h0c31;
        command_transport_done_i=1;external_fault=1;tick();override_response=0;command_transport_done_i=0;external_fault=0;
        check(fault_o&&fault_reason_o==1&&!activate_host_rx_o&&!ready_o,"controller fault dominates final simultaneous success/retirement");
        reset_all();start();first_two(1);accept();transport_done();reply(16'h0c33,0,0,0);accept();
        @(negedge clk_i);dut.elapsed=127;override_response=1;override_owner=0;override_opcode=16'h0c31;command_transport_done_i=1;
        tick();override_response=0;command_transport_done_i=0;
        check(fault_o&&fault_reason_o==7&&!activate_host_rx_o&&!ready_o,"deadline dominates final simultaneous success/retirement");
        reset_all();start();first_two(1);finish();host_data_length_i=275;tick();
        check(fault_o&&fault_reason_o==3&&!ready_o,"post-bootstrap geometry drift requires common controller recovery");
        $display("PASS checks=%0d scenarios=%0d commands4 pools2 timeout_phases5",checks,scenarios);$finish;
    end
    initial begin #10000000;$fatal(1,"watchdog");end
endmodule
