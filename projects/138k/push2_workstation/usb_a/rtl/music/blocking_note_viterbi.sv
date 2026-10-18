`timescale 1ns/1ps
// Streaming, bounded Viterbi selector for the one-note guidance path.
//
// This is deliberately not the Basic Pitch neural network.  Basic Pitch and
// render_monophonic_melody_track.py remain the workstation teacher/reference.
// The FPGA receives one observation (the fixed-point PCM detector's strongest
// MIDI candidate) per short window and updates a first-order trellis.  Only
// the current cost for 64 pitches plus silence is retained; no path or score
// sequence is written to DDR.
//
// A banded predecessor search (±MAX_STEP semitones, plus silence transitions)
// keeps the hardware bounded.  It is a streaming equivalent of the temporal
// continuity part of the Python Viterbi selector, not a claim that ONNX
// inference runs on the FPGA.
module blocking_note_viterbi #(
    parameter integer LOW_NOTE=36,
    parameter integer HIGH_NOTE=99,
    parameter integer COST_BITS=16,
    parameter integer MAX_STEP=12,
    parameter integer PITCH_EMISSION_SCALE=8,
    // Keep a low-confidence tonal observation alive; explicit silence still
    // wins because its emission is zero when input_silence_i is asserted.
    parameter integer SILENCE_EMISSION=512,
    parameter integer SILENCE_TRANSITION=12
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic input_valid_i,
    output logic input_ready_o,
    input  logic [6:0] input_note_i,
    input  logic [31:0] input_frame_i,
    input  logic [15:0] input_confidence_i,
    input  logic input_silence_i,
    output logic result_valid_o,
    input  logic result_ready_i,
    output logic [6:0] result_note_o,
    output logic [31:0] result_frame_o,
    output logic [15:0] result_confidence_o,
    output logic result_silence_o,
    output logic busy_o
);
    localparam integer PITCH_COUNT=HIGH_NOTE-LOW_NOTE+1;
    localparam integer SILENCE_INDEX=PITCH_COUNT;
    localparam integer STATE_COUNT=PITCH_COUNT+1;
    localparam logic [COST_BITS-1:0] COST_INF={COST_BITS{1'b1}};
    localparam logic [6:0] LOW_NOTE_VALUE=LOW_NOTE[6:0];
    localparam logic [COST_BITS-1:0] SILENCE_EMISSION_VALUE=COST_BITS'(SILENCE_EMISSION);
    localparam logic [COST_BITS-1:0] SILENCE_TRANSITION_VALUE=COST_BITS'(SILENCE_TRANSITION);
    localparam logic [1:0] IDLE=2'd0,HOLD=2'd1;

    logic [1:0] state;
    logic [COST_BITS-1:0] path_cost[0:STATE_COUNT-1];
    logic [COST_BITS-1:0] raw_cost[0:STATE_COUNT-1];
    logic [COST_BITS-1:0] next_cost[0:STATE_COUNT-1];
    logic [COST_BITS-1:0] best_cost;
    logic [COST_BITS-1:0] prior_cost;
    logic [COST_BITS-1:0] transition_cost;
    logic [COST_BITS-1:0] emission_cost;
    logic [COST_BITS-1:0] min_cost;
    integer state_index;
    integer prior_index;
    integer distance;
    integer note_distance;
    integer confidence_penalty;
    integer selected_index;
    integer selected_distance;
    logic [6:0] selected_note_value;
    logic [15:0] selected_confidence_value;
    integer i;

    function automatic [COST_BITS-1:0] saturating_add(
        input [COST_BITS-1:0] left,
        input [COST_BITS-1:0] right
    );
        integer value;
        begin
            value=int'(left)+int'(right);
            saturating_add=(value >= ((1<<COST_BITS)-1)) ? COST_INF : value[COST_BITS-1:0];
        end
    endfunction

    function automatic [COST_BITS-1:0] integer_to_cost(input integer value);
        begin
            integer_to_cost=(value >= ((1<<COST_BITS)-1)) ? COST_INF : value[COST_BITS-1:0];
        end
    endfunction

    function automatic [15:0] confidence_after_distance(
        input [15:0] confidence,
        input integer distance_in
    );
        integer value;
        begin
            value=int'(confidence)-distance_in*256;
            confidence_after_distance=(value<=0) ? 16'd0 :
                (value>=65535 ? 16'hffff : value[15:0]);
        end
    endfunction

    // Build one trellis column from the current observation.  The loops are
    // bounded constants for synthesis; MAX_STEP=12 means at most 25 local
    // predecessors per pitch instead of a 65x65 full matrix.
    always_comb begin
        // Defaults are also useful to conservative synthesis tools, which do
        // not prove that a constant-count generate loop executes at least once.
        prior_cost=COST_INF;
        transition_cost=0;
        emission_cost=0;
        note_distance=0;
        confidence_penalty=0;
        min_cost=COST_INF;
        best_cost=COST_INF;
        selected_index=0;
        selected_distance=0;
        selected_note_value=LOW_NOTE_VALUE;
        selected_confidence_value=0;
        for(state_index=0;state_index<STATE_COUNT;state_index=state_index+1) begin
            raw_cost[state_index]=COST_INF;
            next_cost[state_index]=0;
        end
        for(state_index=0;state_index<STATE_COUNT;state_index=state_index+1) begin
            prior_cost=COST_INF;
            for(prior_index=0;prior_index<STATE_COUNT;prior_index=prior_index+1) begin
                distance=state_index-prior_index;
                if(distance<0)distance=-distance;
                if((state_index==SILENCE_INDEX)||(prior_index==SILENCE_INDEX)) begin
                    if(state_index==prior_index)transition_cost=0;
                    else transition_cost=SILENCE_TRANSITION_VALUE;
                end else if(distance<=MAX_STEP) begin
                    transition_cost=distance[COST_BITS-1:0];
                end else begin
                    transition_cost=COST_INF;
                end
                if(transition_cost!=COST_INF && path_cost[prior_index]!=COST_INF &&
                   saturating_add(path_cost[prior_index],transition_cost)<prior_cost)
                    prior_cost=saturating_add(path_cost[prior_index],transition_cost);
            end
            if(state_index==SILENCE_INDEX) begin
                emission_cost=input_silence_i ? '0 : SILENCE_EMISSION_VALUE;
            end else if(input_silence_i) begin
                emission_cost=SILENCE_EMISSION_VALUE;
            end else begin
                note_distance=state_index+LOW_NOTE-int'(input_note_i);
                if(note_distance<0)note_distance=-note_distance;
                confidence_penalty=(32'h0000ffff-int'(input_confidence_i))>>8;
                emission_cost=integer_to_cost(note_distance*PITCH_EMISSION_SCALE+
                    confidence_penalty);
            end
            raw_cost[state_index]=saturating_add(prior_cost,emission_cost);
        end

        for(state_index=0;state_index<STATE_COUNT;state_index=state_index+1)
            if(raw_cost[state_index]<min_cost)min_cost=raw_cost[state_index];
        best_cost=raw_cost[0];
        for(state_index=0;state_index<STATE_COUNT;state_index=state_index+1) begin
            next_cost[state_index]=(raw_cost[state_index]>=min_cost) ?
                raw_cost[state_index]-min_cost : 0;
            if(raw_cost[state_index]<best_cost)begin
                best_cost=raw_cost[state_index];
                selected_index=state_index;
            end
        end
        selected_distance=selected_index+LOW_NOTE-int'(input_note_i);
        if(selected_distance<0)selected_distance=-selected_distance;
        selected_note_value=(selected_index==SILENCE_INDEX) ? 7'd0 :
            LOW_NOTE_VALUE+selected_index[6:0];
        if(selected_index!=SILENCE_INDEX && selected_distance<256 &&
           int'(input_confidence_i)>=selected_distance*256)
            selected_confidence_value=confidence_after_distance(input_confidence_i,
                selected_distance);
    end

    assign input_ready_o=state==IDLE;
    assign result_valid_o=state==HOLD;
    assign busy_o=state!=IDLE;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin
            state<=IDLE;
            result_note_o<=LOW_NOTE_VALUE;
            result_frame_o<=0;
            result_confidence_o<=0;
            result_silence_o<=1;
            for(i=0;i<STATE_COUNT;i=i+1)path_cost[i]<=0;
        end else begin
            if(state==IDLE && input_valid_i)begin
                for(i=0;i<STATE_COUNT;i=i+1)path_cost[i]<=next_cost[i];
                result_frame_o<=input_frame_i;
                result_silence_o<=(selected_index==SILENCE_INDEX);
                result_note_o<=selected_note_value;
                result_confidence_o<=selected_confidence_value;
                state<=HOLD;
            end else if(state==HOLD && result_ready_i) begin
                state<=IDLE;
            end
        end
    end
endmodule
