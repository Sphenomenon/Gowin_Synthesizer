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
