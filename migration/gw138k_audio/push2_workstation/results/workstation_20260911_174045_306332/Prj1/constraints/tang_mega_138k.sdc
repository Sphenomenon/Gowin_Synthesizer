# Common 50MHz oscillator; Gowin derives the DDR and video PLL clocks.
create_clock -name clk_50m -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50m}]
# 50 * 24 / (15 + 5/8) = 76.8 MHz; PT8211 uses 1600 clocks/frame.
create_generated_clock -name audio_76m8 -source [get_ports {clk_50m}] -master_clock clk_50m -multiply_by 192 -divide_by 125 [get_pins {u_audio_clock/g_hardware.u_pll/PLL_inst/CLKOUT0}]
# Name the PHY clocks explicitly. CLKOUT2 is 50*16/2 MHz and CLKDIV is /4.
# These are related clocks; preserve the DDR IP's working setup/hold paths.
create_generated_clock -name ddr_mem400 -source [get_ports {clk_50m}] -master_clock clk_50m -multiply_by 8 [get_pins {u_memory/u_pll/u_pll_0/PLL_inst/CLKOUT2}]
create_generated_clock -name ddr_ui100 -source [get_pins {u_memory/u_pll/u_pll_0/PLL_inst/CLKOUT2}] -master_clock ddr_mem400 -divide_by 4 [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT}]
# Preserve the actual two-PLL cascade and dedicated HCLK /5 topology.
create_generated_clock -name video_ref49 -source [get_ports {clk_50m}] -master_clock clk_50m -multiply_by 99 -divide_by 100 [get_pins {u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst/CLKOUT0}]
create_generated_clock -name video_serial742 -source [get_pins {u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst/CLKOUT0}] -master_clock video_ref49 -multiply_by 15 [get_pins {u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst/CLKOUT0}]
create_generated_clock -name video_pixel148 -source [get_pins {u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst/CLKOUT0}] -master_clock video_serial742 -divide_by 5 [get_pins {u_video/u_clock/g_hardware.u_pll/u_pixel_div/CLKOUT}]
set_false_path -from [get_ports {midi_rx_i}]
set_false_path -from [get_ports {button1_n}]
# Capture bank + metadata stays frozen until render completion ACK.
# req_meta -> req_sync -> req_settled -> capture: >=30ns at 100MHz.
set_max_delay 20.000 -from [get_regs {u_video/u_renderer/u_capture/held_*}] -to [get_regs {u_video/u_renderer/u_capture/snapshot_* u_video/u_renderer/u_capture/render_bank*}]
set_false_path -hold -from [get_regs {u_video/u_renderer/u_capture/held_*}] -to [get_regs {u_video/u_renderer/u_capture/snapshot_* u_video/u_renderer/u_capture/render_bank*}]
set_false_path -to [get_pins {u_video/u_renderer/u_capture/req_meta_s0/D}]
set_false_path -to [get_pins {u_video/u_renderer/u_capture/ack_meta_s0/D}]
set_false_path -hold -to [get_pins {u_video/u_renderer/g_analysis.u_analysis/u_capture/ack_meta_s0/D}]
# Pixel -> DDR request mailbox, stable until all requested read data arrives.
set_max_delay 20.000 -from [get_regs {u_video/u_scanout/held_request*}] -to [get_regs {u_video/u_scanout/request_word*}]
set_false_path -hold -from [get_regs {u_video/u_scanout/held_request*}] -to [get_regs {u_video/u_scanout/request_word*}]
# Completed line tags stay fixed until the line's bank is reused.
set_max_delay 12.000 -from [get_regs {u_video/u_scanout/done0_tag* u_video/u_scanout/done1_tag*}] -to [get_regs {u_video/u_scanout/tag0* u_video/u_scanout/tag1*}]
set_false_path -hold -from [get_regs {u_video/u_scanout/done0_tag* u_video/u_scanout/done1_tag*}] -to [get_regs {u_video/u_scanout/tag0* u_video/u_scanout/tag1*}]
set_false_path -to [get_pins {u_video/u_scanout/request_meta_s0/D}]
set_false_path -to [get_pins {u_video/u_scanout/ack_meta_s0/D}]
set_false_path -to [get_pins {u_video/u_scanout/done0_meta_s0/D}]
set_false_path -to [get_pins {u_video/u_scanout/done1_meta_s0/D}]
# The Gray counter changes at most once/line (14.815 us), not once/pixel.
# Gowin includes source clock latency in max_delay; 20 ns leaves >700x margin
# to the minimum update interval. Gray conversion is registered separately.
set_max_delay 20.000 -from [get_regs {u_video/u_scanout/under_gray*}] -to [get_regs {u_video/u_scanout/under_meta*}]
set_false_path -hold -from [get_regs {u_video/u_scanout/under_gray*}] -to [get_regs {u_video/u_scanout/under_meta*}]
# Independent slow flags; only first-stage sampling is asynchronous.
# Read-only UART now consumes the memory status synchronizer.
set_false_path -to [get_pins {u_video/flags_meta*/D}]
# Runtime telemetry: source-registered Gray changes no faster than 1024
# pixel clocks (6.896 us). Bound inter-bit flight to 20 ns and retain both
# destination synchronizer stages under normal 50 MHz setup/hold analysis.
set_max_delay 20.000 -from [get_regs {u_video/u_diagnostics/pixel_block_gray*}] -to [get_regs {u_video/u_diagnostics/pixel_block_meta*}]
set_false_path -hold -from [get_regs {u_video/u_diagnostics/pixel_block_gray*}] -to [get_regs {u_video/u_diagnostics/pixel_block_meta*}]
set_max_delay 20.000 -from [get_regs {u_video/u_diagnostics/pixel_frame_gray*}] -to [get_regs {u_video/u_diagnostics/pixel_frame_meta*}]
set_false_path -hold -from [get_regs {u_video/u_diagnostics/pixel_frame_gray*}] -to [get_regs {u_video/u_diagnostics/pixel_frame_meta*}]
set_max_delay 20.000 -from [get_regs {u_video/u_diagnostics/memory_rendered_gray*}] -to [get_regs {u_video/u_diagnostics/memory_rendered_meta*}]
set_false_path -hold -from [get_regs {u_video/u_diagnostics/memory_rendered_gray*}] -to [get_regs {u_video/u_diagnostics/memory_rendered_meta*}]
set_max_delay 20.000 -from [get_regs {u_video/u_diagnostics/memory_underrun_gray*}] -to [get_regs {u_video/u_diagnostics/memory_underrun_meta*}]
set_false_path -hold -from [get_regs {u_video/u_diagnostics/memory_underrun_gray*}] -to [get_regs {u_video/u_diagnostics/memory_underrun_meta*}]
set_false_path -to [get_pins {u_video/u_diagnostics/flags_meta*/D}]
# Telemetry retains all three reset-release synchronizers. Only their async
# entry pins are excluded; each release stage and downstream consumer stays timed.
set_false_path -to [get_pins {u_video/u_diagnostics/pixel_global_reset_pipe*/CLEAR u_video/u_diagnostics/pixel_ready_pipe*/CLEAR u_video/u_diagnostics/memory_ready_pipe*/CLEAR}]
set_false_path -to [get_pins {u_memory/u_recovery/calibrated_meta*/D}]
set_false_path -to [get_pins {u_memory/u_recovery/lock_observed*/CLEAR u_memory/u_recovery/health_observed*/CLEAR}]
# Async reset entry points of reset-release synchronizers. Their outputs and
# all downstream reset distribution remain timed in each destination domain.
set_false_path -to [get_pins {u_video/ui_reset_pipe*/CLEAR u_video/source_reset_pipe*/CLEAR u_video/pixel_reset_pipe*/CLEAR u_video/u_clock/pixel_reset_pipe*/CLEAR u_memory/ui_reset_sync*/CLEAR}]
# Both PLL2 output clocks are stopped during reset release. The 50MHz
# startup sequence waits 80ns before ENCLK0 enables FCLK (UG306 dynamic gate).
# The VO/SDF audit in check_build.py bounds every real reset route to 40ns.
# Gowin max_delay does not override recovery here; exclude inactive edges.
set_false_path -to [get_pins {u_video/u_clock/g_hardware.u_pll/u_startup/startup_pipe*/CLEAR u_video/u_clock/g_hardware.u_pll/u_startup/serializer_reset*/PRESET}]
set_false_path -to [get_pins {u_video/u_clock/g_hardware.u_pll/u_pixel_div/RESETN}]
set_false_path -to [get_pins {u_video/u_dvi/*/tmds_serdes_inst0/RESET}]
# Official gw5a prim_sim.v IDES8_MEM samples CALIB through calib_0/1/2
# in FCLK; only calib_1 & ~calib_2 acts. Cut this built-in sync entry only.
set_false_path -from [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*/u_ddr_phy_data_io/ides_calib_d*/Q}] -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*/u_ddr_phy_data_io/*u_ides8_mem/CALIB}]
# Reference DDR .vo has clk50 recalib_s[0] -> recalib_s[1] synchronizer.
# Keep its second stage and all PHY payload timing analyzed.
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/ddr_sync/recalib_s_0_s0/D}]
# The audited C-IP FSM stops memory_clk 160ns before releasing this reset,
# then waits 80ns before restarting it. check_build.py independently verifies
# all actual reset routes in VO/SDF within 40ns of this stopped-clock window.
# Reproduce the source/hash/108-cell audit: scripts/audit_ddr_reset_sequence.py.
# Endpoint-only cuts are required for Gowin recovery/removal exceptions.
# The independent audit checks the unique source and each active WDS RESET.
# Select IO primitive groups, excluding constant-reset SDPB cells.
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*u_dqs/RESET}]
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*u_dqs_gen/RESET}]
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*u_oser8_mem/RESET}]
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*u_ides8_mem/RESET}]
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*u_cmd_gen/RESET}]
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/u_ddr_phy_cmd_lane/u_ddr_phy_cmd_io/u_ck_gen/RESET}]
# These eight falling-edge UI registers share the same stopped-clock reset.
# They are checked against the same 40ns routed distribution budget.
set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_init/*rburst_neg*/CLEAR}]
# UPDNCNTL freezes DLL STEP at least 620ns before the one-time UI capture.
# Endpoint-only budget includes the full DLL CLKIN -> STEP -> D arc;
# the routed-netlist audit checks the eight D pins' unique DLL STEP source.
set_max_delay 40.000 -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/dll_step_base*/D}]
set_false_path -hold -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/dll_step_base*/D}]
# Official DQS timing models sample HOLD on PCLK (100MHz), not FCLK.
# Preserve a single PCLK-period setup budget and retain its hold checks.
set_max_delay 10.000 -from [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_init/*/Q}] -to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_phy_wds/*/u_dqs/HOLD}]
# Keep synchronous pixel/UI critical paths visible beside CDC reports.
report_timing -setup -max_paths 50
report_timing -setup -from_clock [get_clocks {video_pixel148}] -to_clock [get_clocks {video_pixel148}] -max_paths 25
report_timing -setup -from_clock [get_clocks {ddr_ui100}] -to_clock [get_clocks {ddr_ui100}] -max_paths 25

