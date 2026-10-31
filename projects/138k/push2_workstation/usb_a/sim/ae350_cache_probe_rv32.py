"""Execute actual cache probe ELF bytes against an explicit abstract cache/PMA.

This model tests the software protocol and negative controls. It is not an A25
implementation, hard-IP simulation, timing proof or encrypted-IP validation.
"""
from ae350_probe_rv32 import ProbeCpu
from ae350_rv32_startup import CpuTrap,ModelError

class CacheProbeCpu(ProbeCpu):
    def __init__(self,*args,drop_writeback=False,drop_invalidate=False,
                 wrong_alias=False,mmio_cacheable=False,stuck_pma=False,trap_at_cctl=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.csrs.update({0x7cb:0,0x7cc:0})
        for i in range(16):self.csrs.setdefault(0xbd0+i,0x100000+i)
        self.initial_pma={i:self.csrs[i] for i in (*range(0xbc0,0xbc4),*range(0xbd0,0xbe0))}
        self.ram=bytearray(8192);self.dcache={};self.icache={};self.dirty=set()
        self.drop_writeback=drop_writeback;self.drop_invalidate=drop_invalidate
        self.wrong_alias=wrong_alias;self.mmio_cacheable=mmio_cacheable;self.stuck_pma=stuck_pma
        self.trap_at_cctl=trap_at_cctl
        self.mmio_reads=0;self.mmio_saved=None;self.cctl_trace=[];self.control_trace=[]
        self.hits={'i':0,'d':0};self.fills={'i':0,'d':0};self.writebacks=0

    def external(self,address,width):
        if address%width:raise CpuTrap(4)
        if 0<=address<=8192-width:return address
        if 0x4000<=address<=0x5000-width:
            return (0 if self.wrong_alias else 0x1000)+(address&0xfff)
        return None

    def attribute(self,address):
        for i in range(16):
            cfg=self.csrs[0xbc0+i//4]>>(8*(i%4))&255
            if cfg&3==0:continue
            if cfg&3!=3:raise ModelError('model requires explicit NAPOT entries')
            encoded=self.csrs[0xbd0+i];ones=0
            while encoded>>ones&1:ones+=1
            size=1<<(ones+3);base=(encoded&~((1<<ones)-1))<<2
            if base<=address<base+size:return cfg>>2&15
        return None

    def backing(self,address,width,value=None):
        index=self.external(address,width)
        if index is None:raise CpuTrap(5 if value is None else 7)
        if value is None:return int.from_bytes(self.ram[index:index+width],'little')
        self.ram[index:index+width]=value.to_bytes(width,'little')

    def read(self,address,width=4,*,fetch=False):
        if not fetch and address==0xf80000f0:
            if self.mmio_cacheable and self.csrs[0x7ca]&2:
                if self.mmio_saved is None:self.mmio_saved=self.mmio_reads
                return self.mmio_saved
            value=self.mmio_reads;self.mmio_reads=(value+1)&0xffffffff;return value
        index=self.external(address,width)
        if index is None:return super().read(address,width,fetch=fetch)
        active=self.csrs[0x7ca]&(1 if fetch else 2)
        if not active or self.attribute(address)!=11:return self.backing(address,width)
        cache=self.icache if fetch else self.dcache;kind='i' if fetch else 'd';line=address&~31
        if line not in cache:
            cache[line]=bytearray(self.ram[self.external(line,32):self.external(line,32)+32]);self.fills[kind]+=1
        else:self.hits[kind]+=1
        offset=address-line;return int.from_bytes(cache[line][offset:offset+width],'little')

    def write(self,address,value,width=4):
        index=self.external(address,width)
        if index is None:return super().write(address,value,width)
        value&=(1<<(8*width))-1
        if not self.csrs[0x7ca]&2 or self.attribute(address)!=11:return self.backing(address,width,value)
        line=address&~31
        if line not in self.dcache:
            self.read(address,width)
        offset=address-line;self.dcache[line][offset:offset+width]=value.to_bytes(width,'little');self.dirty.add(line)

    def maintenance(self,op,address):
        self.cctl_trace.append((op,address));line=address&~31
        if op==23:self.dcache.clear();self.dirty.clear();return
        if op==24:
            for key in list(self.icache):
                if key%32768==address%32768:self.icache.pop(key)
            return
        if op==8:
            if not self.drop_invalidate:self.icache.pop(line,None)
            return
        if op not in (0,1,2):raise ModelError('unexpected probe CCTL command')
        if op in (1,2) and line in self.dirty and not self.drop_writeback:
            index=self.external(line,32);self.ram[index:index+32]=self.dcache[line];self.dirty.remove(line);self.writebacks+=1
        if op in (0,2) and not self.drop_invalidate:
            self.dcache.pop(line,None);self.dirty.discard(line)

    def step(self):
        insn=self.read(self.pc,fetch=True);op=insn&127
        # Standard MUL emitted for cache geometry, not a DSP extension.
        if op==0x33 and insn>>25==1 and (insn>>12)&7==0:
            rd=insn>>7&31;rs1=insn>>15&31;rs2=insn>>20&31
            if rd:self.registers[rd]=self.registers[rs1]*self.registers[rs2]&0xffffffff
            self.pc+=4;self.steps+=1;return
        csr=insn>>20;f3=insn>>12&7;rs1=insn>>15&31
        writing=op==0x73 and f3 in (1,2,3,5,6,7) and (f3 in (1,5) or rs1)
        old=self.csrs.get(csr);traps=len(self.traps)
        injected=writing and csr==0x7cc and len(self.cctl_trace)+1==self.trap_at_cctl
        if injected:self.unsupported_csrs.add(0x7cc)
        super().step()
        if injected:self.unsupported_csrs.discard(0x7cc)
        if writing and len(self.traps)==traps:
            if self.stuck_pma and csr==0xbc0:self.csrs[csr]=old
            if csr==0x7cc:self.maintenance(self.csrs[csr],self.csrs[0x7cb])
            if csr in (0x7ca,0xbc0,0xbd0,0xbd1):self.control_trace.append((csr,self.csrs[csr]))
        if insn==0x0000100f:
            # Model architectural instruction visibility. CCTL writeback has
            # independent uncached readback checks *before* every fence.i.
            for line in list(self.dirty):
                index=self.external(line,32);self.ram[index:index+32]=self.dcache[line];self.dirty.remove(line)
            self.icache.clear()

    def run_cache(self,limit=1000000):
        if self.run()!='services_main':return 'loader_halt'
        for _ in range(limit):
            if self.diagnostics.get(24):return 'pass' if self.diagnostics[24]==0x50415353 else 'fail'
            if self.pc==self.symbols['cache_probe_halt']:return 'trap_halt'
            self.step()
        raise ModelError('bounded cache probe instruction budget exceeded')
