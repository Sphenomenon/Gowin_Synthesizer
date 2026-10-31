"""Native independent RTC source, conservative STA bound and direct-net gate.

The maintained accumulator averages 32768 Hz; STA uses two minimum 762-cycle
half-periods, not the average period. This is no measured jitter/board claim.
"""
from pathlib import Path
import hashlib
import re

try:
    from tools.workstation_ae350_clock_placement import check_named_ports, direct_net
    from tools.workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist
except ModuleNotFoundError:
    from workstation_ae350_clock_placement import check_named_ports, direct_net
    from workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist

POLICY = 'reference50_fractional32768_bound1524_v1'
SOURCE = 'rtl/clock/workstation_ae350_rtc.sv'
SOURCE_SHA256 = '59fbe21b3a6627245c9edb38484e9ae9955f615e9dba445a21e22ff66a22f536'
SHARED_TOP = 'rtl/workstation/gw138k_push_workstation_top.v'
TOP = 'workstation_custom_138k_top'
INSTANCE = 'u_rtc/rtc_tick_s1'
CLOCK_PIN = INSTANCE + '/Q'
CLOCK_NAME = 'cpu_rtc_bound'
SDC = ('create_generated_clock -name ' + CLOCK_NAME + ' -source [get_ports {clk_50m}] '
       '-divide_by 1524 [get_pins {' + CLOCK_PIN + '}]\n')
CLOCK_ENTRY = dict(name=CLOCK_NAME, source='clk_50m', pin=CLOCK_PIN,
                   average_frequency_hz=32768, minimum_half_period_reference_cycles=762,
                   maximum_half_period_reference_cycles=763, sta_divide_by=1524,
                   sta_minimum_period_ns=30480, policy=POLICY)
SOURCE_BINDING = ("`ifdef WORKSTATION_CUSTOM_138K\n"
                  "    wire rtc_clk;\n"
                  "    workstation_ae350_rtc u_rtc(.clk_50m(clk_50m),.reset_n(system_reset_n),.rtc_clk(rtc_clk));\n"
                  "`endif")
CPU_BINDING = ("`ifdef WORKSTATION_CUSTOM_138K\n"
               "        .RTC_CLK(rtc_clk),\n"
               "`else\n"
               "        .RTC_CLK(clk_50m),\n"
               "`endif")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('AE350 independent RTC: ' + message)


def validate_constraints(text):
    lines = text.splitlines()
    require(lines.count(SDC.rstrip('\n')) == 1, 'exact conservative RTC clock declaration is required')
    for line in lines:
        active = line.strip()
        if not active or active.startswith('#'):
            continue
        require(not re.search(r'\b(?:remove_clock|remove_generated_clock|reset_timing)\b', active),
                'RTC clock removal/reset is not allowed')
        if CLOCK_NAME in active or CLOCK_PIN in active or 'u_rtc/' in active:
            require(line == SDC.rstrip('\n'), 'competing RTC clock declaration or override')
    return dict(clock_name=CLOCK_NAME, clock_pin=CLOCK_PIN,
                sta_divide_by=1524, sta_minimum_period_ns=30480,
                average_frequency_hz=32768, average_is_not_sta_frequency=True)


def source_contract(root):
    root = Path(root)
    payload = (root / SOURCE).read_bytes()
    require(digest(payload) == SOURCE_SHA256, 'maintained RTC source identity changed')
    top = (root / SHARED_TOP).read_text()
    require(top.count(SOURCE_BINDING) == 1 and top.count(CPU_BINDING) == 1 and
            len(re.findall(r'\bworkstation_ae350_rtc\s+u_rtc\s*\(', top)) == 1 and
            top.count('.RTC_CLK(') == 2 and top.count('wire system_reset_n=reset_n;') == 1,
            'native RTC source/reference/reset or hard-macro binding changed')
    return dict(policy=POLICY, source=SOURCE, source_sha256=SOURCE_SHA256,
                source_reference_hz=50000000, reset='system_reset_n',
                independent_of_cpu_apb_memory_ready=True, half_period_reference_cycles=[762, 763],
                constraint=SDC.rstrip('\n'),
                **validate_constraints(SDC), source_binding_verified=True,
                synthesis_connectivity_verified=False, sta_verified=False,
                physical_timing_verified=False, hardware_tested=False)


