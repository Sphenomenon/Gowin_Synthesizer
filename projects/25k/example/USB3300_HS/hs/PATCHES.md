# GW25K high-speed CDC adaptations

The unmodified upstream copies, commit IDs, licenses and source hashes are in
`../vendor/ultraembedded_usb_hs/`. The local `usb_cdc_core.v` and
`usb_desc_rom.v` derive from `core_usb_cdc` commit
`d61b43fbd97fcb333fde203d7b885da315e3c2d4`. Their original LGPL-2.1-or-later
notices remain. The separately integrated ULPI wrapper is GPL-2.0-or-later;
see its upstream notice. No upstream vendor source is edited.

## Control and enumeration changes

- Limit every control read to `min(wLength, actual response size)`. End the
  final short packet; emit a terminating ZLP when the actual response is
  shorter than requested and falls on the current EP0 packet boundary.
- A new SETUP token aborts an earlier control read or pending terminating
  ZLP and clears an EP0 protocol STALL. Request-specific STALL is masked
  until the SETUP DATA0 ACK is transmitted; it then applies to the next
  control stage. The unsupported-descriptor test verifies ACK, STALL and
  subsequent recovery through a new SETUP.
- Add Device Qualifier and Other Speed Configuration descriptors with the
  opposite speed's EP0/bulk sizes. Unknown descriptors return STALL.
- Return the bus-powered status (two zero bytes), current configuration, and
  alternate setting zero for interfaces 0 and 1. Permit SET_INTERFACE zero
  on either CDC interface.
- Preserve upstream SET_ADDRESS handling: the top requests the new address
  after SETUP, while `usbf_device_core.current_addr_q` commits it only after
  the host ACK of the status ZLP. No hierarchy reference is used in RTL.
- Retain the upstream CDC line-coding behavior: GET returns 115200/8N1;
  SET_LINE_CODING, line-state and related OUT requests are acknowledged but
  do not control a UART in this loopback diagnostic.

## Identification and ROM map

Local diagnostic VID:PID is **FB9A:FB9B**. This does not assign a production
USB identifier. Device strings use manufacturer `GW25K`, product
`GW25K-USB-HS`, and serial `GW25KHS01`. Device string indexes are 1, 2 and 3.

| Start | Bytes | Response |
| ---: | ---: | --- |
| 0 | 18 | Device, EP0 64 HS / 8 FS |
| 18 | 67 | CDC configuration, bulk 512 HS / 64 FS |
| 85 | 4 | Language 0409 |
| 89 | 12 | Manufacturer UTF-16LE |
| 101 | 26 | Product UTF-16LE |
| 127 | 20 | Serial UTF-16LE |
| 147 | 7 | CDC line coding |
| 154 | 10 | Device qualifier |
| 164 | 67 | Other-speed configuration |
| 231 | 2 | GET_STATUS zeros |
| 233 | 1 | GET_CONFIGURATION, dynamic |
| 234 | 1 | GET_INTERFACE zero |

## Negotiation and observations

The 60 MHz HS negotiation state machine now requires six alternating
K-J-K-J-K-J states, each stable for at least 150 cycles (2.5 us). SE0/SE1 and
short glitches cannot count as chirps. It keeps the upstream roughly 3 ms
reset detection, 1.1 ms device chirp and FS fallback timing.

Added output ports:

- `hs_active_o`: negotiated high-speed state.
- `configured_o`: current SET_CONFIGURATION state.
- `usb_reset_o`: SIE bus reset observation.
- `chirp_active_o`: device chirp transmission phase.
- `hs_state_o[2:0]`: 0 detached, 1 await reset, 2 device chirp,
  3 await host chirps, 4 FS fallback, 5 HS.
- `device_address_o[6:0]`: requested address register. It can precede the
  SIE's actual address commit until the status ACK arrives.

The external loopback FIFO must reserve a complete 512-byte HS packet before
asserting `outport_accept_i`: this input is packet admission, not per-byte
backpressure. The unchanged upstream stream interfaces do not provide robust
IN retransmission or RX CRC rollback, and suspend/resume is incomplete.
Successful clean-link bring-up is not a USB compliance test.

## Validation

Run `sh ./run_hs_control_sim.sh` from the example project root. The
independent host BFM supplies real UTMI PID/token/CRC16 packets. It verifies
filtered HS chirp negotiation, device/configuration descriptors, requested
length truncation and short termination, unknown descriptor STALL, qualifier,
other-speed descriptor, UTF-16 product string, GET_STATUS, GET_CONFIGURATION,
SET_ADDRESS commit after status ACK, SET_CONFIGURATION, GET_INTERFACE, CDC
requests, and a 512-byte binary bulk OUT/FIFO/IN loopback including TX CRC.
The BFM does not force internal protocol state. It inspects the SIE's active
address only to assert correct SET_ADDRESS timing.
