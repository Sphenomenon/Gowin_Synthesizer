"""Native AE350 dedicated CORE clock contract; no EDA or board operations.

MUG1031-1.3.1 PDF54/56 (printed46/48) requires PLL_R[0] > clkout1.
The requested CST location and the actual routed location are distinct proofs.
"""
from pathlib import Path
import hashlib
import re

try:
    from tools.workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist
except ModuleNotFoundError:  # Existing physical auditors run from tools/.
    from workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist

POLICY = 'pll_r0_clkout1_v1'
SOURCE = 'boards/custom_138k/ae350.cst'
DESTINATION = 'constraints/custom_138k.ae350.cst'
INSTANCE = 'u_cpu_pll/PLL_inst'
SITE = 'PLL_R[0]'
OUTPUT = 'CLKOUT1'
TOP = 'workstation_custom_138k_top'
CONSTRAINT = 'INS_LOC "' + INSTANCE + '" ' + SITE + ';\n'
MANUAL = dict(path='docs/ae350/manuals/MUG1031-1.3.1_Gowin_RiscV_AE350_SOC硬件设计用户手册.pdf',
              sha256='0f357e21c8341a23a399a32a54bc706de953767235826ed39886924549756dc3',
              pdf_pages=[54, 56], printed_pages=[46, 48])


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('AE350 dedicated core clock: ' + message)


