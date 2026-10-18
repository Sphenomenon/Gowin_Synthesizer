# USB2 protocol paths

The USB2 connector is wired to the USB3300-EZK analog DP/DM pins, not directly
to FPGA GPIO. FPGA DATA[7:0] is the ULPI bus; its pin mapping is recorded in
`../../../原理图信息汇总.md` section 5.2. All current FPGA BANKs are 3.3 V according
to the user's board update. That does not change the PHY's internal 1.8 V rails.

## Verified board baseline

The parent task recorded a successful USB3300 hardware probe on 2026-10-16:
VID `0424`, PID `0004`, Scratch `55`/`AA`, Function Control `45`, Interface
Control `00`, OTG Control `00`, and 600047 CLKOUT edges in a 10 ms window.
See `../reports/usb2_status_20261016_013816_decoded.json` and `../PROBE.md`.
This verifies register access and clock activity. It does not establish USB
enumeration, 3-pin serial operation, or 480 Mbps traffic.

## Existing open source Full-Speed stack

`../../vendor/fpga_usb_device/` contains selected source from WangXuan95's
FPGA-USB-Device at pinned commit `ebf0696f0b1dc604a4ed8eedee4c3eae1643e66f`.
Its LGPL-2.1 license and provenance are in `LICENSE`, `NOTICE.md`, and
`SOURCE.json`. The local source is a 12 Mbps GPIO stack. It has no ULPI or
High-Speed module. The existing address-filter adaptation is under
`../../usb1_device/rtl/usb1_address_filter.v`.

A byte-wide ULPI frontend could reuse its transaction and CDC class layers,
but requires new packet parsing, CRC handling, transmit buffering/handshakes,
receive-status decoding, reset detection, and tests. A PHY by itself does not
provide EP0 or a device class.

## USB3300 3-pin Full-Speed serial candidate

