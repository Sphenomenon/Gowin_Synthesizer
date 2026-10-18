#!/usr/bin/env python3
"""Additional routed audio PLL and atomic mailbox audit; no hardware access."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
from run import TEAM
sys.path.insert(0,str(TEAM/'scripts'))
from check_video_pll_init import RoutedDesign,require
from check_build import inspect_timing

def inspect(root, audio_prefix='u_audio'):
    pnr=root/'impl/pnr'
    netlist=(pnr/'Prj1.vo').read_text()
    sdf=(pnr/'Prj1.sdf').read_text()
    report=(pnr/'Prj1.tr').read_text()
    sdc=(root/'constraints/tang_mega_138k.sdc').read_text()
    errors,timing=inspect_timing(report,sdc)
    require(not errors,'; '.join(errors))
    d=RoutedDesign(sdf,netlist)
    prefix='u_audio_clock/g_hardware.u_pll'
    pll=prefix+'/PLL_inst'; helper=prefix+'/u_pll_init'
    require(pll in d.cells and d.cells[pll][0]=='PLL','audio PLL missing')
    ports=d.cells[pll][1]
    require(ports['CLKIN']==d.clock_net,'audio PLL reference is not direct 50MHz')
    expected={'FCLKIN':'"50"','MDIV_SEL':'24','MDIV_FRAC_SEL':'0',
        'ODIV0_SEL':'15','ODIV0_FRAC_SEL':'5','IDIV_SEL':'1','FBDIV_SEL':'1',
        'CLKOUT0_EN':'"TRUE"','CLKFB_SEL':'"INTERNAL"',
        'DYN_ICP_SEL':'"TRUE"','DYN_LPF_SEL':'"TRUE"',
        'DYN_MDIV_SEL':'"FALSE"','DYN_ODIV0_SEL':'"FALSE"'}
    for key,value in expected.items(): require(d.parameters.get((pll,key))==value,f'audio PLL {key} wrong')
    require(hashlib.sha256((root/'vendor/sipeed_dvi/video_pll_init.v').read_bytes()).hexdigest()==
        'ca1e667fe6f5e9c67e566a8acbd215039b027743bd105d32e1bf91ac380e0453','PLL_INIT helper changed')
    helper_regs=[n for n,(kind,_) in d.cells.items() if n.startswith(helper+'/') and kind.startswith('DFF')]
    require(helper_regs and all(d.cells[n][1]['CLK']==d.clock_net for n in helper_regs),'PLL_INIT clock changed')
    control=[]
    for bus,width in [('ICPSEL',6),('LPFRES',3),('LPFCAP',2),('RESET',1)]:
        bits=d.bits(ports[bus]);require(len(bits)==width,'audio PLL bus width')
        for index,net in enumerate(reversed(bits)):
            role=bus if bus=='RESET' else f'{bus}[{index}]'
            if bus=='LPFCAP' or (bus=='ICPSEL' and index>=2):
                require(d.constants.get(net)==0,'audio PLL expected zero changed')
            else:
                require(net not in d.constants,'dynamic PLL_INIT output bypassed')
                path=d.trace(net,pll+'/'+role,helper,role)
                require(path['total_ns']<=10,f'audio PLL_INIT exceeds 10ns: {role}')
                control.append({'endpoint':role,**path})
    audio_clocks=[c for c in timing['clocks'] if c['object']==pll+'/CLKOUT0']
    require(len(audio_clocks)==1 and abs(audio_clocks[0]['frequency_mhz']-76.8)<0.001,'audio clock not timed at 76.8MHz')
    mailboxes=[]
    for mailbox,minimum in [('u_midi_cdc',8),('u_display_cdc',64)]:
        base=audio_prefix+'/'+mailbox+'/'
        destinations=[n for n,(kind,_) in d.cells.items() if n.startswith(base+'destination_data') and kind.startswith('DFF')]
        require(len(destinations)>=minimum,f'{mailbox}: missing payload registers')
        paths=[]
        for name in destinations:
            net=d.cells[name][1]['D'];require(net in d.drivers,'mailbox payload has no registered source')
            source,pin=d.drivers[net]
            require(source.startswith(base+'held_data') and pin=='Q','mailbox payload not held directly')
            flight=d.arc(source,'CLK','Q')+d.route(source+'/Q',name+'/D')
            require(flight<=20,'mailbox held payload flight exceeds 20ns')
            paths.append({'from':source,'to':name,'cq_plus_route_ns':flight})
        for signal,next_signal in [('req_meta','req_sync'),('ack_meta','ack_sync')]:
            stages=[n for n,(kind,_) in d.cells.items() if n.startswith(base+signal+'_') and kind.startswith('DFF')]
            require(len(stages)==1,f'{mailbox}: event synchronizer first stage missing')
            second=[n for n,(kind,p) in d.cells.items() if n.startswith(base+next_signal+'_') and kind.startswith('DFF') and p['D']==d.cells[stages[0]][1]['Q']]
            require(len(second)==1,f'{mailbox}: event synchronizer bypassed')
        mailboxes.append({'name':mailbox,'payload_bits':len(paths),'maximum_cq_plus_route_ns':max(p['cq_plus_route_ns'] for p in paths),'paths':paths})
    runtime_gray=None
    runtime_meta=[n for n,(kind,_) in d.cells.items() if n.startswith('u_runtime/sample_meta') and kind.startswith('DFF')]
    if runtime_meta:
        require(len(runtime_meta)==32,'runtime audio counter Gray width changed')
        paths=[]
        for name in runtime_meta:
            net=d.cells[name][1]['D'];require(net in d.drivers,'runtime Gray has no source')
            source,pin=d.drivers[net]
            require(source.startswith('u_runtime/sample_gray') and pin=='Q','runtime Gray is not source registered')
            second=[n for n,(kind,ports) in d.cells.items() if n.startswith('u_runtime/sample_sync') and kind.startswith('DFF') and ports['D']==d.cells[name][1]['Q']]
            require(len(second)==1,'runtime Gray second synchronizer missing')
            flight=d.arc(source,'CLK','Q')+d.route(source+'/Q',name+'/D')
            require(flight<=20,'runtime Gray flight exceeds 20ns')
            paths.append({'from':source,'to':name,'cq_plus_route_ns':flight})
        runtime_gray={'bits':32,'maximum_cq_plus_route_ns':max(p['cq_plus_route_ns'] for p in paths),'paths':paths}
    require('IO_LOC "debug_uart_tx"' not in (root/'constraints/tang_mega_138k.cst').read_text() or runtime_gray is not None,
        'runtime UART pin exists but counter CDC is absent')
    return {'passed':True,'hardware_tested':False,'timing':timing,'audio_pll_parameters':expected,'runtime_gray':runtime_gray,
        'pfd_mhz':50,'vco_mhz':1200,'sample_rate_hz':48000,'pll_init_paths':control,
        'maximum_pll_init_ns':max(p['total_ns'] for p in control),'mailboxes':mailboxes,
        'bitstream_sha256':hashlib.sha256((pnr/'Prj1.fs').read_bytes()).hexdigest(),
        'limitations':['PLL analog lock/jitter and actual wiring require board measurement.',
            'AE350 fixed PLL location remains a later placement requirement; CPU is absent.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists(): parser.error('Refusing to replace audit evidence')
    try: evidence=inspect(args.project.resolve())
    except (ValueError,KeyError,OSError) as error:
        evidence={'passed':False,'error':str(error),'hardware_tested':False}
    args.output.write_text(json.dumps(evidence,indent=2)+'\n')
    print('PASS audio routed audit' if evidence['passed'] else 'FAIL '+evidence['error'])
    raise SystemExit(0 if evidence['passed'] else 1)

if __name__=='__main__': main()
