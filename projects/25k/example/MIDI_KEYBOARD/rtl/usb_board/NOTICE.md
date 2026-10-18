# USB board adapter provenance and validation boundary

`midi_usb2_link.v` is an implementation of the USB3300 physical link, two bidirectional Bulk endpoint pairs and a three-interface USB composite device. It is designed for the board's 60 MHz ULPI clock and the application's independent 50 MHz clock. It is not an alias for the CDC loopback. No original file in `example/USB3300_HS` was modified.

Files under `vendor/` are copied from the local USB3300_HS reference. `vendor/UPSTREAM.json` records the original paths and SHA256. The SIE TX/RX and CRC16 sources are Copyright 2014–2019 Ultra-Embedded.com, LGPL-2.1-or-later; their complete notices remain in each file and `vendor/LICENSE-LGPL-2.1`. The ULPI wrapper is GPL-2.0-or-later; its original notice and `vendor/LICENSE-GPL-2.0` are retained. Derived use and distribution must preserve the corresponding source/license obligations. `midi_usb_hs_phy.v` is extracted from the same locally modified CDC core's PHY negotiation controller. `midi_usb2_boot.v` is copied from the project's USB3300 recovery/initialization block with a module-name prefix.

Local SIE changes prefix module names and verify token CRC5, which was unconditionally reported as valid in the reference. Boot failures release DATA, cool down for 10 ms at 60 MHz, and retry the complete PHY ID/scratch/configuration verification; a successful handoff stops retrying. The application/control/transaction layer is new: it buffers and validates an entire OUT packet before exposing data, suppresses duplicate OUT delivery, preserves IN packet data until ACK, resets toggles on clear-halt, and independently routes endpoint 1 and endpoint 2. It does not reuse the reference's uncommitted CDC byte stream.

## Modules

- `midi_usb2_link`: board port contract, USB3300 boot and pad ownership, ULPI wrapper and application bridge. It uses Gowin `LUT2` and `IOBUF` primitives for the immediate DIR drive inhibit. All MIDI and control application ports are in `clk_50mhz`. `online` and `hs_active` are synchronized to that clock. `control_reset` stays high while unavailable, asserts at session loss, and releases in the application clock.
- `midi_usb_bridge`: the independently testable UTMI boundary, four Gray-pointer asynchronous FIFOs, and configuration/session synchronization. MIDI CDC units are complete 32-bit USB-MIDI events. Vendor CDC units are bytes; frame parsing remains above this adapter. No multi-bit application payload is synchronized bit by bit.
- `midi_usb_device`: 60 MHz transaction/control logic. EP0 uses 64-byte packets in FS and HS. MIDI uses EP1 OUT `01` and IN `81`; vendor control uses EP2 OUT `02` and IN `82`. Both Bulk pairs use 512-byte packets in HS and 64-byte packets in FS. IN packets aggregate available data and flush after 16 idle USB clocks; MIDI packets contain whole 4-byte events. A completed packet occupies its buffer until ACK. Each OUT endpoint owns a complete packet buffer and NAKs when its previous packet cannot drain. Malformed MIDI byte counts are STALLed; SysEx support is determined by the application codec, not this byte transport.
- `generated/usb_composite_desc_rom.v`: deterministic generated device, configuration, strings, qualifier and other-speed configuration. The default `FB9A:FB9B` values are inherited local laboratory identifiers, not a product allocation. Use authorized identifiers before distribution.

The control endpoint implements GET_DESCRIPTOR, GET_STATUS, SET_ADDRESS with status-ACK commit, GET/SET_CONFIGURATION, GET/SET_INTERFACE (alternate 0), and per-direction endpoint halt GET/SET/CLEAR_FEATURE. Unsupported class/vendor requests, invalid interfaces, invalid endpoints and unsupported feature selectors STALL. Screen commands use IF2 Bulk, not EP0 vendor requests. SET_CONFIGURATION, USB bus reset, PHY reset and boot failure invalidate all application FIFOs. SET_INTERFACE resets only the corresponding MIDI or vendor endpoint pair and its CDC buffers, preserving the other interface; no previous session's byte or MIDI packet is implicitly replayed.

Packet storage and FIFO payload memories use synchronous read ports with head prefetch, permitting Gowin block-RAM inference. MIDI packet RAM stores complete 32-bit events; vendor packet RAM stores bytes. Only pointers and validity state reset: stale RAM contents remain inaccessible after session reset. Read-ahead preserves one transfer per clock and keeps the visible head stable during backpressure.

Host suspend preserves address, configuration, endpoint toggles and all application/packet queues. FS idle J is retained. After 3 ms of HS inactivity, the controller restores FS termination and waits 125 us to distinguish idle J from a persistent reset SE0; host resume K and its terminating SE0 restore the negotiated HS receiver. Only a qualified reset clears the session. The PHY clock remains running and no PHY low-power command is issued. Remote wake is neither advertised nor initiated, and remote-wakeup feature requests STALL.

## Build inputs

Add all `*.v` in this directory, `generated/`, and `vendor/`, and add `vendor/` to the HDL include path for `usbf_defs.v`. The only top-level physical-port module is `midi_usb2_link`. Use the parent board's ULPI and 50/60 MHz constraints after review. The FIFO synchronizer registers have `ASYNC_REG` attributes; timing constraints must identify both clocks, constrain Gray-pointer CDC paths/skew appropriately, and avoid treating arbitrary payload paths as synchronous. Both pointer domains receive a common asynchronously asserted session reset and synchronize reset release locally.

Generate/check descriptors from the project directory:

```sh
python3 tools/generate_usb_descriptors.py
python3 tools/generate_usb_descriptors.py --check
```

`config/usb_descriptors.json` records both speeds' exact descriptor bytes and the generated ROM SHA256. Supply `--vid 0x.... --pid 0x....` to generate authorized product identifiers. The default values are only for this laboratory build.

## Verified offline and remaining work

`sim/tb_usb_board_device.v` is a host BFM at the UTMI boundary, not a forced-state endpoint model. It performs physical-speed chirp negotiation/fallback, packet PID/token/CRC generation, descriptor traversal, address/configuration, independent MIDI/vendor traffic, packet aggregation, duplicate OUT, bad CRC16/token CRC5/PHY-error rejection, DATA2 rejection, IN retransmission without ACK, UTMI TX backpressure, endpoint halt, host suspend/resume, deconfiguration, bus reset and re-enumeration. Suspend coverage includes 10 ms idle and 20 ms host resume K, retaining both IN packet queues and stalled OUT CDC heads at both speeds. Run it with `HIGH_SPEED=1` and `HIGH_SPEED=0`. `sim/tb_usb_board_cdc.v` tests asynchronous FIFO order, pointer wrap, full, stalls and pending-data reset with independent 50/60 MHz clocks. `sim/tb_usb_board_boot.v` models PHY register transactions, a transient timeout followed by a complete verified boot, DIR preemption, and repeated permanent failures with bounded retries and released DATA ownership.

These simulations do not constitute USB electrical/compliance certification or real host enumeration. ULPI electrical timing, actual build resource/timing closure, host operating-system class binding, actual MIDI traffic and vendor access remain board/host integration checks. Suspend current limits and the PHY's FS termination/resume transition timing require physical validation; keeping the ULPI clock active does not establish low-power compliance. Isochronous transfers, multiple alternate settings, USB MIDI 2.0, multiple virtual cables, remote wake, LPM, USB test modes, Microsoft OS descriptors and WebUSB descriptors are outside this implementation.
