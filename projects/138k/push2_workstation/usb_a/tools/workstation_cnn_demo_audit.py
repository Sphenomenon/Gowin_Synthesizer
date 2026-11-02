"""Physical gates for the explicit CNN filming composition; no board actions.

The complete-workstation gates retain their original feature requirements.
Only this profile selects three PLLs and the fixed-reference native DAC.
"""
from pathlib import Path
import json
import re


def inspect_retirement(cells, parameters, sdc):
    retired = ('u_lcd/', 'u_cpu/', 'u_bluetooth/', 'u_runtime/',
               'u_video/u_renderer/', 'u_video/u_scanout/', 'u_video/u_dvi/',
               'u_video/u_clock/', 'u_delay_dma/')
    assert not any(name.startswith(retired) for name in cells), 'CNN retired hierarchy remains'
    assert not any(kind in ('OSER10', 'DCS') for kind, ports in cells.values()), 'CNN display/rate selector remains'
    assert {name for name, (kind, ports) in cells.items() if kind == 'CLKDIV'} == {
        'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv'}, 'CNN divider inventory changed'
    ground = {ports['G'] for kind, ports in cells.values() if kind == 'GND'}
    high = {ports['V'] for kind, ports in cells.values() if kind == 'VCC'}
    for port in ('tmds_clk_p', 'tmds_clk_n', *(f'tmds_data_{side}[{bit}]'
                  for side in ('p', 'n') for bit in range(3))):
        hits = [(kind, pins) for kind, pins in cells.values() if pins.get('O') == port]
        assert len(hits) == 1 and hits[0][0] == 'OBUF' and hits[0][1]['I'] in ground, 'CNN TMDS pin active: ' + port
    assert not any(clock in sdc for clock in ('video_ref49', 'video_serial742', 'video_pixel148', 'selected44')), 'CNN retired clock remains'
    reference = cells['clk_12m288_ibuf']
    assert reference == ('IBUF', {'I':'clk_12m288', 'O':'dac_mclk_d'}), 'CNN DAC reference changed'
    for port, source in (('dac_mclk','dac_mclk_d'), ('hp_bck','hp_bck_d'),
                         ('hp_ws','hp_ws_d'), ('hp_din','hp_din_d')):
        hits = [(name, kind, pins) for name, (kind, pins) in cells.items() if pins.get('O') == port]
        assert len(hits) == 1 and hits[0][1:] == ('OBUF', {'I':source,'O':port}), 'CNN serial pin changed: ' + port
        if port != 'dac_mclk':
            drivers = [(name, kind, pins) for name, (kind,pins) in cells.items() if pins.get('Q') == source]
            assert len(drivers) == 1 and drivers[0][0].startswith('u_fpc_audio/') and \
                drivers[0][1].startswith('DFF') and drivers[0][2]['CLK'] == 'dac_mclk_d', 'CNN serial clock changed: ' + port
    stages = [cells[f'u_fpc_audio/release_pipe_{bit}_s0'] for bit in range(4)]
    for bit, (kind, pins) in enumerate(stages):
        assert kind == 'DFFCE' and pins['CLK'] == 'dac_mclk_d' and pins['CE'] in high, 'CNN DAC release clock changed'
        assert pins['CLEAR'] == stages[0][1]['CLEAR'], 'CNN DAC release reset changed'
        assert (pins['D'] in high if bit == 0 else pins['D'] == stages[bit-1][1]['Q']), 'CNN DAC release chain changed'
        assert parameters[(f'u_fpc_audio/release_pipe_{bit}_s0','INIT')] == "1'b0", 'CNN DAC release initialization changed'
    return dict(profile='CNN-DEMO', no_display_or_rate_selector=True, static_low_TMDS=True,
                DAC_reference_hz=12288000, local_release_stages=4, serial_pins_directly_registered=True)


