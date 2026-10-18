# USB2 / USB3300 ULPI register probe

`rtl/usb2_ulpi_probe.v` independently exercises the board's USB3300 PHY over its
60 MHz ULPI bus. It is a register probe, not a USB enumeration or packet core.
The FPGA must receive CLKOUT from the PHY; it must not drive that clock pin.

The reference is Microchip USB3300 datasheet **DS00001783C**, §6.1.4–6.1.6:
<https://ww1.microchip.com/downloads/en/DeviceDoc/00001783C.pdf>.
The USB3300's register identity is **VID 0424 / PID 0004**, not PID 0007.

## Operation and safety

During reset, STP is high and DATA is high impedance even without a running
clock. `reset_n` must be released synchronously to `clk_ulpi60`. After the
default 32-clock internal startup delay the controller:

1. Reads VID/PID, then Function/Interface/OTG baseline values.
2. Writes Scratch 16h with 55h and AAh and checks both readbacks.
3. Writes Interface 07h=00h and OTG 0Ah=00h, then Function 04h=45h.
4. Reads all three configured registers and checks exact values.

Function 45h selects full-speed peripheral operation with the PHY's internal
D+ 1.5 kΩ pull-up enabled; SuspendM remains one, and Reset remains zero.
Interface 00h retains synchronous ULPI operation. OTG 00h disables both D+/D−
15 kΩ pull-downs, all VBUS drive/charge/discharge controls and the ID pull-up;
it uses the PHY's internal VBUS comparator. No host power operation is issued.
The pull-up alone does not produce enumeration: this probe sends no USB replies.

DATA output enable is gated immediately by raw DIR, and also by delayed DIR to
preserve the PHY-to-Link turnaround cycle. The first sampled DIR-high cycle of
a register read is turnaround; only the next continuous DIR-high/NXT-low cycle
is captured. Commands and write data remain stable through NXT stalls. A PHY
preemption before command acceptance is retried up to the configured bound.
A preemption during a write-data phase aborts rather than repeating the write.

STP is high for exactly one registered write-stop cycle with DATA=Idle00.
It has no raw DIR combinational path; it returns low after the stop or an abort.
Once complete or failed, the Link drives Idle00 whenever it owns the bus and
continues yielding DATA to the PHY. No further register commands are issued.

`TIMEOUT_CYCLES` defaults to 60000, or 1 ms per complete register operation at
60 MHz. This includes waiting for the bus, command/data ACKs, and bus release.
A stopped PHY clock cannot advance this timeout; the separate root top-level
50 MHz observer reports missing CLKOUT.

## Results

Success is `probe_done=1, error=0, id_ok=1, scratch_ok=1, stage=12h`.
Failure also sets `probe_done=1`, but sets `error=1` and stops the script.
VID/PID, register results, `last_read`, flags and `stage` then remain stable.
Register outputs initially hold baseline values and later hold final readbacks.

`stage[4:0]` is the current script step:

| Step | Operation |
| --- | --- |
| 00 | Startup |
| 01–04 | Read VID low/high, PID low/high |
| 05–07 | Read baseline Function, Interface, OTG |
| 08–09 | Write/read Scratch 55h |
| 0A–0B | Write/read Scratch AAh |
| 0C–0E | Write Interface 00h, OTG 00h, Function 45h |
| 0F–11 | Read/check Interface, OTG, Function |
| 12 | Success |

`stage[7:5]` is zero during normal execution, or the latched failure reason:

| Reason | Meaning |
| --- | --- |
| 1 | Register operation timed out |
| 2 | Command preemption retry limit reached |
| 3 | Short/invalid register read or internal invalid step |
| 4 | VID/PID mismatch |
| 5 | Scratch mismatch |
| 6 | Final configuration readback mismatch |
| 7 | PHY took the bus during write data/stop |

`rxcmd_count` and `rxdata_count` are saturating ULPI byte counts classified by
NXT while DIR owns the bus. They exclude turnaround and register-read return
bytes. They remain active after completion and are not USB packet/error counts.

## Simulation

Run `sh prj/usb2_device/run_probe_sim.sh` with Icarus Verilog installed.
The independent PHY model updates DIR/NXT/DATA after sampling each clock edge;
it does not consult the Link FSM to acknowledge transactions.

The 12 scenarios cover a complete 17-operation script with delayed command and
write-data ACKs, RxCmd/RX-data preemption and retry, unknown turnaround data,
all five exact safe writes, post-completion RX monitoring and stable results;
then Scratch and PID mismatches, missing command ACK, short read, invalid read
NXT, repeated preemption, write-data preemption, configuration mismatch, missing
read DIR, missing write-data ACK, and a PHY that never releases a completed read.
The harness quiesces the modeled PHY after each bounded abort before the next
reset. These tests establish controller behavior against the model; hardware
register readback and USB enumeration remain separate checks.
