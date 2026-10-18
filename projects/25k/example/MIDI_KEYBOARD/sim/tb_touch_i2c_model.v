`ifndef MIDI_I2C_SLAVE_MODEL_V
`define MIDI_I2C_SLAVE_MODEL_V
`timescale 1ns / 1ps
// Bus-level, byte-addressed slave model. It observes the actual open-drain
// pins and supplies ACK/data; no hierarchical force of the DUT is used.
module midi_i2c_slave_model #(parameter [6:0] ADDRESS = 7'h0d) (
    inout wire scl, inout wire sda, input wire nack_all
);
    reg [7:0] mem [0:255];
    reg sda_low = 0;
    assign sda = sda_low ? 1'b0 : 1'bz;
    localparam RECEIVE=0, ACK=1, SEND=2, HOST_ACK=3, IGNORE=4;
    integer state = IGNORE, bit_index = 7, ack_phase = 0;
    integer writes = 0, starts = 0, stops = 0, final_nacks = 0;
    integer data_bytes = 0, last_data_bytes = 0;
    reg active = 0, first_byte = 1, pointer_pending = 0;
    reg next_read = 0, ack_value = 0;
    reg [7:0] pointer = 0, received = 0, tx = 0;
    integer i;
    initial begin
        for (i = 0; i < 256; i = i + 1) mem[i] = 0;
        mem[0] = 8'h11; mem[1] = 8'h40;
        for (i = 0; i < 16; i = i + 1) begin
            mem[100+i*2] = 8'he8; mem[101+i*2] = 8'h03; // signal 1000
            mem[132+i*2] = 8'h4c; mem[133+i*2] = 8'h04; // reference 1100
        end
    end
    always @(negedge sda) if (scl === 1'b1) begin
        starts = starts + 1; active = 1; state = RECEIVE;
        first_byte = 1; bit_index = 7; received = 0;
        ack_phase = 0; next_read = 0; data_bytes = 0;
    end
    always @(posedge sda) if (scl === 1'b1 && active) begin
        stops = stops + 1; active = 0; state = IGNORE;
        last_data_bytes = data_bytes; sda_low = 0;
    end
    always @(posedge scl) if (active) begin
        case (state)
            RECEIVE: begin
                received[bit_index] = sda;
                if (bit_index == 0) begin
                    ack_value = !nack_all;
                    if (first_byte) begin
                        ack_value = ack_value && received[7:1] == ADDRESS;
                        next_read = received[0]; pointer_pending = !received[0]; first_byte = 0;
                    end else if (pointer_pending) begin
                        pointer = received; pointer_pending = 0;
                    end else begin
                        mem[pointer] = received; pointer = pointer + 1;
                        writes = writes + 1; data_bytes = data_bytes + 1;
                    end
                    state = ACK; ack_phase = 0;
                end else bit_index = bit_index - 1;
            end
            ACK: ack_phase = 1;
            SEND: begin
                if (bit_index == 0) begin state = HOST_ACK; ack_phase = 0; end
                else bit_index = bit_index - 1;
            end
            HOST_ACK: begin
                ack_value = !sda; ack_phase = 1;
                if (sda) final_nacks = final_nacks + 1;
            end
        endcase
    end
    always @(negedge scl) if (active) begin
        case (state)
            ACK: begin
                if (!ack_phase) sda_low = ack_value;
                else begin
                    sda_low = 0; bit_index = 7; received = 0;
                    if (!ack_value) state = IGNORE;
                    else if (next_read) begin
                        tx = mem[pointer]; state = SEND; sda_low = !tx[7];
                    end else state = RECEIVE;
                end
            end
            SEND: sda_low = !tx[bit_index];
            HOST_ACK: begin
                if (!ack_phase) sda_low = 0;
                else if (ack_value) begin
                    pointer = pointer + 1; tx = mem[pointer]; bit_index = 7;
                    state = SEND; sda_low = !tx[7];
                end else begin state = IGNORE; sda_low = 0; end
            end
        endcase
    end
endmodule
`endif
