`timescale 1ns/1ps
`include "src/memory/ddr_address_map.vh"
module tb_video_scanout #(parameter integer USE_QUEUES=0, VIDEO_720P30=0, VIDEO_720P60=0,
                         READ_LATENCY_CYCLES=64, ACTIVE_LINES=8,
                         WRITE_TURNAROUND_CYCLES=0, SCAN_WRITE_WINDOW=0,
                         USE_SCAN_ADMISSION_MODULE=0, COMPETING_CLIENTS=0,
                         SAMPLE_RATE_HZ=48000, REGISTER_UNDERRUN_EVENT=0);
    localparam integer VIDEO_720=VIDEO_720P30 || VIDEO_720P60;
    localparam integer WIDTH=VIDEO_720 ? 1280 : 1920, HEIGHT=ACTIVE_LINES;
    localparam integer H_TOTAL=VIDEO_720P60 ? 1650 : VIDEO_720P30 ? 3300 : 2200;
    localparam integer V_BLANK=VIDEO_720 ? 30 : 45;
    localparam realtime PIXEL_HALF_NS=VIDEO_720 ? 6.734007 : 3.3670035;
    reg memory_clk=0, pixel_clk=0, reset_n=0;
    always #5 memory_clk=~memory_clk;
    always #(PIXEL_HALF_NS) pixel_clk=~pixel_clk;
    reg [11:0] pixel_x=0;
    reg [10:0] pixel_y=HEIGHT;
    reg vblank_start=0;
    wire data_enable=pixel_x<WIDTH && pixel_y<HEIGHT;
    wire hsync=VIDEO_720P60 ? pixel_x>=1390 && pixel_x<1430 :
        VIDEO_720P30 ? pixel_x>=3040 && pixel_x<3080 : pixel_x>=2008 && pixel_x<2052;
    wire vsync=pixel_y==HEIGHT+1;
    reg frame_pending=1;
    reg [28:0] frame_base=`PRJ1_DDR_VIDEO_FRAME0_APP_BASE;
    wire frame_swap,front_bank,front_valid,request_valid,fetch_fault;
    wire [28:0] request_address;
    wire [31:0] underruns;
    wire [23:0] rgb;
    wire out_de,out_hsync,out_vsync;
    wire request_ready,response_valid;
    wire [255:0] response_data;
    reg model_ready=0,model_response_valid=0;
    reg [255:0] model_response_data=0;
    wire model_request;
    wire [28:0] model_address;
    wire native_fault,native_write;
    wire fetch_busy;
    integer background_writes=0;
    integer memory_cycle=0;
    integer writer_accepts=0,cpu_accepts=0,writer_issues=0,cpu_issues=0;
    integer audio_accepts=0,delay_accepts=0,music_accepts=0,display_accepts=0;
    integer audio_issues=0,delay_issues=0,music_issues=0,display_issues=0;
    integer writer_wait=0,cpu_wait=0,writer_max_wait=0,cpu_max_wait=0;
    integer audio_max_wait=0,delay_max_wait=0,music_max_wait=0,display_max_wait=0;
    integer window_writer_tail=0,window_cpu_tail=0,maximum_writer_tail=0,maximum_cpu_tail=0;
    integer fetch_cycles=0,max_fetch_cycles=0,max_prefill_line_cycles=0,max_runtime_line_cycles=0;
    integer max_scan_credits=0,max_response_fifo=0,max_native_reads=0;
    reg previous_fetch_busy=0;
    reg competition_running=1;
    integer accepted_at[0:7][0:1023];
    integer max_accept_to_native[0:7],read_issued_at[0:7],max_native_to_response[0:7];
    reg [7:0] client_read_inflight=0;
    integer statistic_owner;
    initial for(statistic_owner=0;statistic_owner<8;statistic_owner=statistic_owner+1)begin
        max_accept_to_native[statistic_owner]=0;read_issued_at[statistic_owner]=0;
        max_native_to_response[statistic_owner]=0;
    end
    generate
        if(USE_QUEUES) begin : g_native
            wire app_enable,app_write_enable,app_write_end;
            wire [2:0] app_command;
            wire [255:0] app_data;
            wire [31:0] app_mask;
            wire writer_valid,writer_ready,cpu_valid,cpu_ready;
            wire raw_writer_ready,raw_cpu_ready;
            wire audio_ready,audio_response,delay_ready,delay_response;
            wire music_ready,music_response,display_ready,display_response;
            integer audio_next_due=500,delay_next_due=750,music_next_due=1000,display_next_due=1250;
            integer audio_sequence=0,delay_sequence=0,music_sequence=0,display_sequence=0;
            reg audio_pending=0,delay_pending=0,music_pending=0,display_pending=0;
            wire audio_valid=COMPETING_CLIENTS && competition_running && memory_cycle>=audio_next_due && !audio_pending;
            wire delay_valid=COMPETING_CLIENTS && competition_running && memory_cycle>=delay_next_due && !delay_pending;
            wire music_valid=COMPETING_CLIENTS && competition_running && memory_cycle>=music_next_due && !music_pending;
            wire display_valid=COMPETING_CLIENTS && competition_running && memory_cycle>=display_next_due && !display_pending;
            wire audio_write=!audio_sequence[0],delay_write=!delay_sequence[0],music_write=!music_sequence[0];
            // Keep test addresses inside each native-word region over full
            // 1080-line runs; the full sequence remains in data for checking.
            wire [28:0] writer_address=29'h08000000+29'((writer_accepts%131072)*8);
            wire [28:0] cpu_address=29'h00400000+29'((cpu_accepts%131072)*8);
            wire [255:0] writer_data={8{32'(writer_accepts)}};
            wire [255:0] cpu_data={8{32'(cpu_accepts)}};
            reg command_stalled=0;
            reg [575:0] held_native_command;
            integer issue_owner,issue_index,response_owner;
            wire [7:0] client_responses={display_response,delay_response,music_response,audio_response,4'd0};
            if(USE_SCAN_ADMISSION_MODULE) begin : g_window
                workstation_ddr_scan_window #(.ENABLE(SCAN_WRITE_WINDOW)) admission (
                    .scan_fetch_busy_i(fetch_busy),.writer_valid_i(!COMPETING_CLIENTS || competition_running),.writer_ready_o(writer_ready),
                    .writer_valid_o(writer_valid),.writer_ready_i(raw_writer_ready),
                    .cpu_valid_i(COMPETING_CLIENTS!=0 && competition_running),.cpu_write_i(1'b1),.cpu_ready_o(cpu_ready),
                    .cpu_valid_o(cpu_valid),.cpu_ready_i(raw_cpu_ready));
            end else begin : g_legacy_admission
                assign writer_valid=(!COMPETING_CLIENTS || competition_running) && (!SCAN_WRITE_WINDOW || !fetch_busy);
                assign writer_ready=raw_writer_ready && (!SCAN_WRITE_WINDOW || !fetch_busy);
                assign cpu_valid=COMPETING_CLIENTS!=0 && competition_running;
                assign cpu_ready=raw_cpu_ready;
            end
            basic_pitch_ddr_client_queues queues (
                .clk(memory_clk),.reset_n(reset_n),.bist_done(1'b1),
                .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),
                .scan_valid(request_valid),.scan_address(request_address),
                .scan_ready(request_ready),.scan_response(response_valid),
                .display_valid(display_valid),.display_address(29'h00200008),
                .display_ready(display_ready),.display_response(display_response),
                .audio_valid(audio_valid),.audio_write(audio_write),
                .audio_address(29'h00600000),.audio_data(256'h445566),
                .audio_ready(audio_ready),.audio_response(audio_response),
                .music_valid(music_valid),.music_write(music_write),.music_address(29'h04000000),
                .music_data(256'h1234),.music_mask(32'hfffffffc),
                .music_ready(music_ready),.music_response(music_response),
                .delay_valid(delay_valid),.delay_write(delay_write),.delay_address(29'h0c000000),.delay_data(256'h778899),
                .delay_ready(delay_ready),.delay_response(delay_response),
                .writer_valid(writer_valid),.writer_address(COMPETING_CLIENTS ? writer_address : 29'h08000000),
                .writer_data(COMPETING_CLIENTS ? writer_data : 256'h1234),.writer_ready(raw_writer_ready),
                .cpu_valid(cpu_valid),.cpu_write(1'b1),.cpu_address(cpu_address),.cpu_data(cpu_data),.cpu_mask(32'hffffff00),
                .cpu_ready(raw_cpu_ready),
                .app_cmd(app_command),.app_en(app_enable),.app_wren(app_write_enable),.app_wend(app_write_end),
                .app_address(model_address),.app_data(app_data),.app_mask(app_mask),
                .app_ready(model_ready),.app_write_ready(model_ready),
                .app_response(model_response_valid),.app_response_data(model_response_data),
                .response_data(response_data),.response_fault(native_fault));
            assign model_request=app_enable && app_command==3'b001;
            assign native_write=app_write_enable;
            // Bounded-rate request models, not replacements for actual media
            // DMA verification. Reads have one outstanding request per client.
            always @(posedge memory_clk) if(reset_n && COMPETING_CLIENTS) begin
                if(command_stalled && held_native_command!=={app_command,model_address,app_data,app_mask,256'd0})
                    $fatal(1,"native command/address/data/mask changed under controller stall");
                command_stalled<=queues.u_core.command_full && !app_enable;
                held_native_command<={app_command,model_address,app_data,app_mask,256'd0};
                if(queues.u_core.count>max_native_reads)max_native_reads=queues.u_core.count;
                if(fetch_busy && SCAN_WRITE_WINDOW && USE_SCAN_ADMISSION_MODULE &&
                   (writer_ready || cpu_ready || writer_valid || cpu_valid))
                    $fatal(1,"scan window admitted new background writes or false producer ACK");
                if(!fetch_busy || !previous_fetch_busy)begin window_writer_tail=0;window_cpu_tail=0;end
                if(competition_running && writer_ready)begin
                    accepted_at[3][writer_accepts%1024]=memory_cycle;
                    writer_accepts<=writer_accepts+1;writer_wait=0;
                end
                else if(competition_running)begin writer_wait=writer_wait+1;if(writer_wait>writer_max_wait)writer_max_wait=writer_wait;end
                if(competition_running && cpu_ready)begin
                    accepted_at[2][cpu_accepts%1024]=memory_cycle;
                    cpu_accepts<=cpu_accepts+1;cpu_wait=0;
                end
                else if(competition_running)begin cpu_wait=cpu_wait+1;if(cpu_wait>cpu_max_wait)cpu_max_wait=cpu_wait;end
                previous_fetch_busy=fetch_busy;
                if(audio_response)audio_pending<=0;
                if(delay_response)delay_pending<=0;
                if(music_response)music_pending<=0;
                if(display_response)display_pending<=0;
                for(response_owner=4;response_owner<8;response_owner=response_owner+1)begin
                    if(client_responses[response_owner])begin
                        if(!client_read_inflight[response_owner])$fatal(1,"response without native read");
                        if(memory_cycle-read_issued_at[response_owner]>max_native_to_response[response_owner])
                            max_native_to_response[response_owner]=memory_cycle-read_issued_at[response_owner];
                        client_read_inflight[response_owner]=0;
                    end
                end
                if(audio_valid && audio_ready)begin
                    if(memory_cycle-audio_next_due>audio_max_wait)audio_max_wait=memory_cycle-audio_next_due;
                    accepted_at[4][audio_accepts%1024]=memory_cycle;
                    audio_accepts=audio_accepts+1;audio_sequence<=audio_sequence+1;
                    audio_next_due<=500+integer'((64'(audio_sequence+1)*64'd400000000)/64'(SAMPLE_RATE_HZ));
                    if(!audio_write)audio_pending<=1;
                end
                if(delay_valid && delay_ready)begin
                    if(memory_cycle-delay_next_due>delay_max_wait)delay_max_wait=memory_cycle-delay_next_due;
                    accepted_at[6][delay_accepts%1024]=memory_cycle;
                    delay_accepts=delay_accepts+1;delay_sequence<=delay_sequence+1;
                    delay_next_due<=750+integer'((64'(delay_sequence+1)*64'd200000000)/64'(SAMPLE_RATE_HZ));
                    if(!delay_write)delay_pending<=1;
                end
                if(music_valid && music_ready)begin
                    if(memory_cycle-music_next_due>music_max_wait)music_max_wait=memory_cycle-music_next_due;
                    accepted_at[5][music_accepts%1024]=memory_cycle;
                    music_accepts=music_accepts+1;music_sequence<=music_sequence+1;
                    music_next_due<=music_next_due+5000;if(!music_write)music_pending<=1;
                end
                if(display_valid && display_ready)begin
                    if(memory_cycle-display_next_due>display_max_wait)display_max_wait=memory_cycle-display_next_due;
                    accepted_at[7][display_accepts%1024]=memory_cycle;
                    display_accepts=display_accepts+1;display_sequence<=display_sequence+1;
                    display_next_due<=display_next_due+5000;display_pending<=1;
                end
                if(app_enable)begin
                    issue_owner=-1;issue_index=0;
                    case(model_address[28:20])
                        9'h080:begin
                            issue_owner=3;issue_index=writer_issues;
                            if(app_command!=0 || model_address!=29'h08000000+29'((writer_issues%131072)*8) ||
                               app_data!={8{32'(writer_issues)}} || app_mask!=0)
                                $fatal(1,"writer payload/order/duplicate/mask");
                            writer_issues=writer_issues+1;
                            if(fetch_busy)window_writer_tail=window_writer_tail+1;
                        end
                        9'h004:begin
                            issue_owner=2;issue_index=cpu_issues;
                            if(app_command!=0 || model_address!=29'h00400000+29'((cpu_issues%131072)*8) ||
                               app_data!={8{32'(cpu_issues)}} || app_mask!=32'hffffff00)
                                $fatal(1,"CPU payload/order/duplicate/mask");
                            cpu_issues=cpu_issues+1;
                            if(fetch_busy)window_cpu_tail=window_cpu_tail+1;
                        end
                        9'h006:begin issue_owner=4;issue_index=audio_issues;audio_issues=audio_issues+1;end
                        9'h040:begin
                            issue_owner=5;issue_index=music_issues;
                            if(app_command==0 && app_mask!=32'hfffffffc)$fatal(1,"CNN write mask");
                            music_issues=music_issues+1;
                        end
                        9'h0c0:begin issue_owner=6;issue_index=delay_issues;delay_issues=delay_issues+1;end
                        9'h002:begin issue_owner=7;issue_index=display_issues;display_issues=display_issues+1;end
                        default:begin end
                    endcase
                    if(issue_owner>=0)begin
                        if(memory_cycle-accepted_at[issue_owner][issue_index%1024]>max_accept_to_native[issue_owner])
                            max_accept_to_native[issue_owner]=memory_cycle-accepted_at[issue_owner][issue_index%1024];
                        if(app_command==1)begin
                            if(client_read_inflight[issue_owner])$fatal(1,"model exceeded one outstanding read");
                            client_read_inflight[issue_owner]=1;read_issued_at[issue_owner]=memory_cycle;
                        end
                    end
                    if(writer_issues>writer_accepts || cpu_issues>cpu_accepts ||
                       audio_issues>audio_accepts || delay_issues>delay_accepts ||
                       music_issues>music_accepts || display_issues>display_accepts)
                        $fatal(1,"native issue without producer acceptance");
                end
                if(window_writer_tail>maximum_writer_tail)maximum_writer_tail=window_writer_tail;
                if(window_cpu_tail>maximum_cpu_tail)maximum_cpu_tail=window_cpu_tail;
                if(SCAN_WRITE_WINDOW && USE_SCAN_ADMISSION_MODULE &&
                    (window_writer_tail>2 || window_cpu_tail>2))$fatal(1,"accepted background tail exceeded slot and command buffer");
            end
        end else begin : g_direct
            assign request_ready=model_ready;
            assign response_valid=model_response_valid;
            assign response_data=model_response_data;
            assign model_request=request_valid;
            assign model_address=request_address;
            assign native_fault=1'b0;
            assign native_write=1'b0;
        end
    endgenerate
    video_ddr_scanout #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.EXPLICIT_BASE(1)
`ifdef SCANOUT_DIAGNOSTIC_PIPELINE
        ,.REGISTER_UNDERRUN_EVENT(REGISTER_UNDERRUN_EVENT)
