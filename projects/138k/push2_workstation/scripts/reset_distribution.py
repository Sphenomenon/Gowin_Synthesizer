"""Check each HSPI asynchronous-clear exception against routed recovery/removal.
Only board-reset -> TX FF and two-stage HRCLK release -> RX FF are admitted.
Synchronous RESET pins remain under normal STA.
"""
import re
from check_video_pll_init import require,numbers,unescape

def inspect(d,sdf):
    def corners(s):
        vals=numbers(s);require(len(vals)%3==0 and vals,'SDF requires min/typ/max triples')
        return [vals[i:i+3] for i in range(0,len(vals),3)]
    routes={}
    for m in re.finditer(r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+([^\n]+)',sdf):
        routes[(unescape(m[1]),unescape(m[2]))]=corners(m[3])
    def arc(n,a,z):
        m=re.search(r'\(IOPATH '+a+' '+z+r' ([^\n]+)',d.sdf_cells[n]);require(m is not None,'Missing reset arc '+n)
        return corners(m[1])
    def extrema(v,i,maximum):return (max if maximum else min)(x[i]*d.unit for x in v)
    def route(a,z,i,maximum):return extrema(routes[(a,z)],i,maximum)
    # This exact two-stage active-high reset chain shifts constant zero.
    r0=[n for n in d.cells if n.startswith('u_push/link/phy/reg_reset_s')]
    r1=[n for n in d.cells if n.startswith('u_push/link/phy/reg_reset_dly_s')]
    require(len(r0)==len(r1)==1,'HRCLK reset release stages missing')
    p0=d.cells[r0[0]][1];p1=d.cells[r1[0]][1]
    require(d.cells[r0[0]][0]==d.cells[r1[0]][0]=='DFFPE' and p0['CLK']==p1['CLK'],'Reset release primitive/clock')
    require(d.constants.get(p0['D'])==0 and p1['D']==p0['Q'] and p0['PRESET']==p1['PRESET'],'Reset release sequence')
    checked=[]
    for n,(kind,p) in d.cells.items():
        if not n.startswith('u_push/link/phy/') or 'CLEAR' not in p or d.constants.get(p['CLEAR'])==0:continue
        require(kind=='DFFCE','Unsupported HSPI async clear endpoint '+n)
        driver,pin=d.drivers[p['CLEAR']];segments=[]
        if d.cells[driver][0]=='INV':
            inv=driver;source,spin=d.drivers[d.cells[inv][1]['I']]
            require(source.startswith('u_reset/started_') and spin=='Q' and d.cells[source][1]['CLK']==p['CLK'],'TX clear origin')
            segments=[(source+'/Q',inv+'/I'),(inv+'/O',n+'/CLEAR')];extra=arc(inv,'I','O');period=20.0
        else:
            source=driver;require(source==r1[0] and pin=='Q' and p['CLK']==p1['CLK'],'RX clear origin')
            segments=[(source+'/Q',n+'/CLEAR')];extra=[[0,0,0]];period=8.333
        clock,pin=d.drivers[p['CLK']];require(pin=='O' and d.cells[clock][0]=='IBUF','HSPI reset clock source')
        recovery=re.search(r'\(RECOVERY \(negedge CLEAR\) \(posedge CLK\) ([^\n]+)',d.sdf_cells[n])
        removal=re.search(r'\(REMOVAL \(negedge CLEAR\) \(posedge CLK\) ([^\n]+)',d.sdf_cells[n])
        require(recovery is not None and removal is not None,'Missing recovery/removal '+n)
        margins=[]
        for i in [0,1,2]:
            source_clock=route(clock+'/O',source+'/CLK',i,True);dest_clock=route(clock+'/O',n+'/CLK',i,False)
            late=source_clock+extrema(arc(source,'CLK','Q'),i,True)+extrema(extra,i,True)+sum(route(a,z,i,True) for a,z in segments)
            early=route(clock+'/O',source+'/CLK',i,False)+extrema(arc(source,'CLK','Q'),i,False)+extrema(extra,i,False)+sum(route(a,z,i,False) for a,z in segments)
            rec=period+dest_clock-late-extrema(corners(recovery[1]),i,True)-0.05
            rem=early-route(clock+'/O',n+'/CLK',i,True)-extrema(corners(removal[1]),i,True)-0.05
            require(rec>=0 and rem>=0,f'HSPI reset recovery/removal {n}: {rec}/{rem}')
            margins.append({'corner':i,'recovery_ns':rec,'removal_ns':rem})
        checked.append({'source':source,'endpoint':n+'/CLEAR','margins':margins})
    require(len(checked)>=40,'HSPI reset exception coverage unexpectedly small')
    return {'release_chain':r0+r1,'paths':checked,'minimum_recovery_ns':min(m['recovery_ns'] for x in checked for m in x['margins']),'minimum_removal_ns':min(m['removal_ns'] for x in checked for m in x['margins'])}
