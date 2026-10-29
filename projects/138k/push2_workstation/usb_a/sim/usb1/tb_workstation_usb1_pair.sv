`timescale 1ns/1ps
module tb_workstation_usb1_pair #(parameter integer PEER_USB2=0,TRACE=0);
    reg clk_usb=0, clk_peer=0, clk_app=0, reset_n=0, attached=1;
    reg clk_ulpi=0;
    always #10.417 clk_usb=!clk_usb;
    always #10 clk_app=!clk_app;
    initial begin #3.701;forever #10.418 clk_peer=!clk_peer;end
    initial begin #5.301;forever #8.334 clk_ulpi=!clk_ulpi;end
    tri usb_dp,usb_dm;
    assign (weak0,weak1) usb_dp=1'b0;
    assign (weak0,weak1) usb_dm=1'b0;
    wire peer_pullup;
    assign (pull0,pull1) usb_dp=attached&&((PEER_USB2==0)||peer_pullup)?1'b1:1'bz;
    wire service_valid,service_write,service_ready,service_error,session_valid;
    wire[7:0]service_address;
    wire[31:0]service_data,service_result,fault_address;
    wire[3:0]service_mask,fault;
    wire[2:0]flags;
    wire[31:0]identity,protocol_status,midi_count,event_data;
    wire event_valid;
    reg accept_events=1,stall_probe=0;
    workstation_usb1_host host(
        .clk_usb(clk_usb),.reset_n(reset_n),.usb_dp(usb_dp),.usb_dm(usb_dm),
        .uart_rx_i(1'b1),.uart_tx_o(),.service_valid_o(service_valid),.service_write_o(service_write),
        .service_address_o(service_address),.service_write_data_o(service_data),.service_mask_o(service_mask),
        .service_ready_i(service_ready),.service_error_i(service_error),.service_read_data_i(service_result),
        .fault_o(fault),.fault_address_o(fault_address),.line_state_o(),.session_valid_o(session_valid));
    workstation_usb1_diagnostics diagnostics(
        .clk_usb(clk_usb),.reset_n(reset_n),.session_valid_i(session_valid),
        .service_valid_i(service_valid),.service_write_i(service_write),.service_address_i(service_address),
        .service_write_data_i(service_data),.service_mask_i(service_mask),
        .service_ready_o(service_ready),.service_error_o(service_error),.service_read_data_o(service_result),
        .device_flags_o(flags),.identity_o(identity),.protocol_status_o(protocol_status),.midi_count_o(midi_count),
        .midi_valid_o(event_valid),.midi_ready_i(accept_events),.midi_data_o(event_data));
    wire[7:0]rx_data,tx_data,control_txdata,control_rxdata;
    wire rx_valid,rx_active,rx_error,tx_valid,tx_ready;
    wire[1:0]line_state,opmode,xcvr;
    wire termsel,dppd,dmpd,peer_online,control_reset,peer_hs,midi_ready;
    wire peer_reset=!reset_n||((PEER_USB2==0)&&!attached);
    wire peer_tx_driving;
    wire[6:0]peer_address;
    wire[31:0]chirp_commands,normal_packets;
    wire[7:0]phy_function;
    generate if(PEER_USB2==0)begin:usb1_peer
    workstation_usb1_phy peer_phy(.clk_usb(clk_peer),.reset_n(!peer_reset),.usb_dp(usb_dp),.usb_dm(usb_dm),
        .tx_data_i(tx_data),.tx_valid_i(tx_valid),.tx_ready_o(tx_ready),
        .rx_data_o(rx_data),.rx_valid_o(rx_valid),.rx_active_o(rx_active),.rx_error_o(rx_error),
        .line_state_o(line_state),.op_mode_i(opmode),.xcvr_select_i(xcvr),
        .term_select_i(termsel),.dp_pulldown_i(dppd),.dm_pulldown_i(dmpd));
    assign peer_tx_driving=!peer_phy.tx_disable;
    assign chirp_commands=0;
    assign normal_packets=0;
    assign phy_function=8'h45;
    assign peer_pullup=1;
    end else begin:usb2_peer
        tri[7:0]ulpi_data;
        wire ulpi_dir,ulpi_nxt,ulpi_stp;
        usb3300_fs_device_model #(.TRACE(TRACE)) phy_model(
            .clk_ulpi(clk_ulpi),.clk_fs(clk_peer),.reset_n(reset_n),.attached(attached),
            .ulpi_data(ulpi_data),.ulpi_dir(ulpi_dir),.ulpi_nxt(ulpi_nxt),.ulpi_stp(ulpi_stp),
            .usb_dp(usb_dp),.usb_dm(usb_dm),.function_control(phy_function),
            .chirp_commands(chirp_commands),.normal_packets(normal_packets),.tx_driving(peer_tx_driving),.dp_pullup(peer_pullup));
        midi_usb2_link peer(
            .clk_50mhz(clk_app),.reset(peer_reset),.clk_ulpi60(clk_ulpi),
            .ulpi_data(ulpi_data),.ulpi_dir(ulpi_dir),.ulpi_nxt(ulpi_nxt),.ulpi_stp(ulpi_stp),
            .midi_tx_valid(peer_online&&(sent<128||(stall_probe&&sent==128))),
            .midi_tx_ready(midi_ready),.midi_tx_data(midi_word),
            .midi_rx_valid(unexpected_midi),.midi_rx_ready(1'b1),.midi_rx_data(),
            .control_tx_valid(control_txvalid),.control_tx_ready(control_txready),.control_tx_data(control_txdata),
            .control_rx_valid(control_rxvalid),.control_rx_ready(control_rxready),.control_rx_data(control_rxdata),
            .online(peer_online),.control_reset(control_reset),.hs_active(peer_hs));
        assign peer_address=peer.device_address;
        assign line_state=peer.line_state;
        always @(posedge clk_ulpi)begin
            if(reset_n && peer.boot_error)$fatal(1,"25K USB3300 boot failed stage=%02x",peer.boot_stage);
            if(reset_n && peer_hs)$fatal(1,"FS host must not negotiate HS");
            if(reset_n && ulpi_dir && !peer.pads[0].disabled)$fatal(1,"25K ULPI ownership violation");
        end
        initial begin
            #450000000;
            if(connections==0)$fatal(1,"mixed enumeration timeout function=%02x chirps=%0d packets=%0d boot=%02x hs_state=%0d ULPI_model=%0d RX=%0d/%0d fs_rx=%b line=%b",
                phy_function,chirp_commands,normal_packets,peer.boot_stage,peer.phy_state,phy_model.state,
                phy_model.rx_read,phy_model.rx_write,phy_model.fs_rxactive,line_state);
        end
    end endgenerate
    integer sent=0,received=0,tiles=0,tile_delay=0,connections=0,previous_tiles=0;
    reg[31:0]stalled_event;
    reg[2:0]previous_flags=0;
    wire[7:0]note_number=8'd36+8'(sent>>1);
    wire[31:0]midi_word=sent[0]?{8'd0,note_number,8'h80,8'h08}:{8'd100,note_number,8'h90,8'h09};
    wire control_txvalid,control_txready,control_rxvalid,control_rxready,unexpected_midi;
    generate if(PEER_USB2==0)begin:fs_bridge
    midi_usb_bridge #(.FULL_SPEED_ONLY(1)) peer(
        .clk_50mhz(clk_app),.reset(peer_reset),.clk_ulpi60(clk_peer),.enable(!peer_reset),
        .utmi_rxdata(rx_data),.utmi_rxvalid(rx_valid),.utmi_rxactive(rx_active),.utmi_rxerror(rx_error),
        .utmi_linestate(line_state),.utmi_txready(tx_ready),.utmi_txdata(tx_data),.utmi_txvalid(tx_valid),
        .utmi_opmode(opmode),.utmi_xcvr(xcvr),.utmi_termsel(termsel),.utmi_dppd(dppd),.utmi_dmpd(dmpd),
        .midi_tx_valid(peer_online&&(sent<128||(stall_probe&&sent==128))),.midi_tx_ready(midi_ready),.midi_tx_data(midi_word),
        .midi_rx_valid(unexpected_midi),.midi_rx_ready(1'b1),.midi_rx_data(),
        .control_tx_valid(control_txvalid),.control_tx_ready(control_txready),.control_tx_data(control_txdata),
        .control_rx_valid(control_rxvalid),.control_rx_ready(control_rxready),.control_rx_data(control_rxdata),
        .online(peer_online),.control_reset(control_reset),.hs_active(peer_hs),.phy_state(),.device_address());
    assign peer_address=peer.device.device_address;
    end endgenerate
    wire tile_valid,remote_enable;
    wire tile_done=tile_delay==1;
    wire[8:0]tile_x,tile_width;
    wire[7:0]tile_y,tile_height;
    wire[15:0]protocol_errors;
    panel_display_endpoint #(.CLK_HZ(50000000)) panel(
        .clk(clk_app),.reset(peer_reset),.link_reset(control_reset),.settings_toggle(1'b0),
        .rx_valid(control_rxvalid),.rx_ready(control_rxready),.rx_data(control_rxdata),
        .tx_valid(control_txvalid),.tx_ready(control_txready),.tx_data(control_txdata),
        .remote_enable(remote_enable),.manual_settings(),.redraw_required(),.protocol_errors(protocol_errors),
        .tile_valid(tile_valid),.tile_ready(tile_delay==0),.tile_x(tile_x),.tile_y(tile_y),
        .tile_width(tile_width),.tile_height(tile_height),.tile_read_addr(8'd0),.tile_read_data(),.tile_done(tile_done));
    always @(posedge clk_app) begin
        if(peer_reset||!attached)sent<=0;
        else if(peer_online&&(sent<128||(stall_probe&&sent==128))&&midi_ready)sent<=sent+1;
        if(tile_delay>0)tile_delay<=tile_delay-1;
        if(tile_valid&&tile_delay==0)begin
            if(tile_width>62||tile_height>4||tile_width==0||tile_height==0)
                $fatal(1,"invalid PL tile");
            tiles<=tiles+1;tile_delay<=20;
        end
        if(unexpected_midi)$fatal(1,"PL leaked to MIDI OUT");
        if((PEER_USB2==0)&&(peer_hs||opmode!=0||xcvr!=1||!termsel))$fatal(1,"FS-only peer attempted HS");
    end
    always @(posedge clk_usb) begin
        previous_flags<=flags;
        if(flags==7&&previous_flags!=7)begin
            connections<=connections+1;
            $display("USB1 connection %0d at %0t",connections+1,$time);
        end
        if(reset_n&&fault!=0)$fatal(1,"CPU fault=%x address=%08x",fault,fault_address);
        if(reset_n&&!flags[0]&&(identity!=0||protocol_status!=0))$fatal(1,"stale identification outside session");
        if(event_valid&&accept_events)begin
            if(event_data!==((received[0]?32'd0:32'd16384)|
               ((32'd36+32'(received%128>>1))<<7)|(received[0]?32'd0:32'd100)))
                $fatal(1,"MIDI order/value %0d: %08x",received,event_data);
            received<=received+1;
        end
        if(reset_n&&attached&&host.phy.tx_disable==0&&peer_tx_driving)
            $fatal(1,"USB1 pad contention");
    end
    initial begin
        repeat(10)@(negedge clk_usb);reset_n=1;
        wait(received==128&&tiles>=2&&protocol_status[9]);
        if(flags!=7||identity!=32'hfb9bfb9a||protocol_errors!=0||!remote_enable)
            $fatal(1,"first USB1 session validation");
        @(negedge clk_usb);accept_events=0;stall_probe=1;
        wait(event_valid);
        stalled_event=event_data;
        repeat(10000)begin
            @(negedge clk_usb);
            if(!event_valid||event_data!=stalled_event||midi_count!=128)$fatal(1,"event backpressure stability");
        end
        attached=0;
        wait(flags==0);
        if(event_valid||identity!=0||protocol_status!=0)$fatal(1,"detach fence");
        repeat(100000)@(negedge clk_usb);
        previous_tiles=tiles;stall_probe=0;accept_events=1;attached=1;
        wait(received==256&&connections==2&&tiles>=previous_tiles+2&&protocol_status[9]);
        if(protocol_errors!=0||flags!=7||!remote_enable)$fatal(1,"reconnect PL/MIDI");
        if(PEER_USB2!=0)begin
            if(chirp_commands<2||normal_packets<100||phy_function!=8'h45)
                $fatal(1,"USB3300 fallback not exercised chirps=%0d packets=%0d function=%02x",chirp_commands,normal_packets,phy_function);
            $display("PASS USB1 host / USB2 device FS fallback: ULPI boot/chirp timeout/64B/MIDI 256/PL CAPS tiles/warm hotplug chirps=%0d packets=%0d",chirp_commands,normal_packets);
        end
        $display("PASS USB1 physical FS pair: production RV32I/NRZI/CRC/enumeration/MIDI 256/PL CAPS tiles/backpressure/hotplug stale-event fence");
        $finish;
    end
    initial begin
        #1500000000;
        $fatal(1,"USB1 timeout pc=%08x flags=%x events=%0d tiles=%0d status=%x line=%x peer_addr=%0d configured=%b",
            host.instruction_address,flags,received,tiles,protocol_status,line_state,peer_address,peer_online);
    end
endmodule
