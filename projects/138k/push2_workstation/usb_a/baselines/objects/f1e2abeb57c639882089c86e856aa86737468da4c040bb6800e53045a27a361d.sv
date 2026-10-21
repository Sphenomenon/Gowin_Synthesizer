`timescale 1ns/1ps
// Audio-domain register services for the existing recorder and score player.
// This module does not schedule samples, write DDR or synthesize note events.
module gw138k_controlled_services (
    input wire clk, reset_n, command_valid, command_write,
    input wire [11:0] command_address,
    input wire [31:0] command_data,
    input wire [3:0] command_strobes,
    output wire command_ready,
    output logic [31:0] response_data,
    output logic response_error,
    output wire cpu_event_valid,
    output wire [17:0] cpu_event,
    input wire cpu_event_ready,
    input wire panel_event_valid,input wire [6:0] panel_command,output wire panel_event_ready,
    input wire [31:0] control_state,control_pitch,control_options,applied_events,pc_health,
    input wire [127:0] held_notes,
    input wire sample_valid,
    input wire [31:0] active_mask, deadline_miss, midi_overflow, note_drop,
    input wire [31:0] underrun_count, midi_cdc_drop, observation_drop, record_drop,
    output logic record_enable,
    output logic [31:0] snap_status,snap_left,snap_right,snap_sequence,
    input wire record_valid,
    input wire [95:0] record_packet,
    output wire record_ready,
    output wire score_write, score_start, score_stop,
    output logic [7:0] score_address,
    output wire [63:0] score_data,
    output logic [8:0] score_length,
    input wire score_running, score_done,
    input wire [31:0] led_mask, score_frame
);
    localparam [11:0] ID=12'h000, VERSION=12'h004, CAPABILITIES=12'h008,
        SNAPSHOT=12'h010, SNAP_VALID=12'h014,
        REC_ENABLE=12'h080, REC_STATUS=12'h084, REC_POP=12'h088,
        REC_SEQ=12'h08c, REC_LEFT=12'h090, REC_RIGHT=12'h094, REC_RELEASE=12'h098,
        SCORE_ADDR=12'h100, SCORE_TIME=12'h104, SCORE_MASK=12'h108,
        SCORE_COMMIT=12'h10c, SCORE_LENGTH=12'h110, SCORE_START=12'h114,
        SCORE_STOP=12'h118, SCORE_STATUS=12'h11c, SCORE_CLEAR=12'h120,
        SCORE_LEDS=12'h124, SCORE_FRAME=12'h128, SCORE_LOADED=12'h12c;
    logic [31:0] samples, cue_time, cue_mask, previous_time;
    logic [31:0] snapshot [0:8];
    logic snapshot_valid, record_snapshot_valid, done_sticky;
    logic [95:0] record_snapshot;
    logic [8:0] loaded;
    assign panel_event_ready=1'b1;
    wire panel_score_toggle=panel_event_valid && panel_command==0;
    wire panel_record_toggle=panel_event_valid && panel_command==1;
    wire event_address=command_address==12'h180;
    assign cpu_event_valid=command_valid && command_write && event_address && !response_error;
    assign cpu_event=command_data[17:0];
    assign command_ready=!cpu_event_valid || cpu_event_ready;
    wire aligned=command_address[1:0]==0;
    wire legal_write=command_valid && command_write && !response_error;
    assign record_ready=legal_write && command_address==REC_POP;
    assign score_write=legal_write && command_address==SCORE_COMMIT;
    assign score_start=(legal_write && command_address==SCORE_START) ||
        (panel_score_toggle && !score_running && score_length!=0 && score_length<=loaded);
    assign score_stop=(legal_write && command_address==SCORE_STOP) ||
        (panel_score_toggle && score_running);
    assign score_data={cue_time,cue_mask};
    integer i;
    always_comb begin
        response_data=0; response_error=0;
        if(!aligned || (command_write && command_strobes!=4'hf)) response_error=1;
        else if(command_write) begin
            case(command_address)
                12'h180: response_error=command_data[31:18]!=0 || command_data[17:14]>6 ||
                    (command_data[17:14]==1 && command_data[6:0]==0) ||
                    (command_data[17:14]==6 && command_data[13:7]>1);
                12'h1a8,12'h1ac,12'h1b0,12'h1b4: response_error=0;
                SNAPSHOT: response_error=command_data!=1;
                REC_ENABLE: response_error=command_data>1;
                REC_POP: response_error=command_data!=1 || !record_valid || record_snapshot_valid;
                REC_RELEASE: response_error=command_data!=1 || !record_snapshot_valid;
                SCORE_ADDR: response_error=command_data>255 || score_running;
                SCORE_TIME, SCORE_MASK: response_error=score_running;
                SCORE_COMMIT: response_error=command_data!=1 || score_running || loaded==256 ||
                    {1'b0,score_address}!=loaded || (loaded!=0 && cue_time<previous_time);
                SCORE_LENGTH: response_error=command_data==0 || command_data>256 || score_running;
                SCORE_START: response_error=command_data!=1 || score_running ||
                    score_length==0 || score_length>loaded;
                SCORE_STOP: response_error=command_data!=1;
                SCORE_CLEAR: response_error=command_data!=1 || score_running;
                default: response_error=1;
            endcase
        end else begin
            case(command_address)
                12'h184: response_data=control_state;
                12'h188: response_data=control_pitch;
                12'h18c: response_data=control_options;
                12'h190: response_data=held_notes[31:0];
                12'h194: response_data=held_notes[63:32];
                12'h198: response_data=held_notes[95:64];
                12'h19c: response_data=held_notes[127:96];
                12'h1a0: response_data=applied_events;
                12'h1a4: response_data=pc_health;
                12'h1a8: response_data=snap_status;
                12'h1ac: response_data=snap_sequence;
                12'h1b0: response_data=snap_left;
                12'h1b4: response_data=snap_right;
                ID: response_data=32'h41313338; // "A138"
                VERSION: response_data=32'h00010000;
                CAPABILITIES: response_data=63; // snapshot, recorder readout, score upload
                SNAP_VALID: response_data={31'd0,snapshot_valid};
                12'h020,12'h024,12'h028,12'h02c,12'h030,12'h034,12'h038,12'h03c,12'h040:
                    begin
                        response_error=!snapshot_valid;
                        if(snapshot_valid) response_data=snapshot[4'((command_address-12'h020)>>2)];
                    end
                REC_ENABLE: response_data={31'd0,record_enable};
                REC_STATUS: response_data={30'd0,record_valid,record_snapshot_valid};
                REC_SEQ,REC_LEFT,REC_RIGHT: begin
                    response_error=!record_snapshot_valid;
                    if(record_snapshot_valid) case(command_address)
                        REC_SEQ: response_data=record_snapshot[95:64];
                        REC_LEFT: response_data=record_snapshot[63:32];
                        default: response_data=record_snapshot[31:0];
                    endcase
                end
                SCORE_ADDR: response_data={24'd0,score_address};
                SCORE_TIME: response_data=cue_time;
                SCORE_MASK: response_data=cue_mask;
                SCORE_LENGTH: response_data={23'd0,score_length};
                SCORE_STATUS: response_data={30'd0,done_sticky,score_running};
                SCORE_LEDS: response_data=led_mask;
                SCORE_FRAME: response_data=score_frame;
                SCORE_LOADED: response_data={23'd0,loaded};
                default: response_error=1;
            endcase
        end
    end
    always_ff @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            samples<=0; snapshot_valid<=0; record_enable<=0;
            snap_status<=0;snap_left<=0;snap_right<=0;snap_sequence<=0;
            record_snapshot_valid<=0; record_snapshot<=0;
            score_address<=0; score_length<=0; cue_time<=0; cue_mask<=0;
            previous_time<=0; loaded<=0; done_sticky<=0;
            for(i=0;i<9;i=i+1) snapshot[i]<=0;
        end else begin
            if(sample_valid) samples<=samples+1;
            if(score_done) done_sticky<=1;
            if(score_start) done_sticky<=0;
            if(panel_record_toggle) record_enable<=~record_enable;
            if(legal_write) case(command_address)
                12'h1a8: snap_status<=command_data;
                12'h1ac: snap_sequence<=command_data;
                12'h1b0: snap_left<=command_data;
                12'h1b4: snap_right<=command_data;
                SNAPSHOT: begin
                    snapshot_valid<=1;
                    snapshot[0]<=active_mask; snapshot[1]<=samples;
                    snapshot[2]<=deadline_miss; snapshot[3]<=midi_overflow;
                    snapshot[4]<=note_drop; snapshot[5]<=underrun_count;
                    snapshot[6]<=midi_cdc_drop; snapshot[7]<=observation_drop;
                    snapshot[8]<=record_drop;
                end
                REC_ENABLE: record_enable<=command_data[0];
                REC_POP: begin record_snapshot<=record_packet; record_snapshot_valid<=1; end
                REC_RELEASE: record_snapshot_valid<=0;
                SCORE_ADDR: score_address<=command_data[7:0];
                SCORE_TIME: cue_time<=command_data;
                SCORE_MASK: cue_mask<=command_data;
                SCORE_LENGTH: score_length<=command_data[8:0];
                SCORE_COMMIT: begin loaded<=loaded+1'b1; previous_time<=cue_time; end
                SCORE_START: done_sticky<=0;
                SCORE_CLEAR: begin loaded<=0; previous_time<=0; score_length<=0; done_sticky<=0; end
                default: begin end
            endcase
        end
    end
endmodule
