#!/usr/bin/env python3
"""Keep the existing audio/DDR/video/AE350 audits; check the new USB crossings."""
from pathlib import Path
import hashlib,importlib.util,json,re,sys
ROOT=Path(__file__).resolve().parent
b=Path(sys.argv[1]).resolve();p=b/'Prj1';out=b/'usb_a_audit.json'
assert not out.exists(),'preserve prior audit'
old=ROOT.parents[1]/'usb_host/scripts/audit.py'
spec=importlib.util.spec_from_file_location('usb_old_audit',old);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sys.path.insert(0,str(p/'scripts'))
import check_video_pll_init as video
base.install_shared_enable_proof(video)
sys.path.insert(0,str(ROOT.parents[1]/'ae350/scripts'))
import check_workstation
req=video.require
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
try:
    result=check_workstation.inspect(b,existing_audit_command=[sys.executable,str(old),str(b),'--existing'],
        cpu_control_trace=lambda d,n,e,r:d.trace(n,e,base.CPU_HELPER,r))
    d=video.RoutedDesign((p/'impl/pnr/Prj1.sdf').read_text(),(p/'impl/pnr/Prj1.vo').read_text())
    pll='u_usb_pll/PLL_inst';ports=d.cells[pll][1]
    for k,v in {'FCLKIN':'"50"','MDIV_SEL':'24','MDIV_FRAC_SEL':'0','ODIV0_SEL':'25',
                'ODIV0_FRAC_SEL':'0','CLKOUT1_EN':'"FALSE"'}.items():req(d.parameters[(pll,k)]==v,'USB PLL '+k)
    paths=[]
    for bus in ['ICPSEL','LPFRES','RESET']:
        for i,net in enumerate(reversed(d.bits(ports[bus]))):
            if net in d.constants:continue
            role=bus if bus=='RESET' else f'{bus}[{i}]'
            name,pin=d.drivers[net];kind,ff=d.cells[name]
            req(name.startswith('u_usb_pll/pll_control_') and pin=='Q' and ff['CLK']==d.clock_net,'USB PLL tuple register')
            upstream=d.trace(ff['D'],name+'/D',base.USB_HELPER,role)
            flight=d.input_delay+d.route('clk_50m_ibuf/O',name+'/CLK')+d.arc(name,'CLK','Q')+d.route(name+'/Q',pll+'/'+role)
            req(flight<=10 and upstream['total_ns']<=10,'USB PLL propagation exceeds 10ns')
            paths.append(dict(endpoint=role,flight_ns=flight))
    def regs(prefix):return {n:ports for n,(kind,ports) in d.cells.items() if n.startswith(prefix) and kind.startswith('DFF')}
    crossings=[]
    root='u_push/events/fifo/unbuffered/'
    for branch,source in [('produce_cdc','produce_w_'),('consume_cdc','consume_r_')]:
        targets=regs(root+branch+'/stage0_');req(len(targets)==7,'event FIFO Gray pointer width')
        for n,ff in targets.items():
            src,pin=d.drivers[ff['D']];kind,sp=d.cells[src]
            req(src.startswith(root+source) and pin=='Q' and kind.startswith('DFF'),'registered Gray source')
            req(sp['CLK']!=ff['CLK'],'event clock separation')
            req(sum(p2['D']==ff['Q'] for p2 in regs(root+branch+'/stage1_').values())==1,'Gray second stage')
            flight=d.arc(src,'CLK','Q')+d.route(src+'/Q',n+'/D');req(flight<10,'Gray flight exceeds 10ns')
            crossings.append(dict(source=src,target=n,flight_ns=flight))
    payloads=[]
    for root in ['u_push/feedback/','u_runtime/u_usb_cdc/']:
        targets=regs(root+'destination_data_');req(targets,'missing held snapshot')
        for n,ff in targets.items():
            src,pin=d.drivers[ff['D']];req(src.startswith(root+'held_data_') and pin=='Q','held snapshot source')
            flight=d.arc(src,'CLK','Q')+d.route(src+'/Q',n+'/D');req(flight<=20,'snapshot flight exceeds 20ns')
            payloads.append(dict(source=src,target=n,flight_ns=flight))
        for first,second in [('req_meta','req_sync'),('ack_meta','ack_sync')]:
            stages=regs(root+first+'_');req(len(stages)==1,'snapshot synchronizer '+first)
            q=next(iter(stages.values()))['Q'];req(sum(ff['D']==q for ff in regs(root+second+'_').values())==1,'snapshot second stage')
    for first,second in [('rx_dp_ms','rx_dp0_q'),('rx_dp0_q','rx_dp1_q'),('rx_dn_ms','rx_dn0_q'),('rx_dn0_q','rx_dn1_q'),('rxd_ms','rxd0_q'),('rxd0_q','rxd1_q')]:
        a=regs('u_usb_host/u_phy/'+first+'_');bb=regs('u_usb_host/u_phy/'+second+'_');req(len(a)==len(bb)==1,'USB PHY input stages')
        x=next(iter(a.values()));y=next(iter(bb.values()));req(y['D']==x['Q'] and x['CLK']==y['CLK']==ports['CLKOUT0'],'USB PHY48 resampling')
    rpt=(p/'impl/pnr/Prj1.rpt.txt').read_text()
    for name,pad in [('usb1_dp','H13'),('usb1_dn','G13')]:
        line=re.search(r'^'+name+r'\s+\|[^\n]+',rpt,re.M)
        req(line and pad+'/3' in line[0] and 'LVCMOS33' in line[0],'USB-A routed pad '+name)
    req(regs('u_usb_host/rv/'),'Vex USB Host CPU missing')
    req(not any(n.startswith('u_push/link/') for n in d.cells),'obsolete HSPI link still present')
    req((p/'src/usb_a/usbh_core.sv').read_text().count('usbh_fifo #(.DEPTH(512),.ADDR_W(9))')==2,'USB512 FIFOs')
    counts=dict(re.findall(r'<Numbers of (Setup|Hold) Violated Endpoints>:(\d+)',(p/'impl/pnr/Prj1.tr').read_text()))
    req(counts=={'Setup':'0','Hold':'0'},'timing violations')
    result.update(passed=True,hardware_tested=False,usb_cpu='VexRiscv',ch569_used=False,
        usb_pll_paths=paths,event_cdc=crossings,feedback_cdc=payloads,setup_hold=counts,
        bitstream_sha256=sha(p/'impl/pnr/Prj1.fs'),auditor_sha256=sha(Path(__file__)))
except (ValueError,KeyError,OSError,AssertionError,SystemExit) as e:
    result=dict(passed=False,error=str(e),hardware_tested=False)
out.write_text(json.dumps(result,indent=2)+'\n')
print({k:v for k,v in result.items() if k in ['passed','error','bitstream_sha256','setup_hold','usercode']})
raise SystemExit(0 if result['passed'] else 1)