def shared_plls(design):
    from fractions import Fraction
    expected = {'u_audio_clock/g_hardware.u_pll/PLL_inst', 'u_usb_pll/PLL_inst',
                'u_memory/u_pll/u_pll_0/PLL_inst'}
    assert {name for name,(kind,ports) in design.cells.items() if kind=='PLL'} == expected, 'CNN PLL inventory changed'
    frequency={}
    for instance,output,mhz in (('u_audio_clock/g_hardware.u_pll/PLL_inst',0,Fraction('76.8')),
            ('u_usb_pll/PLL_inst',0,Fraction(48)),('u_memory/u_pll/u_pll_0/PLL_inst',2,Fraction(400))):
        params={key:value for (cell,key),value in design.parameters.items() if cell==instance}
        assert design.cells[instance][1]['CLKIN']==design.clock_net, 'PLL reference clock changed'
        for key,value in dict(FCLKIN='"50"',IDIV_SEL='1',FBDIV_SEL='1',CLKFB_SEL='"INTERNAL"',
                DYN_MDIV_SEL='"FALSE"',DYN_IDIV_SEL='"FALSE"',DYN_FBDIV_SEL='"FALSE"').items():
            assert params[key]==value,'PLL parameter changed: '+instance+'/'+key
        assert params[f'CLKOUT{output}_EN']=='"TRUE"' and params[f'DYN_ODIV{output}_SEL']=='"FALSE"', 'PLL output enable/divisor changed'
        multiply=Fraction(params['MDIV_SEL'])+Fraction(int(params['MDIV_FRAC_SEL']),8)
        divide=Fraction(params[f'ODIV{output}_SEL'])+Fraction(int(params.get(f'ODIV{output}_FRAC_SEL','0')),8)
        actual=50*multiply/divide
        assert actual==mhz, f'{instance}: actual {actual}MHz != {mhz}MHz'
        frequency[instance]=float(actual)
    result = {}
    for prefix in ('u_audio_clock/g_hardware.u_pll','u_usb_pll'):
        instance = prefix+'/PLL_inst'
        ports = design.cells[instance][1]
        paths = []
        for bus,width,first_bit in (('ICPSEL',6,3),('LPFRES',3,0),('RESET',1,9)):
            bits = design.bits(ports[bus])
            assert len(bits)==width, 'PLL tuple width changed'
            for bit,net in enumerate(reversed(bits)):
                endpoint = instance+'/'+(bus if bus=='RESET' else f'{bus}[{bit}]')
                if net in design.constants:
                    assert design.constants[net]==0, 'PLL control constant changed: '+endpoint
                    paths.append(dict(endpoint=endpoint,constant=0,total_ns=0));continue
                source,pin = design.drivers[net]
                kind,p = design.cells[source]
                assert re.fullmatch(re.escape(prefix+f'/pll_control_{first_bit+bit}')+r'_s\d+',source), 'PLL control owner changed'
                assert kind.startswith('DFF') and pin=='Q' and p['CLK']==design.clock_net, 'PLL control clock changed'
                total = design.input_delay+design.route('clk_50m_ibuf/O',source+'/CLK')+design.arc(source,'CLK','Q')+design.route(source+'/Q',endpoint)
                assert total<=10, f'{endpoint}: {total}ns exceeds 10ns'
                paths.append(dict(endpoint=endpoint,source=source,total_ns=total))
        result[prefix]=dict(paths=paths,bound_ns=10,maximum_ns=max(p['total_ns'] for p in paths),output_mhz=frequency[instance])
    instance='u_memory/u_pll/u_pll_0/PLL_inst'
    helper='u_memory/u_pll/u_pll_init'
    paths=[]
    for bus,width in (('ICPSEL',6),('LPFRES',3),('LPFCAP',2),('RESET',1)):
        bits=design.bits(design.cells[instance][1][bus]);assert len(bits)==width
        for bit,net in enumerate(reversed(bits)):
            role=bus if bus=='RESET' else f'{bus}[{bit}]'
            endpoint=instance+'/'+role
            if bus=='LPFCAP' or bus=='ICPSEL' and bit>0:
                assert design.constants.get(net)==0, 'DDR PLL static control changed'
                path=dict(total_ns=0,constant=0)
            else:
                assert net not in design.constants,'DDR PLL helper replaced by constant'
                path=design.trace(net,endpoint,helper,role)
                assert path['total_ns']<=10, f'{endpoint}: {path["total_ns"]}ns exceeds 10ns'
            paths.append(dict(endpoint=endpoint,**path))
    result['u_memory/u_pll']=dict(paths=paths,bound_ns=10,maximum_ns=max(p['total_ns'] for p in paths),output_mhz=frequency[instance])
    return result