def assignments(text):
    """Read active INS_LOC commands and reject ambiguous placement syntax."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'(?m)//[^\n]*|#[^\n]*', '', text)
    result = []
    commands = text.split(';')
    require(not re.search(r'\bINS_LOC\b', commands[-1], re.I), 'unterminated INS_LOC command')
    for command in commands:
        command = command.strip()
        if not re.search(r'\bINS_LOC\b', command, re.I):
            continue
        match = re.fullmatch(r'INS_LOC\s+(?:"([^"\n]+)"|([^\s";]+))\s+([^\s;]+)', command)
        require(match is not None, 'unrecognized or indirect INS_LOC command')
        result.append((match[1] or match[2], match[3]))
    return result


def validate_constraints(text):
    selected = assignments(text)
    require([site for name, site in selected if name == INSTANCE] == [SITE],
            'exactly one ' + INSTANCE + ' assignment to ' + SITE + ' is required')
    require([name for name, site in selected if site == SITE] == [INSTANCE],
            SITE + ' has a competing PLL assignment')
    return dict(policy=POLICY, instance=INSTANCE, requested_site=SITE, output=OUTPUT,
                unique_assignment_verified=True)


def compose(root, stage, existing):
    root, stage = Path(root), Path(stage)
    payload = (root / SOURCE).read_bytes()
    require(payload == CONSTRAINT.encode(), 'versioned board constraint changed')
    original = assignments(existing)
    require(not any(name == INSTANCE or site == SITE for name, site in original),
            'parent CST already assigns the dedicated core PLL or site')
    combined = existing + ('' if existing.endswith('\n') else '\n') + payload.decode() + '\n'
    result = validate_constraints(combined)
    destination = stage / DESTINATION
    require(not destination.exists(), 'staged component already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    result.update(component=SOURCE, component_sha256=digest(payload), staged_component=DESTINATION,
                  before_cst_sha256=digest(existing.encode()), combined_cst_sha256=digest(combined.encode()),
                  manual=MANUAL, placement_verified=False, hardware_tested=False)
    return combined, result


def verify_prepared(root, stage, evidence):
    root, stage = Path(root), Path(stage)
    payload = (root / SOURCE).read_bytes()
    require(payload == CONSTRAINT.encode() and (stage / DESTINATION).read_bytes() == payload,
            'prepared board component differs from its source')
    combined = (stage / 'constraints/custom_138k.cst').read_text()
    suffix = CONSTRAINT + '\n'
    require(combined.endswith(suffix), 'dedicated core clock component is not the selected CST suffix')
    result = validate_constraints(combined)
    result.update(component=SOURCE, component_sha256=digest(payload), staged_component=DESTINATION,
                  before_cst_sha256=digest(combined[:-len(suffix)].encode()),
                  combined_cst_sha256=digest(combined.encode()), manual=MANUAL,
                  placement_verified=False, hardware_tested=False)
    require(result == evidence, 'prepared dedicated clock metadata changed')
    return result


def direct_net(netlist, scope, net, seen=()):
    """Resolve scalar module ports only; do not collapse IBUF/BUFG cells."""
    require(re.fullmatch(IDENTIFIER, net) is not None, 'non-scalar direct core clock binding')
    # Verilog escapes are lexical, not a different signal identity: \\core_clk
    # and core_clk name the same net. SynthesisNetlist already normalizes
    # formal port/declaration keys; normalize bindings before traversal too.
    net = net.removeprefix('\\')
    require((scope, net) not in seen, 'cyclic scalar clock binding')
    frame = netlist.frames[scope]
    if scope and net in frame['ports']:
        return direct_net(netlist, netlist.scopes[scope], frame['ports'][net], (*seen, (scope, net)))
    # Keep the scope separate: a top scalar named \\child/x is distinct from
    # local x inside the child module even though both display as child/x.
    return scope, net


def check_named_ports(text):
    # SynthesisNetlist intentionally has a small lexical surface. Check duplicate
    # formal names before its dictionaries could collapse an ambiguous binding.
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    require(not re.search(r'\bassign\b', text), 'continuous assignments are outside the direct routed clock proof')
    pattern = r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER + r')[ \t]*\((.*?)^[ \t]*\);'
    for module in re.finditer(r'^module\s+' + IDENTIFIER + r'\s*\((.*?)\);(.*?)^endmodule\b', text, re.M | re.S):
        header, body = module[1], module[2]
        ports = [name.strip().removeprefix('\\') for name in header.split(',')] if header.strip() else []
        require(all(re.fullmatch(IDENTIFIER, name.strip()) for name in header.split(',')) if ports else True,
                'unsupported or ANSI module port declaration')
        declarations = re.findall(r'^(?:input|output|inout)\s+(?:(?:wire|reg|logic)\s+)?'
                                  r'(?:\[\d+:\d+\]\s+)?(' + IDENTIFIER + r')\s*;', body, re.M)
        require(len(ports) == len(set(ports)) == len(declarations) and
                set(ports) == {name.removeprefix('\\') for name in declarations},
                'module port declarations are not completely parsed')
        for match in re.finditer(pattern, body, re.M | re.S):
            binding = r'\.(' + IDENTIFIER + r')\(\s*([^()]*?)\s*\)'
            require(re.fullmatch(r'[\s,]*', re.sub(binding, '', match[3])) is not None,
                    'unsupported or omitted named port binding on ' + match[2])
            names = [name.removeprefix('\\') for name, unused in re.findall(binding, match[3])]
            require(len(names) == len(set(names)), 'duplicate named port on ' + match[2])
        # The generated routed netlist has declarations, primitive instances
        # and defparams. Reject every other statement so the small hierarchy
        # reader cannot silently omit an additional driver or consumer.
        residue = re.sub(pattern, '', body, flags=re.M | re.S)
        declaration = (r'^(?:input|output|inout|wire)\s+(?:(?:wire|reg|logic)\s+)?'
                       r'(?:\[\d+:\d+\]\s+)?' + IDENTIFIER +
                       r'(?:\s*,\s*' + IDENTIFIER + r')*\s*;')
        residue = re.sub(declaration, '', residue, flags=re.M)
        residue = re.sub(r'defparam\s+' + IDENTIFIER + r'\s*\.\w+\s*=\s*[^;]+;', '', residue)
        require(not residue.strip(), 'unsupported or omitted routed netlist statement')
    return text


def audit_routed(cst, timing_report, vo, *, top=TOP):
    result = validate_constraints(cst)
    rows, locationless_rows = [], []
    node = re.compile(re.escape(INSTANCE) + r'/CLKOUT[0-6]$')
    for number, line in enumerate(timing_report.splitlines(), 1):
        fields = line.split()
        if not fields or node.fullmatch(fields[-1]) is None or 'tCL' not in fields:
            continue
        # Pulse/clock summary sections omit fanout and physical site. They are
        # valid clock observations, but cannot prove placement. Keep them
        # distinct from the full routed path rows and require the latter below.
        if re.fullmatch(r'\s*[+-]?\d+(?:\.\d+)?\s+[+-]?\d+(?:\.\d+)?\s+tCL\s+\S+\s+'
                        + re.escape(INSTANCE) + r'/CLKOUT[0-6]\s*', line):
            locationless_rows.append(number)
            continue
        match = re.fullmatch(r'\s*[+-]?\d+(?:\.\d+)?\s+[+-]?\d+(?:\.\d+)?\s+tCL\s+\S+\s+\d+\s+'
                             r'(PLL_[A-Z]\[\d+\])\s+(' + re.escape(INSTANCE) + r'/CLKOUT[0-6])\s*', line)
        require(match is not None, 'unrecognized routed PLL clock location row')
        rows.append(dict(line=number, site=match[1], node=match[2]))
    require(any(row['node'] == INSTANCE + '/' + OUTPUT for row in rows),
            'actual routed CLKOUT1 location evidence is missing')
    require({row['site'] for row in rows} == {SITE}, 'actual routed CPU PLL is not uniquely at ' + SITE)
    netlist = SynthesisNetlist(check_named_ports(vo), top)
    require(INSTANCE in netlist.cells and netlist.cells[INSTANCE]['kind'] == 'PLL',
            'unique CPU PLL primitive is missing')
    cpus = [name for name, cell in netlist.cells.items() if cell['kind'] == 'AE350_SOC']
    require(len(cpus) == 1, 'exactly one AE350 hard macro is required')
    cpu = cpus[0]
    def net(name, port):
        require(port in netlist.cells[name]['ports'], 'required pin is missing: ' + name + '/' + port)
        return direct_net(netlist, netlist.scopes[name], netlist.cells[name]['ports'][port])
    core = net(INSTANCE, OUTPUT)
    require(net(cpu, 'CORE_CLK') == core, 'CORE_CLK is not directly driven by the dedicated CLKOUT1')
    require(not any(direct_net(netlist, '', name) == core for name in netlist.directions[top]),
            'direct core clock must not be an external top port')
    endpoints = []
    for name, cell in netlist.cells.items():
        if cell['kind'] in netlist.modules:
            continue
        for port, value in cell['ports'].items():
            scope = netlist.scopes[name]
            scalar = re.fullmatch(IDENTIFIER, value) is not None
            touches_core = any(direct_net(netlist, scope, token[0]) == core
                               for token in re.finditer(IDENTIFIER, value))
            if not touches_core:
                continue
            require(scalar, 'non-scalar consumer/driver on direct core clock: ' + name + '/' + port)
            allowed = ((name == INSTANCE and port == OUTPUT) or
                       (name == cpu and port == 'CORE_CLK') or
                       (cell['kind'].startswith('DFF') and port == 'CLK'))
            require(allowed, 'unreviewed driver/consumer on direct core clock: ' + name + '/' + port)
            endpoints.append(name + '/' + port)
    result.update(observed_site=SITE, actual_output=OUTPUT, routed_location_rows=rows,
                  locationless_clock_row_lines=locationless_rows,
                  hard_macro=cpu, core_clock_net=(core[0] + '/' if core[0] else '') + core[1],
                  core_clock_net_identity=dict(scope=core[0], name=core[1]),
                  direct_core_clock_endpoints=sorted(endpoints),
                  direct_unique_driver_verified=True, placement_verified=True,
                  routed_report_sha256=digest(timing_report.encode()), routed_vo_sha256=digest(vo.encode()),
                  cst_sha256=digest(cst.encode()), manual=MANUAL,
                  full_physical_acceptance=False, hardware_tested=False)
    return result
