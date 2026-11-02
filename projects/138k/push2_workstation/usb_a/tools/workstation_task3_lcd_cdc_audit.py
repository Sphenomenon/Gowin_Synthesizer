"""Paired LCD input chains in the actual mapped netlist.

This establishes pad-to-first-stage isolation, exact chain depth, clock, reset
and early-stage fanout. Final PANIC fanout is recorded for a separate business
boundary proof. Bundled-data stability, APB CDC and routed placement/MTBF also
remain separate gates. It installs no timing exceptions.
"""
from pathlib import Path
import hashlib

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_recording_phase1_cdc import complete_closure

POLICY = 'task3-paired-lcd-pad-synchronizers-v1'
PAIR = 'u_task3_pair_link'
PHY = PAIR + '/transport/phy'
SOURCE_SHA256 = {
    'rtl/workstation/workstation_task3_lcd_phy.sv':
        'd2ba6cb9be0f1597fe700c1200643eb9654aa2b16d46c69ae2d4bf75c4ee82eb',
    'rtl/workstation/workstation_task3_lcd_pins.sv':
        'c86ccfa544e0e463df423801152227dfc07feb8f633ad4436cae8feb51a4e87e',
    'rtl/workstation/workstation_task3_paired_link.sv':
        'c866d4418aaf3cf7f253ec53246481c429c3a7f26f2f90ba00ee83f7405ae062',
}


def require(ok, message):
    if not ok:
        raise ValueError('paired LCD synchronizer audit: ' + message)


def audit_lcd_input_chains(n, *, stage, role):
    require(role in ('M', 'W'), 'explicit paired role required')
    for path, expected in SOURCE_SHA256.items():
        require(hashlib.sha256((Path(stage) / path).read_bytes()).hexdigest() == expected,
                'reviewed source changed: ' + path)
    require(n.frames.get(PAIR, {}).get('kind') == 'workstation_task3_paired_link' and
            n.frames.get(PHY, {}).get('kind') == 'workstation_task3_lcd_phy',
            'actual paired link/PHY missing')
    g = Graph(n)
    root = g.register('u_reset', 'started')
    root_q = n.pin(root, 'Q')
    require(root_q not in g.high | g.low and n.pin(root, 'CLK') == 'clk_50m',
            'actual nonconstant local root publisher missing')
    reset = BooleanDiagram([root_q])
    # Networks use n->n. These are local pad names, not reversed cable contacts.
    data_pads = [('lcd_g', bit) for bit in range(1, 5)] if role == 'M' else [('lcd_r', bit) for bit in range(4)]
    req_pad, ack_pad, panic_pad = (('lcd_g', 5), ('lcd_g', 0), ('lcd_b', 2)) if role == 'M' else (
        ('lcd_r', 4), ('lcd_b', 0), ('lcd_b', 1))
    chains = []
    for name, pad in (('ack', ack_pad), ('req', req_pad), ('panic', panic_pad)):
        chains.append((name, pad, [g.register(PHY, name + '_meta'), g.register(PHY, name + '_sync')]))
    for bit, pad in enumerate(data_pads):
        chains.append(('data%d' % bit, pad, [g.register(PHY, stem, bit)
            for stem in ('data_meta', 'data_sync', 'data_settled')]))
    chains.append(('independent_panic', panic_pad, g.group(PAIR, 'peer_panic_sync', 2)))
    pad_consumers, rows = {}, []
    all_chain_regs = {path for _, _, chain in chains for path in chain}
    actual_sync_regs = {p for p in g.regs if p.startswith(PHY + '/') and
        p.rsplit('/', 1)[1].startswith(('ack_meta_', 'ack_sync_', 'req_meta_', 'req_sync_',
            'panic_meta_', 'panic_sync_', 'data_meta_', 'data_sync_', 'data_settled_'))}
    require(actual_sync_regs == all_chain_regs - set(chains[-1][2]), 'PHY synchronizer inventory changed')
    for name, (port, bit), chain in chains:
        pad_cell = '%s_%d_iobuf' % (port, bit)
        require(pad_cell in n.cells and n.cells[pad_cell]['kind'] == 'IOBUF',
                'actual input pad primitive missing: ' + pad_cell)
        require(set(n.cells[pad_cell]['ports']) == {'I', 'O', 'IO', 'OEN'} and
                n.pin(pad_cell, 'IO') == '%s[%d]' % (port, bit) and
                n.pin(pad_cell, 'I') in g.low and n.pin(pad_cell, 'OEN') in g.high,
                'receive pad direction/identity changed: ' + pad_cell)
        pad_net = n.pin(pad_cell, 'O')
        pad_consumers.setdefault(pad_cell, set()).add((chain[0], 'D', 'ff'))
        previous = pad_net
        ff_rows = []
        for index, path in enumerate(chain):
            cell = n.cells[path]
            require(cell['kind'] == 'DFFCE' and set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'} and
                    cell['parameters'].get('INIT', "1'b0") == "1'b0",
                    'synchronizer primitive/zero INIT changed: ' + path)
            require(n.pin(path, 'CLK') == 'clk_50m' and n.pin(path, 'CE') in g.high and
                    n.pin(path, 'D') == previous, 'chain clock/enable/direct input changed: ' + path)
            require(reset.net(g, n.pin(path, 'CLEAR')) == reset.invert(reset.inputs[root_q]),
                    'chain CLEAR is not inverse actual root: ' + path)
            closure = complete_closure(n, g, [path])
            if index + 1 < len(chain):
                require(closure['ff_endpoints'] == {chain[index + 1] + '/D': 'clk_50m'} and
                        not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                        'early synchronizer has extra/bypassed consumer: ' + path)
            elif name not in ('panic', 'independent_panic'):
                require(bool(closure['ff_endpoints']) and
                        all(clock == 'clk_50m' for clock in closure['ff_endpoints'].values()) and
                        not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                        'settled input has unexpected domain/opaque/top consumer: ' + path)
            ff_rows.append(dict(register=path, clock='clk_50m', effective_init=0,
                input=previous, common_root_clear=True, complete_consumer_closure=closure))
            previous = n.pin(path, 'Q')
        rows.append(dict(id=name, input_pad=pad_cell, pad_net=pad_net, stages=len(chain), registers=ff_rows))
    for pad, expected in pad_consumers.items():
        # Graph conservatively includes all IOBUF pins as opaque terminals.
        # Its O is the publisher, not an additional input consumer.
        actual = set(g.fan[n.pin(pad, 'O')]) - {(pad, 'O', 'unsupported')}
        require(actual == expected, 'raw asynchronous pad bypasses declared first stages: ' + pad)
    # No LCD data or handshake is allowed to act as an FPGA clock.
    for path in g.regs:
        if path.startswith(PAIR + '/'):
            require(n.pin(path, 'CLK') in ('ram_clk', 'clk_50m'), 'LCD signal used as local clock: ' + path)
    return dict(policy=POLICY, paired_role=role, source_sha256=SOURCE_SHA256,
        actual_root_publisher=root, input_pad_count=len(pad_consumers), chains=rows,
        synchronized_state_bits=len(all_chain_regs), all_raw_pad_fanout_exact=True,
        cable_network_mapping='M.n_to_W.n', no_LCD_signal_clock=True,
        external_bundled_data_timing_verified=False, APB_CDC_verified=False,
        synchronized_PANIC_business_fanout_verified=False, whole_source_CDC_accepted=False,
        routed_CDC_verified=False, physical_recovery_removal_verified=False,
        hardware_tested=False, timing_exceptions_installed=False)
