`timescale 1ns/1ps
// One cold-start control event after CPU/DDR/UI readiness. Use the existing
// Panic/ordered delay flush so a long initial DDR wait cannot leave a shifted
// delay history. No audio data; serial input passes unchanged outside 3 bytes.
module basic_pitch_startup_panic #(
    parameter integer CLK_HZ=50_000_000,BAUD=115200
)(
    input wire clk_i,rst_ni,system_ready_i,serial_i,
    output wire serial_o,done_o
);
    localparam [1:0] WAIT_READY=0,SEND=1,COMPLETE=2;
    (* ASYNC_REG="TRUE" *) reg ready_meta,ready_sync;
    reg [1:0] state,byte_index;
    reg [5:0] settle;
    reg inflight;
    wire tx_ready,tx_done,tx_serial;
    wire tx_valid=state==SEND && !inflight;
    wire [7:0] tx_data=byte_index==0?8'hb0:byte_index==1?8'd120:8'd0;
    initial if(CLK_HZ<1 || BAUD<1 || CLK_HZ/BAUD<8)
        $fatal(1,"startup Panic requires positive clocks and at least8 clocks/bit");
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_tx(
        .clk(clk_i),.rst_n(rst_ni),.data({24'd0,tx_data}),.valid(tx_valid),
        .ready(tx_ready),.serial_out(tx_serial),.byte_done(tx_done));
    assign serial_o=state==SEND?tx_serial:serial_i;
    assign done_o=state==COMPLETE;
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin ready_meta<=0;ready_sync<=0;end
        else begin ready_meta<=system_ready_i;ready_sync<=ready_meta;end
    end
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin state<=WAIT_READY;settle<=0;byte_index<=0;inflight<=0;end
        else case(state)
            WAIT_READY:begin
                if(!ready_sync)settle<=0;
                else if(settle==31)state<=SEND;
                else settle<=settle+1'b1;
            end
            SEND:begin
                if(tx_valid && tx_ready)inflight<=1;
                if(inflight && tx_done)begin
                    inflight<=0;
                    if(byte_index==2)state<=COMPLETE;
                    else byte_index<=byte_index+1'b1;
                end
            end
            COMPLETE:begin end
            default:$fatal(1,"invalid startup Panic state");
        endcase
    end
endmodule