# Audio PLL qualification/reset release entry points only. Keep synchronous
# downstream reset distribution and both clocks under ordinary STA.
set_false_path -to [get_pins {u_audio_clock/audio_reset_pipe*/CLEAR}]
set_false_path -to [get_pins {u_managed/u_audio/reset_50_pipe*/CLEAR u_managed/u_audio/reset_audio_pipe*/CLEAR u_managed/u_midi_drop_cdc/source_release*/CLEAR u_managed/u_midi_drop_cdc/destination_release*/CLEAR}]
# MIDI and final-PCM held-word mailboxes: source freezes payload through ACK;
# req_meta -> req_sync -> req_settled -> capture gives >=3 destination periods.
# 20ns is less than 3*13.020833ns and 3*20ns respectively.
set_max_delay 20.000 -from [get_regs {u_managed/u_audio/u_midi_cdc/held_data*}] -to [get_regs {u_managed/u_audio/u_midi_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_managed/u_audio/u_midi_cdc/held_data*}] -to [get_regs {u_managed/u_audio/u_midi_cdc/destination_data*}]
set_max_delay 20.000 -from [get_regs {u_managed/u_audio/u_display_cdc/held_data*}] -to [get_regs {u_managed/u_audio/u_display_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_managed/u_audio/u_display_cdc/held_data*}] -to [get_regs {u_managed/u_audio/u_display_cdc/destination_data*}]
set_false_path -to [get_pins {u_managed/u_audio/u_midi_cdc/req_meta*/D u_managed/u_audio/u_midi_cdc/ack_meta*/D u_managed/u_audio/u_display_cdc/req_meta*/D u_managed/u_audio/u_display_cdc/ack_meta*/D}]
set_false_path -to [get_pins {u_managed/effect_mask_meta*/D u_managed/effect_order_meta*/D}]
set_false_path -to [get_pins {u_managed/effect_mask_sync*/RESET u_managed/effect_mask_meta*/RESET}]
# Identical mailbox release pipelines are merged into u_managed/u_audio/reset_50_pipe
# and reset_audio_pipe by synthesis; the surviving entry points are above.
report_timing -setup -from_clock [get_clocks {audio_76m8}] -to_clock [get_clocks {audio_76m8}] -max_paths 25
# Audio count is source-registered Gray, advancing once per 20.833us sample.
# Bound each bit's flight to far less than the update interval; retain both
# 50MHz synchronizer stages. Reset discontinuities are qualified by flags.
set_max_delay 20.000 -from [get_regs {u_runtime/sample_gray*}] -to [get_regs {u_runtime/sample_meta*}]
set_false_path -hold -from [get_regs {u_runtime/sample_gray*}] -to [get_regs {u_runtime/sample_meta*}]
set_false_path -to [get_pins {u_runtime/flags_meta*/D}]

