"""Strict RV32I/Zicsr/Zifencei interpreter for the *actual* cold-loader bytes.

Stop at services_main, before MMIO business logic. This intentionally models
documented local-memory access; it cannot prove the encrypted hard IP has that
behavior. Unknown instructions, addresses, CSRs and instruction lengths fail.
"""
ROM, ILM, DLM = 0x80000000, 0xA0000000, 0xA0200000


class ModelError(ValueError):
    pass


class CpuTrap(Exception):
    def __init__(self, cause):
        self.cause = cause


def signed(value, bits=32):
    return (value & ((1 << bits) - 1)) - ((value >> (bits - 1) & 1) << bits)


class StartupCpu:
    def __init__(self, image, symbols, *, csr_overrides=None, unsupported_csrs=(),
                 stuck_enable=(), writable=True, corrupt_copy_address=None, rom_readable=True):
        if len(image) not in (16384, 65536, 131072):
            raise ModelError('model requires selected physical 16, 64 or 128 KiB ROM')
        self.image, self.symbols = bytearray(image), symbols
        self.ilm, self.dlm = bytearray([0xA7] * 65536), bytearray([0xB9] * 65536)
        self.registers, self.pc = [0] * 32, ROM
        self.csrs = {0x304: 0, 0x305: 0, 0x341: 0, 0x342: 0,
                     0xFC0: 0x439ADA, 0xFC1: 0x439ADA, 0x7C0: ILM, 0x7C1: DLM, 0x7CA: 0}
        self.csrs.update(csr_overrides or {})
        self.unsupported_csrs, self.stuck_enable = set(unsupported_csrs), set(stuck_enable)
        self.writable, self.corrupt_copy_address, self.rom_readable = writable, corrupt_copy_address, rom_readable
        self.diagnostics, self.steps, self.traps = {}, 0, []
        self.fenced, self.executed_ilm, self.last_rom_read = False, False, None
        self.min_sp = None
        self.executed_opcodes = set()

    def region(self, address, width, *, write=False, fetch=False):
        if address % width:
            raise CpuTrap(6 if write else 0 if fetch else 4)
        if ROM <= address <= ROM + len(self.image) - width:
            if write or (not fetch and not self.rom_readable):
                raise CpuTrap(7 if write else 5)
            return self.image, address - ROM
        for base, data, csr in ((ILM, self.ilm, 0x7C0), (DLM, self.dlm, 0x7C1)):
            if base <= address <= base + len(data) - width:
                if not self.csrs[csr] & 1 or (write and not self.writable):
                    raise CpuTrap(7 if write else 1 if fetch else 5)
                if fetch:
                    if base != ILM or not self.fenced:
                        raise ModelError('instruction fetch before fence.i or outside ILM')
                    self.executed_ilm = True
                return data, address - base
        if not fetch and 0xF8000000 <= address <= 0xF800001C and width == 4:
            return None, address
        raise CpuTrap(7 if write else 1 if fetch else 5)

    def read(self, address, width=4, *, fetch=False):
        data, index = self.region(address, width, fetch=fetch)
        if not fetch and ROM <= address < ROM + len(self.image):
            self.last_rom_read = address
        if data is None:
            return self.diagnostics.get(index - 0xF8000000, 0)
        return int.from_bytes(data[index:index + width], 'little')

    def write(self, address, value, width=4):
        data, index = self.region(address, width, write=True)
        if data is None:
            self.diagnostics[index - 0xF8000000] = value & 0xFFFFFFFF
        else:
            if address == self.corrupt_copy_address and self.last_rom_read is not None:
                value ^= 1
            data[index:index + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, 'little')

    def step(self):
        pc, r = self.pc, self.registers
        try:
            insn = self.read(pc, fetch=True)
            if insn & 3 != 3:
                raise ModelError('unsupported instruction length')
            op, rd, f3, rs1, rs2, f7 = insn & 127, insn >> 7 & 31, insn >> 12 & 7, insn >> 15 & 31, insn >> 20 & 31, insn >> 25
            self.executed_opcodes.add((op, f3))
            next_pc, result = (pc + 4) & 0xFFFFFFFF, None
            imm = signed(insn >> 20, 12)
            if op == 0x37:
                result = insn & 0xFFFFF000
            elif op == 0x17:
                result = pc + (insn & 0xFFFFF000)
            elif op == 0x13:
                if f3 == 0:
                    result = r[rs1] + imm
                elif f3 == 6:
                    result = r[rs1] | (imm & 0xFFFFFFFF)
                elif f3 == 7:
                    result = r[rs1] & (imm & 0xFFFFFFFF)
                elif f3 == 5 and f7 == 0:
                    result = r[rs1] >> rs2
                else:
                    raise ModelError('unsupported OP-IMM instruction')
            elif op == 3:
                if f3 not in (0, 1, 2, 4, 5):
                    raise ModelError('unsupported load')
                width = {0: 1, 1: 2, 2: 4, 4: 1, 5: 2}[f3]
                if rs1 == 2:
                    self.check_stack(width, imm)
                value = self.read((r[rs1] + imm) & 0xFFFFFFFF, width)
                result = value if f3 >= 4 else signed(value, width * 8)
            elif op == 0x23:
                if f3 not in (0, 1, 2):
                    raise ModelError('unsupported store')
                offset = signed((insn >> 25 << 5) | (insn >> 7 & 31), 12)
                if rs1 == 2:
                    self.check_stack(1 << f3, offset)
                self.write((r[rs1] + offset) & 0xFFFFFFFF, r[rs2], 1 << f3)
            elif op == 0x63:
                offset = signed(((insn >> 31) << 12) | ((insn >> 7 & 1) << 11) |
                                ((insn >> 25 & 63) << 5) | ((insn >> 8 & 15) << 1), 13)
                conditions = {0: r[rs1] == r[rs2], 1: r[rs1] != r[rs2],
                              4: signed(r[rs1]) < signed(r[rs2]), 5: signed(r[rs1]) >= signed(r[rs2]),
                              6: r[rs1] < r[rs2], 7: r[rs1] >= r[rs2]}
                if f3 not in conditions:
                    raise ModelError('unsupported branch')
                if conditions[f3]:
                    next_pc = (pc + offset) & 0xFFFFFFFF
            elif op == 0x6F:
                offset = signed(((insn >> 31) << 20) | ((insn >> 12 & 255) << 12) |
                                ((insn >> 20 & 1) << 11) | ((insn >> 21 & 1023) << 1), 21)
                result, next_pc = pc + 4, (pc + offset) & 0xFFFFFFFF
            elif op == 0x67 and f3 == 0:
                result, next_pc = pc + 4, (r[rs1] + imm) & 0xFFFFFFFE
            elif op == 0x0F:
                if insn == 0x0000100F:
                    self.fenced = True
                elif insn != 0x0FF0000F:  # Exact FENCE iorw,iorw emitted by the loader.
                    raise ModelError('unsupported fence instruction')
            elif op == 0x73 and f3 in (1, 2, 3, 5, 6, 7):
                csr = insn >> 20
                if csr in self.unsupported_csrs or csr not in self.csrs:
                    raise CpuTrap(2)
                value = r[rs1] if f3 < 5 else rs1
                old = self.csrs[csr]
                operation = f3 & 3
                if operation == 1 or value:
                    if csr in (0xFC0, 0xFC1):
                        raise CpuTrap(2)
                    new = value if operation == 1 else old | value if operation == 2 else old & ~value
                    self.csrs[csr] = (new & ~1 if csr in self.stuck_enable else new) & 0xFFFFFFFF
                result = old
            else:
                raise ModelError('unsupported RV32 instruction at %#x: %#010x' % (pc, insn))
            if result is not None and rd:
                r[rd] = result & 0xFFFFFFFF
                # AUIPC+ADDI may briefly construct an out-of-range SP value.
                # Bound and sample actual stack accesses rather than construction.
            r[0], self.pc = 0, next_pc
        except CpuTrap as trap:
            if not self.csrs[0x305]:
                raise ModelError('trap before valid ROM mtvec')
            self.csrs[0x342], self.csrs[0x341] = trap.cause, pc
            self.traps.append(dict(cause=trap.cause, pc=pc))
            self.pc = self.csrs[0x305] & ~3
        self.steps += 1

    def check_stack(self, width, offset):
        address = self.registers[2] + offset
        if not self.symbols['__stack_bottom'] <= address < address + width <= self.symbols['__stack_top']:
            raise ModelError('stack access escaped DLM reserved stack')
        self.min_sp = self.registers[2] if self.min_sp is None else min(self.min_sp, self.registers[2])

    def run(self, limit=500000):
        for _ in range(limit):
            if self.pc == self.symbols['services_main']:
                return 'services_main'
            if self.pc == self.symbols['local_halt']:
                return 'halt'
            self.step()
        raise ModelError('startup instruction budget exceeded')
