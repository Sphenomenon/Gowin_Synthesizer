`timescale 1ns/1ps
// Continuous stereo PCM pitch shifting. Two read heads, separated by half a
// 1024-sample window, crossfade before either delay wraps. One input produces
// one output: this is not a source-clock SRC or a stored-sample voice engine.
//
// The owner snapshots the sole committed ratio on valid/ready and clears on
// cancellation, history/rate reset and source disconnect. No RAM reset sweep:
// each unread history location is masked until overwritten in this epoch.
// Both rates use the same sample window (16..1040 samples, <=23.6ms at 44.1k).
// Enable/unity transitions use a 64-frame wet ramp; settled dry returns exact
// current PCM, including low bits. All samples
// still refresh history. Clear cancels an outstanding result. An illegal busy
// request sets sticky fault and drops only that request; it never stops clocks.
module workstation_stream_pitch (
    input wire clk_i,rst_ni,clear_i,
    input wire valid_i,enable_i,
    input wire [21:0] ratio_q20_i,
    input wire signed [31:0] left_i,right_i,
    output wire ready_o,quiescent_o,
    output reg valid_o,fault_o,
    output reg signed [31:0] left_o,right_o
);
    localparam [2:0] IDLE=0,READ_REQUEST=1,READ_WAIT=2,
        MULTIPLY_PREPARE=3,MULTIPLY_RUN=4,MULTIPLY_STORE=5;
    reg [2:0] state;
    reg [10:0] write_pointer;
    reg [11:0] filled;
    reg [25:0] phase;
    // Fixed-width modular subtraction gives both Q16 read positions. 2048
    // history entries leave a full safety gap beyond the largest delay.
    wire [21:0] ratio=ratio_q20_i<22'd524288 ? 22'd524288 :
        ratio_q20_i>22'd2097152 ? 22'd2097152 : ratio_q20_i;
    wire [25:0] second_phase=phase ^ 26'h2000000;
    wire [26:0] read_position_a={write_pointer,16'd0}-27'd1048576-{1'b0,phase};
    wire [26:0] read_position_b={write_pointer,16'd0}-27'd1048576-{1'b0,second_phase};
    wire [10:0] delay_age_a=write_pointer-read_position_a[26:16];
    wire [10:0] delay_age_b=write_pointer-read_position_b[26:16];
    wire [25:0] mirrored_phase=26'd0-phase;
    wire [16:0] triangle=phase[25] ? mirrored_phase[25:9] : phase[25:9];
    reg [10:0] addresses[0:3];
    reg [3:0] tap_live;
    reg [15:0] fraction_a,fraction_b;
    reg [16:0] weight_a;
    reg bypass;
    reg [6:0] wet_frames;
    wire wants_wet=enable_i && ratio!=22'd1048576;
    wire [6:0] next_wet_frames=wants_wet ? (wet_frames==64 ? 7'd64 : wet_frames+7'd1) : (wet_frames==0 ? 7'd0 : wet_frames-7'd1);
    reg [16:0] wet_weight;
    reg signed [31:0] wet_left,wet_right;
    reg signed [31:0] dry_left,dry_right;
    reg [1:0] read_index;
    reg [2:0] multiply_index;
    reg signed [31:0] taps_left[0:3],taps_right[0:3];
    reg signed [31:0] interpolated[0:3];
    reg signed [32:0] multiply_a,addend;
    reg signed [17:0] multiply_b;
    reg signed [50:0] product;
    wire signed [50:0] sum=$signed({{18{addend[32]}},addend})+(product>>>16);
    wire accepted=valid_i && ready_o;
    wire memory_request=state==READ_REQUEST;
    wire memory_valid_left,memory_valid_right;
    wire [31:0] memory_left,memory_right;
    assign ready_o=rst_ni && !clear_i && state==IDLE;
    assign quiescent_o=state==IDLE;
    // Reuse the maintained physical SDP composition and its registered read
    // contract. Stereo remains paired on every request, phase and result.
    workstation_sdp_banked #(.WORDS(2048)) history_left(
        .rst_ni,.clear_i,.write_clk_i(clk_i),.write_enable_i(accepted),
        .write_addr_i(write_pointer),.write_data_i(left_i),
        .read_clk_i(clk_i),.read_request_i(memory_request),
        .read_addr_i(addresses[read_index]),.read_valid_o(memory_valid_left),.read_data_o(memory_left));
    workstation_sdp_banked #(.WORDS(2048)) history_right(
        .rst_ni,.clear_i,.write_clk_i(clk_i),.write_enable_i(accepted),
        .write_addr_i(write_pointer),.write_data_i(right_i),
        .read_clk_i(clk_i),.read_request_i(memory_request),
        .read_addr_i(addresses[read_index]),.read_valid_o(memory_valid_right),.read_data_o(memory_right));

    function automatic signed [31:0] saturate(input signed [50:0] x);
        if(x>51'sd2147483647)saturate=32'sh7fffffff;
        else if(x< -51'sd2147483648)saturate=32'sh80000000;
        else saturate=x[31:0];
    endfunction
    integer i;
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            state<=IDLE;write_pointer<=0;filled<=0;phase<=0;
            fraction_a<=0;fraction_b<=0;weight_a<=0;tap_live<=0;
            bypass<=1;wet_frames<=0;wet_weight<=0;wet_left<=0;wet_right<=0;dry_left<=0;dry_right<=0;read_index<=0;multiply_index<=0;
            multiply_a<=0;multiply_b<=0;addend<=0;product<=0;
            valid_o<=0;fault_o<=0;left_o<=0;right_o<=0;
            for(i=0;i<4;i=i+1)begin addresses[i]<=0;taps_left[i]<=0;taps_right[i]<=0;interpolated[i]<=0;end
        end else begin
            valid_o<=0;
            if(clear_i)begin
                state<=IDLE;write_pointer<=0;filled<=0;phase<=0;
                left_o<=0;right_o<=0;fault_o<=0;wet_frames<=0;wet_weight<=0;
            end else begin
                if(valid_i && !ready_o)fault_o<=1;
                if(memory_valid_left!=memory_valid_right)fault_o<=1;
                case(state)
                    IDLE:if(accepted)begin
                        addresses[0]<=read_position_a[26:16];addresses[1]<=read_position_a[26:16]+11'd1;
                        addresses[2]<=read_position_b[26:16];addresses[3]<=read_position_b[26:16]+11'd1;
                        tap_live[0]<= {1'b0,delay_age_a}<=filled;
                        tap_live[1]<= {1'b0,delay_age_a}-12'd1<=filled;
                        tap_live[2]<= {1'b0,delay_age_b}<=filled;
                        tap_live[3]<= {1'b0,delay_age_b}-12'd1<=filled;
                        fraction_a<=read_position_a[15:0];fraction_b<=read_position_b[15:0];
                        weight_a<=triangle[16:0];
                        phase<=phase+26'd65536-{8'd0,ratio[21:4]};
                        write_pointer<=write_pointer+11'd1;
                        if(filled<12'd2048)filled<=filled+12'd1;
                        wet_frames<=next_wet_frames;wet_weight<={next_wet_frames,10'd0};
                        bypass<=next_wet_frames==0;
                        dry_left<=left_i;dry_right<=right_i;
                        read_index<=0;state<=READ_REQUEST;
                    end
                    READ_REQUEST:state<=READ_WAIT;
                    READ_WAIT:if(memory_valid_left && memory_valid_right)begin
                        taps_left[read_index]<=tap_live[read_index] ? $signed(memory_left) : 32'sd0;
                        taps_right[read_index]<=tap_live[read_index] ? $signed(memory_right) : 32'sd0;
                        if(read_index==3)begin multiply_index<=0;state<=MULTIPLY_PREPARE;end
                        else begin read_index<=read_index+1'b1;state<=READ_REQUEST;end
                    end
                    MULTIPLY_PREPARE:begin
                        case(multiply_index)
                            0:begin
                                multiply_a<=$signed({taps_left[1][31],taps_left[1]})-$signed({taps_left[0][31],taps_left[0]});
                                multiply_b<=$signed({2'd0,fraction_a});addend<={taps_left[0][31],taps_left[0]};
                            end
                            1:begin
                                multiply_a<=$signed({taps_right[1][31],taps_right[1]})-$signed({taps_right[0][31],taps_right[0]});
                                multiply_b<=$signed({2'd0,fraction_a});addend<={taps_right[0][31],taps_right[0]};
                            end
                            2:begin
                                multiply_a<=$signed({taps_left[3][31],taps_left[3]})-$signed({taps_left[2][31],taps_left[2]});
                                multiply_b<=$signed({2'd0,fraction_b});addend<={taps_left[2][31],taps_left[2]};
                            end
                            3:begin
                                multiply_a<=$signed({taps_right[3][31],taps_right[3]})-$signed({taps_right[2][31],taps_right[2]});
                                multiply_b<=$signed({2'd0,fraction_b});addend<={taps_right[2][31],taps_right[2]};
                            end
                            4:begin
                                multiply_a<=$signed({interpolated[0][31],interpolated[0]})-$signed({interpolated[2][31],interpolated[2]});
                                multiply_b<=$signed({1'b0,weight_a});addend<={interpolated[2][31],interpolated[2]};
                            end
                            5:begin
                                multiply_a<=$signed({interpolated[1][31],interpolated[1]})-$signed({interpolated[3][31],interpolated[3]});
                                multiply_b<=$signed({1'b0,weight_a});addend<={interpolated[3][31],interpolated[3]};
                            end
                            6:begin
                                multiply_a<=$signed({wet_left[31],wet_left})-$signed({dry_left[31],dry_left});
                                multiply_b<=$signed({1'b0,wet_weight});addend<={dry_left[31],dry_left};
                            end
                            default:begin
                                multiply_a<=$signed({wet_right[31],wet_right})-$signed({dry_right[31],dry_right});
                                multiply_b<=$signed({1'b0,wet_weight});addend<={dry_right[31],dry_right};
                            end
                        endcase
                        state<=MULTIPLY_RUN;
                    end
                    MULTIPLY_RUN:begin product<=multiply_a*multiply_b;state<=MULTIPLY_STORE;end
                    MULTIPLY_STORE:begin
                        if(multiply_index<4)interpolated[multiply_index[1:0]]<=saturate(sum);
                        else if(multiply_index==4)wet_left<=saturate(sum);
                        else if(multiply_index==5)wet_right<=saturate(sum);
                        else if(multiply_index==6)left_o<=bypass ? dry_left : saturate(sum);
                        else begin
                            right_o<=bypass ? dry_right : saturate(sum);
                            valid_o<=1;state<=IDLE;
                        end
                        if(multiply_index!=7)begin multiply_index<=multiply_index+1'b1;state<=MULTIPLY_PREPARE;end
                    end
                    default:begin state<=IDLE;fault_o<=1;end
                endcase
            end
        end
    end
endmodule
