`default_nettype none
// Complete, consecutive final-output stereo PCM blocks. The published RAM
// bank remains immutable until the analysis/display consumer acknowledges.
module output_audio_capture #(parameter integer SAMPLE_BITS=10) (
    input wire source_clk, source_reset_n,
    input wire [31:0] pcm_pair,
    input wire sample_valid,
    input wire clk, reset_n,
    output reg ready,
    input wire release_block,
    output reg [31:0] snapshot_sequence, snapshot_skipped,
    input wire read_enable,
    input wire [SAMPLE_BITS-1:0] read_addr,
    output reg [31:0] read_data
);
    reg [31:0] samples[0:(2 << SAMPLE_BITS)-1];
    reg write_bank, read_bank, complete, pending;
    reg [SAMPLE_BITS-1:0] index;
    reg held_bank, request_toggle, acknowledge_toggle;
    reg [31:0] sequence_count, skipped_count, held_sequence, held_skipped;
    (* ASYNC_REG="TRUE" *) reg req_meta,req_sync,ack_meta,ack_sync;
    reg req_settled;
    always @(posedge source_clk)
        if(source_reset_n && sample_valid && !complete) samples[{write_bank,index}]<=pcm_pair;
    always @(posedge clk)
        if(read_enable) read_data<=samples[{read_bank,read_addr}];
    always @(posedge source_clk or negedge source_reset_n) begin
        if(!source_reset_n) begin
            write_bank<=0; index<=0; complete<=0; pending<=0;
            held_bank<=0; request_toggle<=0; ack_meta<=0; ack_sync<=0;
            sequence_count<=0; skipped_count<=0; held_sequence<=0; held_skipped<=0;
        end else begin
            ack_meta<=acknowledge_toggle; ack_sync<=ack_meta;
            if(pending && ack_sync==request_toggle) pending<=0;
            if(sample_valid) begin
                if(complete) skipped_count<=skipped_count+1'b1;
                else if(&index) complete<=1;
                else index<=index+1'b1;
            end
            if(complete && !pending) begin
                held_bank<=write_bank; held_sequence<=sequence_count; held_skipped<=skipped_count;
                request_toggle<=~request_toggle; pending<=1;
                sequence_count<=sequence_count+1'b1;
                write_bank<=~write_bank; index<=0; complete<=0;
            end
        end
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            req_meta<=0; req_sync<=0; req_settled<=0; acknowledge_toggle<=0;
            ready<=0; read_bank<=0; snapshot_sequence<=0; snapshot_skipped<=0;
        end else begin
            req_meta<=request_toggle; req_sync<=req_meta; req_settled<=req_sync;
            if(!ready && req_settled!=acknowledge_toggle) begin
                read_bank<=held_bank; snapshot_sequence<=held_sequence; snapshot_skipped<=held_skipped;
                ready<=1;
            end
            if(ready && release_block) begin ready<=0; acknowledge_toggle<=req_settled; end
        end
    end
endmodule
`default_nettype wire
