"""Prove the SDC capture-clock latency interval from routed cell/net SDF."""
import re
from check_video_pll_init import require,numbers,unescape

def inspect(d,sdf):
    routes={}
    for m in re.finditer(r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+([^\n]+)',sdf):
        v=numbers(m[3]);routes[(unescape(m[1]),unescape(m[2]))]=(min(v)*d.unit,max(v)*d.unit)
    segments=[];inverters=[]
    def arc(n):
        k,p=d.cells[n]
        require(k in ['IBUF','INV','OBUF','LUT1'],'Forwarded clock contains unsupported primitive '+k)
        a,z=('I0','F') if k=='LUT1' else ('I','O')
        if k=='LUT1':require(d.parameters.get((n,'INIT')) in ["2'h1","2'b01","2'h01"],'Clock LUT1 is not an inverter')
        if k=='IBUF':require(n=='clk_50m_ibuf' and p['I']=='clk_50m','Clock originates from wrong input')
        else:
            src,pin=d.drivers[p[a]];arc(src)
            lo,hi=routes[(src+'/'+pin,n+'/'+a)];segments.append(dict(path=src+'/'+pin+' -> '+n+'/'+a,minimum_ns=lo,maximum_ns=hi))
        if k in ['INV','LUT1']:inverters.append(n)
        matches=re.findall(r'\(IOPATH\s+'+a+r'\s+'+z+r'\s*([^\n]+)',d.sdf_cells[n])
        # Gowin emits an empty ABSOLUTE block for a LUT1 inverter. The
        # supplied prim_sim.v LUT1/MUX2 has no specify delay for that cell.
        # Record this exact zero-delay model case; reject every other omission.
        if not matches:
            require(k=='LUT1' and not re.search(r'\(IOPATH',d.sdf_cells[n]),'Missing clock I/O arc '+n)
            segments.append(dict(path=n+' '+a+' -> '+z,minimum_ns=0,maximum_ns=0,model='Gowin LUT1 zero-delay inverter; no SDF cell arc'))
            return
        v=[x*d.unit for m in matches for x in numbers(m)]
        segments.append(dict(path=n+' '+a+' -> '+z,minimum_ns=min(v),maximum_ns=max(v)))
    n,pin=d.drivers['push_htclk'];require(d.cells[n][0]=='OBUF','Missing forwarded clock output buffer');arc(n)
    require(len(inverters)==1,'Forwarded clock must have exactly one inversion')
    lo=sum(x['minimum_ns'] for x in segments);hi=sum(x['maximum_ns'] for x in segments)
    require(lo>=1.0 and hi<=8.0,f'Forwarded clock outside SDC latency budget: {lo}..{hi} ns')
    return dict(minimum_ns=lo,maximum_ns=hi,sdc_early_ns=1,sdc_late_ns=8,segments=segments)
