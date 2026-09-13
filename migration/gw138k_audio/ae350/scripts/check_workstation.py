#!/usr/bin/env python3
"""Audit complete routed workstation: existing DDR/video/audio plus CPU/control."""
import argparse,hashlib,json,os,re,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'scripts'))
from check_audio_build import inspect as inspect_audio
from check_video_pll_init import RoutedDesign,require
from gowin_paths import gowin_simlib

def trace_cpu_control(d,net,endpoint,role,visiting=None):
    """Allow only the proven identical two-bit init-enable chain to be shared.
    Gowin may merge the CPU/video reference helpers' unconditional enable
    registers. State and ROM data must still belong to the CPU's own helper.
    """
    helper='u_cpu_pll/u_pll_init'
    if net in d.constants:return dict(total_ns=0,sources=[])
    visiting=set() if visiting is None else visiting
    require(net not in visiting,'CPU PLL control combinational loop')
    name,output=d.drivers[net];kind,ports=d.cells[name]
    if kind.startswith('DFF'):
        if name.startswith(helper+'/'):return d.trace(net,endpoint,helper,role)
        shared='u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/'
        require(role=='RESET' and name==shared+'enable_r_1_s0','unapproved shared CPU PLL source '+name)
        first=shared+'enable_r_0_s0';p0=d.cells[first][1]
        reset=d.cells['u_cpu_pll/pll_control_9_s0'][1]['PRESET']
        require(d.cells[first][0]=='DFFCE' and kind=='DFFCE','shared init enable cell type')
        require(p0['CLK']==ports['CLK']==d.clock_net and p0['CLEAR']==ports['CLEAR']==reset,'shared enable clock/reset differs from CPU helper reset')
        require(d.constants.get(p0['D'])==1 and d.constants.get(p0['CE'])==1 and d.constants.get(ports['CE'])==1 and ports['D']==p0['Q'],'shared enable is not a two-cycle shift of constant one')
        require(d.parameters.get((first,'INIT'))=="1'b0" and d.parameters.get((name,'INIT'))=="1'b0",'shared enable initial values differ')
        return dict(total_ns=d.input_delay+d.route('clk_50m_ibuf/O',name+'/CLK')+d.arc(name,'CLK','Q')+d.route(name+'/Q',endpoint),sources=[name],shared_enable_proven=True)
    require(kind=='INV' or re.fullmatch(r'LUT[1-6]',kind),'unsupported CPU PLL control primitive '+kind)
    pins=['I'] if kind=='INV' else [f'I{i}' for i in range(int(kind[3:]))]
    candidates=[];sources=[]
    for pin in pins:
        child=trace_cpu_control(d,ports[pin],name+'/'+pin,role,visiting|{net})
        if child['sources']:
            sources.extend(child['sources']);candidates.append(child['total_ns']+d.arc(name,pin,output)+d.route(name+'/'+output,endpoint))
    require(candidates,'constant CPU PLL control cone needs review')
    return dict(total_ns=max(candidates),sources=sorted(set(sources)))

