`timescale 1ns/1ps
// Explicit probe transport, disabled by default. Typed transactions are NOT
// the existing USB/BLE wire protocols. No probe result grants audio permission:
// business needs BOTH ALLOW_BUSINESS and external measured budget qualification.
// All frame bytes use the local clock and the conservative nibble PHY.
module workstation_task3_lcd_transport #(
    parameter bit EXPERIMENT_ENABLE=1'b0,
    parameter bit ALLOW_BUSINESS=1'b0,
    parameter integer PHY_STALL_TIMEOUT_CYCLES=50000,
    parameter integer HEARTBEAT_INTERVAL_CYCLES=500000,
    parameter integer PROBE_INTERVAL_CYCLES=1000000,
    parameter integer LINK_TIMEOUT_CYCLES=5000000
)(
    input wire clk_i,reset_ni,enable_i,panic_i,budget_validated_i,
    input wire [31:0] local_boot_i,peer_boot_i,session_i,
    input wire tx_valid_i,
    output wire tx_ready_o,
    input wire [3:0] tx_channel_i,
    input wire [255:0] tx_payload_i,
    input wire [5:0] tx_length_i,
    output wire rx_valid_o,
    input wire rx_ready_i,
    output reg [3:0] rx_channel_o,
    output reg [255:0] rx_payload_o,
    output reg [5:0] rx_length_o,
    output wire link_ready_o,business_ready_o,pad_drive_o,
    output reg fault_o,
    output reg [3:0] failure_code_o,
    output wire peer_panic_o,
    output wire [3:0] phy_tx_data_o,
    output wire phy_tx_req_o,phy_rx_ack_o,phy_panic_o,
    input wire [3:0] phy_rx_data_i,
    input wire phy_rx_req_i,phy_tx_ack_i,phy_peer_panic_i,
    output reg [31:0] tx_packets_o,rx_packets_o,crc_errors_o,sequence_errors_o,
    output reg [31:0] rejected_packets_o,overflow_count_o,congestion_cycles_o,
    output reg [31:0] last_rtt_cycles_o,max_rtt_cycles_o,probe_results_o,link_timeouts_o
);
    // Fixed 52-byte frame: D3,version1,kind,channel,length,reserved0,
    // sender boot32,session32,sequence32,payload32,CRC16-CCITT, little endian
    // integers/CRC. CRC covers bytes0..49, initFFFF, polynomial1021.
    localparam [2:0] TX_IDLE=0,TX_BUILD=1,TX_SEND=2;
    reg [2:0] tx_state;
    reg [415:0] tx_packet,rx_packet;
    reg [5:0] tx_index,rx_index;
    reg [15:0] tx_crc,rx_crc;
    reg [31:0] tx_sequence,rx_sequence,clock_counter,tx_age,rx_age,probe_age;
    reg [31:0] held_local_boot,held_peer_boot,held_session,probe_token,probe_sent_at;
    reg enabled_q,peer_seen,tx_ever_sent,probe_pending,echo_pending,rx_held_valid;
    reg [63:0] echo_payload;
    wire phy_tx_ready,phy_rx_valid,phy_fault;
    wire [7:0] phy_rx_byte;
    wire active=EXPERIMENT_ENABLE && enable_i;
    wire config_good=local_boot_i!=0 && peer_boot_i!=0 && session_i!=0;
    wire live=reset_ni && active && enabled_q && !fault_o && !panic_i && !peer_panic_o;
    assign pad_drive_o=active;
    assign phy_panic_o=active && panic_i;
    assign link_ready_o=live && peer_seen;
    assign business_ready_o=link_ready_o && ALLOW_BUSINESS && budget_validated_i;
    assign rx_valid_o=live && rx_held_valid && (rx_channel_o==0 || business_ready_o);
    wire probe_due=peer_seen && !probe_pending && probe_age>=32'(PROBE_INTERVAL_CYCLES);
    wire heartbeat_due=!tx_ever_sent || tx_age>=32'(HEARTBEAT_INTERVAL_CYCLES);
    wire maintenance=echo_pending || probe_due || heartbeat_due;
    assign tx_ready_o=live && config_good && tx_state==TX_IDLE && !maintenance &&
        tx_length_i<=32 && (tx_channel_i==0 || business_ready_o) && tx_sequence!=32'hffffffff;
    wire tx_is_business=tx_state!=TX_IDLE && tx_packet[23:16]==4;
    wire phy_byte_valid=live && tx_state==TX_SEND && (!tx_is_business || business_ready_o);
    wire phy_byte_fire=phy_byte_valid && phy_tx_ready;
    wire [7:0] header_kind=rx_packet[23:16];
    wire [7:0] header_channel=rx_packet[31:24];
    wire [7:0] header_length=rx_packet[39:32];
    wire [31:0] header_boot=rx_packet[79:48],header_session=rx_packet[111:80],header_sequence=rx_packet[143:112];
    wire [255:0] header_payload=rx_packet[399:144];
    wire header_bad=rx_packet[15:8]!=1 || rx_packet[47:40]!=0 ||
        header_kind>4 || header_channel>15 || header_length>32 ||
        ((header_kind<=2) && (header_channel!=0 || header_length!=(header_kind==0?0:8))) ||
        (header_kind==3 && header_channel!=0) || (header_kind==4 && header_channel==0);
    function automatic [15:0] crc16_byte(input [15:0] old_crc,input [7:0] byte_value);
        reg [15:0] c;integer b;
        begin c=old_crc^{byte_value,8'd0};for(b=0;b<8;b=b+1)c=c[15]?((c<<1)^16'h1021):(c<<1);crc16_byte=c;end
    endfunction
    task automatic fail(input [3:0] code);
        begin fault_o<=1;failure_code_o<=code;peer_seen<=0;rx_held_valid<=0;end
    endtask
    task automatic launch(input [7:0] kind,input [3:0] channel,input [5:0] length,input [255:0] payload);
        integer b;
        begin
            tx_packet<=0;
            tx_packet[7:0]<=8'hd3;tx_packet[15:8]<=8'd1;tx_packet[23:16]<=kind;
            tx_packet[31:24]<={4'd0,channel};tx_packet[39:32]<={2'd0,length};tx_packet[47:40]<=0;
            tx_packet[79:48]<=held_local_boot;tx_packet[111:80]<=held_session;tx_packet[143:112]<=tx_sequence;
            for(b=0;b<32;b=b+1)tx_packet[144+b*8+:8]<=b<integer'(length)?payload[b*8+:8]:8'd0;
            tx_crc<=16'hffff;tx_index<=0;tx_state<=TX_BUILD;tx_age<=0;tx_ever_sent<=1;
            tx_sequence<=tx_sequence+1'b1;
        end
    endtask
    initial if(HEARTBEAT_INTERVAL_CYCLES<16 || PROBE_INTERVAL_CYCLES<16 ||
        LINK_TIMEOUT_CYCLES<=HEARTBEAT_INTERVAL_CYCLES || LINK_TIMEOUT_CYCLES>=32'h80000000)
        $fatal(1,"invalid bounded LCD probe timing");
    workstation_task3_lcd_phy #(.STALL_TIMEOUT_CYCLES(PHY_STALL_TIMEOUT_CYCLES)) phy(
        .clk_i(clk_i),.reset_ni(reset_ni),.enable_i(active && enabled_q && !fault_o),.panic_i(panic_i),
        .tx_valid_i(phy_byte_valid),.tx_ready_o(phy_tx_ready),.tx_byte_i(tx_packet[tx_index*8+:8]),
        .rx_valid_o(phy_rx_valid),.rx_ready_i(1'b1),.rx_byte_o(phy_rx_byte),
        .tx_data_o(phy_tx_data_o),.tx_req_o(phy_tx_req_o),.rx_ack_o(phy_rx_ack_o),
        .rx_data_i(phy_rx_data_i),.rx_req_i(phy_rx_req_i),.tx_ack_i(phy_tx_ack_i),.peer_panic_i(phy_peer_panic_i),
        .peer_panic_o(peer_panic_o),.fault_o(phy_fault),.timeout_count_o(),.tx_bytes_o(),.rx_bytes_o());
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            tx_state<=TX_IDLE;tx_packet<=0;rx_packet<=0;tx_index<=0;rx_index<=0;tx_crc<=16'hffff;rx_crc<=16'hffff;
            tx_sequence<=0;rx_sequence<=0;clock_counter<=0;tx_age<=0;rx_age<=0;probe_age<=0;
            held_local_boot<=0;held_peer_boot<=0;held_session<=0;probe_token<=0;probe_sent_at<=0;
            enabled_q<=0;peer_seen<=0;tx_ever_sent<=0;probe_pending<=0;echo_pending<=0;echo_payload<=0;rx_held_valid<=0;
            rx_channel_o<=0;rx_payload_o<=0;rx_length_o<=0;fault_o<=0;failure_code_o<=0;
            tx_packets_o<=0;rx_packets_o<=0;crc_errors_o<=0;sequence_errors_o<=0;
            rejected_packets_o<=0;overflow_count_o<=0;congestion_cycles_o<=0;
            last_rtt_cycles_o<=0;max_rtt_cycles_o<=0;probe_results_o<=0;link_timeouts_o<=0;
        end else begin
            clock_counter<=clock_counter+1'b1;
            if(!active)begin
                enabled_q<=0;peer_seen<=0;tx_state<=TX_IDLE;rx_index<=0;tx_sequence<=0;rx_sequence<=0;
                tx_ever_sent<=0;probe_pending<=0;echo_pending<=0;rx_held_valid<=0;
                tx_age<=0;rx_age<=0;probe_age<=0;fault_o<=0;failure_code_o<=0;
            end else if(!enabled_q)begin
                enabled_q<=1;held_local_boot<=local_boot_i;held_peer_boot<=peer_boot_i;held_session<=session_i;
                if(!config_good)fail(1);
            end else if(!fault_o)begin
                if(panic_i || peer_panic_o)fail(2);
                else if(local_boot_i!=held_local_boot || peer_boot_i!=held_peer_boot || session_i!=held_session)fail(1);
                else if(phy_fault)fail(3);
                else if(!business_ready_o && (tx_is_business || (rx_held_valid && rx_channel_o!=0)))begin
                    // Budget revocation cancels held/in-flight business, never
                    // defers it for replay after a later qualification.
                    if(!(&rejected_packets_o))rejected_packets_o<=rejected_packets_o+1'b1;fail(9);
                end
                else if(rx_age==32'(LINK_TIMEOUT_CYCLES) ||
                    (probe_pending && clock_counter-probe_sent_at>=32'(LINK_TIMEOUT_CYCLES)))begin
                    fail(4);if(!(&link_timeouts_o))link_timeouts_o<=link_timeouts_o+1'b1;
                end else begin
                    if(tx_age<32'(HEARTBEAT_INTERVAL_CYCLES))tx_age<=tx_age+1'b1;
                    if(probe_age<32'(PROBE_INTERVAL_CYCLES))probe_age<=probe_age+1'b1;
                    if(rx_age<32'(LINK_TIMEOUT_CYCLES))rx_age<=rx_age+1'b1;
                    if(rx_valid_o && rx_ready_i)rx_held_valid<=0;
                    if(tx_valid_i && !tx_ready_o && !(&congestion_cycles_o))congestion_cycles_o<=congestion_cycles_o+1'b1;
                    case(tx_state)
                        TX_IDLE:begin
                            if(tx_sequence==32'hffffffff)fail(5);
                            else if(echo_pending)begin launch(2,0,8,{192'd0,echo_payload});echo_pending<=0;end
                            else if(probe_due)begin
                                launch(1,0,8,{192'd0,probe_token,clock_counter});probe_pending<=1;
                                probe_sent_at<=clock_counter;probe_age<=0;
                            end else if(heartbeat_due)launch(0,0,0,0);
                            else if(tx_valid_i && tx_ready_o)launch(tx_channel_i==0?8'd3:8'd4,tx_channel_i,tx_length_i,tx_payload_i);
                        end
                        TX_BUILD:begin
                            tx_crc<=crc16_byte(tx_crc,tx_packet[tx_index*8+:8]);
                            if(tx_index==49)begin
                                tx_packet[415:400]<=crc16_byte(tx_crc,tx_packet[tx_index*8+:8]);tx_index<=0;tx_state<=TX_SEND;
                            end else tx_index<=tx_index+1'b1;
                        end
                        TX_SEND:if(phy_byte_fire)begin
                            if(tx_index==51)begin tx_state<=TX_IDLE;tx_index<=0;if(!(&tx_packets_o))tx_packets_o<=tx_packets_o+1'b1;end
                            else tx_index<=tx_index+1'b1;
                        end
                        default:tx_state<=TX_IDLE;
                    endcase
                    if(phy_rx_valid)begin
                        if(rx_index==0)begin
                            if(phy_rx_byte==8'hd3)begin rx_packet[7:0]<=phy_rx_byte;rx_crc<=crc16_byte(16'hffff,phy_rx_byte);rx_index<=1;end
                        end else begin
                            rx_packet[rx_index*8+:8]<=phy_rx_byte;
                            if(rx_index<50)rx_crc<=crc16_byte(rx_crc,phy_rx_byte);
                            if(rx_index==51)begin
                                rx_index<=0;
                                if({phy_rx_byte,rx_packet[407:400]}!=rx_crc)begin
                                    if(!(&crc_errors_o))crc_errors_o<=crc_errors_o+1'b1;fail(6);
                                end else if(header_bad || header_boot!=held_peer_boot || header_session!=held_session)begin
                                    if(!(&rejected_packets_o))rejected_packets_o<=rejected_packets_o+1'b1;fail(7);
                                end else if(header_sequence!=rx_sequence || rx_sequence==32'hffffffff)begin
                                    if(!(&sequence_errors_o))sequence_errors_o<=sequence_errors_o+1'b1;fail(5);
                                end else begin
                                    rx_sequence<=rx_sequence+1'b1;rx_age<=0;peer_seen<=1;
                                    if(!(&rx_packets_o))rx_packets_o<=rx_packets_o+1'b1;
                                    if(header_kind==1)begin
                                        if(echo_pending)begin if(!(&overflow_count_o))overflow_count_o<=overflow_count_o+1'b1;fail(8);end
                                        else begin echo_pending<=1;echo_payload<=header_payload[63:0];end
                                    end else if(header_kind==2)begin
                                        if(!probe_pending || header_payload[63:32]!=probe_token || header_payload[31:0]!=probe_sent_at)begin
                                            if(!(&rejected_packets_o))rejected_packets_o<=rejected_packets_o+1'b1;fail(7);
                                        end else begin
                                            probe_pending<=0;probe_token<=probe_token+1'b1;
                                            last_rtt_cycles_o<=clock_counter-probe_sent_at;
                                            if(clock_counter-probe_sent_at>max_rtt_cycles_o)max_rtt_cycles_o<=clock_counter-probe_sent_at;
                                            if(!(&probe_results_o))probe_results_o<=probe_results_o+1'b1;
                                        end
                                    end else if(header_kind==3 || header_kind==4)begin
                                        if(header_kind==4 && !business_ready_o)begin
                                            if(!(&rejected_packets_o))rejected_packets_o<=rejected_packets_o+1'b1;fail(9);
                                        end else if(rx_held_valid && !rx_ready_i)begin
                                            if(!(&overflow_count_o))overflow_count_o<=overflow_count_o+1'b1;fail(8);
                                        end else begin
                                            rx_channel_o<=header_channel[3:0];rx_length_o<=header_length[5:0];rx_payload_o<=header_payload;rx_held_valid<=1;
                                        end
                                    end
                                end
                            end else rx_index<=rx_index+1'b1;
                        end
                    end
                end
            end else begin tx_state<=TX_IDLE;rx_held_valid<=0;end
        end
    end
endmodule