def prepared(root, stage):
    result = source_contract(root)
    stage = Path(stage)
    require((stage / SOURCE).read_bytes() == (Path(root) / SOURCE).read_bytes(),
            'prepared RTC source differs from maintained source')
    require((stage / SHARED_TOP).read_bytes() == (Path(root) / SHARED_TOP).read_bytes(),
            'prepared RTC composition differs from maintained source')
    validate_constraints((stage / 'constraints/custom_138k.sdc').read_text())
    return result


def verify_prepared(root, stage, evidence):
    result = prepared(root, stage)
    require(result == evidence, 'prepared RTC metadata changed')
    return result


def audit_netlist(text, *, top=TOP):
    n = SynthesisNetlist(check_named_ports(text), top)
    cell = n.cells.get(INSTANCE, {})
    require(cell.get('kind') == 'DFFCE' and {'CLK', 'D', 'CLEAR', 'CE', 'Q'}.issubset(cell.get('ports', {})) and
            n.pin(INSTANCE, 'CLK') == 'clk_50m' and
            cell.get('parameters', {}).get('INIT') == "1'b0",
            'kept RTC register or independent 50MHz source changed')
    ones = {"1'b1"} | {n.pin(p, 'V') for p, c in n.cells.items() if c['kind'] == 'VCC'}
    require(n.pin(INSTANCE, 'CE') in ones, 'kept RTC toggle register enable is not constant one')
    cpus = [p for p, c in n.cells.items() if c['kind'] == 'AE350_SOC']
    require(len(cpus) == 1, 'exactly one AE350 hard macro is required')
    cpu = cpus[0]

    def net(name, port):
        require(port in n.cells[name]['ports'], 'required RTC pin missing: ' + name + '/' + port)
        return direct_net(n, n.scopes[name], n.cells[name]['ports'][port])

    rtc = net(INSTANCE, 'Q')
    require(net(cpu, 'RTC_CLK') == rtc, 'RTC_CLK is not directly driven by the kept RTC Q')
    require(not any(direct_net(n, '', port) == rtc for port in n.directions[top]),
            'RTC output must not be an external top port')
    endpoints = []
    for name, cell in n.cells.items():
        if cell['kind'] in n.modules:
            continue
        for port, value in cell['ports'].items():
            scope = n.scopes[name]
            if not any(direct_net(n, scope, token[0]) == rtc for token in re.finditer(IDENTIFIER, value)):
                continue
            require(re.fullmatch(IDENTIFIER, value) is not None,
                    'non-scalar driver/consumer on RTC output: ' + name + '/' + port)
            feedback = (name.startswith('u_rtc/') and re.fullmatch(r'LUT[1-6]', cell['kind']) and
                        re.fullmatch(r'I[0-5]', port) and int(port[1:]) < int(cell['kind'][3:]))
            require((name == INSTANCE and port == 'Q') or (name == cpu and port == 'RTC_CLK') or feedback,
                    'unreviewed driver/consumer on RTC output: ' + name + '/' + port)
            endpoints.append(name + '/' + port)
    return dict(policy=POLICY, register=INSTANCE, source_clock='clk_50m', hard_macro=cpu,
                rtc_net_identity=dict(scope=rtc[0], name=rtc[1]), direct_endpoints=sorted(endpoints),
                direct_unique_driver_verified=True, synthesis_connectivity_verified=True,
                netlist_sha256=digest(text.encode()), average_frequency_hz=32768,
                sta_minimum_period_ns=30480, sta_verified=False,
                physical_timing_verified=False, hardware_tested=False)
