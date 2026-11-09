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
W_POLICY='task3_W_DDR_init_min0p8_central_reset_all_clear_max6p5_v3'
W_RESET_REGION='R[64:72]C[78:96]'
M_DQS_POLICY='task3_M_DDR_init_DQS_local_and_central_reset_max6p5_v3'
M_HOLD_POLICY='task3_M_DDR_config_and_HOLD_publishers_local_reset_max6p5_v4'
# Exact custom-board lane order, observed at R73/R100/R91/R82 C0 in M v39.
# These regions move only the original config FF and its HOLD LUT.
M_DQS_REGIONS=('R[69:78]C[2:18]','R[96:105]C[2:18]',
               'R[87:96]C[2:18]','R[78:87]C[2:18]')


def require(ok,message):
    if not ok:raise ValueError('preboard DDR timing: '+message)


def tighten(cst,sdc,routed_netlist,*,role=None,dqs_hold_locality=False,hold_i_locality=False):
    require(role in (None,'M','W'),'unknown physical role')
    require(not dqs_hold_locality or role=='M','DQS locality requires explicit M')
    require(not hold_i_locality or dqs_hold_locality,'HOLD publisher locality requires M DQS policy')
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
    policy=M_HOLD_POLICY if hold_i_locality else M_DQS_POLICY if dqs_hold_locality else W_POLICY if role=='W' else POLICY
    reset_region=W_RESET_REGION if role=='W' or dqs_hold_locality else DDR_FAR_LAUNCH_REGION
    reset_sinks=[];extra=''
    if role=='W' or dqs_hold_locality:
        # W v15 placed reset at R105C179; the actual initialization CLEAR at
        # R65C23 then had 8.455ns data delay and -0.527ns recovery. Retain the
        # opposite-corner initialization data path, but centralize its reset
        # source and constrain every actual direct vendor reset receiver.
        reset_net=n.pin(INVERTER,'O')
        reset_sinks=sorted(p+'/CLEAR' for p,c in n.cells.items()
            if p.startswith(DDR_PHY+'/') and c['kind']=='DFFCE' and
               n.pin(p,'CLEAR')==reset_net)
        require(len(reset_sinks)==39 and DDR_LAUNCH+'/CLEAR' in reset_sinks and
                DDR_CAPTURE+'/CLEAR' in reset_sinks and
                all(n.pin(p.rsplit('/',1)[0],'CLK') in ('clk_50m','memory_clk') for p in reset_sinks),
                'W direct vendor functional reset receiver inventory changed')
        extra='set_max_delay 6.500 -from [get_pins {'+RESET+'/Q}] -to [get_pins {'+' '.join(reset_sinks)+'}]\n'
    dqs=[];dqs_lines=[]
    if dqs_hold_locality:
        power={n.pin(p,'V')for p,c in n.cells.items()if c['kind']=='VCC'}
        for lane,region in enumerate(M_DQS_REGIONS):
            config=f'{DDR_PHY}/u_ddr_init/read_rclksel_conf_{lane}_s0'
            hold=f'{DDR_PHY}/u_ddr_init/hold_gen[{lane}].hold_i_s0'
            gate=f'{DDR_PHY}/u_ddr_init/hold_Z_{lane}_s'
            hard=f'{DDR_PHY}/u_ddr_phy_wds/data_lane_gen[{lane}].u_ddr_phy_data_lane/u_ddr_phy_data_io/u_dqs'
            require(all(p in n.cells for p in (config,gate,hard)),'DQS boundary missing')
            ff,lut,dq=(n.cells[p]for p in (config,gate,hard))
            require(ff['kind']=='DFFCE' and ff['parameters']=={'INIT':"1'b0"} and
                    set(ff['ports'])=={'D','Q','CLK','CE','CLEAR'} and
                    n.pin(config,'D')in power and lut['kind']=='LUT2' and
                    lut['parameters']=={'INIT':"4'h4"} and
                    set(lut['ports'])=={'I0','I1','F'} and dq['kind']=='DQS' and
                    dq['parameters'].get('DQS_MODE')=='"X4"','DQS FF/LUT/primitive configuration changed')
            require(n.pin(config,'Q')==n.pin(gate,'I0') and
                    n.pin(gate,'F')==n.pin(hard,'HOLD') and
                    n.pin(config,'CLEAR')==n.pin(hard,'RESET') and
                    n.pin(config,'CLK')==n.pin(hard,'PCLK')==n.pin(DDR_PHY+'/fclkdiv','CLKOUT'),
                    'DQS HOLD data/reset/clock topology changed')
            require(all(p not in ct for p in (config,gate)),'DQS config already constrained')
            dqs_lines += [f'INS_LOC "{p}" {region};'for p in (config,gate)]
            dqs.append(dict(lane=lane,config=config,gate=gate,DQS=hard,region=region,
                            vendor_topology_unchanged=True))
            if hold_i_locality:
                require(hold in n.cells and n.cells[hold]['kind']=='DFFCE' and
                        n.pin(hold,'CLK')==n.pin(config,'CLK') and
                        n.pin(hold,'Q')==n.pin(gate,'I1') and hold not in ct,
                        'DQS HOLD publisher/clock/topology changed')
                dqs_lines.append(f'INS_LOC "{hold}" {region};')
                dqs[-1]['hold_publisher']=hold
    adapted_cst=cst+(f'\n# {policy}\nINS_LOC "{RESET}" {reset_region};\n'+
                     '\n'.join(dqs_lines)+('\n'if dqs_lines else '')).encode()
    adapted_sdc=st.replace(DDR_STRICT_MINIMUM,MINIMUM,1)+(f'\n# {policy}\n'+MAXIMUM+'\n'+extra)
    require(adapted_sdc.replace(MINIMUM,DDR_STRICT_MINIMUM,1).split('\n# '+policy+'\n')[0]==st,
            'unrelated timing constraints changed')
    return adapted_cst,adapted_sdc.encode(),dict(policy=policy,
        source_reset=RESET,launch=DDR_LAUNCH,capture=DDR_CAPTURE,
        exact_vendor_functional_reset_inversion_proven=True,
        minimum_data_delay_ns=0.8,maximum_functional_reset_delay_ns=7.5,
        original_finite_hold_relationship_restored=True,
        clock_skew_and_native_hold_checks_retained=True,
        previous_minimum_ns=3.5,reset_region=reset_region,
        all_direct_vendor_reset_sinks=reset_sinks,
        all_direct_vendor_reset_maximum_ns=6.5 if role=='W' or dqs_hold_locality else None,
        **(dict(diagnosed_DQS_HOLD_boundaries=dqs)if dqs_hold_locality else {}),
        before_cst_sha256=digest(cst),before_sdc_sha256=digest(sdc),
        after_cst_sha256=digest(adapted_cst),after_sdc_sha256=digest(adapted_sdc.encode()),
        false_paths_added=False,clock_periods_changed=False,vendor_bytes_changed=False,
        routed_timing_verified=False,hardware_tested=False)
