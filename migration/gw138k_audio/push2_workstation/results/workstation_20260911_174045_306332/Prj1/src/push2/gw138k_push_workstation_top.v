// USB derivative; source origin hashes in integration/ORIGINS.json.
// Independent C-revision migration candidate. Original Prj1 top is retained.
// G1 MIDI is on a separate expansion pin; BL616 V14 is not reused.
module gw138k_push_workstation_top (
    inout wire usb1_dp,usb1_dn,
    input wire clk_50m,
    input wire button1_n,
    input wire midi_rx_i,
    input wire pc_uart_rx_i,
    output wire hp_bck,
    output wire hp_ws,
    output wire hp_din,
    output wire pa_en,
    output wire debug_uart_tx,
    output wire hdmi_tx_en,
    input wire hdmi_hpd,
    output wire tmds_clk_p,
    output wire tmds_clk_n,
    output wire [2:0] tmds_data_p,
    output wire [2:0] tmds_data_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs,ddr_ras,ddr_cas,ddr_we,ddr_ck,ddr_ck_n,ddr_cke,ddr_odt,ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs,ddr_dqs_n
);
    wire reset_n;
    reset_release u_reset(.clk(clk_50m),.ext_reset_n(button1_n),.reset_n(reset_n));
    wire audio_clk,audio_reset_n,audio_locked;
    gw138k_audio_clock u_audio_clock(.clk_50m(clk_50m),.reset_n(reset_n),
        .audio_clk(audio_clk),.audio_reset_n(audio_reset_n),.pll_locked(audio_locked));
    wire usb_clk,usb_locked;
    gw138k_cpu_pll_cell #(.OUTPUT_DIV0(25),.OUTPUT1_ENABLE("FALSE")) u_usb_pll(
        .clkin(clk_50m),.init_clk(clk_50m),.reset(!reset_n),.enable0(1'b1),
        .lock(usb_locked),.clkout0(usb_clk),.clkout1());
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] usb_release=0;
    wire usb_qualified=reset_n && usb_locked;
    always @(posedge usb_clk or negedge usb_qualified)
        if(!usb_qualified)usb_release<=0;else usb_release<={usb_release[2:0],1'b1};
    wire usb_reset_n=usb_release[3];
    wire mmio_select,mmio_write,mmio_ready;
    wire [7:0] mmio_address;wire [31:0] mmio_wdata,mmio_rdata;
    wire [223:0] usb_words;
    iosys2 u_usb_host(.clk(usb_clk),.resetn(usb_reset_n),.uart_rx(1'b1),.uart_tx(),
        .usb_dp(usb1_dp),.usb_dm(usb1_dn),.mmio_select(mmio_select),.mmio_write(mmio_write),
        .mmio_address(mmio_address),.mmio_wdata(mmio_wdata),.mmio_ready(mmio_ready),.mmio_rdata(mmio_rdata));
    wire [31:0] output_pcm,output_reference,active_voices,display_status;
    wire [2:0] effect_mask;
    wire output_sample_valid;
    wire audio_sample_valid;
    wire memory_clk,memory_reset_n,memory_calibrated,memory_pll_locked;
    wire pclk,preset_n,psel,penable,pwrite;
    wire [31:0] paddr,pwdata,service_data;
    wire [3:0] pstrb;
    wire service_ready,service_error;
    wire ui_select=psel && paddr[31:12]==20'hf8020;
    wire ui_ready,ui_error;
    wire [31:0] ui_read_data;
    wire ui_command_reset_n,ui_command_valid,ui_command_ready,ui_command_write,ui_response_error;
    wire [11:0] ui_command_address;
    wire [31:0] ui_command_data,ui_response_data;
    wire [3:0] ui_command_strobes;
    wire ui_pending,ui_visible,ui_next_visible,ui_frame_commit;
    wire [28:0] ui_front_base,ui_next_base;
    gw138k_apb_cdc u_ui_control(.reset_n(preset_n && memory_reset_n),.pclk(pclk),.audio_clk(memory_clk),
        .psel(ui_select),.penable(penable),.pwrite(pwrite),.paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .pready(ui_ready),.pslverr(ui_error),.prdata(ui_read_data),.command_reset_n(ui_command_reset_n),
        .command_valid(ui_command_valid),.command_ready(ui_command_ready),.command_write(ui_command_write),
        .command_address(ui_command_address),.command_data(ui_command_data),.command_strobes(ui_command_strobes),
        .response_data(ui_response_data),.response_error(ui_response_error));
    gw138k_ui_services u_ui_services(.clk(memory_clk),.reset_n(ui_command_reset_n),
        // No touchscreen is attached. A future verified board input adapter
        // supplies logical 800x480 events in memory_clk, independently of audio.
        .input_attached(1'b0),.input_valid(1'b0),.input_down(1'b0),.input_x(16'd0),.input_y(16'd0),
        .command_valid(ui_command_valid),.command_ready(ui_command_ready),.command_write(ui_command_write),
        .command_address(ui_command_address),.command_data(ui_command_data),.command_strobes(ui_command_strobes),
        .response_data(ui_response_data),.response_error(ui_response_error),.frame_commit(ui_frame_commit),
        .pending(ui_pending),.visible(ui_visible),.next_visible(ui_next_visible),.front_base(ui_front_base),.next_base(ui_next_base));
    wire service_select=psel && paddr[31:12]==20'hf8010;
    wire [447:0] performance_words;
    wire all_usb_valid,all_usb_ready;wire [17:0] all_usb_event;
    wire [447:0] push_snapshot;
    push2_usb_a_control u_push(.clk(usb_clk),.reset_n(usb_reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .feedback_clk(clk_50m),.feedback_reset_n(reset_n),.performance_words(push_snapshot),
        .select(mmio_select),.write(mmio_write),.address(mmio_address),.wdata(mmio_wdata),.ready(mmio_ready),.rdata(mmio_rdata),
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.telemetry(usb_words));
    gw138k_usb_controlled_audio u_managed(
        .usb_event_valid(all_usb_valid),.usb_event_ready(all_usb_ready),.usb_event_data(all_usb_event),
        .pc_uart_rx_i(pc_uart_rx_i),.performance_words_o(performance_words),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(audio_reset_n),.midi_rx_i(midi_rx_i),
        .pclk(pclk),.preset_n(preset_n),.psel(service_select),.penable(penable),.pwrite(pwrite),
        .paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .prdata(service_data),.pready(service_ready),.pslverr(service_error),
        .hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .sample_valid_o(audio_sample_valid),
        .display_valid_o(output_sample_valid),.display_pcm_o(output_pcm),.display_reference_o(output_reference),
        .display_voices_o(active_voices),.display_status_o(display_status),.effect_mask_o(effect_mask));
    wire signed [16:0] output_mid_pcm=$signed({output_pcm[31],output_pcm[31:16]})+
                                            $signed({output_pcm[15],output_pcm[15:0]});
    wire signed [31:0] output_mid={output_mid_pcm,15'd0};
    wire [7:0] memory_flags;
    wire [127:0] video_diagnostics;
    gw138k_push_performance_uart u_runtime(
        .push_words(224'd0),.performance_feedback(push_snapshot),
        .usb_clk(usb_clk),.usb_reset_n(usb_reset_n),.usb_words(usb_words),
        .performance_words(performance_words),
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .audio_locked(audio_locked),.sample_valid(audio_sample_valid),.memory_flags(memory_flags),
        .audio_status(display_status),.video_diagnostics(video_diagnostics),.serial_out(debug_uart_tx),
        .cpu_clk(pclk),.cpu_reset_n(preset_n),.cpu_words({trap_cause,heartbeat,ram_result,signature,last_fetch,fetch_count,ui_report}));
    assign hdmi_tx_en = 1'b1;
    wire [2:0] app_cmd;
    wire app_en,app_rdy,app_wren,app_wend,app_wrdy,app_rvalid;
    wire [28:0] app_addr;
    wire [255:0] app_wdata,app_rdata;
    wire [31:0] app_wmask;
    ddr3_platform u_memory (
        .clk_50m(clk_50m),.rst_n(reset_n),.ui_clk(memory_clk),.ui_rst_n(memory_reset_n),
        .calib_done(memory_calibrated),.pll_locked(memory_pll_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wend),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.app_rend(),
        .ddr_addr(ddr_addr),.ddr_bank(ddr_bank),.ddr_cs(ddr_cs),.ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas),.ddr_we(ddr_we),.ddr_ck(ddr_ck),.ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke),.ddr_odt(ddr_odt),.ddr_reset_n(ddr_reset_n),.ddr_dm(ddr_dm),
        .ddr_dq(ddr_dq),.ddr_dqs(ddr_dqs),.ddr_dqs_n(ddr_dqs_n)
    );
    wire cpu_mem_req,cpu_mem_write,cpu_mem_ready,cpu_mem_response;
    wire [28:0] cpu_mem_address;
    wire [255:0] cpu_mem_data;
    wire [31:0] cpu_mem_mask;
    hdmi_display u_video (
        .ui_pending(ui_pending),.ui_visible(ui_visible),.ui_next_visible(ui_next_visible),
        .ui_front_base(ui_front_base),.ui_next_base(ui_next_base),.ui_frame_commit(ui_frame_commit),
        .cpu_req(cpu_mem_req),.cpu_write(cpu_mem_write),.cpu_address(cpu_mem_address),
        .cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),
        .clk_50m(clk_50m), .reset_n(reset_n),
        .hdmi_hpd(hdmi_hpd),.video_diagnostics(video_diagnostics),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.memory_pll_locked(memory_pll_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wend),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),
        .sample_data(output_mid), .sample_valid(output_sample_valid),.output_pcm(output_pcm),
        .trigger_reference(output_reference),
        .active_voices(active_voices), .status_data(display_status), .effect_mask(effect_mask),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n)
    );
    wire core_clk,bus_clk,pll_locked;
    wire system_reset_n=reset_n;
    gw138k_cpu_pll_cell u_cpu_pll(.clkin(clk_50m),.init_clk(clk_50m),.reset(!system_reset_n),
        .enable0(1'b1),.lock(pll_locked),.clkout0(bus_clk),.clkout1(core_clk));
    reg [16:0] lock_count=0;
    reg lock_qualified=0;
    // DDR loss restarts only the CPU/control path. Audio remains independent.
    wire cpu_memory_ready=memory_flags[1:0]==2'b11 && memory_flags[6] && !memory_flags[2];
    wire ready_async=system_reset_n && pll_locked && cpu_memory_ready;
    always @(posedge clk_50m or negedge ready_async)
        if(!ready_async) begin lock_count<=0;lock_qualified<=0;end
        else if(!lock_qualified) begin
            if(lock_count==17'd100000) lock_qualified<=1;
            else lock_count<=lock_count+1'b1;
        end
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] core_reset_pipe=0;
    always @(posedge core_clk or negedge lock_qualified)
        if(!lock_qualified) core_reset_pipe<=0;
        else core_reset_pipe<={core_reset_pipe[2:0],1'b1};
    wire cpu_reset_n=core_reset_pipe[3];
    wire rom_clk,rom_reset_n,rom_write;
    wire [31:0] rom_address,rom_read_data,fetch_count,last_fetch;
    wire [1:0] rom_transfer;
    wire ram_clk,ram_reset_n,ram_write;
    wire [31:0] ram_address;
    wire [63:0] ram_read_data,ram_write_data;
    wire [1:0] ram_transfer;
    wire [2:0] ram_size;
    wire [63:0] external_read_data;
    wire cpu_bus_ready,cpu_bus_error;
    wire local_address=ram_address[31:13]==0 && (ram_size==0 ||
        (ram_size==1 && !ram_address[0]) || (ram_size==2 && ram_address[1:0]==0) ||
        (ram_size==3 && ram_address[2:0]==0));
    reg local_data_phase;
    always @(posedge ram_clk or negedge ram_reset_n)
        if(!ram_reset_n) local_data_phase<=1;
        else if(cpu_bus_ready) local_data_phase<=local_address;
    gw138k_ahb_ddr u_cpu_ddr(.reset_n(ram_reset_n),.hclk(ram_clk),.memory_clk(memory_clk),
        .haddr(ram_address),.htrans(local_address?2'b00:ram_transfer),.hsize(ram_size),
        .hwrite(ram_write),.hwdata(ram_write_data),.hrdata(external_read_data),.hready(cpu_bus_ready),.hresp(cpu_bus_error),
        .req_valid(cpu_mem_req),.req_write(cpu_mem_write),.req_address(cpu_mem_address),
        .req_data(cpu_mem_data),.req_mask(cpu_mem_mask),.req_ready(cpu_mem_ready),
        .rsp_valid(cpu_mem_response),.rsp_data(app_rdata));
    reg [31:0] signature,ram_result,heartbeat,trap_cause,trap_pc,ui_report;
    wire valid_word=paddr[31:12]==20'hf8000 && paddr[1:0]==0 && pstrb==4'hf;
    always @(posedge pclk or negedge preset_n) begin
        if(!preset_n) begin signature<=0;ram_result<=0;heartbeat<=0;trap_cause<=0;trap_pc<=0;ui_report<=3;end
        else if(psel && penable && pwrite && valid_word) case(paddr[11:0])
            0:signature<=pwdata;
            4:ram_result<=pwdata;
            8:heartbeat<=pwdata;
            12:trap_cause<=pwdata;
            16:trap_pc<=pwdata;
            20:ui_report<=pwdata;
            default:begin end
        endcase
    end
    gw138k_boot_memory u_boot_memory(.rom_clk(rom_clk),.rom_reset_n(rom_reset_n),.rom_address(rom_address),
        .rom_transfer(rom_transfer),.rom_data(rom_read_data),.fetch_count(fetch_count),.last_fetch(last_fetch),
        .ram_clk(ram_clk),.ram_reset_n(ram_reset_n),.ram_address(ram_address),.ram_transfer((cpu_bus_ready && local_address)?ram_transfer:2'b00),
        .ram_size(ram_size),.ram_write(ram_write),.ram_write_data(ram_write_data),.ram_read_data(ram_read_data));
    RiscV_AE350_SOC_Top u_cpu (
        .ROM_HRDATA(rom_read_data),.ROM_HREADY(1'b1),.ROM_HRESP(1'b0),.ROM_HADDR(rom_address),
        .ROM_HTRANS(rom_transfer),.ROM_HWRITE(rom_write),.ROM_HCLK(rom_clk),.ROM_HRSTN(rom_reset_n),
        .DDR_HRDATA(local_data_phase?ram_read_data:external_read_data),.DDR_HREADY(cpu_bus_ready),.DDR_HRESP(cpu_bus_error),.DDR_HADDR(ram_address),
        .DDR_HBURST(),.DDR_HPROT(),.DDR_HSIZE(ram_size),.DDR_HTRANS(ram_transfer),
        .DDR_HWDATA(ram_write_data),.DDR_HWRITE(ram_write),.DDR_HCLK(ram_clk),.DDR_HRSTN(ram_reset_n),
        .APB_PRDATA(service_select?service_data:ui_select?ui_read_data:32'h41313338),.APB_PREADY(service_select?service_ready:ui_select?ui_ready:1'b1),.APB_PSLVERR(service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
        .APB_PENABLE(penable),.APB_PSEL(psel),.APB_PWDATA(pwdata),.APB_PWRITE(pwrite),
        .APB_PPROT(),.APB_PSTRB(pstrb),.APB_PCLK(pclk),.APB_PRSTN(preset_n),
        .TCK_IN(1'b0),.TMS_IN(1'b1),.TRST_IN(1'b1),.TDI_IN(1'b0),.TDO_OUT(),.TDO_OE(),
        .CORE0_WFI_MODE(),.RTC_WAKEUP(),
        .CORE_CLK(core_clk),.DDR_CLK(bus_clk),.AHB_CLK(bus_clk),.APB_CLK(bus_clk),.RTC_CLK(clk_50m),
        .POR_RSTN(cpu_reset_n),.HW_RSTN(cpu_reset_n));
endmodule
