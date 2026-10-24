// Native 1-bit SDIO discovery, no CMD53/data DMA/firmware/network stack.
// CMD0, CMD5 query/poll, CMD3, CMD7, CMD52 CCCR + bounded CIS walk,
// then IOEx / IORx function-1 enable. All data lines remain inputs.
module sdio_identify #(
    parameter integer CLK_HZ=50000000,
    parameter integer SD_HZ=250000,
    parameter integer POWER_MS=200,
    parameter integer MAX_POLLS=1000,
    parameter [15:0] EXPECTED_VENDOR=16'h024c,
    parameter [15:0] EXPECTED_DEVICE=16'hd723
)(
    input wire clk, resetn,
    output wire sd_clk,
    inout wire sd_cmd,
    input wire [3:0] sd_dat,
    output reg wl_enable,
    output reg done, identified, failed,
    output wire [255:0] debug
);
    localparam integer MS_TICKS=CLK_HZ/1000;
    localparam POWER=0, CLOCKS=1, ISSUE=2, WAIT_CMD=3, NEXT=4, POLL_DELAY=5, FINISH=6, FAIL=7;
    reg [3:0] state;
    reg [5:0] step;
    reg [31:0] ms_div, power_ms;
    wire ms_tick=ms_div==MS_TICKS-1;
    reg [6:0] startup_clocks;
    reg start;
    reg [5:0] command;
    reg [31:0] argument;
    wire [31:0] response;
    wire cmd_done, cmd_idle, card_tick;
    wire [3:0] cmd_error;
    reg [31:0] last_response, command_count;
    reg [7:0] error_code;
    reg [31:0] ocr;
    reg [15:0] rca, vendor_id, device_id;
    reg [7:0] cccr_revision, capabilities, function_interface;
    reg [23:0] cis_pointer;
    reg [16:0] cursor;
    reg [7:0] tuple_code, tuple_link;
    reg [2:0] man_index;
    reg [8:0] tuple_count;
    reg [15:0] polls;
    wire cmd52_write=step==20;
    wire [16:0] address = step==4 ? 17'h00000 : step==5 ? 17'h00008 :
        step==6 ? 17'h00009 : step==7 ? 17'h0000a : step==8 ? 17'h0000b :
        step==9 ? 17'h00100 : step==19 || step==20 ? 17'h00002 :
        step==21 ? 17'h00003 : cursor;
    reg [7:0] io_enable;
    (* ASYNC_REG = "TRUE" *) reg [3:0] dat_meta, dat_sync;
    always @(posedge clk) begin
        if(!resetn) begin dat_meta<=4'hf; dat_sync<=4'hf; end
        else begin dat_meta<=sd_dat; dat_sync<=dat_meta; end
    end
    always @* begin
        command=52;
        argument={cmd52_write,3'b000,1'b0,1'b0,address,1'b0,(cmd52_write ? io_enable|8'h02 : 8'h00)};
        case(step)
            0: begin command=0; argument=0; end
            1: begin command=5; argument=0; end
            2: begin command=5; argument=ocr & 32'h00300000; end
            3: begin command=3; argument=0; end
            22: begin command=7; argument={rca,16'b0}; end
        endcase
    end
    sdio_command #(.CLK_HZ(CLK_HZ),.SD_HZ(SD_HZ)) bus (
        .clk(clk),.resetn(resetn),.start(start),.command(command),.argument(argument),
        .expect_response(step!=0),.check_crc(step!=1 && step!=2),.wait_busy(step==22),
        .dat0(sd_dat[0]),.sd_clk(sd_clk),.sd_cmd(sd_cmd),.idle(cmd_idle),
        .card_tick(card_tick),.done(cmd_done),.error(cmd_error),.response(response));
    assign debug[31:0]=32'h5344494f;
    assign debug[63:32]={error_code,4'b0,dat_sync,step,2'b0,state,failed,identified,done,wl_enable};
    assign debug[95:64]=ocr;
    assign debug[127:96]={rca,cccr_revision,capabilities};
    assign debug[159:128]={function_interface,cis_pointer};
    assign debug[191:160]={vendor_id,device_id};
    assign debug[223:192]=last_response;
    assign debug[255:224]=command_count;
    task fail_with;
        input [7:0] code;
        begin failed<=1; error_code<=code; state<=FAIL; end
    endtask
    task advance;
        input [5:0] next_step;
        begin step<=next_step; state<=ISSUE; end
    endtask
    always @(posedge clk) begin
        if(!resetn) begin
            state<=POWER; step<=0; ms_div<=0; power_ms<=0; startup_clocks<=0;
            wl_enable<=0; done<=0; identified<=0; failed<=0; error_code<=0;
            start<=0; ocr<=0; rca<=0; cccr_revision<=0; capabilities<=0;
            cis_pointer<=0; cursor<=0; tuple_code<=0; tuple_link<=0; man_index<=0;
            vendor_id<=0; device_id<=0; function_interface<=0; tuple_count<=0;
            polls<=0; io_enable<=0; last_response<=0; command_count<=0;
        end else begin
            start<=0;
            if(ms_tick) ms_div<=0; else ms_div<=ms_div+1'b1;
            case(state)
                POWER: if(ms_tick) begin
                    if(power_ms==POWER_MS-1) begin wl_enable<=1; power_ms<=0; state<=CLOCKS; end
                    else power_ms<=power_ms+1'b1;
                end
                CLOCKS: if(ms_tick) begin
                    // Additional power stabilization after releasing WL_DIS#.
                    if(power_ms==POWER_MS-1) begin power_ms<=0; startup_clocks<=0; state<=NEXT; end
                    else power_ms<=power_ms+1'b1;
                end
                NEXT: if(card_tick) begin
                    if(startup_clocks==79) advance(0);
                    else startup_clocks<=startup_clocks+1'b1;
                end
                ISSUE: if(cmd_idle && !start) begin start<=1; state<=WAIT_CMD; end
                WAIT_CMD: if(cmd_done) begin
                    last_response<=response; command_count<=command_count+1'b1;
                    if(cmd_error!=0) fail_with({4'h1,cmd_error});
                    else if(command==52 && (response & 32'h0000cb00)!=0) fail_with(8'h20);
                    else case(step)
                        0: advance(1);
                        1: begin
                            ocr<=response; polls<=0;
                            if(response[30:28]==0) fail_with(8'h21);
                            else if((response & 32'h00300000)==0) fail_with(8'h22);
                            else advance(2);
                        end
                        2: if(response[31]) begin ocr<=response; advance(3); end
                           else if(polls==MAX_POLLS-1) fail_with(8'h23);
                           else begin polls<=polls+1'b1; state<=POLL_DELAY; end
                        3: if(response[31:16]==0 || (response & 32'h0000e000)!=0) fail_with(8'h24);
                           else begin rca<=response[31:16]; advance(22); end
                        22: if((response & 32'hfdffe008)!=0) fail_with(8'h25); else advance(4);
                        4: begin cccr_revision<=response[7:0]; advance(5); end
                        5: begin capabilities<=response[7:0]; advance(6); end
                        6: begin cis_pointer[7:0]<=response[7:0]; advance(7); end
                        7: begin cis_pointer[15:8]<=response[7:0]; advance(8); end
                        8: begin
                            cis_pointer[23:16]<=response[7:0];
                            if(response[7:1]!=0 || {response[0],cis_pointer[15:0]}==0) fail_with(8'h26);
                            else begin cursor<={response[0],cis_pointer[15:0]}; advance(9); end
                        end
                        9: begin function_interface<=response[7:0]; advance(10); end
                        10: begin
                            tuple_code<=response[7:0]; tuple_count<=tuple_count+1'b1;
                            if(tuple_count==255 || cursor==17'h1ffff) fail_with(8'h27);
                            else if(response[7:0]==8'hff) fail_with(8'h28);
                            else begin
                                cursor<=cursor+1'b1;
                                if(response[7:0]==0) advance(10); else advance(11);
                            end
                        end
                        11: begin
                            tuple_link<=response[7:0];
                            if(response[7:0]==8'hff || {1'b0,cursor}+response[7:0]+1>18'h1ffff) fail_with(8'h29);
                            else if(tuple_code==8'h20) begin
                                if(response[7:0]<4) fail_with(8'h2a);
                                else begin cursor<=cursor+1'b1; man_index<=0; advance(12); end
                            end else begin cursor<=cursor+response[7:0]+1'b1; advance(10); end
                        end
                        12: begin
                            case(man_index)
                                0: vendor_id[7:0]<=response[7:0];
                                1: vendor_id[15:8]<=response[7:0];
                                2: device_id[7:0]<=response[7:0];
                                3: device_id[15:8]<=response[7:0];
                            endcase
                            if(man_index==3) begin
                                if(vendor_id!=EXPECTED_VENDOR || {response[7:0],device_id[7:0]}!=EXPECTED_DEVICE)
                                    fail_with(8'h2b);
                                else begin identified<=1; advance(19); end
                            end else begin man_index<=man_index+1'b1; cursor<=cursor+1'b1; advance(12); end
                        end
                        19: begin io_enable<=response[7:0]; advance(20); end
                        20: begin polls<=0; advance(21); end
                        21: if(response[1]) begin done<=1; state<=FINISH; end
                            else if(polls==MAX_POLLS-1) fail_with(8'h2c);
                            else begin polls<=polls+1'b1; state<=POLL_DELAY; end
                        default: fail_with(8'h2f);
                    endcase
                end
                POLL_DELAY: if(ms_tick) state<=ISSUE;
                FINISH: state<=FINISH;
                FAIL: state<=FAIL;
                default: fail_with(8'h2f);
            endcase
        end
    end
endmodule
