"""Complete mapped W DMA transition check for the ready/response repair.

The reference contains all803 reset-inclusive next-Q functions from the
previously audited full W mapping. Named old-state correspondence and opaque
DDR/FIFO output correspondence are explicit assumptions. Every combinational
cell expands; no internal predicate is a cut. The separate native838-FF miter
and four-state twin regression establish the source alternative's semantics.
This check neither proves whole-design induction nor grants routed acceptance.
"""
from pathlib import Path
import hashlib
import json

from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, logical, sat_compare

REFERENCE = 'rtl/audio/delay_ddr/workstation_runtime_delay_dma_nextq_v1.proof.json'
REFERENCE_SHA256 = '35aeeed23b89fbb52b0ebe9ccfe228dfea87f41efb23e223247ac9ce5f1d224b'
SCOPE = 'u_managed/runtime/delay_dma'


def require(ok, message):
    if not ok:
        raise ValueError('W DMA mapping: ' + message)


class DmaCircuit(Circuit):
    def net(self, net, active=()):
        if net in self.g.high | self.g.low or net in self.memo or self.g.drivers.get(net):
            return super().net(net, active)
        # Graph deliberately treats RAM and the encrypted DDR interface as
        # terminals. Cut only their declared output pins, with exact owner,
        # primitive, output port and bit identity; never an internal LUT net.
        matches = []
        for path, port, role in self.g.fan[net]:
            kind = self.n.cells[path]['kind']
            if role != 'unsupported':
                continue
            memory = kind in ('SDPX9B', 'SDPB') and port == 'DO'
            ddr = kind == '~GW_DDR3_PHY_MC.DDR3_Memory_Interface_Top' and port in (
                'controller_rvalid', 'controller_rdata', 'calib_done',
                'controller_cmd_ready', 'controller_wr_data_rdy')
            if not (memory or ddr):
                continue
            bits = self.g.binding_bits(self.n.scopes[path], self.n.cells[path]['ports'][port])
            bits = [self.n.canonical(self.n.scopes[path], bit) for bit in bits]
            require(bits.count(net) == 1, 'opaque output bit is ambiguous')
            matches.append((logical(path), port, bits.index(net), kind))
        require(len(matches) == 1, 'unknown/ambiguous boundary: ' + net)
        token = 'opaque/' + str(matches[0])
        require(token in self.allowed_opaque, 'unreviewed opaque output: ' + token)
        self.used_opaque.add(token)
        self.memo[net] = self.e.node('state', token)
        return self.memo[net]


def audit(n):
    raw = (Path(__file__).resolve().parents[1] / REFERENCE).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == REFERENCE_SHA256, 'reference drift')
    reference = json.loads(raw)
    from tools.workstation_w_delay_ready import PARENT_SHA256
    require(reference['source_parent_sha256'] == PARENT_SHA256 and reference['scope'] == SCOPE,
            'reference owner/source mismatch')
    e = Expressions()
    values = {}
    for index, node in enumerate(reference['nodes']):
        kind, *args = node
        if kind == 'constant':
            value = args[0]
        elif kind == 'state':
            value = e.node('state', *args)
        else:
            require(kind == 'choose', 'unreviewed reference equation')
            value = e.choose(*(values[child] for child in args))
        values[index] = value
    c = DmaCircuit(n, e)
    c.allowed_opaque = {node[1] for node in reference['nodes']
                        if node[0] == 'state' and node[1].startswith('opaque/')}
    c.used_opaque = set()
    actual_names = {name for name in c.state if name.startswith(SCOPE + '/')}
    require(actual_names == set(reference['state_names']) and len(actual_names) == 803,
            'complete803-state inventory changed')
    proofs = []
    for name, root, init, clock in zip(reference['state_names'], reference['roots'],
                                      reference['inits'], reference['clocks'], strict=True):
        actual, actual_init, actual_clock = c.next_q(c.state[name])
        require((actual_init, actual_clock) == (init, clock), 'INIT/clock changed: ' + name)
        proofs.append(dict(register=name, **sat_compare(e, actual, values[root], label=name)))
    require(c.used_opaque == c.allowed_opaque, 'opaque output inventory changed')
    return dict(policy='task3_W_complete803_mapped_DMA_transition_correspondence_v1',
                reference_sha256=REFERENCE_SHA256,
                reference_netlist_sha256=reference['reference_netlist_sha256'],
                exact_reset_inclusive_next_Q_equations=len(proofs),
                INIT_and_clock_checked=True, no_internal_combinational_cuts=True,
                conditional_named_state_correspondence=True,
                arbitrary_opaque_outputs=sorted(c.used_opaque),
                whole_design_induction=False, proofs=proofs,
                routed_timing_verified=False, hardware_tested=False)