def inspect(build, *, existing_audit_command=None, cpu_control_trace=trace_cpu_control):
    stage=build/'Prj1';pnr=stage/'impl/pnr'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs=json.loads((build/'workstation_inputs.json').read_text())
    require(all(sha(stage/f)==h for f,h in inputs.items()),'frozen input changed')
    env=dict(os.environ,GOWIN_SIMLIB=str(gowin_simlib()),PRJ1_DDR_REFERENCE=str(next((build/'reference').glob('*.vo'))))
    # Board extensions can provide a stricter external audit of new routes /
    # synthesis sharing while retaining the frozen original checkers verbatim.
    command=existing_audit_command or [sys.executable,'scripts/check_build.py']
    p=subprocess.run(command,cwd=stage,env=env,capture_output=True,text=True)
    (build/'check_existing.log').write_text(p.stdout+p.stderr)
    require(p.returncode==0,'existing DDR/video audit failed: '+p.stdout[-1800:]+p.stderr[-500:])
    audio=inspect_audio(stage,audio_prefix='u_managed/u_audio')
    audio['limitations']=['Analog audio and HDMI reception require connected peripherals.']
    d=RoutedDesign((pnr/'Prj1.sdf').read_text(),(pnr/'Prj1.vo').read_text())
    cpus=[n for n,(kind,_) in d.cells.items() if kind=='AE350_SOC'];require(len(cpus)==1,'physical AE350 count')
    pll='u_cpu_pll/PLL_inst';ports=d.cells[pll][1];soc=d.cells[cpus[0]][1]
    require(soc['CORE_CLK']==ports['CLKOUT1'],'CPU dedicated clock changed')
    require(all(soc[x]==ports['CLKOUT0'] for x in ['AHB_CLK','APB_CLK','DDR_CLK']),'CPU bus aliases changed')
    for port in ['CORE_CE','AXI_CE','DDR_CE','AHB_CE','APB2AHB_CE']:require(d.constants.get(soc[port])==1,'clock disabled '+port)
    for k,v in {'FCLKIN':'"50"','MDIV_SEL':'24','MDIV_FRAC_SEL':'0','ODIV0_SEL':'24','ODIV1_SEL':'12','CLKOUT1_EN':'"TRUE"'}.items():
        require(d.parameters.get((pll,k))==v,'CPU PLL '+k)
    cst=(stage/'constraints/tang_mega_138k.cst').read_text()
    require('INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];' in cst,'CPU PLL placement')
    clocks=audio['timing']['clocks']
    for port,mhz in [('CLKOUT0',50),('CLKOUT1',100)]:
        found=[x for x in clocks if x['object']==pll+'/'+port]
        require(len(found)==1 and found[0]['frequency_mhz']==mhz,'missing/wrong CPU clock constraint')
    paths=[]
    for bus in ['ICPSEL','LPFRES','RESET']:
        for index,net in enumerate(reversed(d.bits(ports[bus]))):
            if net in d.constants:continue
            role=bus if bus=='RESET' else f'{bus}[{index}]';source,pin=d.drivers[net]
            require(source.startswith('u_cpu_pll/pll_control') and pin=='Q','PLL control retiming missing')
            require(d.cells[source][1]['CLK']==d.clock_net,'PLL helper retiming clock')
            upstream=cpu_control_trace(d,d.cells[source][1]['D'],source+'/D',role)
            flight=d.input_delay+d.route('clk_50m_ibuf/O',source+'/CLK')+d.arc(source,'CLK','Q')+d.route(source+'/Q',pll+'/'+role)
            require(flight<=10,'CPU PLL initialization >10ns')
            paths.append(dict(endpoint=role,total_ns=flight,upstream=upstream))
    cdc=[]
    groups=[('u_managed/u_control_cdc/','request_held','request_local',49),
            ('u_managed/u_control_cdc/','response_held','response_local',33),
            ('u_runtime/u_cpu_cdc/','held_data','destination_data',224)]
    cpu_ddr=any(n.startswith('u_cpu_ddr/') for n in d.cells)
    cpu_ui=any(n.startswith('u_ui_control/') for n in d.cells)
    pc_midi=any(n.startswith('u_managed/u_audio/u_pc_rx/') for n in d.cells)
    if pc_midi:
        groups += [('u_managed/u_audio/u_pc_cdc/','held_data','destination_data',8),('u_runtime/u_performance_cdc/','held_data','destination_data',448)]
        require('IO_LOC "pc_uart_rx_i" V14;' in cst and 'IO_LOC "midi_rx_i" P16;' in cst,'independent PC/G1 pin binding')
        for prefix in ['u_managed/u_audio/u_pc_rx/','u_managed/u_audio/u_midi_rx/']:
            first=[n for n,(kind,_) in d.cells.items() if n.startswith(prefix+'rx_sync_0') and kind.startswith('DFF')]
            second=[n for n,(kind,_) in d.cells.items() if n.startswith(prefix+'rx_sync_1') and kind.startswith('DFF')]
            require(len(first)==1 and len(second)==1 and d.cells[second[0]][1]['D']==d.cells[first[0]][1]['Q'],'UART RX two-stage synchronizer '+prefix)
        for bit in [0,1]:
            first=[n for n,(kind,_) in d.cells.items() if n.startswith('u_managed/u_audio/pc_health_meta_'+str(bit)+'_') and kind.startswith('DFF')]
            second=[n for n,(kind,_) in d.cells.items() if n.startswith('u_managed/u_audio/pc_health_sync_'+str(bit)+'_') and kind.startswith('DFF')]
            require(len(first)==1 and len(second)==1 and d.cells[second[0]][1]['D']==d.cells[first[0]][1]['Q'],'PC health synchronizer')
        require(any(n.startswith('u_video/u_scanout/composite_active') and kind.startswith('DFF') for n,(kind,_) in d.cells.items()),'simultaneous graph composition absent')
        require(any(n.startswith('u_video/u_scanout/analysis_base') and kind.startswith('DFF') for n,(kind,_) in d.cells.items()),'analysis page not held for whole frame')
    if cpu_ui:
        require(cpu_ddr,'UI without CPU DDR')
        groups += [('u_ui_control/','request_held','request_local',49),('u_ui_control/','response_held','response_local',33)]
        top=(stage/'src/ae350/gw138k_ui_workstation_top.v').read_text()
        display=(stage/'src/video/hdmi_display.v').read_text()
        require('20\'hf8020' in top and '.input_attached(1\'b0)' in top,'UI address/input binding')
        require('video_ddr_scanout #(.EXPLICIT_BASE(1))' in display and '.new_frame_base(selected_base)' in display,'explicit scanout base disabled')
        require('.front_bank(analysis_bank),.frame_swap(analysis_commit)' in display,'analysis writer ownership disconnected')
        for base in ['u_video/u_view/analysis_eligible','u_video/u_view/ui_eligible','u_video/u_scanout/front_base','u_ui_services/pending','ui_report']:
            require(any(n.startswith(base) and kind.startswith('DFF') for n,(kind,_) in d.cells.items()),'UI retained state absent '+base)
        require((stage/'firmware/ui_main.c').is_file(),'missing UI firmware')
    if cpu_ddr:
        require(d.constants.get(soc['DDR_HREADY']) is None,'CPU external DDR HREADY tied off')
        groups += [('u_cpu_ddr/','request_held','request_local',96),('u_cpu_ddr/','response_held','response_local',64)]
        pending=[n for n,(kind,_) in d.cells.items() if n.startswith('u_video/u_arbiter/cpu_read_pending') and kind.startswith('DFF')]
        require(len(pending)==1,'CPU read ownership/reset drain guard absent')
    for base,src,dst,width in groups:
        targets=[n for n,(kind,_) in d.cells.items() if n.startswith(base+dst) and kind.startswith('DFF')]
        # Constant zero payload bits may be pruned; verify every live bit.
        require(targets and len(targets)<=width,'CDC payload count '+base+dst)
        flights=[]
        for target in targets:
            source,pin=d.drivers[d.cells[target][1]['D']]
            require(source.startswith(base+src) and pin=='Q','CDC payload source changed '+target)
            flight=d.arc(source,'CLK','Q')+d.route(source+'/Q',target+'/D');require(flight<=20,'CDC >20ns '+target)
            flights.append(flight)
        cdc.append(dict(name=base+dst,retained_bits=len(targets),maximum_ns=max(flights)))
    for base in ['u_managed/u_control_cdc/','u_runtime/u_cpu_cdc/']+(['u_cpu_ddr/'] if cpu_ddr else [])+(['u_ui_control/'] if cpu_ui else [])+(['u_managed/u_audio/u_pc_cdc/','u_runtime/u_performance_cdc/'] if pc_midi else []):
        for first,second in [('req_meta','req_sync'),('ack_meta','ack_sync')]:
            targets=[n for n,(kind,_) in d.cells.items() if n.startswith(base+first+'_') and kind.startswith('DFF')]
            require(len(targets)==1,'CDC first stage missing '+base+first)
            matches=[n for n,(kind,p) in d.cells.items() if n.startswith(base+second+'_') and kind.startswith('DFF') and p['D']==d.cells[targets[0]][1]['Q']]
            require(len(matches)==1,'CDC second stage missing '+base+second)
    base='u_managed/u_midi_drop_cdc/'
    targets=[n for n,(kind,_) in d.cells.items() if n.startswith(base+'meta') and kind.startswith('DFF')]
    require(len(targets)==32,'MIDI drop Gray bus must retain all 32 bits')
    flights=[]
    for target in targets:
        source,pin=d.drivers[d.cells[target][1]['D']]
        require(source.startswith(base+'gray') and pin=='Q','MIDI drop Gray source is not registered')
        second=[n for n,(kind,p) in d.cells.items() if n.startswith(base+'sync_value') and kind.startswith('DFF') and p['D']==d.cells[target][1]['Q']]
        require(len(second)==1,'MIDI drop second synchronizer missing')
        flight=d.arc(source,'CLK','Q')+d.route(source+'/Q',target+'/D');require(flight<=20,'MIDI drop Gray >20ns')
        flights.append(flight)
    cdc.append(dict(name=base+'gray',retained_bits=32,maximum_ns=max(flights)))
    resource=ET.parse(stage/'impl/gwsynthesis/Prj1_syn_rsc.xml').getroot()
    modules={n.attrib['name']:n.attrib for n in resource.iter('SubModule')}
    require(int(modules['recorder']['Bsram'])==3 and int(modules['score']['Bsram'])==2,'recorder/score memories absent')
    header=(pnr/'Prj1.fs').read_text()[:1100]
    require('//Device Version: C' in header and '//Part Number: GW5AST-LV138PG484AC2/I1' in header,'wrong target')
    return dict(passed=True,hardware_tested=False,bitstream_sha256=sha(pnr/'Prj1.fs'),usercode=re.search(r'//UserCode: (0x[0-9A-Fa-f]+)',header)[1],
        expression_controls=pc_midi and 'input wire [447:0] performance_words' in (stage/'src/ae350/gw138k_performance_uart.sv').read_text(),
        frozen_inputs=len(inputs),audio=audio,ae350=cpus[0],cpu_external_ddr=cpu_ddr,cpu_ui=cpu_ui,pc_midi=pc_midi,simultaneous_graphs=pc_midi,cpu_pll_paths=paths,control_cdc=cdc,resource=resource.attrib,
        artifact_sha256={f.name:sha(f) for f in [pnr/'Prj1.fs',pnr/'Prj1.vo',pnr/'Prj1.sdf',pnr/'Prj1.tr']})

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('build',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args();out=a.output or a.build/'workstation_audit.json'
    if out.exists():ap.error('refuse to replace evidence')
    try:r=inspect(a.build.resolve())
    except (ValueError,KeyError,OSError) as e:r=dict(passed=False,error=str(e))
    out.write_text(json.dumps(r,indent=2)+'\n');print({k:v for k,v in r.items() if k not in ['audio','cpu_pll_paths']})
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
