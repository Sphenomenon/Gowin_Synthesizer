"""Narrow constraints and source-netlist checks for the BLE DDR storage FIFOs."""
import re
from tools.workstation_synthesis_netlist import SynthesisNetlist

STORE = 'u_bluetooth/g_store.u_store'


def constraints():
    lines = []
    for fifo in ('u_commands', 'u_responses'):
        for side in ('read', 'write'):
            base = STORE+'/'+fifo+'/'+side
            # The MSB Gray register can alias the binary MSB after synthesis.
            path = f'-from [get_regs {{{base}_gray_?_* {base}_binary_?_*}}] -to [get_regs {{{base}_gray_meta*}}]'
            lines += ['set_max_delay 10.000 '+path, 'set_false_path -hold '+path]
    lines += [f'set_false_path -to [get_pins {{{STORE}/ready_meta*/D}}]']
    return '\n'.join(lines)+'\n'


def audit(text, clocks):
    netlist = SynthesisNetlist(text, 'workstation_custom_138k_top')
    evidence = {}
    for fifo, bits, write_clock, read_clock in (
            ('u_commands', 5, 'clk_50m', 'ddr_ui100'), ('u_responses', 3, 'ddr_ui100', 'clk_50m')):
        scope = STORE+'/'+fifo
        for side, source, target in (('write',write_clock,read_clock), ('read',read_clock,write_clock)):
            first = {}
            second = {}
            for name, cell in netlist.cells.items():
                if not cell['kind'].startswith('DFF'):
                    continue
                for stem, registers in (('meta', first), ('sync', second)):
                    match = re.fullmatch(re.escape(scope+'/'+side+'_gray_'+stem+'_')+r'(\d+)_s\d+', name)
                    if match:
                        registers[int(match[1])] = name
            if set(first) != set(range(bits)) or set(second) != set(range(bits)):
                raise ValueError('BLE storage FIFO synchronizer inventory changed: '+scope+'/'+side)
            for bit in range(bits):
                one, two = first[bit], second[bit]
                if (netlist.pin(one,'CLK') != clocks['clocks'][target]['net'] or
                        netlist.pin(two,'CLK') != clocks['clocks'][target]['net'] or
                        netlist.pin(two,'D') != netlist.pin(one,'Q')):
                    raise ValueError('BLE storage FIFO direct two-stage synchronization changed')
                source_registers = [name for name,cell in netlist.cells.items()
                    if netlist.scopes[name] == scope and cell['kind'].startswith('DFF') and
                    netlist.pin(name,'Q') == netlist.pin(one,'D')]
                if not source_registers or any(netlist.pin(name,'CLK') != clocks['clocks'][source]['net'] for name in source_registers):
                    raise ValueError('BLE storage FIFO Gray source clock changed')
            evidence[fifo+'/'+side] = dict(bits=bits, source_clock=source, destination_clock=target)
    return dict(fifos=evidence, gray_max_delay_ns=10, routed_timing_verified=False)
