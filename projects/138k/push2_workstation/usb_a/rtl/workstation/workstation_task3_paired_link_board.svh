    wire [31:0] task3_pair_local_boot,task3_pair_peer_boot,task3_pair_session,task3_pair_generation;
    wire task3_pair_probe_enable,task3_pair_budget_validated,task3_pair_business_enable;
    wire task3_pair_link_ready,task3_pair_panic,task3_pair_record_arm,task3_pair_record_cancel;
    wire task3_pair_tx_valid,task3_pair_tx_ready,task3_pair_rx_valid,task3_pair_rx_ready;
    wire [3:0] task3_pair_tx_channel,task3_pair_rx_channel;
    wire [255:0] task3_pair_tx_payload,task3_pair_rx_payload;
    wire [5:0] task3_pair_tx_length,task3_pair_rx_length;
    wire task3_pair_config_select=psel && paddr[31:12]==20'hf8080;
    wire task3_pair_config_ready,task3_pair_config_error;
    wire [31:0] task3_pair_config_data;
    // This explicit experimental recipe makes the real business cones
    // reachable. All runtime authorizations still reset to zero.
    workstation_task3_paired_link #(.ROLE_M(
`ifdef WORKSTATION_TASK3_M_PAIRED
        1'b1
`else
        1'b0
`endif
    ),.EXPERIMENT_ENABLE(1'b1),.ALLOW_BUSINESS(1'b1)) u_task3_pair_link(
        .clk_i(clk_50m),.reset_ni(reset_n),.external_panic_i(
`ifdef WORKSTATION_TASK3_M_PAIRED
            task3_m_panic
`else
            1'b0
`endif
        ),.pclk(pclk),.preset_n(preset_n),
        .psel(task3_pair_config_select),.penable(penable),.pwrite(pwrite),.paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .pready(task3_pair_config_ready),.pslverr(task3_pair_config_error),.prdata(task3_pair_config_data),
        .local_boot_o(task3_pair_local_boot),.peer_boot_o(task3_pair_peer_boot),.session_o(task3_pair_session),.generation_o(task3_pair_generation),
        .probe_enable_o(task3_pair_probe_enable),.budget_validated_o(task3_pair_budget_validated),.business_enable_o(task3_pair_business_enable),
        .link_ready_o(task3_pair_link_ready),.panic_o(task3_pair_panic),.record_arm_o(task3_pair_record_arm),.record_cancel_o(task3_pair_record_cancel),
        .tx_valid_i(task3_pair_tx_valid),.tx_ready_o(task3_pair_tx_ready),.tx_channel_i(task3_pair_tx_channel),.tx_payload_i(task3_pair_tx_payload),.tx_length_i(task3_pair_tx_length),
        .rx_valid_o(task3_pair_rx_valid),.rx_ready_i(task3_pair_rx_ready),.rx_channel_o(task3_pair_rx_channel),.rx_payload_o(task3_pair_rx_payload),.rx_length_o(task3_pair_rx_length),
        .lcd_r(lcd_r),.lcd_g(lcd_g),.lcd_b(lcd_b),.lcd_pclk(lcd_pclk),.lcd_hsync(lcd_hsync),.lcd_vsync(lcd_vsync),.lcd_de(lcd_de),.lcd_bl(lcd_bl),
        .lcd_ctp_rst(lcd_ctp_rst),.lcd_ctp_sda(lcd_ctp_sda),.lcd_ctp_scl(lcd_ctp_scl),.lcd_ctp_int(lcd_ctp_int));
