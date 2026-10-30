# Native physical PLL audit

`workstation_physical_pll_audit.py` checks the existing DDR configuration/reset,
video PLL initialization, serializer startup and shared PLL control paths. The
10 ns shared control budget and complete ten-bit `ICPSEL`/`LPFRES`/`RESET` tuples
remain required. This subgate does not establish full STA, CDC, reset, electrical
or hardware acceptance.

The default and legacy manifest policy requires all seven PLLs, including the
LCD PLL, and four shared control tuples. A sealed, completed
`custom138k-workstation-r00-no-local-panel-v1` profile may select exactly six PLLs
and three shared tuples. This selection verifies the profile configuration,
revision and metadata, recomputes the candidate identity, checks every staged
synthesis input, and compares the copied profile/process/metadata with the exact
source candidate. Another no-panel candidate cannot supply those identities.
Missing metadata never selects the reduced inventory. DDR and both video PLLs
remain mandatory in either policy.

Nested physical manifest inputs are accepted only when their resolved paths stay
inside the physical directory and their bytes match the manifest. A no-panel
audit requires a new external `--workspace`; the auditor's view, links and
recomputed DDR proof outputs go there. The physical and source directories are
read as inputs. Select a new external JSON output as well; external mode refuses
to overwrite existing evidence or write inside the source candidate:

```sh
GOWIN_SIMLIB=/path/to/Gowin_EDA/IDE/simlib/gw5a \
python3 tools/workstation_physical_pll_audit.py \
  --physical /path/to/completed-physical-candidate \
  --workspace /path/to/new-external-audit-workspace \
  --json /path/to/external-review.json --self-test
```

The caller must first verify a completed, successful P&R process and its exact
VO/SDF output hashes. This PLL subgate binds the files it reads, but does not
replace that independent completion gate. Synthesis inventory verification alone
cannot pass routed propagation checks. Source identity and acceptance stay bound
to the selected candidate; no previous candidate's result is inherited.

The targeted regression is `sim/test_workstation_physical_pll_audit.py`. Set
`GW138K_PLL_AUDIT_PHYSICALS` to an OS-path-separated list of existing candidates to
add real source/manifest and PLL inventory checks. The regression invokes no EDA
and has no fallback build. The shared tuple cases exercise every required bit's
owner, direct 50 MHz clock, constant polarity and original propagation budget.
