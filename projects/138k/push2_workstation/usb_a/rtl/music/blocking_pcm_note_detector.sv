`timescale 1ns/1ps
// A bounded streaming window followed by a time-multiplexed 64-note scan.
// The detector evaluates one fundamental and its second harmonic per note,
// using one shared fixed-point recurrence.  It stores no note sequence.
module blocking_pcm_note_detector #(
    parameter integer WINDOW_LOG2=12,
    parameter integer LOW_NOTE=36,
    parameter integer HIGH_NOTE=99,
    parameter integer SILENCE_MEAN_ABS=96
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic start_window_i,
    input  logic [31:0] source_frame_i,
    output logic sample_ready_o,
    input  logic sample_valid_i,
    input  logic signed [15:0] sample_i,
    output logic result_valid_o,
    input  logic result_ready_i,
    output logic [6:0] result_note_o,
    output logic [31:0] result_frame_o,
    output logic [15:0] result_confidence_o,
    output logic silence_o,
    output logic busy_o
);
    localparam integer WINDOW_SIZE=1<<WINDOW_LOG2;
    // Four bits of input headroom keep the lowest candidate's resonant state
    // within 32 bits.  The Q2.16 coefficient multiply is deliberately split
    // into signed high/unsigned low 16-bit halves so synthesis uses one short
    // 18x18 DSP path instead of a timing-critical 32x18 cascade.
    localparam integer STATE_BITS=32;
    localparam logic [6:0] LOW_NOTE_VALUE=LOW_NOTE[6:0];
    localparam logic [6:0] HIGH_NOTE_VALUE=HIGH_NOTE[6:0];
    localparam logic [31+WINDOW_LOG2:0] SILENCE_SUM=
        SILENCE_MEAN_ABS*WINDOW_SIZE;
    localparam [3:0] IDLE=0,LOAD=1,SETUP=2,READ_SAMPLE=3,MULTIPLY_LOW=4,
        MULTIPLY_HIGH=5,MAC_SAMPLE=6,FINISH_HARMONIC=7,FINISH_NOTE=8,
        FINISH_SCAN=9,HOLD_RESULT=10;

    `include "music_note_coefficients.svh"

    (* ram_style="block",syn_ramstyle="block_ram" *)
    logic signed [15:0] sample_memory[0:WINDOW_SIZE-1];
    logic [WINDOW_LOG2-1:0] sample_address;
    logic signed [15:0] sample_q;
    logic [3:0] state;
    logic [6:0] candidate_note;
    logic harmonic;
    logic signed [STATE_BITS-1:0] recurrence_1,recurrence_2;
    logic signed [17:0] multiplier_operand;
    logic signed [35:0] multiplier_product;
    logic signed [19:0] low_product_scaled;
    logic signed [STATE_BITS:0] recurrence_next,coefficient_scaled_q;
    logic signed [17:0] coefficient;
    logic [STATE_BITS:0] fundamental_score,candidate_score;
    logic [STATE_BITS:0] best_score,second_score;
    logic [6:0] best_note;
    logic [31:0] window_frame;
    logic [31+WINDOW_LOG2:0] absolute_sum;
    wire signed [15:0] sample_scaled=sample_q>>>4;

    wire [15:0] sample_absolute=sample_i[15] ? (~sample_i+16'd1) : sample_i;
    wire [STATE_BITS-1:0] recurrence_1_abs=recurrence_1[STATE_BITS-1] ?
        (~recurrence_1+1'b1) : recurrence_1;
    wire [STATE_BITS-1:0] recurrence_2_abs=recurrence_2[STATE_BITS-1] ?
        (~recurrence_2+1'b1) : recurrence_2;
    wire [STATE_BITS:0] harmonic_magnitude={1'b0,recurrence_1_abs}+{1'b0,recurrence_2_abs};
    wire [STATE_BITS:0] completed_score=fundamental_score+(harmonic_magnitude>>1);
    wire window_silent=absolute_sum < SILENCE_SUM;
    wire [STATE_BITS:0] score_margin=best_score>second_score ? best_score-second_score : 0;
    wire confidence_saturated=|score_margin[STATE_BITS:16];

    assign sample_ready_o=state==LOAD;
    assign busy_o=state!=IDLE && state!=HOLD_RESULT;

    always_ff @(posedge clk_i) begin
        if(state==LOAD && sample_valid_i) sample_memory[sample_address]<=sample_i;
        if(state==READ_SAMPLE) sample_q<=sample_memory[sample_address];
    end

    always_comb begin
        coefficient=music_note_coefficient(candidate_note,harmonic);
        multiplier_operand=state==MULTIPLY_LOW ?
            $signed({2'b00,recurrence_1[15:0]}) :
            $signed({{2{recurrence_1[31]}},recurrence_1[31:16]});
        multiplier_product=coefficient*multiplier_operand;
        recurrence_next={{(STATE_BITS-15){sample_scaled[15]}},sample_scaled}+
            coefficient_scaled_q-{$signed(recurrence_2[STATE_BITS-1]),recurrence_2};
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state<=IDLE;sample_address<=0;candidate_note<=LOW_NOTE_VALUE;harmonic<=0;
            recurrence_1<=0;recurrence_2<=0;fundamental_score<=0;candidate_score<=0;
            low_product_scaled<=0;coefficient_scaled_q<=0;
            best_score<=0;second_score<=0;best_note<=LOW_NOTE_VALUE;window_frame<=0;
            absolute_sum<=0;result_valid_o<=0;result_note_o<=0;result_frame_o<=0;
            result_confidence_o<=0;silence_o<=0;
        end else begin
            case(state)
                IDLE:begin
                    result_valid_o<=0;
                    if(start_window_i)begin
                        sample_address<=0;window_frame<=source_frame_i;absolute_sum<=0;state<=LOAD;
                    end
                end
                LOAD:if(sample_valid_i)begin
                    absolute_sum<=absolute_sum+{{(16+WINDOW_LOG2){1'b0}},sample_absolute};
                    if(&sample_address)begin
                        sample_address<=0;candidate_note<=LOW_NOTE_VALUE;harmonic<=0;
                        best_score<=0;second_score<=0;best_note<=LOW_NOTE_VALUE;state<=SETUP;
                    end else sample_address<=sample_address+1'b1;
                end
                SETUP:begin
                    sample_address<=0;recurrence_1<=0;recurrence_2<=0;state<=READ_SAMPLE;
                end
                READ_SAMPLE:state<=MULTIPLY_LOW;
                MULTIPLY_LOW:begin
                    low_product_scaled<=multiplier_product[35:16];state<=MULTIPLY_HIGH;
                end
                MULTIPLY_HIGH:begin
                    coefficient_scaled_q<=$signed(multiplier_product[32:0])+
                        $signed({{13{low_product_scaled[19]}},low_product_scaled});
                    state<=MAC_SAMPLE;
                end
                MAC_SAMPLE:begin
                    recurrence_2<=recurrence_1;
                    if(recurrence_next[STATE_BITS]!=recurrence_next[STATE_BITS-1])
                        recurrence_1<=recurrence_next[STATE_BITS] ?
                            {1'b1,{(STATE_BITS-1){1'b0}}} : {1'b0,{(STATE_BITS-1){1'b1}}};
                    else recurrence_1<=recurrence_next[STATE_BITS-1:0];
                    if(&sample_address)state<=FINISH_HARMONIC;
                    else begin sample_address<=sample_address+1'b1;state<=READ_SAMPLE;end
                end
                FINISH_HARMONIC:begin
                    if(!harmonic)begin
                        fundamental_score<=harmonic_magnitude;harmonic<=1;state<=SETUP;
                    end else begin candidate_score<=completed_score;state<=FINISH_NOTE;end
                end
                FINISH_NOTE:begin
                    if(candidate_score>best_score)begin
                        second_score<=best_score;best_score<=candidate_score;best_note<=candidate_note;
                    end else if(candidate_score>second_score)second_score<=candidate_score;
                    if(candidate_note==HIGH_NOTE_VALUE)state<=FINISH_SCAN;
                    else begin candidate_note<=candidate_note+1'b1;harmonic<=0;state<=SETUP;end
                end
                FINISH_SCAN:begin
                    silence_o<=window_silent;
                    result_note_o<=best_note;
                    result_frame_o<=window_frame+(WINDOW_SIZE>>1);
                    result_confidence_o<=window_silent ? 0 :
                        confidence_saturated ? 16'hffff : score_margin[15:0];
                    result_valid_o<=1;state<=HOLD_RESULT;
                end
                HOLD_RESULT:if(result_ready_i)begin result_valid_o<=0;state<=IDLE;end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
