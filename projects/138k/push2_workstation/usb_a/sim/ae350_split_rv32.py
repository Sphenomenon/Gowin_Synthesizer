"""Execute actual split ELF bytes in the strict RV32 model; no timing claim."""
from ae350_probe_rv32 import ProbeCpu
from ae350_rv32_startup import CpuTrap, ModelError, ROM, ILM, signed


def m_result(funct3, a, b):
    """RV32M including division-by-zero and signed overflow, no host floats."""
    a, b = a & 0xffffffff, b & 0xffffffff
    sa, sb = signed(a), signed(b)
    if funct3 == 0:
        return a * b
    if funct3 == 1:
        return (sa * sb) >> 32
    if funct3 == 2:
        return (sa * b) >> 32
    if funct3 == 3:
        return (a * b) >> 32
    if funct3 in (4, 6):
        if not b:
            return -1 if funct3 == 4 else a
        q = abs(sa) // abs(sb)
        if (sa < 0) != (sb < 0):
            q = -q
        return q if funct3 == 4 else sa - q * sb
    if funct3 in (5, 7):
        if not b:
            return 0xffffffff if funct3 == 5 else a
        return a // b if funct3 == 5 else a % b
    raise ModelError('unsupported RV32M instruction')


class SplitCpu(ProbeCpu):
    def __init__(self, image, symbols, *, upper_alias=False, **kwargs):
        if len(image) != 131072:
            raise ModelError('split model requires full explicit 128 KiB image')
        super().__init__(image, symbols, **kwargs)
        self.upper_alias = upper_alias
        self.upper_rom_fetches = 0
        self.region_transitions = []
        self.last_fetch_region = None
        self.m_instructions = 0

    def region(self, address, width, *, write=False, fetch=False):
        if self.upper_alias and ROM+65536 <= address < ROM+131072:
            address -= 65536
        return super().region(address, width, write=write, fetch=fetch)

    def step(self):
        region = 'ROM_COLD' if ROM+65536 <= self.pc < ROM+131072 else 'ILM' if ILM <= self.pc < ILM+65536 else 'ROM_LOAD'
        if region != self.last_fetch_region:
            self.region_transitions.append(dict(pc=f'0x{self.pc:08x}', region=region))
            self.last_fetch_region = region
        if region == 'ROM_COLD':
            self.upper_rom_fetches += 1
        try:
            word = self.read(self.pc, fetch=True)
        except CpuTrap:
            return super().step()
        if word & 0xfe00007f == 0x02000033:
            rd, f3, rs1, rs2 = word >> 7 & 31, word >> 12 & 7, word >> 15 & 31, word >> 20 & 31
            if rd:
                self.registers[rd] = m_result(f3, self.registers[rs1], self.registers[rs2]) & 0xffffffff
            self.registers[0] = 0
            self.pc = (self.pc+4) & 0xffffffff
            self.steps += 1
            self.m_instructions += 1
            return
        super().step()

    def call(self, name, *args, limit=2000000):
        if len(args) > 8:
            raise ModelError('test runner supports register arguments only')
        saved = [self.registers[n] for n in (2,8,9,18,19,20,21,22,23,24,25,26,27)]
        self.pc = self.symbols[name]
        self.registers[1] = self.symbols['services_main']
        for i, value in enumerate(args):
            self.registers[10+i] = value & 0xffffffff
        start = self.steps
        for _ in range(limit):
            if self.pc == self.symbols['services_main']:
                actual = [self.registers[n] for n in (2,8,9,18,19,20,21,22,23,24,25,26,27)]
                if saved != actual:
                    raise ModelError('callee did not preserve ABI registers/stack')
                return dict(result=self.registers[10], instructions=self.steps-start)
            if self.pc == self.symbols['local_halt']:
                raise ModelError('split function trapped into loader halt')
            self.step()
        raise ModelError('split function instruction budget exceeded: ' + name)
