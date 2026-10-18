#!/usr/bin/env python3
"""Audit the real AE350 primitive, dedicated clock, ROM, timing and frozen inputs."""
from pathlib import Path
import argparse,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[2]/'Mega_138K/Dev/Prj1/scripts'))
from check_video_pll_init import RoutedDesign,require

def inspect(build):
    stage=build/'project';pnr=stage/'impl/pnr'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs=json.loads((build/'inputs.json').read_text())
    require(all(sha(stage/f)==h for f,h in inputs.items()),'frozen input changed')
    tr=(pnr/'boot.tr').read_text();sdf=(pnr/'boot.sdf').read_text();vo=(pnr/'boot.vo').read_text()
    rows=re.findall(r'^\s*(clk_50m|cpu_bus50|cpu_core100)\s+(setup|hold)\s+(-?[\d.]+)\s+(\d+)\s*$',tr,re.M)
    require(len(rows)==6 and all(float(r[2])==0 and int(r[3])==0 for r in rows),'nonzero/missing timing summary')
    slacks=[float(x) for x in re.findall(r'^Slack\s*:\s*(-?[\d.]+)',tr,re.M)]
    require(slacks and min(slacks)>=0,'negative detailed setup/hold/recovery/removal slack')
    d=RoutedDesign(sdf,vo)
    cpu=[n for n,(kind,_) in d.cells.items() if kind=='AE350_SOC'];require(len(cpu)==1,'exactly one physical AE350 required')
    pll='u_cpu_pll/PLL_inst';ports=d.cells[pll][1];soc=d.cells[cpu[0]][1]
    require(soc['CORE_CLK']==ports['CLKOUT1'],'CPU not on PLL CLKOUT1')
    require(all(soc[x]==ports['CLKOUT0'] for x in ['AHB_CLK','APB_CLK','DDR_CLK']),'bus clock aliases changed')
    cst=(stage/'constraints/boot.cst').read_text()
    for line in ['IO_LOC "clk_50m" V22;','IO_LOC "button1_n" AB13;','IO_LOC "debug_uart_tx" U15;','INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];']:
        require(line in cst,'physical constraint changed: '+line)
    expected={'FCLKIN':'"50"','MDIV_SEL':'24','MDIV_FRAC_SEL':'0','ODIV0_SEL':'24','ODIV0_FRAC_SEL':'0','ODIV1_SEL':'12','CLKOUT1_EN':'"TRUE"'}
    for k,v in expected.items():require(d.parameters.get((pll,k))==v,'PLL '+k+' wrong')
    for port in ['CORE_CE','AXI_CE','DDR_CE','AHB_CE','APB2AHB_CE']:
        require(d.constants.get(soc[port])==1,'CPU clock enable disabled: '+port)
    require(any(d.constants.get(x) is None for x in d.bits(soc['ROM_HRDATA'])),'instruction bus tied off')
    paths=[]
    for bus in ['ICPSEL','LPFRES','RESET']:
        for index,net in enumerate(reversed(d.bits(ports[bus]))):
            if net in d.constants:continue
            role=bus if bus=='RESET' else f'{bus}[{index}]'
            source,pin=d.drivers[net]
            require(source.startswith('u_cpu_pll/pll_control') and pin=='Q','PLL control is not directly registered')
            require(d.cells[source][1]['CLK']==d.clock_net,'PLL control stage not on reference clock')
            # Verify the registered D input still originates in the same
            # official helper bit/state cone, then measure the new Q route.
            upstream=d.trace(d.cells[source][1]['D'],source+'/D','u_cpu_pll/u_pll_init',role)
            path={'source':source,'endpoint':role,'upstream':upstream,
                'total_ns':d.input_delay+d.route('clk_50m_ibuf/O',source+'/CLK')+
                    d.arc(source,'CLK','Q')+d.route(source+'/Q',pll+'/'+role)}
            require(path['total_ns']<=10,'PLL_INIT control exceeds 10ns')
            paths.append(path)
    require(paths,'PLL_INIT audit found no controls')
    header=(pnr/'boot.fs').read_text()[:1100]
    require('//Device Version: C' in header and '//Part Number: GW5AST-LV138PG484AC2/I1' in header,'wrong part in bitstream')
    return {'passed':True,'hardware_tested':False,'ae350_primitive':cpu[0],'bus_clock_net':ports['CLKOUT0'],
        'core_clock_net':ports['CLKOUT1'],'minimum_detailed_slack_ns':min(slacks),'setup_hold_endpoints':0,
        'maximum_pll_init_ns':max(x['total_ns'] for x in paths),'pll_init_paths':paths,
        'bitstream_sha256':sha(pnr/'boot.fs'),'usercode':re.search(r'//UserCode: (0x[0-9A-Fa-f]+)',header)[1],
        'frozen_input_count':len(inputs),'evidence_sha256':{f.name:sha(f) for f in [pnr/'boot.fs',pnr/'boot.vo',pnr/'boot.sdf',pnr/'boot.tr']}}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);a=p.parse_args();out=a.build/'routed_audit.json'
    if out.exists():p.error('refuse to replace audit')
    try:r=inspect(a.build)
    except (ValueError,KeyError,OSError) as error:r={'passed':False,'error':str(error),'hardware_tested':False}
    out.write_text(json.dumps(r,indent=2)+'\n');print(r if not r['passed'] else {k:v for k,v in r.items() if k!='pll_init_paths'})
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
