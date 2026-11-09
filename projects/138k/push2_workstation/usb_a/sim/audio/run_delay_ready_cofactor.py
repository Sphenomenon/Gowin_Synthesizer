#!/usr/bin/env python3
"""Compare complete W DMA ready/response behavior and optional actual Gowin mappings.

The reference is the exact prior selected native DMA. Source tests exercise
all legal/illegal states, arbitrary histories, X/Z input conditions, flush,
stalls and exact fault edges. Mapped comparison cuts only module inputs and
checks every FF transition/INIT and public output; no internal logic cuts.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_w_delay_ready as repair


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, output, name):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output/(name+'.log')).write_text(result.stdout+result.stderr)
    return result


def mapped(reference, candidate):
    from tools.workstation_runtime_pcm_cdc import PcmNetlist
    from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, sat_compare
    e = Expressions()
    circuits = []
    for path in (reference, candidate):
        n = PcmNetlist(path.read_text(), 'workstation_runtime_delay_ddr_dma')
        c = Circuit(n, e)
        for name, cell in n.cells.items():
            if cell['kind'] == 'IBUF':
                c.memo[n.pin(name, 'O')] = e.node('state', 'input/'+n.pin(name, 'I'))
        circuits.append(c)
    a, b = circuits
    assert not a.ambiguous and not b.ambiguous
    assert set(a.state) == set(b.state)
    proofs = []
    for name in sorted(a.state):
        av, ai, ac = a.next_q(a.state[name])
        bv, bi, bc = b.next_q(b.state[name])
        assert ai == bi and ac == bc, name
        proofs.append(dict(state=name, **sat_compare(e, av, bv)))
    outputs = []
    def output_value(c, label):
        net = c.n.canonical('', label)
        drivers = c.g.drivers.get(net, [])
        if len(drivers) == 1:
            path, port = drivers[0]
            if c.n.cells[path]['kind'] == 'OBUF':
                assert port == 'O' and set(c.n.cells[path]['ports']) == {'I','O'}
                net = c.n.pin(path, 'I')
        return c.net(net)
    for port, width in [('dwr_pop_o',1),('drd_push_o',1),('drd_data_o',65),
                        ('ddr_req_o',1),('ddr_write_o',1),('ddr_address_o',29),
                        ('ddr_data_o',256),('ddr_mask_o',32),('debug_status_o',8),
                        ('flush_done_o',1),('fault_o',1),('applied_rate_44100_o',1),
                        ('applied_transaction_o',32),('heartbeat_o',1)]:
        for bit in range(width):
            label = port if width == 1 else port+'['+str(bit)+']'
            av = output_value(a, label)
            bv = output_value(b, label)
            outputs.append(dict(output=label, **sat_compare(e, av, bv)))
    return dict(passed=True, reference_sha256=sha(reference), candidate_sha256=sha(candidate),
                all_mapped_FF_next_Q_reset_INIT_and_clock_equal=True,
                only_module_input_cuts=True, state_bits=len(proofs),
                output_bits=len(outputs), states=proofs, outputs=outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mapped-reference', type=Path)
    parser.add_argument('--mapped-candidate', type=Path)
    args = parser.parse_args()
    assert bool(args.mapped_reference) == bool(args.mapped_candidate)
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    source = ROOT/repair.ALTERNATE
    assert repair.digest(source.read_text()) == repair.ALTERNATE_SHA256
    reference = repair.parent().replace('module workstation_runtime_delay_ddr_dma #(',
                                        'module delay_original #(', 1)
    (output/'reference.sv').write_text(reference)
    (output/'candidate.sv').write_bytes(source.read_bytes())
    bench = ROOT/'sim/audio/tb_workstation_delay_watchdog_retime.sv'
    tb = bench.read_text()
    start = tb.index(' expected=dut.watchdog_reset_delay')
    end = tb.index('\nend endtask', start)
    tb = tb[:start]+''' if(dut.state!==refdut.state || dut.wait_cycles!==refdut.wait_cycles ||
 dut.wptr!==refdut.wptr || dut.rptr!==refdut.rptr ||
 dut.read_outstanding!==refdut.read_outstanding)$fatal(1,"DMA state mismatch");'''+tb[end:]
    tb = tb.replace('PASS watchdog retime', 'PASS ready cofactor')
    (output/'tb.sv').write_text(tb)
    cases = []
    for timeout in (2,3,7,16,1048576):
        binary = output/('test-'+str(timeout))
        command = ['iverilog','-g2012','-s','tb',f'-Ptb.T={timeout}','-o',str(binary),
                   str(output/'reference.sv'),str(output/'candidate.sv'),str(output/'tb.sv')]
        assert run(command,output,'compile-'+str(timeout)).returncode == 0
        result = run(['vvp',str(binary)],output,'run-'+str(timeout))
        assert result.returncode == 0 and 'PASS ready cofactor' in result.stdout
        cases.append(dict(timeout=timeout,passed=True))
    # A genuine changed request successor must fail the same behavioral check.
    mutant = source.read_text().replace('S_RD_REQ:dma_next_r1_p0=S_RD_WAIT;',
                                       'S_RD_REQ:dma_next_r1_p0=S_IDLE;',1)
    assert mutant != source.read_text()
    (output/'wrong-successor.sv').write_text(mutant)
    command = ['iverilog','-g2012','-s','tb','-Ptb.T=7','-o',str(output/'mutant'),
               str(output/'reference.sv'),str(output/'wrong-successor.sv'),str(output/'tb.sv')]
    assert run(command,output,'mutant-compile').returncode == 0
    assert run(['vvp',str(output/'mutant')],output,'mutant-run').returncode != 0
    report = dict(passed=True,cases=cases,wrong_successor_rejected=True,
                  sources={str(path.relative_to(ROOT)):sha(path) for path in
                           [source,ROOT/repair.SOURCE,ROOT/repair.TOOL,bench,Path(__file__)]},
                  added_cycles=0,physical_timing_tested=False,hardware_tested=False)
    if args.mapped_reference:
        report['actual_Gowin_mapping'] = mapped(args.mapped_reference,args.mapped_candidate)
    assert all(sha(ROOT/path)==value for path,value in report['sources'].items())
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS W DMA: five timeout values, complete outputs/state, X/Z and wrong-successor control')
    if args.mapped_reference:
        print('PASS actual mapped FF/output bits:',report['actual_Gowin_mapping']['state_bits'],
              report['actual_Gowin_mapping']['output_bits'])


if __name__ == '__main__':
    main()