create_generated_clock -name cpu_bus50 -source [get_ports {clk_50m}] -master_clock clk_50m -multiply_by 1 [get_pins {u_cpu_pll/PLL_inst/CLKOUT0}]
create_generated_clock -name cpu_core100 -source [get_ports {clk_50m}] -master_clock clk_50m -multiply_by 2 [get_pins {u_cpu_pll/PLL_inst/CLKOUT1}]
set_false_path -to [get_pins {core_reset_pipe*/CLEAR}]
# Ask place/route to shorten the analogue PLL helper control paths. The
# independent VO/SDF audit still includes input-clock flight and enforces 10ns.
# Control reset synchronizer async entries; synchronous consumers stay timed.
set_false_path -to [get_pins {u_managed/u_control_cdc/p_release*/CLEAR u_managed/u_control_cdc/a_release*/CLEAR u_runtime/u_cpu_cdc/source_release*/CLEAR u_runtime/u_cpu_cdc/destination_release*/CLEAR}]
set_false_path -to [get_pins {u_managed/u_control_cdc/req_meta*/D u_managed/u_control_cdc/ack_meta*/D u_runtime/u_cpu_cdc/req_meta*/D u_runtime/u_cpu_cdc/ack_meta*/D}]
# APB payload is held for the complete request/response round trip.
# Decode follows an audio-domain capture register; time both stages separately.
set_max_delay 20.000 -from [get_regs {u_managed/u_control_cdc/request_held*}] -to [get_regs {u_managed/u_control_cdc/request_local*}]
set_false_path -hold -from [get_regs {u_managed/u_control_cdc/request_held*}] -to [get_regs {u_managed/u_control_cdc/request_local*}]
set_max_delay 20.000 -from [get_regs {u_managed/u_control_cdc/response_held*}] -to [get_regs {u_managed/u_control_cdc/response_local*}]
set_false_path -hold -from [get_regs {u_managed/u_control_cdc/response_held*}] -to [get_regs {u_managed/u_control_cdc/response_local*}]
set_max_delay 20.000 -from [get_regs {u_runtime/u_cpu_cdc/held_data*}] -to [get_regs {u_runtime/u_cpu_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_runtime/u_cpu_cdc/held_data*}] -to [get_regs {u_runtime/u_cpu_cdc/destination_data*}]
# MIDI-drop source increments no faster than 320us. Do not sample its binary
# bus across domains; source-registered Gray plus two destination stages.
set_max_delay 20.000 -from [get_regs {u_managed/u_midi_drop_cdc/gray*}] -to [get_regs {u_managed/u_midi_drop_cdc/meta*}]
set_false_path -hold -from [get_regs {u_managed/u_midi_drop_cdc/gray*}] -to [get_regs {u_managed/u_midi_drop_cdc/meta*}]