def routed_cdc(design, vo, native_source):
    """Check real retained mailbox, level and Gray receivers and route delays."""
    from tools.audit_clk50_cdc_routes import pointer_source
    result = dict(mailboxes={}, levels={}, gray={}, native_controls={}, native_input={})
    cells=design.cells
    def regs(prefix,stem):
        return {name:ports for name,(kind,ports) in cells.items()
                if name.startswith(prefix+'/'+stem+'_') and kind.startswith('DFF')}
    def one(prefix,stem):
        found=regs(prefix,stem)
        assert len(found)==1, f'{prefix}/{stem}: expected one FF, got {len(found)}'
        return next(iter(found.items()))
    def pair(first,second,bound=2):
        a,b=cells[first][1],cells[second][1]
        assert a['Q']==b['D'] and a['CLK']==b['CLK'], 'broken local CDC chain: '+first
        flight=design.arc(first,'CLK','Q')+design.route(first+'/Q',second+'/D')
        assert flight<=bound, f'{first}->{second}: {flight}ns exceeds {bound}ns'
        return flight
    for prefix,width,bound in (('u_song_command_cdc',4,20),('u_tf_control_cdc',24,20),
            ('u_fpc_audio/u_samples',41,10),('u_native_usb/input_owner/feedback',93,20),
            ('u_cnn_status_push_cdc',6,20)):
        chains=[]
        for first,second,source in (('req_meta','req_sync','request_toggle'),('ack_meta','ack_sync','acknowledge_toggle')):
            a,ap=one(prefix,first);b,bp=one(prefix,second);s,sp=one(prefix,source)
            assert ap['D']==sp['Q'] and ap['CLK']!=sp['CLK'], 'broken async mailbox input: '+prefix
            chains.append(dict(first=a,second=b,flight_ns=pair(a,b)))
        settled,_=one(prefix,'req_settled');sync,_=one(prefix,'req_sync');pair(sync,settled)
        payload=regs(prefix,'destination_data')
        assert len(payload)==width, f'{prefix}: payload width changed {len(payload)} != {width}'
        flights=[]
        for target,tp in payload.items():
            source,pin=design.drivers[tp['D']];kind,sp=cells[source]
            assert kind.startswith('DFF') and source.startswith(prefix+'/held_data_') and pin=='Q' and sp['CLK']!=tp['CLK'], 'mailbox payload not held FF: '+target
            flight=design.arc(source,'CLK','Q')+design.route(source+'/Q',target+'/D')
            assert flight<=bound, f'{target}: {flight}ns exceeds {bound}ns'
            flights.append(flight)
        result['mailboxes'][prefix]=dict(payload_bits=width,maximum_payload_flight_ns=max(flights),bound_ns=bound,
            request_settling_stage=True,synchronizers=chains)
    for prefix,width in (('u_music/u_trace_cdc',7),('u_cnn_error_sync',2)):
        first=regs(prefix,'meta');second=regs(prefix,'sync')
        assert len(first)==len(second)==width, 'level synchronizer width changed: '+prefix
        chains=[]
        for a,ap in first.items():
            targets=[b for b,bp in second.items() if bp['D']==ap['Q']]
            assert len(targets)==1, 'level synchronizer bypassed: '+a
            b=targets[0];flight=pair(a,b)
            consumers=[(name,pin) for name,(kind,pins) in cells.items() for pin,net in pins.items()
                       if net==ap['Q'] and not (name==a and pin=='Q')]
            assert consumers==[(b,'D')], 'metastability stage has additional consumers: '+a
            chains.append(dict(first=a,second=b,flight_ns=flight))
        result['levels'][prefix]=chains
    # Complete the additional CNN request/reply and TF byte FIFO pointers;
    # the historical checker separately covers PCM, score and playlist FIFOs.
    for prefix,msb,names in (
            ('u_music/u_ddr_req_cdc',4,('read_gray','write_gray','read_gray_meta','write_gray_meta','read_gray_sync','write_gray_sync','read_binary','write_binary')),
            ('u_music/u_ddr_rsp_cdc',2,('read_gray','write_gray','read_gray_meta','write_gray_meta','read_gray_sync','write_gray_sync','read_binary','write_binary')),
            ('u_tf_audio/u_path/u_capture_fifo',12,('rd_gray','wr_gray','rd_gray_w1','wr_gray_r1','rd_gray_w2','wr_gray_r2','rd_bin','wr_bin')),
            ('u_tf_audio/u_path/u_playback_fifo',12,('rd_gray','wr_gray','rd_gray_w1','wr_gray_r1','rd_gray_w2','wr_gray_r2','rd_bin','wr_bin'))):
        for direction in (0,1):
            gray,meta,second,binary=(names[direction+offset] for offset in (0,2,4,6))
            first=regs(prefix,meta);seconds=regs(prefix,second)
            assert len(first)==len(seconds)==msb+1, 'Gray width changed: '+prefix+'/'+meta
            flights=[]
            for target,tp in first.items():
                source,pin,gates=pointer_source(design,vo,tp['D'],tp['CLK'],prefix)
                kind,sp=cells[source]
                assert kind.startswith('DFF') and pin=='Q' and sp['CLK']!=tp['CLK'] and (
                    source.startswith(prefix+'/'+gray+'_') or source.startswith(prefix+'/'+binary+'_'+str(msb)+'_')), 'Gray source changed: '+target
                following=[name for name,p in seconds.items() if pointer_source(design,vo,p['D'],p['CLK'],prefix)[:2]==(target,'Q')]
                assert len(following)==1, 'Gray second stage missing: '+target
                flight=design.arc(source,'CLK','Q');last=source+'/Q'
                for gate in gates:
                    ports=cells[gate][1]
                    input_pin=next(key for key,value in ports.items() if key.startswith('I') and design.drivers[value]==(source,'Q'))
                    flight+=design.route(last,gate+'/'+input_pin)+design.arc(gate,input_pin,'F');last=gate+'/F'
                flight+=design.route(last,target+'/D')
                assert flight<=10, f'{target}: Gray flight {flight} exceeds 10ns'
                flights.append(flight)
            result['gray'][prefix+'/'+gray]=dict(bits=len(first),maximum_flight_ns=max(flights),bound_ns=10)
    for label,entry in native_source['usb2']['controls'].items():
        flights=[]
        for bit,source in entry['source_registers'].items():
            first=entry['first_stage'][bit];second=entry['second_stage'][bit]
            sp,fp=cells[source][1],cells[first][1]
            assert fp['D']==sp['Q'] and fp['CLK']!=sp['CLK'], 'native USB CDC origin changed'
            flights.append(pair(first,second))
        result['native_controls'][label]=dict(bits=len(flights),maximum_flight_ns=max(flights),bound_ns=2)
    for label,entry in native_source['input_fifo']['pointers'].items():
        flights=[]
        for bit,source in entry['source_registers'].items():
            first=entry['first_stage'][bit];second=entry['second_stage'][bit]
            sp,fp=cells[source][1],cells[first][1]
            assert fp['D']==sp['Q'] and fp['CLK']!=sp['CLK'], 'native input Gray origin changed'
            flight=design.arc(source,'CLK','Q')+design.route(source+'/Q',first+'/D')
            assert flight<=10,'native input Gray flight exceeds 10ns'
            pair(first,second);flights.append(flight)
        result['native_input'][label]=dict(bits=len(flights),maximum_flight_ns=max(flights),bound_ns=10)
    return result


