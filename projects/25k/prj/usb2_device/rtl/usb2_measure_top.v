`timescale 1ns/1ps
`default_nettype none
// Stable USB3300 voltage-measurement image. Normal synchronous ULPI only:
// FC45 = FS DP pull-up; OTG04 = DM pull-down; IF00 = ULPI clock remains on.
// DATA is never interpreted as low-power LineState. Read Debug15 instead.
module usb2_device_top #(
    parameter integer TIMEOUT_CYCLES = 10000000,
    parameter integer STARTUP_CYCLES = 32,
    parameter integer POLL_GAP_CYCLES = 50000
) (
    input wire clk_50mhz,
    input wire clk_ulpi60,
    inout wire [7:0] ulpi_data,
    input wire ulpi_dir,
    input wire ulpi_nxt,
    output wire ulpi_stp,
    output wire led_ready,
    output wire led_done
);
    reg [12:0] powerup = 0;
    always @(posedge clk_50mhz)
        if (!powerup[12]) powerup<=powerup+1'b1;
    wire reset_n = powerup[12];
    (* syn_preserve=1 *) reg reset_meta60=0, reset_sync60=0;
    always @(posedge clk_ulpi60 or negedge reset_n) begin
        if (!reset_n) begin reset_meta60<=0; reset_sync60<=0; end
        else begin reset_meta60<=1; reset_sync60<=reset_meta60; end
    end

    reg run_request50=1, force_stp50=1;
    reg request_toggle50=0, request_write50=0;
    reg [5:0] request_addr50=0;
    reg [7:0] request_data50=0;
    wire [7:0] data_in, data_out;
    wire master_ready60, master_stp60, awake60, ack_toggle60, response_error60;
    wire [7:0] response_data60;
    wire drive_ready = reset_n && run_request50 && master_ready60;
    assign ulpi_stp = !reset_n || force_stp50 || master_stp60;
    usb2_lowpower_master u_master (
        .clk60(clk_ulpi60), .reset_n(reset_sync60),
        .data_i(data_in), .data_o(data_out), .drive_ready(master_ready60),
        .dir(ulpi_dir), .nxt(ulpi_nxt), .stp(master_stp60),
        .run_request50(run_request50), .request_toggle50(request_toggle50),
        .request_write50(request_write50), .request_suspend50(1'b0),
        .request_addr50(request_addr50), .request_data50(request_data50),
        .awake(awake60), .ack_toggle(ack_toggle60),
        .response_data(response_data60), .response_error(response_error60)
    );
    genvar pad;
    generate for (pad=0;pad<8;pad=pad+1) begin:pads
        wire output_disable;
        LUT2 #(.INIT(4'hb)) u_enable /* synthesis syn_dont_touch=1 */ (
            .I0(ulpi_dir), .I1(drive_ready), .F(output_disable)
        );
        IOBUF u_pad (.I(data_out[pad]), .O(data_in[pad]),
                    .OEN(output_disable), .IO(ulpi_data[pad]));
    end endgenerate

    (* syn_preserve=1 *) reg ack_meta50=0, ack_sync50=0;
    (* syn_preserve=1 *) reg awake_meta50=0, awake_sync50=0;
    (* syn_preserve=1 *) reg error_meta50=0, error_sync50=0;
    (* syn_preserve=1 *) reg [7:0] response_meta50=0, response_sync50=0;
    (* syn_preserve=1 *) reg dir_meta50=0, dir_sync50=0;
    reg [15:0] clock_binary60=0;
    (* syn_preserve=1 *) reg [15:0] clock_gray60=0;
    (* syn_preserve=1 *) reg [15:0] clock_gray_meta50=0, clock_gray_sync50=0;
    reg [15:0] clock_gray_prev50=0;
    reg [15:0] clock_quiet50=0;
    reg clock_alive=0;
    always @(posedge clk_ulpi60 or negedge reset_sync60) begin
        if (!reset_sync60) begin clock_binary60<=0;clock_gray60<=0;end
        else begin
            clock_binary60<=clock_binary60+1'b1;
            clock_gray60<=((clock_binary60+16'd1)>>1)^(clock_binary60+16'd1);
        end
    end
    always @(posedge clk_50mhz or negedge reset_n) begin
        if (!reset_n) begin
            ack_meta50<=0;ack_sync50<=0;awake_meta50<=0;awake_sync50<=0;
            error_meta50<=0;error_sync50<=0;response_meta50<=0;response_sync50<=0;
            dir_meta50<=0;dir_sync50<=0;clock_gray_meta50<=0;clock_gray_sync50<=0;
            clock_gray_prev50<=0;clock_quiet50<=0;clock_alive<=0;
        end else begin
            ack_meta50<=ack_toggle60;ack_sync50<=ack_meta50;
            awake_meta50<=awake60;awake_sync50<=awake_meta50;
            error_meta50<=response_error60;error_sync50<=error_meta50;
            response_meta50<=response_data60;response_sync50<=response_meta50;
            dir_meta50<=ulpi_dir;dir_sync50<=dir_meta50;
            clock_gray_meta50<=clock_gray60;clock_gray_sync50<=clock_gray_meta50;
            clock_gray_prev50<=clock_gray_sync50;
            if (clock_gray_sync50!=clock_gray_prev50) begin
                clock_quiet50<=0;clock_alive<=1;
            end else if (clock_quiet50<16'd50000) begin
                clock_quiet50<=clock_quiet50+1'b1;
                if(clock_quiet50==16'd49999) clock_alive<=0;
            end
        end
    end

    localparam [2:0] Q_START=0,Q_GUARD=1,Q_ISSUE=2,Q_ACK=3,Q_GAP=4,Q_FAIL=5;
    reg [2:0] qstate=Q_START;
    reg [31:0] timer50=0,delay50=0;
    reg [4:0] operation=0;
    reg done=0,error=0,id_ok=0;
    reg [3:0] errorcode=0;
    reg [7:0] stage=0,fc=0,if_ctrl=0,otg=0,debug_last=0;
    reg [15:0] vid=0,pid=0;
    reg [3:0] debug_seen_mask=0;
    reg [19:0] debug_read_count=0;
    task fail_measure;
        input [3:0] reason;
        begin
            done<=0;error<=1;errorcode<=reason;
            run_request50<=0;force_stp50<=1;qstate<=Q_FAIL;
        end
    endtask
    task issue_request;
        input wr;
        input [5:0] addr;
        input [7:0] value;
        begin
            request_write50<=wr;request_addr50<=addr;request_data50<=value;
            request_toggle50<=!request_toggle50;timer50<=0;qstate<=Q_ACK;
        end
    endtask
    always @(posedge clk_50mhz or negedge reset_n) begin
        if (!reset_n) begin
            qstate<=Q_START;timer50<=0;delay50<=0;operation<=0;
            run_request50<=1;force_stp50<=1;
            request_toggle50<=0;request_write50<=0;request_addr50<=0;request_data50<=0;
            done<=0;error<=0;id_ok<=0;errorcode<=0;stage<=0;
            fc<=0;if_ctrl<=0;otg<=0;vid<=0;pid<=0;
            debug_last<=0;debug_seen_mask<=0;debug_read_count<=0;
        end else if(qstate!=Q_FAIL) begin
            // Independent 50 MHz watchdog still responds if CLKOUT vanishes.
            if(timer50>=TIMEOUT_CYCLES-1) fail_measure(1);
            else begin
                timer50<=timer50+1'b1;
                case(qstate)
                    Q_START: if(clock_alive && awake_sync50 && !dir_sync50) begin
                        force_stp50<=0;timer50<=0;delay50<=0;qstate<=Q_GUARD;
                    end
                    Q_GUARD: begin
                        if(delay50>=STARTUP_CYCLES-1) begin timer50<=0;qstate<=Q_ISSUE;end
                        else delay50<=delay50+1'b1;
                    end
                    Q_ISSUE: begin
                        stage<=operation==14 ? 8'h20 : {3'b0,operation}+1'b1;
                        case(operation)
                            0:issue_request(0,6'h00,0);
                            1:issue_request(0,6'h01,0);
                            2:issue_request(0,6'h02,0);
                            3:issue_request(0,6'h03,0);
                            4:issue_request(1,6'h16,8'h55);
                            5:issue_request(0,6'h16,0);
                            6:issue_request(1,6'h16,8'haa);
                            7:issue_request(0,6'h16,0);
                            8:issue_request(1,6'h07,8'h00);
                            9:issue_request(0,6'h07,0);
                            10:issue_request(1,6'h0a,8'h04);
                            11:issue_request(0,6'h0a,0);
                            12:issue_request(1,6'h04,8'h45);
                            13:issue_request(0,6'h04,0);
                            14:issue_request(0,6'h15,0);
                            default:fail_measure(7);
                        endcase
                    end
                    Q_ACK: if(ack_sync50==request_toggle50) begin
                        timer50<=0;
                        if(error_sync50) fail_measure(2);
                        else begin
                            operation<=operation+1'b1;qstate<=Q_ISSUE;
                            case(operation)
                                0:vid[7:0]<=response_sync50;
                                1:vid[15:8]<=response_sync50;
                                2:pid[7:0]<=response_sync50;
                                3:begin
                                    pid[15:8]<=response_sync50;
                                    if(vid!=16'h0424 || {response_sync50,pid[7:0]}!=16'h0004) fail_measure(3);
                                    else id_ok<=1;
                                end
                                5:if(response_sync50!=8'h55) fail_measure(4);
                                7:if(response_sync50!=8'haa) fail_measure(4);
                                9:begin if_ctrl<=response_sync50;if(response_sync50!=0) fail_measure(6);end
                                11:begin otg<=response_sync50;if(response_sync50!=8'h04) fail_measure(6);end
                                13:begin fc<=response_sync50;if(response_sync50!=8'h45) fail_measure(6);end
                                14:begin
                                    debug_last<=response_sync50;
                                    debug_seen_mask<=debug_seen_mask | (4'b0001 << response_sync50[1:0]);
                                    if(debug_read_count!=20'hfffff) debug_read_count<=debug_read_count+1'b1;
                                    done<=1;operation<=14;delay50<=0;qstate<=Q_GAP;
                                end
                                default:begin end
                            endcase
                        end
                    end
                    Q_GAP: begin
                        if(delay50>=POLL_GAP_CYCLES-1) begin timer50<=0;qstate<=Q_ISSUE;end
                        else delay50<=delay50+1'b1;
                    end
                    default:fail_measure(7);
                endcase
            end
        end
    end

    // Independent four-page layout for this voltage-measurement image.
    // page0 VID/PID; page1 FC/IF/OTG/error; page2 Debug/mask/read-count; page3 0.
    wire [127:0] live_pages={vid,pid,fc,if_ctrl,otg,4'b0,errorcode,
                            debug_last,debug_seen_mask,debug_read_count,32'b0};
    reg [127:0] pages_hold=0;
    reg [7:0] stage_hold=0;
    reg [4:0] flags_hold=0,page_phase=0;
    reg heartbeat=0;
    always @(posedge clk_50mhz) begin
        page_phase<=page_phase+1'b1;heartbeat<=~heartbeat;
        if(page_phase==5'd31) begin
            pages_hold<=live_pages;stage_hold<=stage;
            flags_hold<={1'b0,done,id_ok,error,clock_alive};
        end
    end
    wire [31:0] payload=page_phase[4:3]==0 ? pages_hold[127:96] :
                        page_phase[4:3]==1 ? pages_hold[95:64] :
                        page_phase[4:3]==2 ? pages_hold[63:32] : pages_hold[31:0];
    wire [63:0] status_raw={payload,16'b0,stage_hold,flags_hold,page_phase[4:3],heartbeat};
    reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50mhz) status_50mhz<=status_raw;
    assign led_ready=clock_alive;
    assign led_done=done && id_ok && !error;
endmodule
`default_nettype wire
