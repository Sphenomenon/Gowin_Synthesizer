"""Fail-closed bsram4 synthesis-structure gate; no EDA or timing acceptance.

Gowin may rewrite wrapper ports. Resolve actual hierarchy and hard primitive
pins from the sealed synthesis netlist; RTL block attributes are insufficient.
"""
import re
from tools.workstation_synthesis_netlist import IDENTIFIER

def audit(n):
    zero={"1'b0"};one={"1'b1"};constant_drivers={}
    for name,c in n.cells.items():
        if c['kind'] in ('GND','VCC'):
            net=n.pin(name,'G' if c['kind']=='GND' else 'V')
            if net in constant_drivers:raise ValueError('snapshot constant has multiple primitive drivers')
            constant_drivers[net]=name
            (zero if c['kind']=='GND' else one).add(net)
    def logical(net):
        # Gowin emits a GND/VCC cell in each RAM wrapper. Different canonical
        # net names are equal only after proving their actual primitive driver.
        return "1'b0" if net in zero else "1'b1" if net in one else net
    def expand(name,port,width):
        scope=n.scopes[name];binding=n.cells[name]['ports'].get(port)
        if binding is None:raise ValueError('snapshot RAM missing primitive pin: '+name+'.'+port)
        def member(text):
            text=text.strip()
            literal=re.fullmatch(r"(\d+)'([bhd])([0-9a-fA-F]+)",text)
            if literal:
                count=int(literal[1]);v=int(literal[3],{'b':2,'h':16,'d':10}[literal[2]])
                if v>>count:raise ValueError('snapshot RAM overflowing literal')
                return ["1'b"+str((v>>i)&1) for i in range(count)]
            selected=re.fullmatch(r'('+IDENTIFIER+r')\s*\[(\d+)(?::(\d+))?\]',text)
            if selected and selected[3] is not None:
                l,r=map(int,(selected[2],selected[3]));step=1 if l>=r else -1
                return [n.canonical(scope,selected[1]+'['+str(i)+']') for i in range(r,l+step,step)]
            if selected:return [n.canonical(scope,text)]
            span=n.ranges[n.frames[scope]['kind']].get(text)
            if span:
                l,r=span;step=1 if l>=r else -1
                return [n.canonical(scope,text+'['+str(i)+']') for i in range(r,l+step,step)]
            if re.fullmatch(IDENTIFIER,text):return [n.canonical(scope,text)]
            raise ValueError('snapshot RAM unsupported bit binding: '+text)
        bits=sum((member(x) for x in reversed(binding[1:-1].split(','))),[]) if binding.startswith('{') and binding.endswith('}') else member(binding)
        if len(bits)!=width:raise ValueError('snapshot RAM pin width drift: '+name+'.'+port)
        return bits
    rams={k:c for k,c in n.cells.items() if k.startswith('u_uart/') and c['kind'] in ('SDPB','DPB','SP','SDPX9B','DPX9B','SPX9','RAM16SDP1','RAM16SDP2','RAM16SDP4')}
    if len(rams)!=8 or any(c['kind']!='SDPB' for c in rams.values()):
        raise ValueError('bsram4 requires exactly eight actual native16-bit SDPB lanes')
    addresses=None;controls=None;data_outputs=set();data_inputs=set()
    for name,c in sorted(rams.items()):
        p=c['parameters']
        if any(p.get(k)!=v for k,v in dict(BIT_WIDTH_0='16',BIT_WIDTH_1='16',READ_MODE="1'b0",RESET_MODE='"SYNC"',BLK_SEL_0="3'b000",BLK_SEL_1="3'b000").items()):
            raise ValueError('snapshot RAM geometry/read/reset parameter drift: '+name)
        if n.pin(name,'CLKA')!='clk_50m' or n.pin(name,'CLKB')!='clk_50m':raise ValueError('snapshot RAM wrong clock: '+name)
        if n.pin(name,'RESET') not in zero:raise ValueError('snapshot RAM contents/output must not be reset')
        if any(x not in zero for p in ('BLKSELA','BLKSELB') for x in expand(name,p,3)):
            raise ValueError('snapshot RAM block select drift')
        wa,ra=expand(name,'ADA',14),expand(name,'ADB',14)
        if any(x not in zero for x in (*wa[9:],*ra[9:],*wa[2:4],*ra[:4])) or any(x not in one for x in wa[:2]):
            raise ValueError('snapshot RAM byte enable/address padding drift')
        if len(set(wa[4:9]))!=5 or len(set(ra[4:9]))!=5 or any(x in zero|one for x in (*wa[4:9],*ra[4:9])):
            raise ValueError('snapshot RAM bank/group address lost')
        addr=(tuple(map(logical,wa)),tuple(map(logical,ra)));ctrl=tuple(logical(n.pin(name,p)) for p in ('CEA','CEB','OCE'))
        if ctrl[0] in zero|one or ctrl[1] in zero or ctrl[2] not in one:
            raise ValueError('snapshot RAM write/read/output enable lost')
        if addresses is not None and (addr!=addresses or ctrl!=controls):raise ValueError('snapshot RAM lanes do not share one address/control owner')
        addresses,controls=addr,ctrl
        di,do=expand(name,'DI',32),expand(name,'DO',32)
        if any(x not in zero for x in di[16:]):raise ValueError('snapshot RAM unexpected upper write lane')
        if any(x in zero|one or x in data_inputs for x in di[:16]):raise ValueError('snapshot RAM write lane missing/aliased')
        if any(x in zero|one or x in data_outputs for x in do[:16]):raise ValueError('snapshot RAM read lane missing/aliased')
        data_inputs.update(di[:16])
        data_outputs.update(do[:16])
    expected_held={i for i in range(58*32)}|{58*32,59*32}
    held={};held_nets=set();uart_cache_nets=set();reference_registers=0;other_clocks=set();wide=[];small_banks={k:set() for k in ('prefetch','prepared_page0','cache_data')}
    for name,c in n.cells.items():
        if not name.startswith('u_uart/') or not c['kind'].startswith('DFF'):continue
        q=n.pin(name,'Q');clk=n.pin(name,'CLK')
        if clk=='clk_50m':reference_registers+=1
        match=re.fullmatch(r'u_uart/held_words\[(\d+)\]',q)
        if match:
            bit=int(match[1])
            if bit in held:raise ValueError('snapshot held bit duplicate driver')
            held[bit]=clk;held_nets.add(q);other_clocks.add(clk)
        for stem,bits in small_banks.items():
            m=re.fullmatch(r'u_uart/'+stem+r'\[(\d+)\]',q) or re.fullmatch(r'u_uart/'+stem+r'_(\d+)_s[0-9]+',name)
            if m:
                if clk!='clk_50m' or int(m[1]) in bits or q!=n.canonical(n.scopes[name],stem+'['+m[1]+']'):raise ValueError('snapshot cache bit clock/driver drift')
                bits.add(int(m[1]))
                if stem=='cache_data':uart_cache_nets.add(q)
        if re.search(r'/(?:words|full_snapshot_50mhz|frozen_snapshot)(?:\[|_)',q):wide.append(q)
    if set(held)!=expected_held or len(other_clocks)!=1 or 'clk_50m' in other_clocks:
        raise ValueError('snapshot one-edge pclk held capture missing/changed')
    if wide or reference_registers>1600:raise ValueError('redundant reference-domain snapshot FF storage returned')
    if any(small_banks[k]!=set(range(width)) for k,width in (('prefetch',384),('prepared_page0',512),('cache_data',32))):
        raise ValueError('snapshot required bounded caches missing/changed')
    # All128 native read bits must reach the registered top payload through
    # at most two explicit FF stages. A decoy unused RAM cannot satisfy this.
    drivers={}
    for name,c in n.cells.items():
        output='Q' if c['kind'].startswith('DFF') else 'F' if re.fullmatch(r'LUT[1-8]',c['kind']) else 'O' if c['kind'].startswith('MUX') else None
        if output and output in c['ports']:
            q=n.pin(name,output)
            if q in drivers or q in constant_drivers:raise ValueError('snapshot ambiguous scalar driver')
            drivers[q]=(name,output)
    def reachable(roots,leaves,ff_limit):
        reached=set();seen=set()
        def walk(net,depth):
            key=(net,depth)
            if key in seen:return
            seen.add(key)
            if net in leaves:reached.add(net);return
            if net in zero|one or net not in drivers:return
            name,output=drivers[net];c=n.cells[name]
            if c['kind'].startswith('DFF'):
                if depth<ff_limit:walk(n.pin(name,'D'),depth+1)
            else:
                for p in c['ports']:
                    if p!=output:walk(n.pin(name,p),depth)
        for root in roots:walk(root,0)
        return reached
    payload=[]
    for name,c in n.cells.items():
        if c['kind'].startswith('DFF') and re.fullmatch(r'status_50mhz\[(?:[0-9]+)\]',n.pin(name,'Q')):
            bit=int(n.pin(name,'Q').split('[')[1][:-1])
            if bit<512:payload.append(n.pin(name,'D'))
    reached=reachable(payload,data_outputs,2)
    if reached!=data_outputs:raise ValueError('snapshot native RAM read data does not reach all registered GAO payload lanes')
    written=reachable(data_inputs,held_nets,0)
    if written!=held_nets:raise ValueError('snapshot held capture does not reach native RAM write data')
    uart_read=reachable([n.pin(drivers[q][0],'D') for q in uart_cache_nets],data_outputs,0)
    if uart_read!=data_outputs:raise ValueError('snapshot native RAM read data does not reach UART cache')
    # This bound includes prepublication page0, next-page prefetch, UART cache,
    # identity/state/UART counters. It is a structural gate, not a CLS estimate.
    return dict(native_sdp_lanes=8,lane_bits=16,read_bandwidth_bits_per_cycle=128,
        held_pclk_bits=len(held),held_clock=next(iter(other_clocks)),reference_registers=reference_registers,
        reference_register_limit=1600,cache_bits={k:len(v) for k,v in small_banks.items()},
        ram_read_bits_reaching_gao=len(reached),redundant_snapshot_ff_names=wide,
        held_bits_reaching_ram=len(written),ram_read_bits_reaching_uart=len(uart_read),
        physical_bsram_count_verified=False,physical_timing_verified=False)
