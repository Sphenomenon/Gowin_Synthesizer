# USB1 60 MHz clock

`usb1_clock_60m` provides the 60 MHz clock required by the USB full-speed core.
Its ports are `clk_50mhz`, `clk_usb60`, `pll_locked`, and `reset_60mhz_n`.
The top-level instance must be `u_clock` for the supplied SDC pin selector.
The board oscillator remains on E2; package pin assignment belongs in the CST.

## Frequency plan

The GW5A-25A uses the `PLLA` primitive with internal feedback. All of these
parameters use the actual divider value, with no minus-one encoding.

| Parameter | Value | Result |
| --- | ---: | --- |
| Reference | 50 MHz | 20 ns period |
| IDIV_SEL | 1 | PFD = 50 MHz |
| FBDIV_SEL | 1 | Feedback frequency = 50 MHz |
| MDIV_SEL | 24 | VCO = 1200 MHz |
| ODIV0_SEL | 20 | CLKOUT0 = 60 MHz |
| MDIV_FRAC_SEL / ODIV0_FRAC_SEL | 0 / 0 | Integer dividers |
| DE0_EN | FALSE | 50% duty cycle |

UG306-1.0.7E section 2.3 gives a 700–1400 MHz VCO range for 15K/25K/60K
parts and a 19–800 MHz reference input range. Section 5.2.1 gives the
frequency equations and direct static parameter encodings (IDIV/FBDIV
1–64, MDIV 2–128, ODIV 1–128). The proposed VCO and reference are inside
those ranges. The installed official GW5A-25A example also uses a 50 MHz
reference, IDIV=1, FBDIV=1. A separate minimum/maximum PFD table has not
been located in the installed manuals; do not claim that such a table was
checked.

`ICP_SEL=6'bXXXXXX` and `LPF_RES=3'bXXX` are the official automatic
calculation markers, not uninitialized application data. The installed
PLLA model comments and UG306 section 5.2.1 explicitly assign calculation
to the software when these parameters are X. The official generated
GW5A-25A example uses the same values and `LPF_CAP=2'b00`.

## Initialization and reset

The installed `PLL_INIT` helper is copied unchanged into `pll_init.v`.
It uses the 50 MHz board clock for mDRP, `CLK_PERIOD=20`, `MULTI_FAC=24`,
and permanent `PLL_INIT_BYPASS=0`. UG306 section 5.2.3 describes this
initialization for fixed-frequency operation. The helper may consume one
BSRAM; the actual resource count comes from the complete root build.

The exported lock is the AND of raw PLL LOCK and the helper's qualified
LOCK. Loss of raw LOCK therefore asserts the 60 MHz reset immediately.
Reset release uses three flip-flops in the 60 MHz domain and requires
three rising edges after qualified LOCK. The module has no physical reset
input and relies on the official helper's initialized power-up state.

The SDC declares 50 MHz on the input and a related 6/5 generated clock
on `u_clock/u_pll/CLKOUT0`. A narrowly scoped `set_false_path -hold` covers
only the helper LOCK Q to the three reset-release CLEAR inputs. Build
`20261016_005614_707313` exposed removal slack -0.109 ns there; its netlist
confirms the three DFFCE stages, first D=1 and subsequent D=previous Q.
This is the asynchronous entry to the reset synchronizer. Per SUG940-2.0.4E
section 5.4.1, `-hold` covers hold/removal; recovery, the chain's Q-to-D
paths and downstream reset checks remain enabled. `syn_preserve` retains
the chain; no Gowin-specific physical placement or MTBF guarantee is claimed.
There are no USB input/output delay assumptions. USB pad receive exceptions, when needed,
belong in the top-level constraints and must stop at the first sampling
register.

## Reproduce the functional check

```sh
python3 clock/sim/run.py
```

This runs the installed `simlib/gw5a/prim_sim.v` PLLA model, without the
shortened `SIM` timing macro. It checks power-up reset, three-edge release,
600 output periods, duty cycle, asynchronous assertion on forced raw LOCK
loss, and synchronized release after relock. The result is saved as
`simulation_report.json`. A nominal 60 MHz period appears as 16.666 ns
(60.0024 MHz) due to the official model's time quantization; this is not a
physical oscillator measurement. The model does not simulate analogue
mDRP calibration changes (UG306 section 5.2.5).

No synthesis, PnR, or hardware download was performed by the clock
implementation task. The source-only IP Tcl generation attempt was
unable to locate the installed PLL IP through `create_ipc`, and the old
official IPC import reported an inconsistent device descriptor. Those
tool compatibility failures are not a completed IP-generator validation.
Root must check the 50/60 MHz clock report, PLL placement and timing
before a board test.

## Sources and provenance

- Clock guide: `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/doc/EN/UG306-1.0.7E_Arora V Clock User Guide.pdf`, printed pages 9, 69–83, 96–101.
- Timing syntax: `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/doc/EN/SUG940-2.0.4E_Gowin Design Timing Constraints User Guide.pdf`, section 5.2.2.
- Helper source: `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/ipcore/PLL_ADV/data/PLLA/pll_init.v`.
- Unmodified helper SHA256: `3fc6bef9a7086f0920bfa47265b1766854a53f6ca1c0f75084eaf6b6ef4d6258`.
- PLLA functional model: installed `IDE/simlib/gw5a/prim_sim.v`, module `PLLA`.
- Official board example: `/private/tmp/gw25k-official-example-20261015/hdmi/svo/src/gowin_pll/gowin_pll.v` (Gowin V1.9.9 Beta-3, GW5A-LV25MG121NES, GW5A-25 version A).
