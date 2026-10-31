`default_nettype none
// All storage, command acceptance, ownership and SRC state are compute-clock
// owned. The APB wrapper crosses complete held commands, never a naked RAM bus.
module workstation_ae350_pcm_owner #(
    parameter bit SUSTAINED_VERIFIED=0,
    parameter integer WINDOW_BITS=10,
    parameter integer PREFILL_FRAMES=256,
    parameter integer HISTORY_TIMEOUT_CYCLES=4000000,
    parameter integer MAX_STEP_ERROR=33554 // +/-2000ppm in Q24
)(
    input wire clk_i,reset_ni,cpu_ready_i,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg [31:0] response_data_o,
    output reg response_error_o,
    input wire session_live_i,
    input wire [31:0] controller_epoch_i,transport_generation_i,
    input wire context_ready_i,rate_44100_i,
    input wire [31:0] physical_epoch_i,
    input wire tf_busy_i,switch_busy_i,
    input wire sample_take_i,
    input wire signed [31:0] legacy_left_i,legacy_right_i,
    output wire signed [31:0] pcm_left_o,pcm_right_o,
    output wire history_clear_o,
    input wire history_ready_i,history_done_i,
    output wire serial_hold_o,
    output reg [21:0] cancel_epoch_o,
    output wire selected_o,failed_o,hard_fault_o
);
    localparam [31:0] ONE=32'd16777216;
    localparam [3:0] H_IDLE=0,H_REQUEST=1,H_WAIT=2,H_SAMPLE=3,H_FAULT=4;
    localparam [31:0] F_CPU_RESET=1,F_SESSION=2,
        F_UNDERRUN=4,F_DESCRIPTOR=5,F_SEQUENCE=6,F_CONTEXT=7,F_TF=8,F_HISTORY=10;
    reg [31:0] memory[0:511];
    reg [127:0] written[0:3];
    reg [7:0] frames[0:3];
    reg [3:0] owned;
    reg [1:0] head_slot,tail_slot;
    reg [6:0] head_index;
    reg [9:0] queued;
    reg [31:0] staged_controller,staged_generation,staged_stream,staged_rate,staged_physical;
    reg [31:0] staged_slot,staged_frames,staged_sequence;
    reg [31:0] active_controller,active_generation,active_stream,active_rate,active_physical;
    // CPU reset never clears the retired key. It cannot reopen the old stream.
    reg [31:0] last_controller,last_generation,last_stream;
    reg retired_key_valid;
    reg armed,selected,failed,cpu_previous;
    reg [31:0] failure,expected_sequence,command_id,applied_id,pending_id;
    reg [3:0] history_state;
    reg desired_source,hold_serial;
    reg [31:0] history_wait;
    reg [23:0] phase;
    reg [31:0] step_q24,input_frames,output_frames,underflows,overflows;
    reg [9:0] minimum_queue,maximum_queue;
    reg [WINDOW_BITS-1:0] window_count;
    reg [WINDOW_BITS+9:0] occupancy_sum;
    reg signed [31:0] integral;
    reg [31:0] cache0,cache1;
    reg [8:0] cache_address;
    reg cache_valid;
    wire [8:0] address0={head_slot,head_index};
    wire at_end0={1'b0,head_index}+8'd1>=frames[head_slot];
    wire [1:0] slot1=at_end0 ? head_slot+2'd1:head_slot;
    wire [6:0] index1=at_end0 ? 7'd0:head_index+7'd1;
    wire at_end1={1'b0,index1}+8'd1>=frames[slot1];
    wire [1:0] slot2=at_end1 ? slot1+2'd1:slot1;
    wire [6:0] index2=at_end1 ? 7'd0:index1+7'd1;
    wire pair_available=queued>=2 && owned[head_slot] && owned[slot1];
    always @(posedge clk_i)begin
        cache0<=memory[address0];cache1<=memory[{slot1,index1}];
        cache_address<=address0;cache_valid<=pair_available;
    end
    wire cache_current=cache_valid && cache_address==address0 && pair_available;
    // Express equality as an XOR mismatch reduction in the real-time PCM
    // permission path; actual mapping/timing needs a new synthesis and P&R.
    wire key_matches=!(|(staged_controller^active_controller)) && !(|(staged_generation^active_generation)) &&
        !(|(staged_stream^active_stream)) && !(|(staged_rate^active_rate)) && !(|(staged_physical^active_physical));
    wire live_matches=session_live_i && !(|(controller_epoch_i^active_controller)) && !(|(transport_generation_i^active_generation));
    wire physical_matches=context_ready_i && !(|(active_physical^physical_epoch_i)) &&
        active_rate==(rate_44100_i ? 32'd44100:32'd48000) && !switch_busy_i;
    wire usable=armed && !failed && live_matches && physical_matches && cpu_ready_i && !tf_busy_i;
    wire prefilled=usable && queued>=10'(PREFILL_FRAMES) && cache_current;
    wire accepted=command_valid_i && command_ready_o;
    wire write_command=accepted && command_write_i;
    wire full_write=command_strobes_i==4'hf && command_address_i[1:0]==0;
    wire window_write=write_command && command_address_i[11];
    wire [1:0] write_slot=command_address_i[10:9];
    wire [6:0] write_index=command_address_i[8:2];
    // The RAM window has its own complete validation rule. A descriptor's
    // unrelated variable frame mask must not enter the PCM RAM write enable.
    wire accepted_window_write=window_write && full_write && armed && key_matches && !owned[write_slot];
    // The original 32-bit subtract/128-bit shift is exactly a prefix mask for
    // frame counts 1..128 and zero for every other 32-bit value. Constant bit
    // thresholds express that rule without a subtract or barrel shifter.
    wire descriptor_frames_valid=staged_frames>=32'd1 && staged_frames<=32'd128;
    wire [127:0] required_mask;
    for(genvar frame_bit=0;frame_bit<128;frame_bit=frame_bit+1)begin:g_required_mask
        assign required_mask[frame_bit]=descriptor_frames_valid && staged_frames[7:0]>8'(frame_bit);
    end
    wire descriptor_missing_frames=|(~written[tail_slot]&required_mask);
    wire new_stream=staged_stream!=0 && (!retired_key_valid ||
        staged_controller!=last_controller || staged_generation!=last_generation || staged_stream>last_stream);
    wire staging_live=session_live_i && staged_controller==controller_epoch_i && staged_generation==transport_generation_i &&
        context_ready_i && staged_physical==physical_epoch_i &&
        staged_rate==(rate_44100_i ? 32'd44100:32'd48000) && !switch_busy_i && !tf_busy_i;
    wire sample_advance=sample_take_i && selected && usable && !hold_serial && cache_current;
    wire [25:0] next_phase={2'b0,phase}+{1'b0,step_q24[24:0]};
    wire [1:0] consume=next_phase[25:24];
    wire [3:0] release0=at_end0 ? (4'b0001<<head_slot):4'b0000;
    wire [3:0] release1=at_end1 ? (4'b0001<<slot1):4'b0000;
    wire [3:0] release_mask=consume==0 ? 4'd0:consume==1 ? release0:release0|release1;
    wire signed [16:0] delta_l=$signed(cache1[15:0])-$signed(cache0[15:0]);
    wire signed [16:0] delta_r=$signed(cache1[31:16])-$signed(cache0[31:16]);
    wire signed [41:0] product_l=delta_l*$signed({1'b0,phase});
    wire signed [41:0] product_r=delta_r*$signed({1'b0,phase});
    wire signed [41:0] interpolation_l=$signed({{2{cache0[15]}},cache0[15:0],24'd0})+product_l;
    wire signed [41:0] interpolation_r=$signed({{2{cache0[31]}},cache0[31:16],24'd0})+product_r;
    wire [15:0] interpolated_l=interpolation_l[39:24],interpolated_r=interpolation_r[39:24];
    // Fixed stereo linear interpolation, no independent channel phase/control.
    assign pcm_left_o=selected ? (usable && !hold_serial && cache_current ? {interpolated_l,16'd0}:32'd0):legacy_left_i;
    assign pcm_right_o=selected ? (usable && !hold_serial && cache_current ? {interpolated_r,16'd0}:32'd0):legacy_right_i;
    assign selected_o=selected;
    assign failed_o=failed;
    assign hard_fault_o=history_state==H_FAULT;
    assign serial_hold_o=hold_serial;
    assign history_clear_o=history_state==H_REQUEST;
    assign command_ready_o=reset_ni && cpu_ready_i;
    wire [31:0] rate_hz=rate_44100_i ? 32'd44100:32'd48000;
    wire [31:0] status={24'd0,session_live_i,context_ready_i,history_state==H_REQUEST || history_state==H_WAIT,
        history_state!=H_IDLE,failed,prefilled,selected,armed};
    // Validate each command in parallel. A specific accepted operation must
    // not traverse the response-data/error mux for unrelated commands before
    // reaching its queue/bitmap updates. The response uses the same predicates.
    wire start_error=armed || selected || history_state!=H_IDLE || !staging_live || !new_stream || &cancel_epoch_o;
    wire commit_error=!usable || !key_matches || staged_slot!={30'd0,tail_slot} || owned[tail_slot] ||
        !descriptor_frames_valid || staged_sequence!=expected_sequence || &expected_sequence || descriptor_missing_frames;
    wire select_error=!key_matches || !prefilled || history_state!=H_IDLE || selected || &cancel_epoch_o;
    wire stop_error=!key_matches || history_state!=H_IDLE || &cancel_epoch_o;
    wire cancel_error=!key_matches || history_state==H_FAULT || &cancel_epoch_o;
    // Match the original response decoder's procedural treatment of unknown
    // strobes/ID bits as well as its binary hardware admission rule.
    reg control_format_ok,control_id_ok;
    always @* begin
        control_format_ok=1'b1;control_id_ok=1'b1;
        if(!full_write)control_format_ok=1'b0;
        if(&command_id)control_id_ok=1'b0;
    end
    wire control_write=write_command && control_format_ok && command_address_i==12'h040 && control_id_ok;
    wire accepted_start=control_write && command_data_i==32'd1 && !start_error;
    wire accepted_commit=control_write && command_data_i==32'd2 && !commit_error;
    wire accepted_select=control_write && command_data_i==32'd3 && !select_error;
    wire accepted_stop=control_write && command_data_i==32'd4 && !stop_error;
    wire accepted_cancel=control_write && command_data_i==32'd5 && !cancel_error;
    wire accepted_control=accepted_start || accepted_commit || accepted_select || accepted_stop || accepted_cancel;
    wire accepted_staging_write=write_command && control_format_ok && !command_address_i[11] &&
        command_address_i>=12'h020 && command_address_i<=12'h03c;
    reg command_error;
    always @* begin
        response_data_o=0;response_error_o=0;command_error=0;
        case(command_address_i)
            12'h000:response_data_o=32'h50434d31;
            12'h004:response_data_o=32'h00010000;
            12'h008:response_data_o=32'h67|(SUSTAINED_VERIFIED ? 32'h8:32'h0);
            12'h00c:response_data_o=status;
            12'h010:response_data_o=failure;
            12'h014:response_data_o={28'd0,~owned};
            12'h018:response_data_o={22'd0,queued};
            12'h01c:response_data_o=expected_sequence;
            12'h020:response_data_o=staged_controller;
            12'h024:response_data_o=staged_generation;
            12'h028:response_data_o=staged_stream;
            12'h02c:response_data_o=staged_rate;
            12'h030:response_data_o=staged_physical;
            12'h034:response_data_o=staged_slot;
            12'h038:response_data_o=staged_frames;
            12'h03c:response_data_o=staged_sequence;
            12'h040:begin
                response_data_o=command_id+1'b1;
                case(command_data_i)
                    1:command_error=start_error;
                    2:command_error=commit_error;
                    3:command_error=select_error;
                    4:command_error=stop_error;
                    5:command_error=cancel_error;
                    default:command_error=1;
                endcase
                if(&command_id)command_error=1;
            end
            12'h044:response_data_o=command_id;
            12'h048:response_data_o=applied_id;
            12'h04c:response_data_o={31'd0,selected};
            12'h050:response_data_o=step_q24;
            12'h054:response_data_o={22'd0,minimum_queue};
            12'h058:response_data_o={22'd0,maximum_queue};
            12'h05c:response_data_o=input_frames;
            12'h060:response_data_o=output_frames;
            12'h064:response_data_o=PREFILL_FRAMES;
            12'h068:response_data_o={22'd0,queued};
            12'h06c:response_data_o=0; // Total effects/output delay unknown: capability false.
            12'h070:response_data_o=rate_hz;
            12'h074:response_data_o=physical_epoch_i;
            12'h078:response_data_o=transport_generation_i;
            12'h07c:response_data_o=controller_epoch_i;
            12'h080:response_data_o=active_stream;
            12'h088:response_data_o=underflows;
            12'h08c:response_data_o=overflows;
            default:begin
                if(!command_address_i[11] || !command_write_i)response_error_o=1;
            end
        endcase
        if(command_address_i[1:0]!=0)response_error_o=1;
        if(command_write_i)begin
            if(!full_write)response_error_o=1;
            else if(command_address_i[11])response_error_o=!armed || !key_matches || owned[write_slot];
            else if(command_address_i>=12'h020 && command_address_i<=12'h03c)response_error_o=0;
            else if(command_address_i==12'h040)response_error_o=command_error;
            else response_error_o=1;
        end
    end
    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value:value+1'b1;
    endfunction
    task automatic flush_queue;
        integer k;
        begin
            owned<=0;head_slot<=0;tail_slot<=0;head_index<=0;queued<=0;
            for(k=0;k<4;k=k+1)written[k]<=0;
            phase<=0;step_q24<=ONE;integral<=0;window_count<=0;occupancy_sum<=0;
        end
    endtask
    task automatic terminate(input [31:0] reason);
        begin
            armed<=0;failed<=1;failure<=reason;flush_queue();
            pending_id<=0;desired_source<=0;
            if(selected || history_state!=H_IDLE)begin
                hold_serial<=1;
                if(history_state==H_IDLE || history_state==H_SAMPLE)history_state<=H_REQUEST;
            end
            if(!(&cancel_epoch_o))cancel_epoch_o<=cancel_epoch_o+1'b1;
        end
    endtask
    integer k;
    reg signed [31:0] average_error,integral_next,target_error,current_error;
    reg [31:0] next_step;
    // Average a complete window to reject block-arrival sawtooth. All
    // extensions are explicit; these temporaries never own sequential state.
    always @* begin
        average_error=$signed((32'(occupancy_sum)+32'(queued))>>WINDOW_BITS)-PREFILL_FRAMES;
        integral_next=integral+average_error*8;
        if(integral_next>MAX_STEP_ERROR)integral_next=MAX_STEP_ERROR;
        if(integral_next< -MAX_STEP_ERROR)integral_next= -MAX_STEP_ERROR;
        target_error=average_error*512+integral_next;
        if(target_error>MAX_STEP_ERROR)target_error=MAX_STEP_ERROR;
        if(target_error< -MAX_STEP_ERROR)target_error= -MAX_STEP_ERROR;
        current_error=$signed(step_q24)-$signed(ONE);
        // <=1024 Q24 units/window: bounded ~61ppm/1024 output frames.
        if(target_error>current_error+1024)current_error=current_error+1024;
        else if(target_error<current_error-1024)current_error=current_error-1024;
        else current_error=target_error;
        next_step=ONE+current_error;
    end
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            owned<=0;head_slot<=0;tail_slot<=0;head_index<=0;queued<=0;
            for(k=0;k<4;k=k+1)begin written[k]<=0;frames[k]<=0;end
            staged_controller<=0;staged_generation<=0;staged_stream<=0;staged_rate<=0;staged_physical<=0;
            staged_slot<=0;staged_frames<=0;staged_sequence<=0;
            active_controller<=0;active_generation<=0;active_stream<=0;active_rate<=0;active_physical<=0;
            last_controller<=0;last_generation<=0;last_stream<=0;retired_key_valid<=0;
            armed<=0;selected<=0;failed<=0;cpu_previous<=0;failure<=0;
            expected_sequence<=0;command_id<=0;applied_id<=0;pending_id<=0;
            history_state<=H_IDLE;desired_source<=0;hold_serial<=0;cancel_epoch_o<=0;history_wait<=0;
            phase<=0;step_q24<=ONE;input_frames<=0;output_frames<=0;
            underflows<=0;overflows<=0;minimum_queue<=512;maximum_queue<=0;
            window_count<=0;occupancy_sum<=0;integral<=0;
        end else begin
            cpu_previous<=cpu_ready_i;
            if(selected && usable && queued<minimum_queue)minimum_queue<=queued;
            if(selected && usable && queued>maximum_queue)maximum_queue<=queued;
            if(sample_advance)begin
                phase<=next_phase[23:0];queued<=queued-{8'd0,consume};
                if(consume==1)begin head_slot<=slot1;head_index<=index1;end
                if(consume==2)begin head_slot<=slot2;head_index<=index2;end
                owned<=owned&~release_mask;
                input_frames<=input_frames+{30'd0,consume};output_frames<=increment(output_frames);
                occupancy_sum<=occupancy_sum+(WINDOW_BITS+10)'(queued);window_count<=window_count+1'b1;
                if(&window_count)begin
                    integral<=integral_next;step_q24<=next_step;occupancy_sum<=0;
                end
            end
            if(history_state==H_REQUEST || history_state==H_WAIT)begin
                if(history_wait==HISTORY_TIMEOUT_CYCLES-1 &&
                    !(history_state==H_REQUEST && history_ready_i) && !(history_state==H_WAIT && history_done_i))begin
                    history_state<=H_FAULT;armed<=0;failed<=1;failure<=F_HISTORY;hold_serial<=1;
                end else history_wait<=history_wait+1'b1;
            end else history_wait<=0;
            case(history_state)
                H_REQUEST:if(history_ready_i)history_state<=H_WAIT;
                H_WAIT:if(history_done_i)begin
                    selected<=desired_source;hold_serial<=0;history_state<=H_SAMPLE;
                end
                H_SAMPLE:if(sample_take_i)begin
                    if(pending_id!=0)applied_id<=pending_id;
                    pending_id<=0;history_state<=H_IDLE;
                end
                default:begin end
            endcase
            if(accepted_window_write)begin
                memory[{write_slot,write_index}]<=command_data_i;written[write_slot][write_index]<=1;
            end
            if(accepted_staging_write)begin
                case(command_address_i)
                    12'h020:staged_controller<=command_data_i;
                    12'h024:staged_generation<=command_data_i;
                    12'h028:staged_stream<=command_data_i;
                    12'h02c:staged_rate<=command_data_i;
                    12'h030:staged_physical<=command_data_i;
                    12'h034:staged_slot<=command_data_i;
                    12'h038:staged_frames<=command_data_i;
                    12'h03c:staged_sequence<=command_data_i;
                    default:begin end
                endcase
            end
            if(accepted_control)command_id<=command_id+1'b1;
            if(accepted_start)begin
                active_controller<=staged_controller;active_generation<=staged_generation;
                active_stream<=staged_stream;active_rate<=staged_rate;active_physical<=staged_physical;
                last_controller<=staged_controller;last_generation<=staged_generation;last_stream<=staged_stream;
                retired_key_valid<=1;armed<=1;failed<=0;failure<=0;expected_sequence<=0;
                input_frames<=0;output_frames<=0;minimum_queue<=512;maximum_queue<=0;flush_queue();
            end
            if(accepted_commit)begin
                owned<=(owned&~(sample_advance ? release_mask:4'd0))|(4'b1<<tail_slot);
                frames[tail_slot]<=staged_frames[7:0];written[tail_slot]<=0;tail_slot<=tail_slot+1'b1;
                queued<=queued+staged_frames[9:0]-(sample_advance ? {8'd0,consume}:10'd0);
                expected_sequence<=expected_sequence+1'b1;
            end
            if(accepted_select || accepted_stop)begin
                desired_source<=accepted_select;hold_serial<=1;history_state<=H_REQUEST;
                pending_id<=command_id+1'b1;cancel_epoch_o<=cancel_epoch_o+1'b1;
                if(accepted_stop)begin armed<=0;flush_queue();end
            end
            if(accepted_cancel)begin
                armed<=0;flush_queue();desired_source<=0;
                cancel_epoch_o<=cancel_epoch_o+1'b1;
                if(selected || history_state!=H_IDLE)begin
                    hold_serial<=1;pending_id<=command_id+1'b1;
                    if(history_state==H_IDLE || history_state==H_SAMPLE)history_state<=H_REQUEST;
                end
                else applied_id<=command_id+1'b1;
            end
            if(write_command && response_error_o && (command_address_i[11] ||
                (command_address_i==12'h040 && command_data_i==2 && owned[tail_slot])))overflows<=increment(overflows);
            if(write_command && response_error_o && command_address_i==12'h040 && command_data_i==2 &&
                usable && key_matches && !owned[tail_slot])begin
                if(staged_sequence!=expected_sequence || &expected_sequence)terminate(F_SEQUENCE);
                else terminate(F_DESCRIPTOR);
            end
            // Revocation has priority over same-edge commands and RAM reads.
            if(armed)begin
                if(cpu_previous && !cpu_ready_i)terminate(F_CPU_RESET);
                else if(!live_matches)terminate(F_SESSION);
                else if(!physical_matches)terminate(F_CONTEXT);
                else if(tf_busy_i)terminate(F_TF);
                else if(sample_take_i && selected && !hold_serial && !cache_current)begin
                    underflows<=increment(underflows);terminate(F_UNDERRUN);
                end
            end
        end
    end
endmodule
`default_nettype wire