# CPU 64-bit AHB to native DDR mailbox: held across the entire round trip.
set_false_path -to [get_pins {u_cpu_ddr/h_release*/CLEAR u_cpu_ddr/m_release*/CLEAR}]
set_false_path -to [get_pins {u_cpu_ddr/req_meta*/D u_cpu_ddr/ack_meta*/D}]
set_max_delay 20.000 -from [get_regs {u_cpu_ddr/request_held*}] -to [get_regs {u_cpu_ddr/request_local*}]
set_false_path -hold -from [get_regs {u_cpu_ddr/request_held*}] -to [get_regs {u_cpu_ddr/request_local*}]
set_max_delay 20.000 -from [get_regs {u_cpu_ddr/response_held*}] -to [get_regs {u_cpu_ddr/response_local*}]
set_false_path -hold -from [get_regs {u_cpu_ddr/response_held*}] -to [get_regs {u_cpu_ddr/response_local*}]

# APB UI presentation mailbox, CPU bus50 -> DDR ui100. Frame publication is
# queued and completes at the scanout frame boundary; audio is not involved.
set_false_path -to [get_pins {u_ui_control/p_release*/CLEAR u_ui_control/a_release*/CLEAR}]
set_false_path -to [get_pins {u_ui_control/req_meta*/D u_ui_control/ack_meta*/D}]
set_max_delay 20.000 -from [get_regs {u_ui_control/request_held*}] -to [get_regs {u_ui_control/request_local*}]
set_false_path -hold -from [get_regs {u_ui_control/request_held*}] -to [get_regs {u_ui_control/request_local*}]
set_max_delay 20.000 -from [get_regs {u_ui_control/response_held*}] -to [get_regs {u_ui_control/response_local*}]
set_false_path -hold -from [get_regs {u_ui_control/response_held*}] -to [get_regs {u_ui_control/response_local*}]

