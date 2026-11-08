`timescale 1ns/1ps
// Optional owner8 extension of the maintained legacy DDR pipeline.
// Disabled mode is the literal legacy instance; selected profiles stay unchanged.
module workstation_recording_ddr_arbiter_pipeline #(
    parameter TAG_BITS=5,
    parameter REGISTER_GRANTS=0,
    parameter bit RECORDING_ENABLE=0
)(
    input wire clk,reset_n,bist_done,
    input wire bist_valid,bist_write,
    input wire [28:0] bist_address,
    input wire [255:0] bist_data,
    output wire bist_ready,bist_response,
    input wire scan_valid,
    input wire [28:0] scan_address,
    output wire scan_ready,scan_response,
    input wire display_valid,
    input wire [28:0] display_address,
    output wire display_ready,display_response,
    input wire audio_valid,audio_write,
    input wire [28:0] audio_address,
    input wire [255:0] audio_data,
    output wire audio_ready,audio_response,
    input wire music_valid,music_write,
    input wire [28:0] music_address,
    input wire [255:0] music_data,
    input wire [31:0] music_mask,
    output wire music_ready,music_response,
    input wire delay_valid,delay_write,
    input wire [28:0] delay_address,
    input wire [255:0] delay_data,
    output wire delay_ready,delay_response,
    input wire writer_valid,
    input wire [28:0] writer_address,
    input wire [255:0] writer_data,
    output wire writer_ready,
    input wire cpu_valid,cpu_write,
    input wire [28:0] cpu_address,
    input wire [255:0] cpu_data,
    input wire [31:0] cpu_mask,
    output wire cpu_ready,cpu_response,
    output reg [2:0] app_cmd,
    output wire app_en,app_wren,app_wend,
    output reg [28:0] app_address,
    output reg [255:0] app_data,
    output reg [31:0] app_mask,
    input wire app_ready,app_write_ready,app_response,
    input wire app_ready_fault_probe_i,
    input wire [255:0] app_response_data,
    output reg [255:0] response_data,
    output reg response_fault,
    input wire recording_valid,recording_write,
    input wire [28:0] recording_address,
    input wire [255:0] recording_data,
    input wire [31:0] recording_mask,
    output wire recording_ready,recording_response,
    output wire [8:0] core_accept_o,native_accept_o,
    output wire transport_fault_o,
    output wire [8:0] native_fault_probe_o
);
    generate if(!RECORDING_ENABLE)begin:g_legacy
        // Literal legacy instance: no new tag bits, queues or fairness state.
        basic_pitch_ddr_arbiter_pipeline #(.TAG_BITS(TAG_BITS),.REGISTER_GRANTS(REGISTER_GRANTS)) u_legacy(
            .clk(clk),
            .reset_n(reset_n),
            .bist_done(bist_done),
            .bist_valid(bist_valid),
            .bist_write(bist_write),
            .bist_address(bist_address),
            .bist_data(bist_data),
            .bist_ready(bist_ready),
            .bist_response(bist_response),
            .scan_valid(scan_valid),
            .scan_address(scan_address),
            .scan_ready(scan_ready),
            .scan_response(scan_response),
            .display_valid(display_valid),
            .display_address(display_address),
            .display_ready(display_ready),
            .display_response(display_response),
            .audio_valid(audio_valid),
            .audio_write(audio_write),
            .audio_address(audio_address),
            .audio_data(audio_data),
            .audio_ready(audio_ready),
            .audio_response(audio_response),
            .music_valid(music_valid),
            .music_write(music_write),
            .music_address(music_address),
            .music_data(music_data),
            .music_mask(music_mask),
            .music_ready(music_ready),
            .music_response(music_response),
            .delay_valid(delay_valid),
            .delay_write(delay_write),
            .delay_address(delay_address),
            .delay_data(delay_data),
            .delay_ready(delay_ready),
            .delay_response(delay_response),
            .writer_valid(writer_valid),
            .writer_address(writer_address),
            .writer_data(writer_data),
            .writer_ready(writer_ready),
            .cpu_valid(cpu_valid),
            .cpu_write(cpu_write),
            .cpu_address(cpu_address),
            .cpu_data(cpu_data),
            .cpu_mask(cpu_mask),
            .cpu_ready(cpu_ready),
            .cpu_response(cpu_response),
            .app_cmd(app_cmd),
            .app_en(app_en),
            .app_wren(app_wren),
            .app_wend(app_wend),
            .app_address(app_address),
            .app_data(app_data),
            .app_mask(app_mask),
            .app_ready(app_ready),
            .app_write_ready(app_write_ready),
            .app_response(app_response),
            .app_response_data(app_response_data),
            .response_data(response_data),
            .response_fault(response_fault));
        assign recording_ready=0;
        assign recording_response=0;
        assign core_accept_o={1'b0,display_ready,delay_ready,music_ready,audio_ready,writer_ready,cpu_ready,scan_ready,bist_ready};
        assign native_fault_probe_o=0;
        assign native_accept_o=0; // unavailable in literal compatibility branch
        assign transport_fault_o=response_fault;
    end else begin:g_recording
    localparam DEPTH=1<<TAG_BITS;
    initial if(TAG_BITS<2 || TAG_BITS>8)$fatal(1,"DDR tag bits must be2..8");
    reg [3:0] tags[0:DEPTH-1];
    reg [TAG_BITS-1:0] read_pointer,write_pointer;
    reg [TAG_BITS:0] count;
    reg prefer_cpu,prefer_music,music_turn,cpu_read_pending,prefer_recording;
    wire cpu_available=cpu_valid && !cpu_read_pending;
    reg [3:0] owner;
    reg valid,is_write;
    reg [8:0] grant;
    reg reservation_valid,reservation_write;
    reg [3:0] reservation_owner;
    reg [8:0] reservation_grant;
    wire effective_valid=REGISTER_GRANTS?reservation_valid:valid;
    wire effective_write=REGISTER_GRANTS?reservation_write:is_write;
    wire [3:0] effective_owner=REGISTER_GRANTS?reservation_owner:owner;
    wire [8:0] effective_grant=REGISTER_GRANTS?(reservation_grant & {9{reservation_valid}}):grant;
    reg [28:0] selected_address;
    reg [255:0] selected_data;
    reg [31:0] selected_mask;
    always @* begin
        owner=0;valid=0;is_write=0;grant=0;
        if(!bist_done) begin
            valid=bist_valid;grant[0]=bist_valid;is_write=bist_write;
        end else if(scan_valid) begin
            owner=1;valid=1;grant[1]=1;
        end else if(music_turn) begin
            // Give a waiting model upload/analysis request one full DDR slot
            // after audio.  A stalled music request retains the turn.
            owner=5;valid=music_valid;grant[5]=music_valid;is_write=music_write;

        end else if(audio_valid) begin
            // Scanout keeps first priority; the streaming audio client is
            // next so a full TF ring cannot be blocked by UI/CPU traffic.
            owner=4;valid=1;grant[4]=1;is_write=audio_write;

        end else if(display_valid) begin
            // Distinct tag avoids changing response ownership at BIST completion.
            owner=7;valid=1;grant[7]=1;
        end else if(music_valid && (!prefer_music || (!cpu_available && !writer_valid && !recording_valid))) begin
            owner=5;valid=1;grant[5]=1;is_write=music_write;

        end else if(delay_valid) begin
            // Preserve delay owner6 below TF/audio/music-turn and above the
            // background group. Offered-load/deadline bounds need separate
            // validation; continuous higher-priority requests may starve it.
            owner=6;valid=1;grant[6]=1;is_write=delay_write;

        end else if(recording_valid && (prefer_recording || (!cpu_available && !writer_valid))) begin
            // Bounded background turn: one recording slot alternates with the
            // old CPU/writer choice; urgent clients retain their priority.
            owner=8;valid=1;grant[8]=1;is_write=recording_write;
        end else if(cpu_available && (!writer_valid || prefer_cpu)) begin
            owner=2;valid=1;grant[2]=1;is_write=cpu_write;
        end else begin
            owner=3;valid=writer_valid;grant[3]=writer_valid;is_write=1;
        end
        selected_address=({29{effective_grant[0]}}&bist_address)|
            ({29{effective_grant[1]}}&scan_address)|({29{effective_grant[2]}}&cpu_address)|
            ({29{effective_grant[3]}}&writer_address)|({29{effective_grant[4]}}&audio_address)|
            ({29{effective_grant[5]}}&music_address)|({29{effective_grant[6]}}&delay_address)|
            ({29{effective_grant[7]}}&display_address)|({29{effective_grant[8]}}&recording_address);
        selected_data=({256{effective_grant[0]}}&bist_data)|({256{effective_grant[2]}}&cpu_data)|
            ({256{effective_grant[3]}}&writer_data)|({256{effective_grant[4]}}&audio_data)|
            ({256{effective_grant[5]}}&music_data)|({256{effective_grant[6]}}&delay_data)|
            ({256{effective_grant[8]}}&recording_data);
        selected_mask=({32{effective_grant[2]}}&cpu_mask)|({32{effective_grant[5]}}&music_mask)|
            ({32{effective_grant[8]}}&recording_mask);
    end
    reg command_full,command_write;
    reg [3:0] command_owner,response_owner;
    reg response_valid;
    // Client acceptance means a complete command has entered this one-entry
    // buffer. Leave one empty cycle on drain: no PHY-ready feedback into
    // arbitration or the client request/ready logic.
    wire can_buffer=reset_n && !command_full;
    wire read_room=count<DEPTH;
    // One-hot selections bypass binary owner decode and selected-write mux in
    // each client's ready cone. Priority/fairness are still the policy above.
    assign bist_ready=can_buffer && effective_grant[0] && (bist_write || read_room);
    assign scan_ready=can_buffer && effective_grant[1] && read_room;
    assign cpu_ready=can_buffer && effective_grant[2] && (cpu_write || read_room);
    assign writer_ready=can_buffer && effective_grant[3];
    assign audio_ready=can_buffer && effective_grant[4] && (audio_write || read_room);
    assign music_ready=can_buffer && effective_grant[5] && (music_write || read_room);
    assign delay_ready=can_buffer && effective_grant[6] && (delay_write || read_room);
    assign display_ready=can_buffer && effective_grant[7] && read_room;
    assign recording_ready=can_buffer && effective_grant[8] && (recording_write || read_room);
    assign core_accept_o={recording_ready,display_ready,delay_ready,music_ready,audio_ready,writer_ready,cpu_ready,scan_ready,bist_ready};
    wire accept=bist_ready || scan_ready || cpu_ready || writer_ready ||
        audio_ready || music_ready || delay_ready || display_ready || recording_ready;
    assign app_en=reset_n && command_full && app_ready &&
        (!command_write || app_write_ready) && (command_write || read_room);
    assign app_wren=app_en && command_write;
    assign app_wend=app_wren;
    wire push=app_en && !command_write;
    wire pop=app_response && count!=0;
    // Decode the authoritative tags, then select through bounded four-way
    // stages. Keep each stage so mapping cannot rebuild a serial owner mux.
    // No shadow state: corruption reaches the same-edge transport fault.
    // Unknown address bits still produce X as the original variable index.
    // Response owner/data continue to retire on their original edge.
    wire [DEPTH-1:0] invalid_owner_by_slot;
    for(genvar slot=0;slot<DEPTH;slot=slot+1)begin:g_invalid_owner
        assign invalid_owner_by_slot[slot]=tags[slot]==4'd3 || tags[slot]>4'd8;
    end
    localparam OWNER_VETO_LEVELS=(TAG_BITS+1)/2;
    wire [DEPTH-1:0] owner_veto_tree[0:OWNER_VETO_LEVELS];
    assign owner_veto_tree[0]=invalid_owner_by_slot;
    for(genvar level=0;level<OWNER_VETO_LEVELS;level=level+1)begin:g_owner_veto_level
        localparam INPUTS=DEPTH>>(level*2);
        localparam OUTPUTS=(INPUTS+3)/4;
        for(genvar group=0;group<DEPTH;group=group+1)begin:g_group
            if(group<OUTPUTS)begin:g_live
                reg selected /* synthesis syn_keep=1 */;
                if(level*2+1<TAG_BITS)begin:g_four
                    always @* case(read_pointer[level*2+:2])
                        2'd0:selected=owner_veto_tree[level][group*4];
                        2'd1:selected=owner_veto_tree[level][group*4+1];
                        2'd2:selected=owner_veto_tree[level][group*4+2];
                        2'd3:selected=owner_veto_tree[level][group*4+3];
                        default:selected=1'bx;
                    endcase
                end else begin:g_two
                    always @* case(read_pointer[level*2])
                        1'b0:selected=owner_veto_tree[level][group*2];
                        1'b1:selected=owner_veto_tree[level][group*2+1];
                        default:selected=1'bx;
                    endcase
                end
                assign owner_veto_tree[level+1][group]=selected;
            end else begin:g_unused
                assign owner_veto_tree[level+1][group]=1'b0;
            end
        end
    end
    wire invalid_return_owner=count!=0 && owner_veto_tree[OWNER_VETO_LEVELS][0];
    wire response_fault_now=app_response && (count==0 || invalid_return_owner);
    assign transport_fault_o=response_fault || response_fault_now;
    // A diagnostic cofactor only: never a native acceptance or ready signal.
    // It equals native_accept_o when the enclosing immediate transport fault
    // is zero, using the same held command and unqualified physical readiness.
    wire native_fault_probe=reset_n && command_full && app_ready_fault_probe_i &&
        (!command_write || app_write_ready) && (command_write || read_room);
    for(genvar client=0;client<9;client=client+1)begin:g_native_accept
        assign native_fault_probe_o[client]=native_fault_probe && command_owner==4'(client);
        assign native_accept_o[client]=app_en && command_owner==4'(client);
    end
    assign recording_response=response_valid && response_owner==8;
    assign bist_response=response_valid && response_owner==0;
    assign display_response=response_valid && response_owner==7;
    assign scan_response=response_valid && response_owner==1;
    assign cpu_response=response_valid && response_owner==2;
    assign audio_response=response_valid && response_owner==4;
    assign music_response=response_valid && response_owner==5;
    assign delay_response=response_valid && response_owner==6;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            command_full<=0;command_write<=0;command_owner<=0;
            app_cmd<=0;app_address<=0;app_data<=0;app_mask<=0;
        end else begin
            if(command_full)begin
                if(app_en)command_full<=0;
            end else begin
                command_full<=effective_valid && (effective_write || read_room);
                command_write<=effective_write;command_owner<=effective_owner;
            end
            // Wide data/address/mask registers need only local idle enables.
            // Their values are committed by command_full at the acceptance
            // edge and held throughout every native stall.
            if(!command_full)begin
                app_cmd<=effective_write?3'b000:3'b001;
                app_address<=selected_address;app_data<=selected_data;app_mask<=selected_mask;
            end
        end
    end
    // Optional registered selection is used only behind stable per-client
    // request queues. Selection can run while the native command is stalled,
    // so the steady native command initiation interval remains two cycles.
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
            reservation_valid<=0;reservation_grant<=0;
            reservation_owner<=0;reservation_write<=0;
        end else if(REGISTER_GRANTS)begin
            if(reservation_valid && can_buffer && (reservation_write || read_room))
                reservation_valid<=0;
            else if(!reservation_valid && valid && (is_write || read_room))begin
                reservation_valid<=1;reservation_grant<=grant;
                reservation_owner<=owner;reservation_write<=is_write;
            end
        end
    end
    // Data and ownership advance together. Native data may change every cycle;
    // consumers must use this returned bus with the registered response pulse.
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin response_valid<=0;response_owner<=0;response_data<=0;end
        else begin
            response_valid<=pop && !invalid_return_owner;
            response_data<=app_response_data;
            if(pop)response_owner<=tags[read_pointer];
        end
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            read_pointer<=0;write_pointer<=0;count<=0;
            prefer_cpu<=0;prefer_music<=0;music_turn<=0;cpu_read_pending<=0;response_fault<=0;prefer_recording<=0;
        end else begin
            if(cpu_ready || writer_ready)prefer_cpu<=writer_ready;
            if(music_ready)prefer_music<=1;
            else if(cpu_ready || writer_ready || recording_ready)prefer_music<=0;
            if(recording_ready)prefer_recording<=0;
            else if(cpu_ready || writer_ready)prefer_recording<=1;
            if(bist_done && !scan_valid)begin
                if(music_turn)begin
                    if(!music_valid || music_ready)music_turn<=0;
                end else if((audio_ready || display_ready) && music_valid)music_turn<=1;
            end
            if(cpu_response)cpu_read_pending<=0;
            if(cpu_ready && !cpu_write)cpu_read_pending<=1;
            if(push)begin tags[write_pointer]<=command_owner;write_pointer<=write_pointer+1'b1;end
            if(pop)read_pointer<=read_pointer+1'b1;
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:begin end
            endcase
            if(response_fault_now)response_fault<=1;
        end
    end
    end endgenerate
endmodule
