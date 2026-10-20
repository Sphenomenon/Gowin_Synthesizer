# Routed design review, 2026-10-03

Reviewed `vivado/bt_verilog.runs/impl_1/bt_verilog_top_routed.dcp` in a separate Vivado batch session using `open_checkpoint`. No project, RTL, constraints, or hardware state was modified. The reports below describe the implemented design containing the UART input false-path constraint.

## Clock crossings

The five `CDC-10` findings from `clk_fpga_0` to `clk_fpga_1` terminate at:

- `system_i/monitor/inst/meta_o_reg[0]/D`
- `system_i/monitor/inst/meta_o_reg[13]/D`
- `system_i/monitor/inst/meta_t_reg[0]/D`
- `system_i/monitor/inst/meta_t_reg[12]/D`
- `system_i/monitor/inst/meta_t_reg[13]/D`

These crossings sample combinational output values and output-enable states for the 1 MHz ILA monitor. They pass through the monitor's two `ASYNC_REG` stages and an output register. They do not feed back into the Bluetooth driver. The findings indicate possible transitory observation glitches or an incoherent combination of independently sampled bits; they do not identify a Bluetooth control-path crossing. The monitor is suitable for observing levels and UART transitions, but a sample taken while enable changes must not be treated as an atomic hardware snapshot.

The UART input appears as a `CDC-1` finding because synchronous enable control inserts a LUT between the two synchronizer registers. Both registers retain `ASYNC_REG=1` and occupy `SLICE_X32Y68`. The implemented first-to-second-stage path has a 0.952 ns data-path delay and 18.819 ns setup slack at 50 MHz. The exception report confirms only the external input-to-first-stage path is cut. The second stage remains timed. Enable and reset transitions discard UART state; while reception is enabled, the LUT passes the first-stage output to the second stage. This is a manually reviewed synchronization structure, not a blanket clean CDC result. A future cleanup can sample the two UART synchronizer stages unconditionally and apply enable only to the byte receiver to make the structure recognizable automatically.

Evidence: `cdc_details_audit.rpt`, `uart_sync_timing_audit.rpt`, `exception_audit.rpt`.

## ROM control warning

All eight patch-ROM RAMB36E1 blocks have `READ_WIDTH_A=1`, `READ_WIDTH_B=0`. Every `WEA` and `WEBWE` pin is tied to `core/initializer/<const0>` in the routed netlist. Runtime reset therefore cannot write or change the stored patch image.

`REQP-1839` flags address and read-enable logic with asynchronous-reset sources, including `reset_sync/stages_reg[1]` and `core/transport/tx_error_reg`. An asynchronous reset transition can invalidate a ROM read output. The initializer discards work during reset or disable. After startup, each patch byte is read through `PATCH_ADDR`, `PATCH_WAIT`, then `PATCH_COPY`; the address and read latency are re-established before the byte enters the HCI payload. A transport error sends the initializer to its failure state. Thus a reset-time read value is not relied upon by the current state machine. The warning remains visible and has not been globally waived.

The prior synthesized-ROM audit reconstructed all 32768 bytes from all 1024 `INIT_00` through `INIT_7F` properties across the eight blocks and found zero differences against `rtl8723ds_patch.mem`. Both byte streams have SHA256 `827718bbda291c2b74ca4ccae3b6892cec6305cbb39d83c0c4c211d21d044bdd`.

Evidence: `rom_control_audit.rpt`, `rom_pin_constants_audit.txt`, `synth_rom_init_dump.txt`, `synth_rom_uart_audit.log`, `routed_rom_uart_audit.log`.