def routed_constraints(sdc, netlist, timing_report):
    """Resolve every member against expanded VO, including encrypted DDR cells."""
    import fnmatch
    universes=dict(get_regs={p for p,c in netlist.cells.items() if c['kind'].startswith('DFF')},
        get_pins={p+'/'+pin for p,c in netlist.cells.items() for pin in c['ports']},
        get_ports=set(netlist.directions['workstation_custom_138k_top']),
        get_clocks=set(re.findall(r'^create_(?:generated_)?clock -name (\S+)',sdc,re.M)))
    resolved={}
    for kind,body in re.findall(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]',sdc):
        for member in body.split():
            key=kind+' '+member
            if key in resolved:continue
            matches=sorted(p for p in universes[kind] if p==member or fnmatch.fnmatchcase(p,member))
            assert matches,'unresolved routed selector: '+key
            resolved[key]=len(matches)
    normalize=lambda line:' '.join(line.split())
    section=timing_report[timing_report.rfind('\n3.8 Timing Constraints Report'):]
    reported={normalize(body):state for state,body in re.findall(r'^\s*TC_\S+\s+(\S+)\s+(.+)',section,re.M)}
    commands=[normalize(line) for line in sdc.splitlines() if re.match(
        r'\s*(?:create_(?:generated_)?clock|set_(?:false_path|max_delay|min_delay|input_delay|output_delay|multicycle_path|clock_groups))\b',line)]
    missing=[line for line in commands if reported.get(line)!='Actived']
    assert not missing,'inactive routed constraints: '+str(missing)
    return dict(all_members_resolved=True,encrypted_DDR_expanded=True,all_commands_active=True,
                selectors=resolved,command_count=len(commands))


