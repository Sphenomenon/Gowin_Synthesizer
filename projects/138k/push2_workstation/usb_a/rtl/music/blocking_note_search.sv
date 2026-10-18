`timescale 1ns/1ps
// Advance through PCM windows only while the trainer requests a new target.
// Sustained copies of the accepted pitch are skipped.  The same pitch can be
// emitted again after a silent separator.  Three agreeing windows reject
// isolated mixed-song peaks without constructing a whole-song note table.
module blocking_note_search #(
    parameter integer HOP_FRAMES=1024,
    parameter integer WINDOW_FRAMES=4096,
    parameter integer STABLE_WINDOWS=3,
    parameter logic [15:0] MIN_CONFIDENCE=16'd1
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic reset_cursor_i,
    input  logic request_next_i,
    input  logic [31:0] total_frames_i,
    output logic window_request_o,
    output logic [31:0] window_frame_o,
    input  logic detector_valid_i,
    output logic detector_ready_o,
    input  logic [6:0] detector_note_i,
    input  logic [31:0] detector_frame_i,
    input  logic [15:0] detector_confidence_i,
    input  logic detector_silence_i,
    output logic target_valid_o,
    input  logic target_ready_i,
    output logic [6:0] target_note_o,
    output logic [31:0] target_frame_o,
    output logic [15:0] target_confidence_o,
    output logic scanning_o,
    output logic end_of_song_o,
    output logic [31:0] windows_scanned_o
);
    localparam [1:0] IDLE=0,REQUEST=1,WAIT_RESULT=2,HOLD_TARGET=3;
    localparam integer STABLE_BITS=STABLE_WINDOWS<=1 ? 1 : $clog2(STABLE_WINDOWS+1);
    localparam logic [STABLE_BITS-1:0] STABLE_LIMIT=STABLE_WINDOWS-1;
    logic [1:0] state;
    logic have_last,saw_separator,candidate_valid;
    logic [6:0] last_note,candidate_note;
    logic [STABLE_BITS-1:0] stable_count;
    wire usable=!detector_silence_i && detector_confidence_i>=MIN_CONFIDENCE;
    wire blocked_continuation=have_last && !saw_separator && detector_note_i==last_note;

    assign detector_ready_o=state==WAIT_RESULT;
    assign scanning_o=state==REQUEST || state==WAIT_RESULT;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin
            state<=IDLE;window_request_o<=0;window_frame_o<=0;target_valid_o<=0;end_of_song_o<=0;
            target_note_o<=0;target_frame_o<=0;target_confidence_o<=0;
            have_last<=0;saw_separator<=1;candidate_valid<=0;last_note<=0;candidate_note<=0;
            stable_count<=0;windows_scanned_o<=0;
        end else begin
            window_request_o<=0;
            if(reset_cursor_i)begin
                state<=IDLE;window_frame_o<=0;target_valid_o<=0;have_last<=0;
                saw_separator<=1;candidate_valid<=0;stable_count<=0;windows_scanned_o<=0;end_of_song_o<=0;
            end else case(state)
                IDLE:if(request_next_i)begin
                    candidate_valid<=0;stable_count<=0;state<=REQUEST;
                end
                REQUEST:begin
                    if(total_frames_i!=0 && window_frame_o+WINDOW_FRAMES>total_frames_i)begin
                        end_of_song_o<=1;state<=IDLE;
                    end else begin window_request_o<=1;state<=WAIT_RESULT;end
                end
                WAIT_RESULT:if(detector_valid_i)begin
                    windows_scanned_o<=windows_scanned_o+1'b1;
                    window_frame_o<=window_frame_o+HOP_FRAMES;
                    if(detector_silence_i)begin
                        saw_separator<=1;candidate_valid<=0;stable_count<=0;state<=REQUEST;
                    end else if(!usable || blocked_continuation)begin
                        candidate_valid<=0;stable_count<=0;state<=REQUEST;
                    end else if(candidate_valid && detector_note_i==candidate_note)begin
                        if(stable_count==STABLE_LIMIT)begin
                            target_valid_o<=1;target_note_o<=detector_note_i;
                            target_frame_o<=detector_frame_i;target_confidence_o<=detector_confidence_i;
                            last_note<=detector_note_i;have_last<=1;saw_separator<=0;state<=HOLD_TARGET;
                        end else begin stable_count<=stable_count+1'b1;state<=REQUEST;end
                    end else begin
                        candidate_valid<=1;candidate_note<=detector_note_i;stable_count<=1;state<=REQUEST;
                    end
                end
                HOLD_TARGET:if(target_valid_o && target_ready_i)begin
                    target_valid_o<=0;state<=IDLE;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
