// Original radio pins; BLE stays autonomous, Wi-Fi is controlled over JTAG.
module wifi_scan_top(
    input wire clk_50mhz,restart_n,module_uart_tx,
    inout wire module_uart_rx,module_bt_dis_n,
    output wire module_wl_dis_n,wifi_sd_clk,debug_uart_tx,
    inout wire wifi_sd_cmd,
    inout wire [3:0] wifi_sd_dat,
    input wire tck_pad_i,tms_pad_i,tdi_pad_i,
    output wire tdo_pad_o
);
    wire [767:0] ble_status;
    wire board_resetn;
    ble_bringup_top #(.SESSION_MS(0)) ble(
        .clk_50mhz(clk_50mhz),.restart_n(restart_n),.module_uart_tx(module_uart_tx),
        .module_uart_rx(module_uart_rx),.module_bt_dis_n(module_bt_dis_n),
        .usb1_dp(1'b1),.usb1_dm(1'b1),.led_ready(),.led_done(),
        .debug_status(ble_status),.board_resetn(board_resetn));
    assign debug_uart_tx=1'b1;
    assign wifi_sd_dat[3:1]=3'bzzz;
    reg wl_enable=0;
    assign module_wl_dis_n=board_resetn && wl_enable;
    wire request;
    wire [95:0] request_data;
    reg reply=0;
    reg [95:0] reply_data=0;
    wifi_jtag_mailbox mailbox(.clk(clk_50mhz),.request(request),.request_data(request_data),
        .reply(reply),.reply_data(reply_data),.tck_pad_i(tck_pad_i),.tms_pad_i(tms_pad_i),
        .tdi_pad_i(tdi_pad_i),.tdo_pad_o(tdo_pad_o));
    wire [10:0] tx_address,rx_address;
    wire [7:0] rx_data;
    wire rx_write;
    wire [31:0] tx_word;
    reg [1:0] tx_byte=0;
    wire [7:0] tx_data=tx_word[8*tx_byte +: 8];
    // One shared read port, four byte-wide RAM banks. RX byte writes and
    // host word writes are mutually exclusive; neither creates a RAM clock.
    wire [8:0] memory_read_address=(pending && !read_pending) ? tx_address[10:2] : request_data[40:32];
    genvar lane;
    generate for(lane=0;lane<4;lane=lane+1) begin: buffer_bank
        reg [7:0] bytes [0:511];
        reg [7:0] read_byte;
        always @(posedge clk_50mhz) begin
            read_byte<=bytes[memory_read_address];
            if(rx_write && rx_address[1:0]==lane) bytes[rx_address[10:2]]<=rx_data;
            else if(request && request_data[7:0]==2 && !pending)
                bytes[request_data[40:32]]<=request_data[64+8*lane +: 8];
        end
        assign tx_word[8*lane +: 8]=read_byte;
    end endgenerate
    always @(posedge clk_50mhz) begin
        tx_byte<=tx_address[1:0];
    end
    reg start=0;
    reg [5:0] command=0;
    reg [31:0] argument=0;
    reg expect_response=0,check_crc=0,wait_busy=0;
    wire transfer_idle,transfer_done;
    wire [3:0] transfer_error;
    wire [31:0] transfer_response;
    sdio_transfer bus(.clk(clk_50mhz),.resetn(board_resetn && wl_enable),.start(start),
        .command(command),.argument(argument),.expect_response(expect_response),
        .check_crc(check_crc),.wait_busy(wait_busy),.sd_clk(wifi_sd_clk),.sd_cmd(wifi_sd_cmd),
        .sd_dat0(wifi_sd_dat[0]),.idle(transfer_idle),.done(transfer_done),.error(transfer_error),
        .response(transfer_response),.tx_address(tx_address),.tx_data(tx_data),
        .rx_write(rx_write),.rx_address(rx_address),.rx_data(rx_data));
    reg pending=0;
    reg read_pending=0;
    reg [31:0] saved_tag=0;
    always @(posedge clk_50mhz) begin
        reply<=0; start<=0;
        if(request && !pending) begin
            saved_tag<=request_data[31:0];
            case(request_data[7:0])
                1: begin
                    if(transfer_idle && module_wl_dis_n) begin
                        command<=request_data[69:64]; argument<=request_data[63:32];
                        expect_response<=!request_data[70]; check_crc<=!request_data[71];
                        wait_busy<=request_data[72]; start<=1; pending<=1;
                    end else begin reply<=1; reply_data<={32'h0000000e,32'd0,request_data[31:0]}; end
                end
                2: begin reply<=1; reply_data<={32'd0,request_data[95:64],request_data[31:0]}; end
                3: begin read_pending<=1; pending<=1; end
                4: begin
                    wl_enable<=request_data[32]; reply<=1;
                    reply_data<={32'd0,request_data[63:32],request_data[31:0]};
                end
                5: begin reply<=1; reply_data<={32'd0,ble_status[request_data[36:32]*32 +: 32],request_data[31:0]}; end
                127: begin reply<=1; reply_data<={32'd0,32'h5344494f,request_data[31:0]}; end
                default: begin reply<=1; reply_data<={32'h0000000f,32'd0,request_data[31:0]}; end
            endcase
        end
        if(read_pending) begin
            read_pending<=0; pending<=0; reply<=1; reply_data<={32'd0,tx_word,saved_tag};
        end
        if(pending && transfer_done) begin
            pending<=0; reply<=1; reply_data<={28'd0,transfer_error,transfer_response,saved_tag};
        end
    end
endmodule
