# Recording owner8 subclient mux

This unselected component shares one existing owner8 slot between two disjoint
storage clients. It owns arbitration and native/read attribution only; each
client retains its object/CRC/task owner and its existing native-commit bridge.
It adds no recording ID, CPU business owner, BLE format or DDR allocation.

All ports use the DDR UI clock. `rst_ni` must assert with the complete recording
transport/ledger/controller reset scope and release with the local clock.
`channel_ready_i` is a synchronous external authority: it may rise only after
that owner proves no previous untagged read return can arrive, by actual drain
or a reset that covers the complete response pipeline. Resetting this mux and
its clients alone cannot prove this. The port is an integration prerequisite,
not a proof of the controller's reset behavior. Admission is blocked while low;
withdrawal during a request or any unowned native acceptance/response causes
sticky isolation. Only a coordinated common reset plus genuine rearm recovers.

Two address ranges are explicit parameters in native 32-bit words. Every BL8
request must be aligned to eight words and fit wholly within its client's
inclusive range. Ranges must be disjoint. The generic defaults and test ranges
allocate no production memory; integration must bind reviewed suballocations
from `rtl/ddr_address_map.vh` and preserve all existing clients.

A local `ready_o` only accepts a command into the owner8 slot. The selected
subclient remains locked through actual `native_accept_i`. Writes retire then;
reads hold ownership through the actual response, including a same-edge native
acceptance/response. Shared read data may fan out, but only the owning client's
response pulse is asserted. At most one command/read is outstanding. On each
completion the other client gets priority; requests retain all data and masks
under backpressure. These guarantees require both clients' normal publication
contract and the actual owner8 acceptance/return ledger.

Each producer keeps `workstation_recording_ddr_native_bridge`. Broadcast the
mux transport fault to both bridges/clients. Aggregate the bridges' registered
`protocol_fault_o` into the transport authority if needed; never OR their
`transport_fault_o` back into the mux input, since those outputs already include
the broadcast input and would create combinational feedback. Production wiring,
failure recovery and absence of such loops remain separate checks.

Command and read budgets count UI clock cycles independently. Completion on
the final allowed edge succeeds. Timeout, invalid region/alignment, unexpected
native/return, authority loss or external transport fault immediately suppress
admission/acknowledgements and latch quarantine. A timeout cannot withdraw a
command already in the DDR pipeline or make a read cease to exist; late returns
are suppressed, and local reset is not a valid rearm strategy.

The standalone regression uses two real native-commit bridges, simultaneous
offers, delayed slot/native/read events, byte masks, saturated writer fairness,
all local range boundaries, timeout/late traffic and source mutations. It does
not prove production allocation, actual DDR arbitration latency, CDC/reset
completeness, physical timing, BSRAM savings or hardware acceptance.
