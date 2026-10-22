"""Explicit native clock declarations and source-netlist topology checks."""

from fractions import Fraction
from pathlib import Path
import json
import re

from tools.stage_usb_firmware import sha


PLAN_SOURCE = 'boards/custom_138k/clocks.json'
OPAQUE_DDR = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT'
EXPECTED_HZ = dict(clk_50m=50000000, ulpi_60m=60000000, audio_76m8=76800000, usb_48m=48000000,
                   ddr_mem400=400000000, ddr_ui100=100000000, video_ref49=49500000,
                   video_serial742=742500000, video_pixel148=148500000, cpu_ram50=50000000,
                   cpu_core100=100000000)
IDENTIFIER = r'(?:\\[^\s]+|[A-Za-z_$][A-Za-z0-9_$]*)'


def clock_bundle(root):
    source = Path(root) / PLAN_SOURCE
    plan = json.loads(source.read_text())
    if plan.get('schema') != 1 or plan.get('identity') != 'custom138k-native-clocks-20261022-v1':
        raise ValueError('native clock plan identity changed')
    entries = [*plan['primary'], *plan['generated']]
    if (len(entries) != len(EXPECTED_HZ) or {entry['name']: entry['frequency_hz'] for entry in entries} != EXPECTED_HZ or
            len({entry.get('pin', entry.get('port')) for entry in entries}) != len(entries)):
        raise ValueError('native clock frequency or target inventory changed')
    if {entry['name']: entry['port'] for entry in plan['primary']} != dict(clk_50m='clk_50m', ulpi_60m='usb2_ulpi_clk'):
        raise ValueError('native primary clock ports changed')
    clocks, lines = {}, []
    for entry in plan['primary']:
        period = 1000000000 / entry['frequency_hz']
        lines.append(f"create_clock -name {entry['name']} -period {period:.6f} -waveform {{0.000000 {period / 2:.6f}}} [get_ports {{{entry['port']}}}]")
        clocks[entry['name']] = dict(query=f"[get_ports {{{entry['port']}}}]", **entry)
    for entry in plan['generated']:
        if entry['source'] not in clocks:
            raise ValueError('native generated clock source missing or not ordered: ' + entry['name'])
        parent = clocks[entry['source']]
        ratio = Fraction(entry['frequency_hz'], parent['frequency_hz'])
        if 'edges' in entry:
            if entry['name'] != 'video_pixel148' or entry['edges'] != [1, 7, 11] or ratio != Fraction(1, 5):
                raise ValueError('native pixel /5 60/40 waveform changed')
            transform = '-edges {1 7 11}'
        else:
            if entry['name'] == 'video_pixel148':
                raise ValueError('native pixel clock lost explicit 60/40 waveform')
            transform = f'-multiply_by {ratio.numerator} -divide_by {ratio.denominator}'
        if 'opaque_ip_prefix' in entry and (entry['pin'] != OPAQUE_DDR or entry['opaque_ip_prefix'] != 'u_memory/u_ddr3/gw3_top'):
            raise ValueError('native unexpected opaque clock target')
        query = f"[get_pins {{{entry['pin']}}}]"
        lines.append(f"create_generated_clock -name {entry['name']} -source {parent['query']} -master_clock {entry['source']} {transform} {query}")
        clocks[entry['name']] = dict(query=query, **entry)
    return dict(source=PLAN_SOURCE, source_sha256=sha(source), plan=plan, sdc='\n'.join(lines) + '\n')


