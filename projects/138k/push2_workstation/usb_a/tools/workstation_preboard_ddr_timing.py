"""Place the observed DDR paths and retain the original finite hold margin.

The previous route is structural evidence only. Its encrypted inputs must be
bound by the caller before these constraints are used for a new implementation.
Both finite limits remain subject to fresh routed setup/hold/recovery checks.
"""
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_custom_board_implementation import (
    TOP,DDR_PHY,DDR_LAUNCH,DDR_CAPTURE,DDR_STRICT_MINIMUM,
    DDR_FAR_LAUNCH_REGION,DDR_FAR_CAPTURE_REGION,digest)

POLICY='task3_preboard_DDR_init_min0p8_reset_max7p5_v2'
RESET='u_memory/u_recovery/controller_reset_n_s1'
INVERTER=DDR_PHY+'/gowin_split_inv_from_n7_s2'
# set_min_delay replaces the hold edge relationship; it is not a router
# request for that many ns of data wire. The 3.5/4ns experiments added an
# unjustified edge offset on top of destination clock skew. Keep the original
# 0.8ns requirement, the opposite-corner placement that repairs the short
# physical path, and the complete routed hold check (including skew).
MINIMUM=DDR_STRICT_MINIMUM.replace('3.500','0.800',1)
MAXIMUM=f'set_max_delay 7.500 -from [get_pins {{{RESET}/Q}}] -to [get_pins {{{DDR_LAUNCH}/CLEAR}}]'


def require(ok,message):
    if not ok:raise ValueError('preboard DDR timing: '+message)


def tighten(cst,sdc,routed_netlist):
    ct,st=cst.decode(),sdc.decode()
    require(ct.splitlines().count(f'INS_LOC "{DDR_LAUNCH}" {DDR_FAR_LAUNCH_REGION};')==1 and
            ct.splitlines().count(f'INS_LOC "{DDR_CAPTURE}" {DDR_FAR_CAPTURE_REGION};')==1,
            'requires exact reviewed opposite-corner initialization regions')
    require(RESET not in ct,'reset source already constrained')
    related=[line for line in st.splitlines()if line.lstrip().startswith('set_min_delay ') and
             (DDR_LAUNCH in line or DDR_CAPTURE in line)]
    require(related==[DDR_STRICT_MINIMUM] and MAXIMUM not in st,
            'unique prior minimum or unselected recovery limit changed')
    n=SynthesisNetlist(routed_netlist,TOP)
    for p in (RESET,DDR_LAUNCH,DDR_CAPTURE):
        require(p in n.cells and n.cells[p]['kind']=='DFFCE' and
                n.cells[p]['parameters'].get('INIT')=="1'b0" and
                set(n.cells[p]['ports'])=={'D','Q','CLK','CE','CLEAR'},
                'observed FF primitive/INIT/pins changed: '+p)
    require(INVERTER in n.cells and n.cells[INVERTER]['kind']=='INV' and
            set(n.cells[INVERTER]['ports'])=={'I','O'} and
            n.pin(RESET,'Q')==n.pin(INVERTER,'I') and
            n.pin(INVERTER,'O')==n.pin(DDR_LAUNCH,'CLEAR')==n.pin(DDR_CAPTURE,'CLEAR'),
            'functional vendor reset is not exact inverse controller Q')
    require(n.pin(RESET,'CLK')==n.pin(DDR_CAPTURE,'CLK')=='clk_50m' and
            n.cells[RESET]['ports']['CLK']==n.cells[DDR_CAPTURE]['ports']['CLK']=='clk_50m_d' and
            n.pin(DDR_LAUNCH,'CLK')=='memory_clk' and
            n.pin(DDR_LAUNCH,'Q')==n.pin(DDR_CAPTURE,'D'),
            'observed direct data or 50MHz-to-DDR reset clock boundary changed')
    adapted_cst=cst+(f'\n# {POLICY}\nINS_LOC "{RESET}" {DDR_FAR_LAUNCH_REGION};\n').encode()
    adapted_sdc=st.replace(DDR_STRICT_MINIMUM,MINIMUM,1)+(f'\n# {POLICY}\n'+MAXIMUM+'\n')
    require(adapted_sdc.replace(MINIMUM,DDR_STRICT_MINIMUM,1).split('\n# '+POLICY+'\n')[0]==st,
            'unrelated timing constraints changed')
    return adapted_cst,adapted_sdc.encode(),dict(policy=POLICY,
        source_reset=RESET,launch=DDR_LAUNCH,capture=DDR_CAPTURE,
        exact_vendor_functional_reset_inversion_proven=True,
        minimum_data_delay_ns=0.8,maximum_functional_reset_delay_ns=7.5,
        original_finite_hold_relationship_restored=True,
        clock_skew_and_native_hold_checks_retained=True,
        previous_minimum_ns=3.5,reset_region=DDR_FAR_LAUNCH_REGION,
        before_cst_sha256=digest(cst),before_sdc_sha256=digest(sdc),
        after_cst_sha256=digest(adapted_cst),after_sdc_sha256=digest(adapted_sdc.encode()),
        false_paths_added=False,clock_periods_changed=False,vendor_bytes_changed=False,
        routed_timing_verified=False,hardware_tested=False)
