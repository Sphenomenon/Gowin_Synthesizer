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
    reg [15:0] write_select_q;
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)write_select_q<=0;
        else begin
            write_select_q[0]<=command_write && command_address==12'h1a8;
            write_select_q[1]<=command_write && command_address==12'h1ac;
            write_select_q[2]<=command_write && command_address==12'h1b0;
            write_select_q[3]<=command_write && command_address==12'h1b4;
            write_select_q[4]<=command_write && command_address==SNAPSHOT;
            write_select_q[5]<=command_write && command_address==REC_ENABLE;
            write_select_q[6]<=command_write && command_address==REC_POP;
            write_select_q[7]<=command_write && command_address==REC_RELEASE;
            write_select_q[8]<=command_write && command_address==SCORE_ADDR;
            write_select_q[9]<=command_write && command_address==SCORE_TIME;
            write_select_q[10]<=command_write && command_address==SCORE_MASK;
            write_select_q[11]<=command_write && command_address==SCORE_COMMIT;
            write_select_q[12]<=command_write && command_address==SCORE_LENGTH;
            write_select_q[13]<=command_write && command_address==SCORE_START;
            write_select_q[14]<=command_write && command_address==SCORE_STOP;
            write_select_q[15]<=command_write && command_address==SCORE_CLEAR;
        end
    end
    wire write_allow_0=command_valid && command_strobes==4'hf && write_select_q[0] && (1'b1);
    wire write_allow_1=command_valid && command_strobes==4'hf && write_select_q[1] && (1'b1);
    wire write_allow_2=command_valid && command_strobes==4'hf && write_select_q[2] && (1'b1);
    wire write_allow_3=command_valid && command_strobes==4'hf && write_select_q[3] && (1'b1);
    wire write_allow_4=command_valid && command_strobes==4'hf && write_select_q[4] && (command_data==1);
    wire write_allow_5=command_valid && command_strobes==4'hf && write_select_q[5] && (command_data<=1);
    wire write_allow_6=command_valid && command_strobes==4'hf && write_select_q[6] && (command_data==1 && record_valid && !record_snapshot_valid);
    wire write_allow_7=command_valid && command_strobes==4'hf && write_select_q[7] && (command_data==1 && record_snapshot_valid);
    wire write_allow_8=command_valid && command_strobes==4'hf && write_select_q[8] && (command_data<=255 && !score_running);
    wire write_allow_9=command_valid && command_strobes==4'hf && write_select_q[9] && (!score_running);
    wire write_allow_10=command_valid && command_strobes==4'hf && write_select_q[10] && (!score_running);
    wire write_allow_11=command_valid && command_strobes==4'hf && write_select_q[11] && (command_data==1 && !score_running && loaded!=256 && {1'b0,score_address}==loaded && (loaded==0 || cue_time>=previous_time));
    wire write_allow_12=command_valid && command_strobes==4'hf && write_select_q[12] && (command_data!=0 && command_data<=256 && !score_running);
    wire write_allow_13=command_valid && command_strobes==4'hf && write_select_q[13] && (command_data==1 && !score_running && score_length!=0 && score_length<=loaded);
    wire write_allow_14=command_valid && command_strobes==4'hf && write_select_q[14] && (command_data==1);
    wire write_allow_15=command_valid && command_strobes==4'hf && write_select_q[15] && (command_data==1 && !score_running);
    wire event_address=command_address==12'h180;
    assign cpu_event_valid=command_valid && command_write && event_address && !(command_strobes!=4'hf || command_data[31:18]!=0 || command_data[17:14]>6 || (command_data[17:14]==1 && command_data[6:0]==0) || (command_data[17:14]==6 && command_data[13:7]>1));
    assign cpu_event=command_data[17:0];
    wire malformed_event=command_strobes!=4'hf || command_data[31:18]!=0 ||
        command_data[17:14]>6 || (command_data[17:14]==1 && command_data[6:0]==0) ||
        (command_data[17:14]==6 && command_data[13:7]>1);
    assign command_ready=!command_write || !event_address || malformed_event || cpu_event_ready;
    wire aligned=command_address[1:0]==0;
    wire legal_write=command_valid && command_write && !response_error;
    assign record_ready=write_allow_6;
    assign score_write=write_allow_11;
    assign score_start=write_allow_13 ||
        (panel_score_toggle && !score_running && score_length!=0 && score_length<=loaded);
    assign score_stop=write_allow_14 ||
        (panel_score_toggle && score_running);
    assign score_data={cue_time,cue_mask};
    reg [38:0] read_select_q;
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)read_select_q<=0;
        else begin
            read_select_q[0]<=!command_write && command_address==12'h184;
            read_select_q[1]<=!command_write && command_address==12'h188;
            read_select_q[2]<=!command_write && command_address==12'h18c;
            read_select_q[3]<=!command_write && command_address==12'h190;
            read_select_q[4]<=!command_write && command_address==12'h194;
            read_select_q[5]<=!command_write && command_address==12'h198;
            read_select_q[6]<=!command_write && command_address==12'h19c;
            read_select_q[7]<=!command_write && command_address==12'h1a0;
            read_select_q[8]<=!command_write && command_address==12'h1a4;
            read_select_q[9]<=!command_write && command_address==12'h1a8;
            read_select_q[10]<=!command_write && command_address==12'h1ac;
            read_select_q[11]<=!command_write && command_address==12'h1b0;
            read_select_q[12]<=!command_write && command_address==12'h1b4;
            read_select_q[13]<=!command_write && command_address==12'h000;
            read_select_q[14]<=!command_write && command_address==12'h004;
            read_select_q[15]<=!command_write && command_address==12'h008;
            read_select_q[16]<=!command_write && command_address==12'h014;
            read_select_q[17]<=!command_write && command_address==12'h020;
            read_select_q[18]<=!command_write && command_address==12'h024;
            read_select_q[19]<=!command_write && command_address==12'h028;
            read_select_q[20]<=!command_write && command_address==12'h02c;
            read_select_q[21]<=!command_write && command_address==12'h030;
            read_select_q[22]<=!command_write && command_address==12'h034;
            read_select_q[23]<=!command_write && command_address==12'h038;
            read_select_q[24]<=!command_write && command_address==12'h03c;
            read_select_q[25]<=!command_write && command_address==12'h040;
            read_select_q[26]<=!command_write && command_address==12'h080;
            read_select_q[27]<=!command_write && command_address==12'h084;
            read_select_q[28]<=!command_write && command_address==12'h08c;
            read_select_q[29]<=!command_write && command_address==12'h090;
            read_select_q[30]<=!command_write && command_address==12'h094;
            read_select_q[31]<=!command_write && command_address==12'h100;
            read_select_q[32]<=!command_write && command_address==12'h104;
            read_select_q[33]<=!command_write && command_address==12'h108;
            read_select_q[34]<=!command_write && command_address==12'h110;
            read_select_q[35]<=!command_write && command_address==12'h11c;
            read_select_q[36]<=!command_write && command_address==12'h124;
            read_select_q[37]<=!command_write && command_address==12'h128;
            read_select_q[38]<=!command_write && command_address==12'h12c;
        end
    end
    wire [31:0] decoded_read_data=
        ({32{read_select_q[0]}} & control_state) |
        ({32{read_select_q[1]}} & control_pitch) |
        ({32{read_select_q[2]}} & control_options) |
        ({32{read_select_q[3]}} & held_notes[31:0]) |
        ({32{read_select_q[4]}} & held_notes[63:32]) |
        ({32{read_select_q[5]}} & held_notes[95:64]) |
        ({32{read_select_q[6]}} & held_notes[127:96]) |
        ({32{read_select_q[7]}} & applied_events) |
        ({32{read_select_q[8]}} & pc_health) |
        ({32{read_select_q[9]}} & snap_status) |
        ({32{read_select_q[10]}} & snap_sequence) |
        ({32{read_select_q[11]}} & snap_left) |
        ({32{read_select_q[12]}} & snap_right) |
        ({32{read_select_q[13]}} & 32'h41313338) |
        ({32{read_select_q[14]}} & 32'h00010000) |
        ({32{read_select_q[15]}} & 32'd63) |
        ({32{read_select_q[16]}} & {31'd0,snapshot_valid}) |
        ({32{read_select_q[17]}} & (snapshot_valid ? snapshot[0] : 32'd0)) |
        ({32{read_select_q[18]}} & (snapshot_valid ? snapshot[1] : 32'd0)) |
        ({32{read_select_q[19]}} & (snapshot_valid ? snapshot[2] : 32'd0)) |
        ({32{read_select_q[20]}} & (snapshot_valid ? snapshot[3] : 32'd0)) |
        ({32{read_select_q[21]}} & (snapshot_valid ? snapshot[4] : 32'd0)) |
        ({32{read_select_q[22]}} & (snapshot_valid ? snapshot[5] : 32'd0)) |
        ({32{read_select_q[23]}} & (snapshot_valid ? snapshot[6] : 32'd0)) |
        ({32{read_select_q[24]}} & (snapshot_valid ? snapshot[7] : 32'd0)) |
        ({32{read_select_q[25]}} & (snapshot_valid ? snapshot[8] : 32'd0)) |
        ({32{read_select_q[26]}} & {31'd0,record_enable}) |
        ({32{read_select_q[27]}} & {30'd0,record_valid,record_snapshot_valid}) |
        ({32{read_select_q[28]}} & (record_snapshot_valid ? record_snapshot[95:64] : 32'd0)) |
        ({32{read_select_q[29]}} & (record_snapshot_valid ? record_snapshot[63:32] : 32'd0)) |
        ({32{read_select_q[30]}} & (record_snapshot_valid ? record_snapshot[31:0] : 32'd0)) |
        ({32{read_select_q[31]}} & {24'd0,score_address}) |
        ({32{read_select_q[32]}} & cue_time) |
        ({32{read_select_q[33]}} & cue_mask) |
        ({32{read_select_q[34]}} & {23'd0,score_length}) |
        ({32{read_select_q[35]}} & {30'd0,done_sticky,score_running}) |
        ({32{read_select_q[36]}} & led_mask) |
        ({32{read_select_q[37]}} & score_frame) |
        ({32{read_select_q[38]}} & {23'd0,loaded});
    assign response_data=decoded_read_data;
    integer i;
    logic [31:0] unused_read_data;
    always_comb begin
        unused_read_data=0; response_error=0;
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
                12'h184: unused_read_data=control_state;
                12'h188: unused_read_data=control_pitch;
                12'h18c: unused_read_data=control_options;
                12'h190: unused_read_data=held_notes[31:0];
                12'h194: unused_read_data=held_notes[63:32];
                12'h198: unused_read_data=held_notes[95:64];
                12'h19c: unused_read_data=held_notes[127:96];
                12'h1a0: unused_read_data=applied_events;
                12'h1a4: unused_read_data=pc_health;
                12'h1a8: unused_read_data=snap_status;
                12'h1ac: unused_read_data=snap_sequence;
                12'h1b0: unused_read_data=snap_left;
                12'h1b4: unused_read_data=snap_right;
                ID: unused_read_data=32'h41313338; // "A138"
                VERSION: unused_read_data=32'h00010000;
                CAPABILITIES: unused_read_data=63; // snapshot, recorder readout, score upload
                SNAP_VALID: unused_read_data={31'd0,snapshot_valid};
                12'h020,12'h024,12'h028,12'h02c,12'h030,12'h034,12'h038,12'h03c,12'h040:
                    begin
                        response_error=!snapshot_valid;
                        if(snapshot_valid) unused_read_data=snapshot[4'((command_address-12'h020)>>2)];
                    end
                REC_ENABLE: unused_read_data={31'd0,record_enable};
                REC_STATUS: unused_read_data={30'd0,record_valid,record_snapshot_valid};
                REC_SEQ,REC_LEFT,REC_RIGHT: begin
                    response_error=!record_snapshot_valid;
                    if(record_snapshot_valid) case(command_address)
                        REC_SEQ: unused_read_data=record_snapshot[95:64];
                        REC_LEFT: unused_read_data=record_snapshot[63:32];
                        default: unused_read_data=record_snapshot[31:0];
                    endcase
                end
                SCORE_ADDR: unused_read_data={24'd0,score_address};
                SCORE_TIME: unused_read_data=cue_time;
                SCORE_MASK: unused_read_data=cue_mask;
                SCORE_LENGTH: unused_read_data={23'd0,score_length};
                SCORE_STATUS: unused_read_data={30'd0,done_sticky,score_running};
                SCORE_LEDS: unused_read_data=led_mask;
                SCORE_FRAME: unused_read_data=score_frame;
                SCORE_LOADED: unused_read_data={23'd0,loaded};
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
            if(write_allow_0)begin snap_status<=command_data; end
            if(write_allow_1)begin snap_sequence<=command_data; end
            if(write_allow_2)begin snap_left<=command_data; end
            if(write_allow_3)begin snap_right<=command_data; end
            if(write_allow_4)begin begin
                    snapshot_valid<=1;
                    snapshot[0]<=active_mask; snapshot[1]<=samples;
                    snapshot[2]<=deadline_miss; snapshot[3]<=midi_overflow;
                    snapshot[4]<=note_drop; snapshot[5]<=underrun_count;
                    snapshot[6]<=midi_cdc_drop; snapshot[7]<=observation_drop;
                    snapshot[8]<=record_drop;
                end end
            if(write_allow_5)begin record_enable<=command_data[0]; end
            if(write_allow_6)begin begin record_snapshot<=record_packet; record_snapshot_valid<=1; end end
            if(write_allow_7)begin record_snapshot_valid<=0; end
            if(write_allow_8)begin score_address<=command_data[7:0]; end
            if(write_allow_9)begin cue_time<=command_data; end
            if(write_allow_10)begin cue_mask<=command_data; end
            if(write_allow_12)begin score_length<=command_data[8:0]; end
            if(write_allow_11)begin begin loaded<=loaded+1'b1; previous_time<=cue_time; end end
            if(write_allow_13)begin done_sticky<=0; end
            if(write_allow_15)begin begin loaded<=0; previous_time<=0; score_length<=0; done_sticky<=0; end end
        end
    end
endmodule