def ddr_source_proofs(stage, output):
    """Re-execute the sealed vendor sequence/configuration proofs in a new view."""
    import os
    import subprocess
    import sys
    stage, output = Path(stage).resolve(), Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    for name in ('scripts','vendor'):
        (output/name).symlink_to(stage/name,target_is_directory=True)
    reference=Path(__file__).resolve().parents[1]/'vendor/ddr3_reference/ddr3_memory_interface.vo'
    (output/'reference').mkdir()
    (output/'reference/ddr3_memory_interface.vo').symlink_to(reference)
    (output/'reference/ddr3_memory_interface.v').symlink_to(stage/'vendor/gowin_ddr3/ddr3_memory_interface.v')
    evidence=output/'docs/evidence';evidence.mkdir(parents=True)
    env=dict(os.environ,PRJ1_DDR_REFERENCE=str(output/'reference/ddr3_memory_interface.vo'),
             GOWIN_SIMLIB='/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a')
    for script, name in (('audit_ddr_reset_sequence.py','ddr_reset_sequence.json'),
                         ('audit_ddr_configuration_paths.py','ddr_configuration_paths.json')):
        run=subprocess.run([sys.executable,'-B',str(stage/'scripts'/script),'--output',str(evidence/name)],
                           env=env,capture_output=True,text=True,timeout=180)
        (output/(script+'.stdout')).write_text(run.stdout)
        (output/(script+'.stderr')).write_text(run.stderr)
        if run.returncode:raise ValueError(script+' failed; preserved logs in '+str(output))
    sys.path.insert(0,str(stage/'scripts'))
    import check_build
    check_build.ROOT=output
    check_build.DDR_AUDIT_SOURCE=reference
    previous=os.environ.get('GOWIN_SIMLIB')
    os.environ['GOWIN_SIMLIB']=env['GOWIN_SIMLIB']
    try:
        errors,reset=check_build.inspect_ddr_audit()
        config_errors,config=check_build.inspect_ddr_configuration_audit()
    finally:
        if previous is None:os.environ.pop('GOWIN_SIMLIB',None)
        else:os.environ['GOWIN_SIMLIB']=previous
    if errors+config_errors:raise ValueError(str(errors+config_errors))
    return dict(reset=reset,configuration=config)