Microchip [DS00001783C](https://ww1.microchip.com/downloads/en/DeviceDoc/00001783C.pdf)
section 6.1.10 and table 6-7 define a legacy serial interface that can reuse the
existing GPIO bit/packet/transaction layers through an adapter:

| PHY pin | Serial role | Direction relative to FPGA |
| --- | --- | --- |
| DATA0 / L2 | TX_ENABLE, active high | Output |
| DATA1 / L1 | Differential data | Output while TX_ENABLE=1; input otherwise |
| DATA2 / K1 | SE0 | Output while TX_ENABLE=1; input otherwise |
| DATA3 / K2 | Interrupt | Input |

For fixed FS operation, candidate mapping is TX data = `usb_dp_tx`, TX SE0 =
`~(usb_dp_tx | usb_dn_tx)`, RX DP = `~SE0 & data`, RX DM = `~SE0 & ~data`.
Transmit-enable follows the existing `usb_oe`; the receive side can locally
loop back the current TX line state while transmitting. J/K/SE0 are
representable. The serial receive interface cannot reconstruct a distinct SE1.
DATA1 polarity is inferred from the differential-data interface; the short
USB3300 serial section does not provide an explicit DP/DM truth table.
Validate that assumption in simulation and on the board.

Function Control `04h=45h` selects FS, normal operation, internal D+ pull-up,
SuspendM=1, Reset=0. OTG Control `0Ah=00h` disables both 15K pull-downs,
VBUS charge/discharge/drive, and external VBUS detection. The clock must be
kept running before entering serial mode: write Interface Control `07h=08h`,
then `07h=0Ah` (ClockSuspendM=1 and 3-pin FsLsSerialMode=1). Section 6.1.4.6
explicitly says ClockSuspendM retains the 60 MHz clock in serial mode.

The mode change asserts DIR and takes at least five clocks. The manual does
not provide a separate serial-ready indication or an explicit maximum entry
latency with ClockSuspendM=1. `usb2_serial_init.v` consequently keeps the entire
DATA bus high-Z and waits a configurable 16 consecutive DIR-high cycles before
`init_done`. This guard exceeds the documented minimum; it is an implementation
assumption, not measured proof of completed mode entry. NXT is not used as a
serial handshake and the manual does not promise a constant NXT level.

The serial pad mux must use TX_ENABLE for DATA1/2 direction, not DIR. Keep STP
low while serial mode is active. To return to ULPI, assert STP, wait for DIR to
deassert, then deassert STP. The PHY clears the serial-mode bit on exit.
RESET/Function Control Reset does not clear the ULPI register set; use this
STP exit and explicit configuration rather than assuming FPGA reset restores
PHY defaults. A PHY 3.3 V power cycle restores register defaults.

`usb2_serial_init.v` starts with STP high and DATA high-Z, verifies ID and
Scratch, then writes and reads back FC41 (detached), OTG00, and IF08. It waits
without a timeout at stage `0F` for `attach_request` from the protocol core's
existing two-second delay. It then writes/reads FC45, writes IF0A, and performs
the mode guard. All DATA pins remain released after success; STP remains low.
The protocol core must continue running through this handover rather than
resetting and starting its attach delay again. `func_ctrl`/`otg_ctrl` and the
initial IF08 are readback values; final `if_ctrl=0A` is a **write shadow** because
ordinary ULPI readback is unavailable after entering serial mode. Stage `14`
means handover complete; an error encodes `{reason[2:0], step[4:0]}`. The initializer
cannot detect a stopped CLKOUT using that same clock; the independent 50 MHz
clock monitor remains necessary.

After the FC45 readback at stage `11`, stage `15` first waits 6000 60 MHz
clocks (100 microseconds) for the pull-up and cable line to settle, then reads
the PHY Debug register `15h`. This independent wait does not consume the ULPI
transaction timeout. Stage `16` then reads USB Interrupt Status `13h` before
resuming stage `12` to enter serial mode. Both reads are read-only, and neither
reads or clears the Interrupt Latch register. `phy_debug[3:0]` is a packed
observation nibble `{SessEnd, SessValid, Linestate[1:0]}` from Status bits 3/2
and Debug bits 1/0; bits 7:4 are zero. These pre-entry snapshots do not change
serial configuration or sample the later serial pins. The model uses Status
`06` and Debug `01` for session valid and Full-Speed J, producing `phy_debug=05`.

The initializer exports explicit `ulpi_data_i`, `ulpi_data_o`, and
`ulpi_data_oe` signals. The top owns one physical tri-state driver per pad and
switches data separately from output enable. A registered `link_active` is
cleared by reset, abort, or mode entry; ULPI output enable is only
`link_active && !DIR && !previous_DIR`. This keeps the immediate DIR safety
path in IOB output-enable rather than putting DIR in the IOB data path.

`sh prj/usb2_device/run_serial_init_sim.sh` passes 17 independent simulated
scenarios using a PHY register BFM. It checks seven exact safe writes and twelve
reads, command/data stability through NXT stalls, both DIR turnarounds,
single/repeated preemption, read framing, ID/scratch/config mismatches,
transaction/startup/mode timeouts, and stable bounded abort. The successful
path waits 230 clocks for attach with an operation timeout of 100 clocks,
retains NXT high during mode entry, restarts the 16-clock guard after a DIR
glitch, and recovers a PHY already in serial mode at startup. It also resets
only the FPGA after success and reruns the complete script while preserving
the PHY registers. These tests verify digital sequencing and ownership; they
do not establish the PHY's analog mode timing or board enumeration. The
separate `run_serial_integration_sim.sh` exercises the full serial top and
host packet path through a DP/DM PHY model.

This path is FS only. The existing 60 MHz/5-times oversampling bit engine
cannot be reused unchanged for 1.5 Mbps LS or 480 Mbps HS. First establish EP0
enumeration, then reuse the existing CDC descriptors/class and loopback.
There is no need to introduce HID solely to test enumeration.

## Installed Gowin Device Controller IP

The current IDE contains USB 2.0 Device Controller version 3.3 at:

```text
/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/ipcore/USB_DEVICE_CONTROLLER/
  usb_device_controller.ipspec
  data/usb_device_controller_top.v
  data/usb_device_controller.v
  doc/usb_device_controller.html
  doc/usb_device_controller_help.html
```

The wrapper has a ULPI branch (`ulpi_dir_i`, `ulpi_nxt_i`, `ulpi_rxdata_i`,
`ulpi_txdata_o`, `ulpi_stp_o`), EP0/descriptor-ROM interfaces, and FS/HS support.
The device list broadly supports `*` and does not exclude GW5A. The generator
library includes ULPI/UTMI and FS/HS configuration options. The implementation
is encrypted Gowin IP, not an open source ULPI core. Installed files alone do
not establish license availability or a successfully generated configuration.
This investigation did not generate, compile, simulate, or download that IP.

Using it would require generated configuration, descriptor ROM, board pad and
clock/reset wiring, and suitable class logic. The other installed USB PHY IP
blocks replace a PHY or implement a host role; they are not a drop-in USB3300
device-enumeration solution. No additional licensed open source ULPI core was
found in the local vendor tree or inspected local caches. No external
repository was cloned.
