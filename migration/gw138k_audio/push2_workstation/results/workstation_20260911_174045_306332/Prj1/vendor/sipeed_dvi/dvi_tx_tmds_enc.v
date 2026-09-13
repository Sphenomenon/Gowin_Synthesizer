// Prj1 1080p60 adaptation of the Sipeed DVI encoder (Apache-2.0).
// Original source/provenance and timing changes: docs/third_party_video.md.
// Four register stages: input/statistics -> transition code -> code statistics
// -> disparity/output. Sampled input at edge N appears at TMDS after edge N+3.
// DE and control follow exactly the same stages as their associated pixel.
module dvi_tx_tmds_enc (
    input  wire       clock,
    input  wire       reset,
    input  wire       den,
    input  wire [7:0] data,
    input  wire [1:0] ctrl,
    output reg  [9:0] tmds
);
    function [3:0] count_ones;
        input [7:0] bits_in;
        reg [1:0] pair0,pair1,pair2,pair3;
        reg [2:0] half0,half1;
        begin
            pair0={1'b0,bits_in[0]}+{1'b0,bits_in[1]};
            pair1={1'b0,bits_in[2]}+{1'b0,bits_in[3]};
            pair2={1'b0,bits_in[4]}+{1'b0,bits_in[5]};
            pair3={1'b0,bits_in[6]}+{1'b0,bits_in[7]};
            half0={1'b0,pair0}+{1'b0,pair1};
            half1={1'b0,pair2}+{1'b0,pair3};
            count_ones={1'b0,half0}+{1'b0,half1};
        end
    endfunction

    reg [7:0] data_reg;
    reg [3:0] input_ones;
    reg den_reg,den_q,den_stats;
    reg [1:0] ctrl_reg,ctrl_q,ctrl_stats;
    reg [8:0] q_stage,q_stats;
    wire use_xnor=(input_ones>4)||((input_ones==4)&&!data_reg[0]);
    wire [8:0] q_transition;
    assign q_transition[8]=!use_xnor;
    // Algebraic prefix parity removes the seven serial XOR/XNOR mux stages.
    // XNOR contributes an inversion only at odd bit positions in the prefix.
    genvar bit_index;
    generate for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin: g_prefix
        assign q_transition[bit_index]=(^data_reg[bit_index:0]) ^
                                      ((bit_index%2==1)&&use_xnor);
    end endgenerate

    wire [3:0] q_ones=count_ones(q_stage[7:0]);
    wire signed [4:0] q_balance=$signed({q_ones,1'b0})-5'sd8;
    reg balanced,negative_balance;
    reg signed [4:0] delta_neutral,delta_inverted,delta_direct;
    reg signed [8:0] cnt_q;
    reg signed [4:0] selected_delta;
    reg [9:0] encoded;
    reg invert_bits;
    wire disparity_zero=(cnt_q==0);
    wire same_direction=(cnt_q[8]==negative_balance);

    always @* begin
        selected_delta=5'sd0;
        invert_bits=1'b0;
        encoded=10'b1101010100;
        if(!den_stats) begin
            case(ctrl_stats)
                2'b00: encoded=10'b1101010100;
                2'b01: encoded=10'b0010101011;
                2'b10: encoded=10'b0101010100;
                2'b11: encoded=10'b1010101011;
            endcase
        end else begin
            if(disparity_zero||balanced) begin
                invert_bits=!q_stats[8];
                selected_delta=delta_neutral;
            end else if(same_direction) begin
                invert_bits=1'b1;
                selected_delta=delta_inverted;
            end else begin
                invert_bits=1'b0;
                selected_delta=delta_direct;
            end
            encoded={invert_bits,q_stats[8],q_stats[7:0]^{8{invert_bits}}};
        end
    end

    always @(posedge clock) begin
        if(reset) begin
            data_reg<=0;input_ones<=0;den_reg<=0;ctrl_reg<=0;
            q_stage<=0;den_q<=0;ctrl_q<=0;
            q_stats<=0;den_stats<=0;ctrl_stats<=0;
            balanced<=0;negative_balance<=0;
            delta_neutral<=0;delta_inverted<=0;delta_direct<=0;
            cnt_q<=0;tmds<=0;
        end else begin
            data_reg<=data;input_ones<=count_ones(data);den_reg<=den;ctrl_reg<=ctrl;
            q_stage<=q_transition;den_q<=den_reg;ctrl_q<=ctrl_reg;
            q_stats<=q_stage;den_stats<=den_q;ctrl_stats<=ctrl_q;
            balanced<=(q_balance==0);negative_balance<=q_balance[4];
            delta_neutral<=q_stage[8] ? q_balance : -q_balance;
            delta_inverted<=(q_stage[8] ? 5'sd2 : 5'sd0)-q_balance;
            delta_direct<=q_balance-(q_stage[8] ? 5'sd0 : 5'sd2);
            tmds<=encoded;
            if(!den_stats) cnt_q<=0;
            else cnt_q<=cnt_q+{{4{selected_delta[4]}},selected_delta};
        end
    end
endmodule