def audit(candidate, physical, output):
    """Fresh, reviewable profile gate using maintained source and routed checks."""
    import sys
    from tools.workstation_cnn_demo import sha
    from tools.workstation_synthesis_netlist import SynthesisNetlist
    from tools.workstation_serializer_startup_audit import normalize_audio_only_sdf,inspect_serializer_startup
    from tools.audit_workstation_timing import audit as timing_audit
    from tools.audit_clk50_cdc_routes import audit as historical_cdc
    from tools.workstation_custom_usb2_cdc import audit_usb2_cdc
    from tools.workstation_custom_input_cdc import audit_input_fifo
    candidate,physical,output=(Path(p).resolve() for p in (candidate,physical,output))
    output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((candidate/'cnn_demo.json').read_text())
    inputs=json.loads((physical/'physical_inputs.json').read_text())
    assert inputs['candidate_identity']==manifest['identity'], 'physical candidate binding changed'
    stage=candidate/'workstation/Prj1'
    assert all(sha(stage/name)==value for name,value in manifest['staged_sha256'].items()), 'prepared source drift'
    assert all(sha(physical/name)==value for name,value in inputs['input_sha256'].items()), 'physical input drift'
    base=physical/'impl/pnr/custom_138k_integration'
    snapshot={str(p):sha(p) for p in physical.rglob('*') if p.is_file()}
    snapshot.update({str(stage/name):value for name,value in manifest['staged_sha256'].items()})
    sys.path.insert(0,str(stage/'scripts'));sys.path.insert(0,str(Path(__file__).resolve().parent))
    from check_video_pll_init import RoutedDesign
    vo=base.with_suffix('.vo').read_text()
    sdf,normalization=normalize_audio_only_sdf(base.with_suffix('.sdf').read_text(),vo)
    design=RoutedDesign(sdf,vo)
    ddr=ddr_source_proofs(stage,output/'ddr-source')
    startup_errors,startup=inspect_serializer_startup(sdf,vo,ddr['reset'],(physical/'physical.sdc').read_text(),startup_grant_role='CNN-DEMO')
    assert not startup_errors,str(startup_errors)
    pll=shared_plls(design)
    timing=timing_audit(physical,report_path=base.with_name(base.name+'_tr_content.html'),targets=dict(
        clk_50m=50.,ulpi_60m=60.,dac_ref12m288=12.288,audio_76m8=76.8,usb_48m=48.,ddr_mem400=400.,ddr_ui100=100.))
    constraints=routed_constraints((physical/'physical.sdc').read_text(),
        SynthesisNetlist(vo,'workstation_custom_138k_top'),base.with_suffix('.tr').read_text())
    vg=(physical/'custom_138k_integration.vg').read_text()
    root=Path(__file__).resolve().parents[1]
    clocks={'clocks':{name:{'net':net} for name,net in dict(clk_50m='clk_50m',usb_48m='usb_clk',
        ulpi_60m='usb2_ulpi_clk',audio_76m8='audio_clk').items()}}
    native=dict(usb2=audit_usb2_cdc(root,vg,clocks),input_fifo=audit_input_fifo(root,vg,clocks))
    additional=routed_cdc(design,vo,native)
    view=output/'historical/Prj1'
    (view/'impl/pnr').mkdir(parents=True);(view/'constraints').mkdir();(view/'src/migration').mkdir(parents=True)
    (view/'scripts').symlink_to(stage/'scripts')
    for suffix in ('vo','sdf'):(view/f'impl/pnr/Prj1.{suffix}').symlink_to(base.with_suffix('.'+suffix))
    (view/'constraints/tang_mega_138k.sdc').symlink_to(physical/'physical.sdc')
    (view/'src/migration/gw138k_stream_cdc.sv').symlink_to(stage/'src/migration/gw138k_stream_cdc.sv')
    historical=historical_cdc(output/'historical',pre_synchronized_diagnostics=True)
    negatives={}
    mutations=(('CNN_request_bypass','u_cnn_status_push_cdc/req_meta_s0','D','GND',lambda:routed_cdc(design,vo,native)),
        ('PLL_reset_high','u_usb_pll/PLL_inst','RESET','VCC',lambda:shared_plls(design)),
        ('DAC_reference_bypass','dac_mclk_obuf','I','GND',lambda:inspect_retirement(design.cells,design.parameters,(physical/'physical.sdc').read_text())))
    for label,cell,pin,bad,check in mutations:
        pins=design.cells[cell][1];original=pins[pin];pins[pin]=bad
        try:
            try:check()
            except (AssertionError,ValueError,KeyError) as error:negatives[label]=dict(rejected=True,reason=str(error))
            else:raise ValueError('physical negative control escaped: '+label)
        finally:pins[pin]=original
    assert all(sha(Path(name))==value for name,value in snapshot.items()), 'audit changed frozen source/route'
    dependencies={str(Path(m.__file__).resolve()):sha(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(root)}
    result=dict(schema=1,profile=manifest['name'],candidate_identity=manifest['identity'],user_code=inputs['user_code'],
        passed=timing['timing_closed'] and historical['passed'],timing=timing,pll=pll,ddr=ddr,startup=startup,
        constraints=constraints,native_source=native,historical_CDC=historical,additional_CDC=additional,
        negative_controls=negatives,sdf_normalization=normalization,input_sha256=snapshot,auditor_sha256=dependencies,
        hardware_tested=False,sram_deployed=False,flash_written=False)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
