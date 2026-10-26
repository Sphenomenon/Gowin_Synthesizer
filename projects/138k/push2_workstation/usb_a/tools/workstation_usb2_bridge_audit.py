"""Check actual Gowin USB2 bridge reset fanout without granting timing exceptions."""

import re

from tools.workstation_synthesis_netlist import SynthesisNetlist


TRANSACTIONS = dict(
    cpu=('transmit_count_q', 'receive_index_q', 'descriptor_cpu_q', 'request_toggle_q',
         'result_sync_q', 'result_cpu_q', 'busy_q', 'done_q'),
    ulpi=('request_sync_q', 'result_toggle_q', 'result_mailbox_q', 'descriptor_ulpi_q',
          'state_q', 'upload_index_q', 'receive_count_q', 'elapsed_q', 'recovery_q'))


def audit_bridge_resets(netlist_text, top='workstation_usb2_host_mmio'):
    netlist = SynthesisNetlist(netlist_text, top)
    bridges = [scope for scope, frame in netlist.frames.items() if frame['kind'] == 'workstation_usb2_cpu_bridge']
    if len(bridges) != 1:
        raise ValueError('USB2 bridge reset audit requires one actual bridge module')
    bridge_scope = bridges[0]
    ancestors = {''}
    scope = bridge_scope
    while scope:
        ancestors.add(scope)
        scope = scope.rpartition('/')[0]
    cells = {label: netlist.cells[bridge_scope + '/' + label]
             for label in netlist.modules['workstation_usb2_cpu_bridge']}
    drivers = {}
    for instance_path, cell in netlist.cells.items():
        if instance_path.rpartition('/')[0] not in ancestors:
            continue
        kind, ports = cell['kind'], cell['ports']
        output = ('Q' if kind.startswith('DFF') else 'F' if re.fullmatch(r'LUT[1-6]', kind)
                  else dict(INV='O', GND='G', VCC='V').get(kind))
        if output and output in ports:
            net = netlist.pin(instance_path, output)
            if net in drivers:
                raise ValueError('USB2 bridge multiple synthesized reset-cone drivers')
            drivers[net] = instance_path

    def value(net, source, source_value, seen=()):
        if net == source:
            return source_value
        if net in ("1'b0", "1'b1"):
            return int(net[-1])
        if net in seen or net not in drivers:
            raise ValueError('USB2 bridge reset cone has an unverified input: ' + net)
        instance_path = drivers[net]
        cell = netlist.cells[instance_path]
        kind, ports = cell['kind'], cell['ports']
        if kind in ('GND', 'VCC'):
            return int(kind == 'VCC')
        if kind == 'INV':
            return 1 - value(netlist.pin(instance_path, 'I'), source, source_value, (*seen, net))
        if re.fullmatch(r'LUT[1-6]', kind):
            initial = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", cell['parameters'].get('INIT', ''))
            width = int(kind[-1])
            if not initial or int(initial[1]) != 1 << width:
                raise ValueError('USB2 bridge reset LUT identity changed')
            address = sum(value(netlist.pin(instance_path, 'I' + str(index)), source, source_value, (*seen, net)) << index
                          for index in range(width))
            return (int(initial[2], 16) >> address) & 1
        raise ValueError('USB2 bridge reset cone is not local combinational inversion: ' + drivers[net])

    def register(instance_path):
        cell = netlist.cells.get(instance_path, {})
        if cell.get('kind') != 'DFFCE' or set(cell.get('ports', {})) != {'Q', 'D', 'CLK', 'CLEAR', 'CE'}:
            raise ValueError('USB2 bridge release stage changed: ' + instance_path)
        if value(netlist.pin(instance_path, 'CE'), '', 0) != 1:
            raise ValueError('USB2 bridge release stage is not unconditionally clocked: ' + instance_path)
        return {port: netlist.pin(instance_path, port) for port in cell['ports']}

    def chain(scope, domain, purpose):
        prefix = domain + '_' + purpose + '_q'
        stages = []
        for index in range(2):
            matches = [scope + '/' + label for label in netlist.modules[netlist.frames[scope]['kind']]
                       if re.fullmatch(prefix + '_' + str(index) + r'_s\d+', label)]
            if len(matches) != 1:
                raise ValueError('USB2 bridge release stage missing: ' + prefix)
            stages.append(matches[0])
        first, second = (register(instance_path) for instance_path in stages)
        if (first['CLK'] != second['CLK'] or first['CLEAR'] != second['CLEAR'] or
                value(first['D'], '', 0) != 1 or second['D'] != first['Q']):
            raise ValueError('USB2 bridge two-stage reset release changed: ' + prefix)
        return dict(clock=second['CLK'], asynchronous_clear=netlist.cells[stages[1]]['ports']['CLEAR'],
                    asynchronous_clear_net=second['CLEAR'], ready=second['Q'], stages=stages)

    chains = {}
    for domain in TRANSACTIONS:
        chains[domain] = dict(session=chain(bridge_scope, domain, 'session'))
        target = 'reg_ack_o' if domain == 'cpu' else 'snapshot_toggle_q'
        targets = [bridge_scope + '/' + label for label in cells if re.fullmatch(target + r'_s\d+', label)]
        if len(targets) != 1:
            raise ValueError('USB2 bridge global reset observation register missing: ' + target)
        candidates = []
        for instance_path in netlist.cells:
            if instance_path.rpartition('/')[0] not in ancestors:
                continue
            if not re.fullmatch(domain + r'_release_q_1_s\d+', instance_path.rpartition('/')[2]):
                continue
            candidate = chain(instance_path.rpartition('/')[0], domain, 'release')
            if candidate['clock'] != chains[domain]['session']['clock']:
                continue
            try:
                inverse = [value(netlist.pin(targets[0], 'CLEAR'), candidate['ready'], source_value)
                           for source_value in (0, 1)]
            except ValueError:
                continue
            if inverse == [1, 0]:
                candidates.append(candidate)
        if len(candidates) != 1:
            raise ValueError('USB2 bridge global local-release chain not resolved: ' + domain)
        chains[domain]['release'] = candidates[0]
    if (chains['cpu']['release']['clock'] == chains['ulpi']['release']['clock'] or
            any(chains['cpu'][purpose]['asynchronous_clear_net'] != chains['ulpi'][purpose]['asynchronous_clear_net']
                for purpose in ('release', 'session'))):
        raise ValueError('USB2 bridge reset domain boundary changed')
    chain_cells = {stage for records in chains.values() for record in records.values() for stage in record['stages']}
    groups = {domain: {name: 0 for name in names} for domain, names in TRANSACTIONS.items()}
    reset_registers = {domain: 0 for domain in TRANSACTIONS}
    for label, cell in cells.items():
        instance_path = bridge_scope + '/' + label
        if not cell['kind'].startswith('DFF') or instance_path in chain_cells:
            continue
        ports = cell['ports']
        matches = [(domain, name) for domain, names in TRANSACTIONS.items() for name in names
                   if re.fullmatch(re.escape(name) + r'(?:_\d+)?_s\d+', label)]
        reset_pin = next((pin for pin in ('CLEAR', 'PRESET') if pin in ports), None)
        if not reset_pin and not matches:
            continue
        domains = [domain for domain in TRANSACTIONS if netlist.pin(instance_path, 'CLK') == chains[domain]['release']['clock']]
        if len(domains) != 1 or not reset_pin:
            raise ValueError('USB2 bridge register lost its local asynchronous reset: ' + label)
        domain = domains[0]
        purpose = 'session' if matches else 'release'
        if matches and (len(matches) != 1 or matches[0][0] != domain or reset_pin != 'CLEAR'):
            raise ValueError('USB2 bridge transaction reset domain changed: ' + label)
        source = chains[domain][purpose]['ready']
        try:
            inverse = [value(netlist.pin(instance_path, reset_pin), source, source_value) for source_value in (0, 1)]
        except (KeyError, ValueError) as error:
            raise ValueError('USB2 bridge register bypasses local reset release: ' + label) from error
        if inverse != [1, 0]:
            raise ValueError('USB2 bridge register bypasses local reset release: ' + label)
        reset_registers[domain] += 1
        if matches:
            groups[domain][matches[0][1]] += 1
    if any(count == 0 for names in groups.values() for count in names.values()):
        raise ValueError('USB2 bridge synthesized transaction register group missing')
    return dict(transaction_reset_topology_verified=True, bridge_instance=bridge_scope, release_chains=chains,
                transaction_registers=groups, locally_reset_registers=reset_registers,
                physical_reset_timing_verified=False, cdc_constraints_complete=False)
