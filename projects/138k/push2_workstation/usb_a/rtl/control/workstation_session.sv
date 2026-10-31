`timescale 1ns/1ps

module workstation_session #(parameter bit D_ONLY_ENABLE=0) (
    input wire clk_i, rst_ni,
    input wire cpu_valid_i,
    input wire [17:0] cpu_event_i,
    input wire arbiter_ready_i,
    output wire cpu_ready_o, internal_o, lifecycle_o,
    input wire fifo_valid_i,
    input wire [17:0] fifo_event_i,
    output wire fifo_ready_o,
    input wire cue_valid_i, cue_stop_i,
    input wire [17:0] cue_event_i,
    output wire cue_ready_o,
    input wire event_ready_i,
    output logic event_valid_o,
    output logic [17:0] event_o,
    input wire mode_pending_i,
    input wire [1:0] mode_i,
    output logic initializing_o,
    output logic [3:0] initialization_step_o
);
    localparam integer INITIALIZATION_EVENTS = 13;
    wire register_ready = !event_valid_o || event_ready_i;
    wire attaching = lifecycle_o && cpu_event_i[6:0] == 7'd1;

    assign internal_o = cpu_event_i[17:14] == 4'd15;
    assign lifecycle_o = cpu_valid_i && internal_o && cpu_event_i[6:0] < 3;
    assign cpu_ready_o = lifecycle_o ||
        (!initializing_o && (internal_o || arbiter_ready_i));
    assign fifo_ready_o = lifecycle_o || (register_ready && !initializing_o);
    assign cue_ready_o = register_ready && !initializing_o && !fifo_valid_i && !cue_stop_i;

    function automatic [17:0] initialization_event(input [3:0] step);
        case (step)
            0: initialization_event = D_ONLY_ENABLE ? {4'd2,7'd20,7'd0} : {4'd2, 7'd96, 7'd0};
            1: initialization_event = D_ONLY_ENABLE ? {4'd2,7'd21,7'd0} : {4'd2, 7'd104, 7'd0};
            2: initialization_event = D_ONLY_ENABLE ? {4'd2,7'd22,7'd0} : {4'd2, 7'd90, 7'd0};
            3: initialization_event = {4'd4, 7'd0, 7'd64};
            4: initialization_event = {4'd2, 7'd64, 7'd0};
            5: initialization_event = {4'd2, 7'd11, 7'd127};
            6: initialization_event = {4'd2, 7'd1, 7'd0};
            7: initialization_event = {4'd2, 7'd5, 7'd0};
            8: initialization_event = {4'd2, 7'd82, 7'd0};
            9: initialization_event = {4'd2, 7'd7, 7'd127};
            10: initialization_event = {4'd3, 7'd73, 7'd0};
            11: initialization_event = D_ONLY_ENABLE ? {4'd2,7'd16,7'd127} : {4'd2, 7'd80, 7'd2};
            default: initialization_event = {4'd2, 7'd81, 7'd0};
        endcase
    endfunction

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            event_valid_o <= 0;
            event_o <= 0;
            initializing_o <= 0;
            initialization_step_o <= 0;
        end else if (lifecycle_o) begin
            event_valid_o <= 0;
            event_o <= 0;
            initializing_o <= (attaching && cpu_event_i[7]) ||
                (cpu_event_i[6:0] == 7'd2 && initializing_o);
            initialization_step_o <= 0;
        end else if (initializing_o) begin
            if (register_ready) begin
                event_valid_o <= initialization_step_o < INITIALIZATION_EVENTS;
                if (initialization_step_o < INITIALIZATION_EVENTS) begin
                    event_o <= initialization_event(initialization_step_o);
                    initialization_step_o <= initialization_step_o + 1'b1;
                end
            end
            if (initialization_step_o == INITIALIZATION_EVENTS && !event_valid_o &&
                !mode_pending_i && mode_i == (D_ONLY_ENABLE ? 2'd3 : 2'd2))
                initializing_o <= 0;
        end else if (fifo_ready_o) begin
            event_valid_o <= fifo_valid_i || (cue_valid_i && !cue_stop_i);
            if (fifo_valid_i) event_o <= fifo_event_i;
            else if (cue_valid_i && !cue_stop_i) event_o <= cue_event_i;
        end
    end
endmodule