# PC mailbox release chains merge with the adapter reset_50/audio chains,
# whose actual entry CLEAR pins are already constrained in workstation.sdc.
# Independent PC MIDI receiver: V14 / 115200, G1 remains P16 / 31250.
set_false_path -to [get_pins {u_managed/u_audio/u_pc_rx/rx_sync_0*/D}]
set_false_path -to [get_pins {u_managed/u_audio/u_pc_cdc/req_meta*/D u_managed/u_audio/u_pc_cdc/ack_meta*/D u_managed/u_audio/pc_health_meta*/D}]
set_max_delay 20.000 -from [get_regs {u_managed/u_audio/u_pc_cdc/held_data*}] -to [get_regs {u_managed/u_audio/u_pc_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_managed/u_audio/u_pc_cdc/held_data*}] -to [get_regs {u_managed/u_audio/u_pc_cdc/destination_data*}]
set_false_path -to [get_pins {u_runtime/u_performance_cdc/source_release*/CLEAR u_runtime/u_performance_cdc/destination_release*/CLEAR u_runtime/u_performance_cdc/req_meta*/D u_runtime/u_performance_cdc/ack_meta*/D}]
set_max_delay 20.000 -from [get_regs {u_runtime/u_performance_cdc/held_data*}] -to [get_regs {u_runtime/u_performance_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_runtime/u_performance_cdc/held_data*}] -to [get_regs {u_runtime/u_performance_cdc/destination_data*}]

# A separate integer 1200MHz /25 PLL output: exact 48MHz for 12Mbps FS.
create_generated_clock -name usb_48m -source [get_ports {clk_50m}] -master_clock clk_50m -multiply_by 24 -divide_by 25 [get_pins {u_usb_pll/PLL_inst/CLKOUT0}]
# Board reset and USB input enter explicit reset / two-stage synchronizers.
set_false_path -to [get_pins {usb_release*/CLEAR}]
set_false_path -from [get_ports {usb1_dp usb1_dn}]
# Telemetry mailbox, stable until its ACK completes. Audio never waits for it.
set_max_delay 20.000 -from [get_regs {u_runtime/u_usb_cdc/held_data*}] -to [get_regs {u_runtime/u_usb_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_runtime/u_usb_cdc/held_data*}] -to [get_regs {u_runtime/u_usb_cdc/destination_data*}]
set_false_path -to [get_pins {u_runtime/u_usb_cdc/req_meta*/D u_runtime/u_usb_cdc/ack_meta*/D}]
set_false_path -to [get_pins {u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR}]
# Gray pointer FIFO boundaries are named after inspecting the generated RTL.
# Bound each pointer bit flight below both clock periods; retain all later
# synchronizer stages and all synchronous USB/audio logic in ordinary STA.
set_max_delay 10.000 -from [get_regs {u_usb_host/u_fifo/fifo/unbuffered/produce_w_gry*}] -to [get_regs {u_usb_host/u_fifo/fifo/unbuffered/produce_cdc/stage0*}]
set_false_path -hold -from [get_regs {u_usb_host/u_fifo/fifo/unbuffered/produce_w_gry*}] -to [get_regs {u_usb_host/u_fifo/fifo/unbuffered/produce_cdc/stage0*}]
set_max_delay 10.000 -from [get_regs {u_usb_host/u_fifo/fifo/unbuffered/consume_r_gry*}] -to [get_regs {u_usb_host/u_fifo/fifo/unbuffered/consume_cdc/stage0*}]
set_false_path -hold -from [get_regs {u_usb_host/u_fifo/fifo/unbuffered/consume_r_gry*}] -to [get_regs {u_usb_host/u_fifo/fifo/unbuffered/consume_cdc/stage0*}]
report_timing -setup -from_clock [get_clocks {usb_48m}] -to_clock [get_clocks {usb_48m}] -max_paths 25

