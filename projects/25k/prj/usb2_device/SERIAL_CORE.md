# USB2 CDC core adaptation and simulation

`generate_serial_core.py` produces independent USB2 versions of the pinned
WangXuan95 USB core and CDC top without modifying vendor or USB1 files.
It verifies the vendor manifest and all vendor hashes, and separately pins the
verified USB1 address filter hash before copying/renaming that filter.
Upstream commit: `ebf0696f0b1dc604a4ed8eedee4c3eae1643e66f`, LGPL-2.1;
license: `../vendor/fpga_usb_device/LICENSE`.

The only core adaptations are insertion of the existing address-selection
bridge and replacement of physical bidirectional DP/DN ports with explicit
`usb_oe`, `dp_tx`, `dn_tx` outputs and resolved `dp_rx`, `dn_rx` inputs.
All input references, including the SE0/reset detector, use those resolved RX
signals. The surrounding top must provide local TX loopback to RX.
Packet/transaction logic, descriptors, 1024-byte send FIFO, 120,000,000-clock
attach delay, and SE0 reset behavior are retained. CDC identity remains
FB9A:FB9A / FPGA-USB-Serial. USB3300 serial mode setup and pad selection belong
to the separately maintained init/top modules.

`rtl/usb2_cdc_loopback.v` exposes the explicit PHY interface and `recv_data`,
`recv_valid`, `send_ready`. It feeds each OUT byte into the existing send FIFO
and tracks saturating received/queued/dropped counts plus sticky received and
overflow flags. The physical USB bus reset clears these session counters.
As with USB1, the unchanged vendor OUT path has no application backpressure;
indefinite writes without reads can fill the FIFO and produce reported drops.

Build `generated/usbfs_core_top.v`, `generated/usb_serial_top.v`, and
`generated/usb2_address_filter.v` together with the wrapper and the six
remaining unmodified vendor USB core modules. Exclude the vendor's two same-name
tops. `prepare_serial_sources.tcl` regenerates these after clean staging.
Generation requires the pinned, read-only sibling
`../usb1_device/rtl/usb1_address_filter.v`.

## Validation

`sh prj/usb2_device/run_serial_sim.sh` connects the explicit RX/TX pins to a
resolved physical DP/DM bus. It retains the verified USB1 independent host
stimulus and protocol assertions, including NRZI, stuffing, CRC5/CRC16, device
and configuration descriptor reads, delayed SET_ADDRESS commit, foreign/old
address silence, malformed and split SETUP rejection, CDC class control,
binary 0–255 exact echo, empty IN NAK, exactly one drop after filling the FIFO,
and address/session reset following a physical SE0 reset.

`sh prj/usb2_device/run_serial_integration_sim.sh` instantiates the actual root
`rtl/usb2_serial_top.v` and `rtl/usb2_serial_init.v`. Its independent
`sim/usb3300_serial_phy_model.sv` exercises all init ULPI register transactions,
checks the seven exact safe writes, prohibits attachment before the core's
request, and checks the serial entry guard releases all DATA pins. It then
uses the actual shared DATA0/1/2 pins to model Table 6-7 of DS00001783C:

- DATA0 controls transmit enable and the direction of DATA1/2.
- Transmit DATA1 plus SE0 DATA2 is translated into physical DP/DM.
- Received physical DP/DM is translated into DATA1 plus SE0 DATA2.
- DATA3 remains a PHY output, and DIR remains high in serial mode.

The same complete host protocol sequence runs through these three physical
serial pins, including the real top's local TX loopback and all SE0 resets.
The init sequence performs twelve register reads. After Function 45h readback
it waits 100 µs, then reads Debug 15h and Interrupt Status 13h before switching
to serial mode. The model returns FS idle J (01h) and status 06h; the test checks
the top's packed `phy_debug=05h` (SessEnd=0, SessValid=1, line=J).
Both simulations accelerate only the existing two-second startup counter.
The integration test retains the actual root powerup/reset and complete PHY
setup sequence. Tests against a behavioral PHY do not establish analog USB
signal margins or replace host enumeration and binary echo on the board.