`endif
    ) dut (
        .clk(memory_clk),.rst_n(reset_n),.enabled(1'b1),
        .new_frame_pending(frame_pending),.new_frame_base(frame_base),
        .new_composite(1'b0),.new_analysis_base(29'd0),
        .frame_swap(frame_swap),.front_bank(front_bank),.front_valid(front_valid),
        .req_valid(request_valid),.req_ready(request_ready),.req_addr(request_address),
        .rsp_valid(response_valid),.rsp_data(response_data),
        .fetch_fault(fetch_fault),.fetch_busy(fetch_busy),.underruns(underruns),
        .pixel_clk(pixel_clk),.pixel_rst_n(reset_n),.pixel_x(pixel_x),.pixel_y(pixel_y),
        .data_enable(data_enable),.hsync(hsync),.vsync(vsync),.vblank_start(vblank_start),
        .rgb(rgb),.out_de(out_de),.out_hsync(out_hsync),.out_vsync(out_vsync));

    function automatic [15:0] color565(input integer position,input integer generation);
        color565={5'b10000 | generation[4:0],position[5:0],position[10:6]^generation[4:0]};
    endfunction
    function automatic [23:0] expand565(input [15:0] color);
        expand565={color[15:11],color[15:13],color[10:5],color[10:9],color[4:0],color[4:2]};
    endfunction

    integer queue_head=0,queue_tail=0;
    reg [28:0] queued_address[0:16383];
    integer queued_due[0:16383];
    integer blocked_cycles=0,stall_mode=0,read_latency=READ_LATENCY_CYCLES;
    integer native_ready_at=0;
    reg last_command_write=0;
    integer selected_generation=1;
    integer response_position,response_generation;
    reg stall_started=0;
    always @(negedge memory_clk) begin
        if(reset_n) begin
            memory_cycle=memory_cycle+1;
            model_ready=memory_cycle%11!=0 && memory_cycle>=native_ready_at;
            model_response_valid=0;
            if(blocked_cycles>0) blocked_cycles=blocked_cycles-1;
            else if(queue_head<queue_tail && memory_cycle>=queued_due[queue_head%16384]) begin
                model_response_valid=1;
                response_generation=queued_address[queue_head%16384]>=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE ? 2 : 1;
                response_position=((queued_address[queue_head%16384] & 29'h000fffff)>>3)*16;
                for(integer lane=0;lane<16;lane=lane+1)
                    model_response_data[lane*16+:16]=color565(response_position+lane,response_generation);
                queue_head=queue_head+1;
            end
        end
    end
    always @(posedge memory_clk) begin
        if(reset_n) begin
            if(USE_QUEUES && (model_request || native_write) && model_ready) begin
                if(native_write!=last_command_write)
                    native_ready_at=memory_cycle+WRITE_TURNAROUND_CYCLES;
                last_command_write=native_write;
            end
            if(model_request && model_ready) begin
                if(queue_tail-queue_head==16384) $fatal(1,"response queue capacity");
                queued_address[queue_tail%16384]=model_address;
                queued_due[queue_tail%16384]=memory_cycle+read_latency;
                queue_tail=queue_tail+1;
                if(stall_mode!=0 && !stall_started && dut.fetch_line==3) begin
                    stall_started=1;
                    blocked_cycles=(stall_mode==1 ? 2100 : 15000)*(VIDEO_720P30 ? 3 : VIDEO_720P60 ? 2 : 1);
                end
            end
            if(frame_swap) frame_pending<=0;
            if(native_write) background_writes=background_writes+1;
            if(native_fault) $fatal(1,"native arbiter response fault");
            if(fetch_fault) $fatal(1,"unexpected fetch fault");
            if(dut.outstanding>8 || dut.response_count>8)
                $fatal(1,"response credit overflow");
            if(dut.outstanding>max_scan_credits)max_scan_credits=dut.outstanding;
            if(dut.response_count>max_response_fifo)max_response_fifo=dut.response_count;
            if(dut.active)begin
                fetch_cycles=fetch_cycles+1;
                if(dut.beat_written && dut.received==WIDTH/16-1)begin
                    if(fetch_cycles>max_fetch_cycles)max_fetch_cycles=fetch_cycles;
                    if(dut.request_word[19])begin
                        if(fetch_cycles>max_prefill_line_cycles)max_prefill_line_cycles=fetch_cycles;
                    end else if(fetch_cycles>max_runtime_line_cycles)max_runtime_line_cycles=fetch_cycles;
                    fetch_cycles=0;
                end
            end else fetch_cycles=0;
        end
    end

    reg delayed_de=0,delayed_hsync=0,delayed_vsync=0;
    integer delayed_x=0,delayed_y=0,delayed_generation=1;
    integer colored_lines=0,black_lines=0,checked_pixels=0;
    integer allowed_black=0;
    reg line_black=0;
    reg [23:0] expected_rgb;
    always @(posedge pixel_clk) begin
        #0.001;
        if(reset_n) begin
            if({out_de,out_hsync,out_vsync}!=={delayed_de,delayed_hsync,delayed_vsync})
                $fatal(1,"timing pipeline mismatch");
            if(delayed_de) begin
                if(delayed_x==0) begin
                    line_black=rgb==0;
                    if(line_black) begin
                        black_lines=black_lines+1;
                        if(!allowed_black)begin
                            if(COMPETING_CLIENTS)$display("DIAGNOSTIC rate=%0d window=%0d turnaround=%0d max_fetch_cycles=%0d max_prefill_line_cycles=%0d max_runtime_line_cycles=%0d maxwait_tf=%0d maxwait_delay=%0d maxwait_music=%0d maxwait_display=%0d",SAMPLE_RATE_HZ,SCAN_WRITE_WINDOW,WRITE_TURNAROUND_CYCLES,max_fetch_cycles,max_prefill_line_cycles,max_runtime_line_cycles,audio_max_wait,delay_max_wait,music_max_wait,display_max_wait);
                            $fatal(1,"unexpected black line %0d",delayed_y);
                        end
                    end else colored_lines=colored_lines+1;
                end
                expected_rgb=line_black ? 24'd0 : expand565(color565(delayed_y*WIDTH+delayed_x,delayed_generation));
                if(rgb!==expected_rgb)
                    $fatal(1,"pixel mismatch x=%0d y=%0d got=%h expected=%h",delayed_x,delayed_y,rgb,expected_rgb);
                checked_pixels=checked_pixels+1;
            end
        end
        delayed_de=reset_n && data_enable;
        delayed_hsync=reset_n && hsync;
        delayed_vsync=reset_n && vsync;
        delayed_x=pixel_x;delayed_y=pixel_y;delayed_generation=selected_generation;
    end

    task automatic drive_pixel(input integer column,input integer row,input bit blank_start);
        @(negedge pixel_clk);
        pixel_x=column;pixel_y=row;vblank_start=blank_start;
    endtask
    task automatic run_frame(input integer mode,input integer allow_missing);
        integer previous_pixels,previous_black,previous_colored;
        begin
            stall_mode=mode;stall_started=0;allowed_black=allow_missing;
            previous_pixels=checked_pixels;previous_black=black_lines;previous_colored=colored_lines;
            drive_pixel(0,HEIGHT,1);
            for(integer blank=1;blank<V_BLANK*H_TOTAL;blank=blank+1)
                drive_pixel(blank%H_TOTAL,HEIGHT,0);
            if(!front_valid) $fatal(1,"front frame not published");
            selected_generation=dut.front_base>=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE ? 2 : 1;
            for(integer row=0;row<HEIGHT;row=row+1)
                for(integer column=0;column<H_TOTAL;column=column+1)
                    drive_pixel(column,row,0);
            drive_pixel(0,HEIGHT,0);
            repeat(3) drive_pixel(1,HEIGHT,0);
            if(checked_pixels-previous_pixels!=WIDTH*HEIGHT) $fatal(1,"pixel coverage mismatch");
            if(mode==1 && (black_lines==previous_black || colored_lines==previous_colored))
                $fatal(1,"late response case did not exercise missing and good lines");
        end
    endtask

    integer requested_mode=0;
    integer drain_cycles;
    initial begin
        if(!$value$plusargs("MODE=%d",requested_mode)) requested_mode=0;
        repeat(8) @(negedge memory_clk);
        reset_n=1;
        run_frame(0,0);
        run_frame(0,0);
        if(requested_mode==1) begin
            run_frame(1,1);
            run_frame(0,0);
        end else if(requested_mode==2) begin
            run_frame(2,1);
            run_frame(0,1);
            run_frame(0,0);
        end else begin
            @(negedge memory_clk);frame_base=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE;frame_pending=1;
            run_frame(0,0);
            run_frame(0,0);
            if(selected_generation!=2) $fatal(1,"new frame was not selected");
            if(underruns!=0) $fatal(1,"steady-state underrun count %0d",underruns);
        end
        if(USE_QUEUES && background_writes==0) $fatal(1,"background traffic not exercised");
        // Count real black scanlines from the checked pixel output, then let
        // the pixel counter/Gray CDC settle. This is independent of the DUT's
        // diagnostic predicate and covers missing-line and stale-epoch loss.
        repeat(12) @(negedge memory_clk);
        if(underruns!==32'(black_lines))
            $fatal(1,"diagnostic count differs from actual black output lines count=%0d black=%0d",underruns,black_lines);
        if(COMPETING_CLIENTS)begin
            @(negedge memory_clk);competition_running=0;
            drain_cycles=0;
            while((writer_accepts!=writer_issues || cpu_accepts!=cpu_issues ||
                   audio_accepts!=audio_issues || delay_accepts!=delay_issues ||
                   music_accepts!=music_issues || display_accepts!=display_issues || queue_head<queue_tail) && drain_cycles<10000)begin
                @(negedge memory_clk);#0.001;drain_cycles=drain_cycles+1;
            end
            repeat(4)@(negedge memory_clk);
            if(writer_accepts!=writer_issues || cpu_accepts!=cpu_issues ||
               audio_accepts!=audio_issues || delay_accepts!=delay_issues ||
               music_accepts!=music_issues || display_accepts!=display_issues || queue_head<queue_tail || client_read_inflight!=0)
                $fatal(1,"accepted tail did not drain exactly once");
            if(writer_issues==0 || cpu_issues==0 || audio_issues==0 || delay_issues==0 || music_issues==0 || display_issues==0)
                $fatal(1,"a competing client never reached native issue");
            if(writer_accepts-writer_issues>2 || cpu_accepts-cpu_issues>2 ||
               audio_accepts-audio_issues>2 || delay_accepts-delay_issues>2 ||
               music_accepts-music_issues>2 || display_accepts-display_issues>2)
                $fatal(1,"accepted work exceeded bounded tail");
            if(writer_max_wait>100000 || cpu_max_wait>100000 || audio_max_wait>100000 ||
               delay_max_wait>100000 || music_max_wait>100000 || display_max_wait>100000)
                $fatal(1,"bounded workload pending exceeded tentative 1ms service target");
            $display("COMPETITION rate=%0d window=%0d native_writer=%0d native_cpu=%0d native_tf=%0d native_delay=%0d native_music=%0d native_display=%0d maxwait_writer=%0d maxwait_cpu=%0d maxwait_tf=%0d maxwait_delay=%0d maxwait_music=%0d maxwait_display=%0d writer_tail=%0d cpu_tail=%0d max_fetch_cycles=%0d max_prefill_line_cycles=%0d max_runtime_line_cycles=%0d max_scan_credits=%0d max_response_fifo=%0d max_native_reads=%0d",SAMPLE_RATE_HZ,SCAN_WRITE_WINDOW,writer_issues,cpu_issues,audio_issues,delay_issues,music_issues,display_issues,writer_max_wait,cpu_max_wait,audio_max_wait,delay_max_wait,music_max_wait,display_max_wait,maximum_writer_tail,maximum_cpu_tail,max_fetch_cycles,max_prefill_line_cycles,max_runtime_line_cycles,max_scan_credits,max_response_fifo,max_native_reads);
            $display("LATENCY accepted_to_native_cpu=%0d accepted_to_native_writer=%0d accepted_to_native_tf=%0d accepted_to_native_music=%0d accepted_to_native_delay=%0d accepted_to_native_display=%0d native_to_response_tf=%0d native_to_response_music=%0d native_to_response_delay=%0d native_to_response_display=%0d",max_accept_to_native[2],max_accept_to_native[3],max_accept_to_native[4],max_accept_to_native[5],max_accept_to_native[6],max_accept_to_native[7],max_native_to_response[4],max_native_to_response[5],max_native_to_response[6],max_native_to_response[7]);
        end
        $display("PASS mode=%0d queues=%0d checked_pixels=%0d colored_lines=%0d black_lines=%0d underruns=%0d background_writes=%0d",requested_mode,USE_QUEUES,checked_pixels,colored_lines,black_lines,underruns,background_writes);
        $finish;
    end
    initial begin #(20000000 + ACTIVE_LINES*100000);$fatal(1,"test timeout");end
endmodule
