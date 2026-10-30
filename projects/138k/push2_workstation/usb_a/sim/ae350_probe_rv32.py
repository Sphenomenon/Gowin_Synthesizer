"""Execute actual probe bytes in a strict model; synthetic counters are not timing evidence."""
from ae350_rv32_startup import StartupCpu, CpuTrap, ModelError, ROM, ILM, signed

class ProbeCpu(StartupCpu):
    def __init__(self,*args,rom_alias_16k=False,ilm_pattern_alias=False,**kwargs):
        super().__init__(*args,**kwargs)
        # The physical diagnostic bank resets every word; the inherited model
        # normally creates only the original five loader registers on demand.
        self.diagnostics.update({index*4:0 for index in range(64)})
        for number,value in {0xfc2:0x40010000,0x301:0x40001100,0x320:0,0x306:0,
                0xbc0:0,0xbc1:0,0xbc2:0,0xbc3:0,0xb00:0,0xb80:0,0xb02:0,0xb82:0}.items():
            self.csrs.setdefault(number,value)
        self.rom_alias_16k=rom_alias_16k;self.ilm_pattern_alias=ilm_pattern_alias

    def region(self,address,width,*,write=False,fetch=False):
        if 0xf8000000<=address<=0xf80000fc and width==4 and not fetch:return None,address
        if self.rom_alias_16k and ROM<=address<ROM+65536:address=ROM+((address-ROM)&0x3fff)
        if self.ilm_pattern_alias and self.diagnostics.get(32,0)>=4 and ILM<=address<ILM+65536:
            address=ILM+((address-ILM)&~0x4000)
        return super().region(address,width,write=write,fetch=fetch)

    def step(self):
        # A model instruction has nominal two synthetic cycles, used only to test
        # read/coherence/delta plumbing. Never report these as hardware CPI.
        self.csrs[0xb00]=self.steps*2&0xffffffff;self.csrs[0xb80]=self.steps*2>>32
        self.csrs[0xb02]=self.steps&0xffffffff;self.csrs[0xb82]=self.steps>>32
        try:insn=self.read(self.pc,fetch=True)
        except CpuTrap:return super().step()
        op=insn&127;rd=insn>>7&31;f3=insn>>12&7;rs1=insn>>15&31;rs2=insn>>20&31;f7=insn>>25
        r=self.registers;result=None
        if insn==0x30200073:
            self.pc=self.csrs[0x341];self.steps+=1;return
        if op==0x13:
            imm=signed(insn>>20,12);shift=rs2
            if f3==0:result=r[rs1]+imm
            elif f3==1 and f7==0:result=r[rs1]<<shift
            elif f3==2:result=int(signed(r[rs1])<imm)
            elif f3==3:result=int(r[rs1]<(imm&0xffffffff))
            elif f3==4:result=r[rs1]^(imm&0xffffffff)
            elif f3==5 and f7 in (0,32):result=(signed(r[rs1]) if f7 else r[rs1])>>shift
            elif f3==6:result=r[rs1]|(imm&0xffffffff)
            elif f3==7:result=r[rs1]&(imm&0xffffffff)
            else:raise ModelError('unsupported probe OP-IMM')
        elif op==0x33:
            a,b=r[rs1],r[rs2]
            if f3==0 and f7 in (0,32):result=a-b if f7 else a+b
            elif f3==1 and f7==0:result=a<<(b&31)
            elif f3==2 and f7==0:result=int(signed(a)<signed(b))
            elif f3==3 and f7==0:result=int(a<b)
            elif f3==4 and f7==0:result=a^b
            elif f3==5 and f7 in (0,32):result=(signed(a) if f7 else a)>>(b&31)
            elif f3==6 and f7==0:result=a|b
            elif f3==7 and f7==0:result=a&b
            else:raise ModelError('unsupported probe OP')
        else:return super().step()
        if rd:r[rd]=result&0xffffffff
        r[0]=0;self.pc=(self.pc+4)&0xffffffff;self.steps+=1

    def run_probe(self,limit=6000000):
        if self.run()!='services_main':return 'loader_halt'
        for _ in range(limit):
            if self.diagnostics.get(24,0):return 'probe_pass' if self.diagnostics[24]==0x50415353 else 'probe_fail'
            self.step()
        raise ModelError('probe instruction budget exceeded')