def audit_clocks(root, stage, netlist_text):
    bundle = clock_bundle(root)
    if (Path(stage) / 'constraints/custom_138k.sdc').read_text() != bundle['sdc']:
        raise ValueError('native staged SDC differs from the explicit clock plan')
    modules = {}
    instance_pattern = re.compile(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER + r')[ \t]*\((.*?)^[ \t]*\);', re.M | re.S)
    for match in re.finditer(r'^module\s+(' + IDENTIFIER + r')\s*\((.*?)^endmodule\b', netlist_text, re.M | re.S):
        name = match[1].removeprefix('\\')
        if name in modules:
            raise ValueError('native duplicate netlist module: ' + name)
        instances = {}
        for instance in instance_pattern.finditer(match[2]):
            kind, label = instance[1].removeprefix('\\'), instance[2].removeprefix('\\')
            if label in instances:
                raise ValueError('native duplicate instance: ' + label)
            parameters = dict(re.findall(r'defparam ' + re.escape(instance[2]) + r'\.(\w+)\s*=\s*([^;]+);', match[2])) if kind in ('PLL', 'CLKDIV') else {}
            ports = dict(re.findall(r'\.(\w+)\(\s*([^()]*?)\s*\)', instance[3]))
            instances[label] = dict(kind=kind, ports=ports, parameters=parameters)
        modules[name] = instances
    frames = {'': dict(kind='workstation_custom_138k_top', ports={})}
    cells = {}

    def walk(kind, prefix, ancestors):
        if kind in ancestors:
            raise ValueError('native recursive clock hierarchy')
        for label, instance in modules[kind].items():
            path = prefix + '/' + label if prefix else label
            cells[path] = instance
            if instance['kind'] in modules:
                frames[path] = instance
                walk(instance['kind'], path, (*ancestors, kind))

    if frames['']['kind'] not in modules:
        raise ValueError('native clock top missing')
    walk(frames['']['kind'], '', ())

    def canonical(scope, net, seen=()):
        key = (scope, net)
        if key in seen:
            raise ValueError('native cyclic clock connection')
        if scope and net in frames[scope]['ports']:
            return canonical(scope.rpartition('/')[0], frames[scope]['ports'][net], (*seen, key))
        for label, instance in modules[frames[scope]['kind']].items():
            if instance['kind'] in ('IBUF', 'BUFG') and instance['ports'].get('O') == net:
                return canonical(scope, instance['ports']['I'], (*seen, key))
        return (scope + '/' if scope else '') + net

    clocks, deferred = {}, []
    for entry in bundle['plan']['primary']:
        clocks[entry['name']] = dict(net=entry['port'], frequency_hz=entry['frequency_hz'])
    for entry in bundle['plan']['generated']:
        path, _, pin = entry['pin'].rpartition('/')
        parent = clocks[entry['source']]
        if 'opaque_ip_prefix' in entry:
            opaque = cells.get(entry['opaque_ip_prefix'], {})
            if opaque.get('kind') != '~GW_DDR3_PHY_MC.DDR3_Memory_Interface_Top':
                raise ValueError('native DDR opaque-IP boundary changed')
            deferred.append(entry['pin'])
            clocks[entry['name']] = dict(net=None, frequency_hz=entry['frequency_hz'], verified=False)
            continue
        cell = cells.get(path)
        if not cell or pin not in cell['ports'] or cell['kind'] not in ('PLL', 'CLKDIV'):
            raise ValueError('native clock target not resolved: ' + entry['pin'])
        parameters = cell['parameters']
        scope = path.rpartition('/')[0]
        input_pin = 'CLKIN' if cell['kind'] == 'PLL' else 'HCLKIN'
        if canonical(scope, cell['ports'][input_pin]) != parent['net']:
            raise ValueError('native clock source wiring changed: ' + entry['name'])
        if cell['kind'] == 'PLL':
            output_index = int(pin.removeprefix('CLKOUT'))
            for parameter in ('DYN_FBDIV_SEL', 'DYN_IDIV_SEL', 'DYN_MDIV_SEL', f'DYN_ODIV{output_index}_SEL'):
                if parameters.get(parameter) != '"FALSE"':
                    raise ValueError('native unexpected dynamic PLL divider')
            for parameter in ('DYN_DPA_EN', f'DYN_PE{output_index}_SEL', f'DYN_DT{output_index}_SEL'):
                if parameters.get(parameter) != '"FALSE"':
                    raise ValueError('native unexpected dynamic PLL phase')
            if (parameters.get(f'CLKOUT{output_index}_EN') != '"TRUE"' or
                    parameters.get('CLKFB_SEL') != '"INTERNAL"' or
                    any(parameters.get(f'CLKOUT{output_index}_{suffix}') != '0'
                        for suffix in ('PE_COARSE', 'PE_FINE', 'DT_STEP'))):
                raise ValueError('native PLL phase, feedback or output enable changed')
            if int(parameters['FBDIV_SEL']) != 1 or int(parameters['IDIV_SEL']) != 1:
                raise ValueError('native PLL feedback/input mode changed')
            if Fraction(parameters['FCLKIN'].strip('"')) * 1000000 != parent['frequency_hz']:
                raise ValueError('native PLL declared input frequency changed')
            multiplier = Fraction(int(parameters['MDIV_SEL'])) + Fraction(int(parameters.get('MDIV_FRAC_SEL', '0')), 8)
            divisor = Fraction(int(parameters[f'ODIV{output_index}_SEL'])) + Fraction(int(parameters.get(f'ODIV{output_index}_FRAC_SEL', '0')), 8)
            actual = parent['frequency_hz'] * multiplier / divisor
        else:
            divisor = int(parameters['DIV_MODE'].strip('"'))
            if divisor != 5 or entry.get('edges') != [1, 7, 11]:
                raise ValueError('native pixel divider waveform changed')
            actual = Fraction(parent['frequency_hz'], divisor)
        if actual != entry['frequency_hz']:
            raise ValueError('native PLL/divider frequency does not match SDC: ' + entry['name'])
        clocks[entry['name']] = dict(net=canonical(scope, cell['ports'][pin]), frequency_hz=int(actual), verified=True)
    return dict(plan_source=bundle['source'], plan_sha256=bundle['source_sha256'], clocks=clocks,
                deferred_opaque_ip_targets=deferred, source_netlist_verified=not deferred,
                routed_timing_verified=False, constraints_complete=False)
