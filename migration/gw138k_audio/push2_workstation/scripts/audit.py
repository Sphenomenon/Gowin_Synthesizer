#!/usr/bin/env python3
"""Retain the original audio/DDR/AE350/HDMI/USB audits, then inspect Push routes."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
BASE=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('build',type=Path);a=ap.parse_args();b=a.build.resolve();p=b/'Prj1';out=b/'push_audit.json'
    if out.exists():ap.error('refuse to overwrite an audit')
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    result=dict(passed=False,hardware_tested=False)
    try:
        old=b/'original_workstation_audit.json'
        if not old.exists():
            r=subprocess.run([sys.executable,str(BASE.parent/'usb_host/scripts/audit.py'),str(b),'--output',str(old)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            (b/'original_audit.log').write_bytes(r.stdout)
        result['original']=json.loads(old.read_text())
        if not result['original']['passed']:raise ValueError('Original workstation audit: '+result['original'].get('error','failed'))
        sys.path.insert(0,str(p/'scripts'))
        from check_video_pll_init import RoutedDesign,require
        d=RoutedDesign((p/'impl/pnr/Prj1.sdf').read_text(),(p/'impl/pnr/Prj1.vo').read_text())
        rpt=(p/'impl/pnr/Prj1.rpt.txt').read_text();cst=(p/'constraints/tang_mega_138k.cst').read_text();sdc=(p/'constraints/tang_mega_138k.sdc').read_text()
        expected={'push_htclk':'J20','push_htreq':'J21','push_htrdy':'L19','push_htvld':'G18','push_hrclk':'L20','push_hrreq':'N20','push_hrack':'J22','push_hrvld':'L15'}
        expected.update({f'push_hd[{k}]':v for k,v in enumerate('G17 H22 L14 K22 K21 K18 L21 M21 M22 N22 L18 M18 N19 N18 K16 L16'.split())})
        for name,pad in expected.items():
            require(f'IO_LOC "{name}" {pad};' in cst,'Push CST pin '+name)
            m=re.search('^'+re.escape(name)+r'\s+\|[^\n]+',rpt,re.M)
            require(m and re.search(r'\|\s*'+pad+r'/3\s*\|',m[0]) and 'LVCMOS33' in m[0],'routed Push pad '+name)
        result['pin_map']=expected
        from reset_distribution import inspect as inspect_reset
        result['hspi_async_reset']=inspect_reset(d,(p/'impl/pnr/Prj1.sdf').read_text())
        result['reset_auditor_sha256']=sha(BASE/'scripts/reset_distribution.py')
        require('u_push/link/phy/*/RESET' not in sdc,'Synchronous HSPI reset excluded from STA')
        def ff(prefix):return [n for n,(k,_) in d.cells.items() if n.startswith(prefix) and k.startswith('DFF')]
        gray=[];root='u_push/events/fifo/unbuffered/'
        for branch,source in [('produce_cdc','produce_w_'),('consume_cdc','consume_r_')]:
            targets=ff(root+branch+'/stage0_');require(len(targets)==7,'Push FIFO Gray width '+branch)
            for target in targets:
                tp=d.cells[target][1];src,pin=d.drivers[tp['D']];sk,sp=d.cells[src]
                require(src.startswith(root+source) and pin=='Q' and sk.startswith('DFF'),'Push Gray source '+target)
                require(sp['CLK']!=tp['CLK'],'Push event FIFO clock boundary')
                second=[n for n in ff(root+branch+'/stage1_') if d.cells[n][1]['D']==tp['Q']]
                require(len(second)==1,'Push Gray second stage')
                flight=d.arc(src,'CLK','Q')+d.route(src+'/Q',target+'/D');require(flight<10,'Push Gray flight >=10ns')
                gray.append(dict(source=src,target=target,flight_ns=flight))
        result['event_fifo_gray']=gray
        chain=[]
        for k in range(3):
            stages=ff('u_push/link/reply_sync_'+str(k)+'_');require(len(stages)==1,'Reply completion synchronizer stage '+str(k));chain.append(stages[0])
        for prev,nxt in zip(chain,chain[1:]):require(d.cells[nxt][1]['D']==d.cells[prev][1]['Q'],'Reply synchronization bypass')
        src,pin=d.drivers[d.cells[chain[0]][1]['D']]
        require(src.startswith('u_push/link/reply_toggle') and pin=='Q','Reply publication source')
        require(d.cells[src][1]['CLK']!=d.cells[chain[0]][1]['CLK'],'Reply clock boundary')
        result['reply_sync']=[src]+chain
        for first,second in [('ready_meta','reg_tx_rdy'),('active_meta','reg_rx_active_sync')]:
            a0=ff('u_push/link/phy/'+first);a1=ff('u_push/link/phy/'+second)
            require(len(a0)==len(a1)==1 and d.cells[a1[0]][1]['D']==d.cells[a0[0]][1]['Q'],'Native handshake synchronizer '+first)
        require('u_push/link/* u_push/midi/*' in sdc,'Held reply crossing does not cover MIDI receiver')
        require('create_clock -name push_rx120 -period 8.333' in sdc,'CH569 return clock constraint')
        require('set_input_delay -clock push_rx120 -clock_fall -max 2.500' in sdc,'Native input I/O budget')
        require(not ff('u_push/feedback/'),'Duplicate performance CDC unexpectedly present')
        result['limits']=['CH569 I/O constraints use explicit engineering budgets (Tco+board skew <=2.5ns; receiver setup2ns/hold0.5ns). Silicon/PVT characterization is not implied by a clean FPGA timing report.','USB Host runs WCH firmware on CH569; audio calculations remain FPGA RTL.']
        result['bitstream_sha256']=sha(p/'impl/pnr/Prj1.fs');result['auditor_sha256']=sha(Path(__file__))
        result['passed']=True
    except (ValueError,KeyError,OSError,AssertionError) as e:result['error']=str(e)
    out.write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k in ['passed','error','bitstream_sha256']})
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
