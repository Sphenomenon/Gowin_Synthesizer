"""Source/offline cache-PMA contract and actual firmware gate; no EDA/board."""
from pathlib import Path
import hashlib,re
from tools.ae350_local_memory import direct_long_calls

def contract():
    return dict(program='cache-pma-v1',diagnostic_magic='CCH1',schema='CAC1',
        cache_bytes=32768,ways=4,sets=256,line_bytes=32,test_bytes=4096,
        cached_page=0x1000,uncached_backing_alias=0x4000,pmacfg0=0x0f2f,
        pmaaddr=[0x5ff,0x11ff],mmio_guard=0xf80000f0,
        active_pma_entries_at_entry='must all be disabled',
        terminal_success='cache off, original PMA restored, all behavior checks passed',
        hardware_verified=False,cache_capacity_stress_verified=False)

def audit_firmware(output,frames):
    output=Path(output);text=(output/'firmware.dis').read_text()
    functions={};current=None
    for line in text.splitlines():
        header=re.fullmatch(r'[0-9a-f]+ <([^>]+)>:',line)
        if header:current=header[1];functions[current]=[]
        word=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+',line)
        if word and current is not None:functions[current].append((int(word[1],16),int(word[2],16)))
    wrapper=[0xff010113,0x00112623,0x000012b7,0x000280e7,0x00c12083,0x01010113,0x00008067]
    if [v for _,v in functions.get('cache_page_call',[])]!=wrapper:
        raise ValueError('cache literal-page call wrapper/16-byte frame changed')
    reads=set();writes=set()
    for pairs in functions.values():
        for _,word in pairs:
            if word&127!=0x73:continue
            f3=(word>>12)&7;csr=word>>20;rs1=(word>>15)&31
            if f3 in (1,2,3,5,6,7):
                reads.add(csr)
                if f3 in (1,5) or rs1:writes.add(csr)
    required={0xfc0,0xfc1,0xfc2,0x7ca,0x7cb,0x7cc,*range(0xbc0,0xbc4),*range(0xbd0,0xbe0)}
    if not required<=reads or not {0x7ca,0x7cb,0x7cc,0xbc0,0xbd0,0xbd1}<=writes:
        raise ValueError('cache firmware required actual CSR operations missing')
    allowed={0x304,0x305,0x7c0,0x7c1,0x7ca,0x7cb,0x7cc,0xbc0,0xbd0,0xbd1}
    if writes-allowed:raise ValueError('cache firmware writes unexpected CSR')
    graphs='\n'.join(p.read_text() for p in output.glob('*.ci'));nodes={};edges={}
    for line in graphs.splitlines():
        node=re.search(r'node: \{ title: "([^"]+)" label: "([^"\\]+)',line)
        edge=re.search(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"',line)
        if node:nodes[node[1]]=node[2]
        if edge:edges.setdefault(edge[1],set()).add(edge[2])
    by_name={f['function'].split(':',3)[-1]:f for f in frames}
    roots=[n for n,name in nodes.items() if name=='services_main'];seen=set();active=set()
    if len(roots)!=1:raise ValueError('cache service graph lacks unique root')
    def visit(node):
        if node in active:raise ValueError('cache probe recursive graph')
        if node in seen:return
        active.add(node);name=nodes.get(node)
        if name!='cache_page_call' and (name not in by_name or by_name[name]['kind']!='static'):
            raise ValueError('cache probe unresolved/dynamic stack node: '+str(name))
        for child in edges.get(node,()):visit(child)
        active.remove(node);seen.add(node)
    visit(roots[0]);reachable={nodes[n] for n in seen};long=direct_long_calls(text)
    for function in reachable:
        for pc,word in functions.get(function,[]):
            if word&127==0x67 and word!=0x00008067 and pc not in long:
                if function!='cache_page_call' or word!=0x000280e7:
                    raise ValueError('cache probe unknown indirect machine call')
    bound=sum(by_name[n]['bytes'] for n in reachable if n!='cache_page_call')+16
    if bound>16384:raise ValueError('cache probe conservative stack exceeds DLM reserve')
    return dict(conservative_peak_bytes=max(bound,16),capacity_bytes=16384,
        method='sum of all reachable static C frames plus exact assembly16-byte wrapper; acyclic closed graph',
        reachable_functions=sorted(reachable),literal_page_call=dict(address=0x1000,words=wrapper,
            target='two verified words: addi a0,zero,17 or29; ret; runtime readback required'),
        actual_csr_reads=sorted(reads),actual_csr_writes=sorted(writes),
        disassembly_sha256=hashlib.sha256(text.encode()).hexdigest(),hardware_verified=False)