# CH569 HSPI16 source synchronous return: CPU/HSPI clock 120 MHz.
create_clock -name push_rx120 -period 8.333 -waveform {0.000 4.167} [get_ports {push_hrclk}]
create_generated_clock -name push_tx50 -source [get_ports {clk_50m}] -master_clock clk_50m -divide_by 1 -invert [get_ports {push_htclk}]
# Gowin treats an output-port capture clock as ideal (zero network latency).
# Account for the real forwarded clock. Routed SDF must prove these bounds:
# clk_50m pad -> inverter -> push_htclk pad is between 1 and 8 ns at all corners.
set_clock_latency -source -early 1.000 [get_clocks {push_tx50}]
set_clock_latency -source -late 8.000 [get_clocks {push_tx50}]
# Engineering I/O budget, to be cross-checked against CH569 timing and board test:
# both directions launch at falling forwarded clock, sample at rising edge.
set_input_delay -clock push_rx120 -clock_fall -max 2.500 [get_ports {push_hd[*] push_hrreq push_hrvld}]
set_input_delay -clock push_rx120 -clock_fall -min 0.000 [get_ports {push_hd[*] push_hrreq push_hrvld}]
set_output_delay -clock push_tx50 -max 2.000 [get_ports {push_hd[*] push_htreq push_htvld}]
set_output_delay -clock push_tx50 -min -0.500 [get_ports {push_hd[*] push_htreq push_htvld}]
set_false_path -to [get_ports {push_hrack}]
set_false_path -from [get_ports {push_htrdy}] -to [get_pins {u_push/link/phy/ready_meta*/D}]
set_false_path -to [get_pins {u_push/link/phy/active_meta*/D u_push/link/reply_sync_0*/D}]
set_false_path -to [get_pins {u_push/link/phy/*/CLEAR u_push/link/reply_toggle*/CLEAR u_push/link/reply_bad*/CLEAR u_push/link/reply_words*/CLEAR u_push/link/receive_words*/CLEAR}]
# Reply storage stays immutable after its synchronized completion toggle until
# the next request. Bound the held memory crossing; no blanket clock false path.
set_max_delay 20.000 -from [get_regs {u_push/link/rxram* u_push/link/reply_bad* u_push/link/reply_words*}] -to [get_regs {u_push/link/* u_push/midi/*}]
set_false_path -hold -from [get_regs {u_push/link/rxram* u_push/link/reply_bad* u_push/link/reply_words*}] -to [get_regs {u_push/link/* u_push/midi/*}]
set_max_delay 10.000 -from [get_regs {u_push/events/fifo/unbuffered/produce_w_gry* u_push/events/fifo/unbuffered/produce_w_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/produce_cdc/stage0*}]
set_false_path -hold -from [get_regs {u_push/events/fifo/unbuffered/produce_w_gry* u_push/events/fifo/unbuffered/produce_w_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/produce_cdc/stage0*}]
set_max_delay 10.000 -from [get_regs {u_push/events/fifo/unbuffered/consume_r_gry* u_push/events/fifo/unbuffered/consume_r_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/consume_cdc/stage0*}]
set_false_path -hold -from [get_regs {u_push/events/fifo/unbuffered/consume_r_gry* u_push/events/fifo/unbuffered/consume_r_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/consume_cdc/stage0*}]
# Gray bit6 equals binary bit6; Gowin merges these two registers.
# Only that proven MSB alias is admitted above; all other bits use Gray sources.
set_false_path -to [get_pins {u_push/event_release*/CLEAR}]
set_false_path -to [get_pins {u_push/events/fifo/unbuffered/rst_cdc/stage*/PRESET}]

# Existing J18 FIFO also uses asynchronous assertion, two-stage release.
set_false_path -to [get_pins {u_usb_host/u_fifo/fifo/unbuffered/rst_cdc/stage*/PRESET}]
