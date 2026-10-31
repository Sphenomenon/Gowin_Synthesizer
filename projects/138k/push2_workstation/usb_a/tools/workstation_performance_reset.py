"""Narrow audit/proposal for the actual 448-bit telemetry async release chain.

This does not change a profile, emit RTL, or waive functional recovery/removal.
The reviewed frozen stream and UART bytes remain required prepared inputs.
"""
import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_synthesis_netlist import IDENTIFIER

SCOPE = 'u_runtime/u_performance_cdc'
POLICY = 'performance-telemetry-async-release-v1'
LOCKED = {
    'src/migration/gw138k_stream_cdc.sv': '90cb55acd6f83965d74b843993bed625d121ae2eefafbd928eb6fececb6e5376',
    'src/usb_host/gw138k_usb_performance_uart.sv': '5df104cd661e6467feca5aab92a2612ab5889d999157326032a228d8414848cf',
}


def require(condition, message):
    if not condition:
        raise ValueError('performance reset audit: ' + message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def proposed_constraints():
    targets = ' '.join(f'{SCOPE}/{stem}_{bit}_s*/CLEAR'
                       for stem in ('source_release', 'destination_release') for bit in range(3))
    lines = ['set_false_path -from [get_pins {u_reset/started_s*/Q u_audio_clock/audio_reset_pipe_3_s*/Q}] '
             '-to [get_pins {' + targets + '}]']
    for stem in ('source_release', 'destination_release'):
        for bit in range(2):
            lines.append(f'set_max_delay 2.000 -from [get_pins {{{SCOPE}/{stem}_{bit}_s*/Q}}] '
                         f'-to [get_pins {{{SCOPE}/{stem}_{bit + 1}_s*/D}}]')
    return '\n'.join(lines) + '\n'


DEMO_TIMING_POLICY = 'independent-demo-runtime-timing-v1'
DEMO_TIMING_TOOL = 'tools/workstation_performance_reset.py'


def demo_clock_reports():
    # Global worst-path limits can otherwise hide the much shorter 50 MHz
    # failures behind thousands of audio-domain paths. These only report.
    return '\n'.join(
        f'report_timing -{kind} {origin}-to_clock [get_clocks {{clk_50m}}] '
        '-max_paths 100 -max_common_paths 1'
        for origin in ('-from_clock [get_clocks {clk_50m}] ', '')
        for kind in ('setup', 'hold')) + '\n'


def demo_timing_lines(role):
    require(role in ('M', 'W'), 'unknown DEMO timing role')
    return ((proposed_constraints() if role == 'W' else '') + demo_clock_reports()).splitlines()


def select_demo_timing(stage, sdc, role):
    """Explicit DEMO-only additions; historical and accepted profiles stay out."""
    lines = demo_timing_lines(role)
    require(all(line not in sdc.splitlines() for line in lines), 'DEMO timing lines already installed')
    source = Path(stage) / DEMO_TIMING_TOOL
    result = sdc + ('' if not sdc or sdc.endswith('\n') else '\n') + '\n'.join(lines) + '\n'
    return result, dict(policy=DEMO_TIMING_POLICY, role=role, source=DEMO_TIMING_TOOL,
        source_sha256=digest(source), added_lines=lines,
        performance_release_selected=role == 'W', clock_or_business_exceptions_added=False,
        synchronizer_clear_exception_count=6 if role == 'W' else 0,
        routed_timing_verified=False)


def verify_demo_timing(stage, sdc, role, evidence):
    lines = demo_timing_lines(role)
    if evidence is None:
        require(all(line not in sdc.splitlines() for line in lines),
                'DEMO timing additions lack sealed selection evidence')
        return dict(mode='sealed_legacy_without_demo_timing_additions')
    require(evidence.get('source') == DEMO_TIMING_TOOL, 'DEMO timing source changed')
    require(evidence.get('source_sha256') == digest(Path(stage) / DEMO_TIMING_TOOL),
            'DEMO timing sealed source identity changed')
    expected = dict(policy=DEMO_TIMING_POLICY, role=role, source=DEMO_TIMING_TOOL,
        source_sha256=evidence['source_sha256'], added_lines=lines,
        performance_release_selected=role == 'W', clock_or_business_exceptions_added=False,
        synchronizer_clear_exception_count=6 if role == 'W' else 0,
        routed_timing_verified=False)
    require(evidence == expected, 'DEMO timing selection metadata changed')
    require(all(sdc.splitlines().count(line) == 1 for line in lines),
            'DEMO timing selected line absent or duplicated')
    return dict(evidence, installed_lines_verified=True)


def audit(n, *, mapping):
    g = Graph(n)
    sources = [g.register('u_reset', 'started'), g.register('u_audio_clock', 'audio_reset_pipe', 3)]
    require(n.cells[sources[0]]['kind'] == 'DFFRE' and n.pin(sources[0], 'CLK') == 'clk_50m' and
            n.cells[sources[1]]['kind'] == 'DFFCE' and n.pin(sources[1], 'CLK') == 'audio_clk',
            'actual asynchronous assertion producers changed')
    chains, protected, clears = [], set(), []
    common_clear = None
    for stem, domain in (('source_release', 'audio_clk'), ('destination_release', 'clk_50m')):
        regs = g.group(SCOPE, stem, 3)
        for bit, p in enumerate(regs):
            require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLK') == domain and n.pin(p, 'CE') in g.high and
                    n.cells[p]['parameters'].get('INIT', "1'b0") == "1'b0", 'release clock/CE/initial state changed')
            expected = g.high if bit == 0 else {n.pin(regs[bit - 1], 'Q')}
            require(n.pin(p, 'D') in expected, 'three-stage release fill/bypass changed')
            common_clear = n.pin(p, 'CLEAR') if common_clear is None else common_clear
            require(n.pin(p, 'CLEAR') == common_clear, 'release common asynchronous assertion changed')
            clears.append(p + '/CLEAR')
            closure = complete_closure(n, g, [p])
            require(not closure['primitive_endpoints'] and not closure['top_output_endpoints'], 'release reaches opaque/exported consumer')
            if bit < 2:
                require(closure['ff_endpoints'] == {regs[bit + 1] + '/D': domain}, 'release stage has extra consumer')
                protected.add(regs[bit + 1] + '/D')
            else:
                require(closure['ff_endpoints'] and all(pin.endswith('/CLEAR') and clk == domain and
                            pin.startswith(SCOPE + '/') for pin, clk in closure['ff_endpoints'].items()),
                        'final release must reset only same-domain local business registers')
                protected.update(closure['ff_endpoints'])
        chains.append(dict(stem=stem,clock=domain,stages=regs,release_edges=3,
                           final_functional_clear_count=len(closure['ff_endpoints'])))
    bd = BooleanDiagram([n.pin(p, 'Q') for p in sources])
    expected = bd.invert(bd.all(bd.inputs.values()))
    require(bd.net(g, common_clear) == expected, 'common async CLEAR must be NAND of exact reset50/audio-reset sources')
    # Routed parser portability must not hide a duplicate/ambiguous local pin.
    if mapping == 'routed':
        require(getattr(n, 'performance_release_lexical_verified', False), 'routed local named-port proof missing')
    return dict(policy=POLICY,assertion_source_pins=[p + '/Q' for p in sources],
        release_clear_pins=clears,common_async_clear=common_clear,common_assertion_nand_exact=True,
        chains=chains,protected_later_data_and_functional_clear_pins=sorted(protected),
        asynchronous_assertion_synchronous_three_edge_release=True,physical_cdc_accepted=False,
        recovery_removal_verified=False,hardware_tested=False)


def netlist(text, *, mapping):
    n = protocol_netlist(text, mapping=mapping)
    if mapping == 'routed':
        expected = {p for p, c in n.cells.items() if c['kind'] not in n.modules and p.startswith(SCOPE + '/')}
        instances = re.compile(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER + r')[ \t]*\((.*?)\);', re.M | re.S)
        ports = re.compile(r'\.(?:(\\[^\s]+)[ \t]+|([A-Za-z_$][A-Za-z0-9_$]*))\s*\(\s*([^()]*?)\s*\)')
        seen = set()
        for match in instances.finditer(text):
            p = match[2].removeprefix('\\')
            if p not in expected:
                continue
            require(p not in seen, 'duplicate routed local primitive')
            seen.add(p)
            bindings = {}
            for port in ports.finditer(match[3]):
                key = (port[1] or port[2]).removeprefix('\\')
                require(key not in bindings, 'duplicate routed local named port')
                bindings[key] = port[3].strip()
            require(not ports.sub('', match[3]).strip(' \t\r\n,') and bindings == n.cells[p]['ports'],
                    'routed local named-port parse disagreement')
        require(seen == expected, 'routed release primitive inventory incomplete')
        n.performance_release_lexical_verified = True
    return n


def validate_sdc(sdc, n, result):
    g = Graph(n)
    lines = proposed_constraints().splitlines()
    require(all(sdc.splitlines().count(line) == 1 for line in lines), 'exact proposed release constraints absent or duplicated')
    pins = {p + '/' + port for p, c in n.cells.items() for port in c['ports']}
    queries = re.findall(r'\[get_pins \{([^}]+)\}\]', lines[0])
    for body, expected in zip(queries, (result['assertion_source_pins'], result['release_clear_pins'])):
        selected = {pin for selector in body.split() for pin in pins if fnmatch.fnmatchcase(pin, selector)}
        require(selected == set(expected), 'async exception source/receiver query resolves outside exact inventory')
    for line, pair in zip(lines[1:], ((chain['stages'][bit],chain['stages'][bit + 1])
                                    for chain in result['chains'] for bit in range(2))):
        bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
        for body, expected in zip(bodies, (pair[0] + '/Q',pair[1] + '/D')):
            selected = {pin for selector in body.split() for pin in pins if fnmatch.fnmatchcase(pin,selector)}
            require(selected == {expected}, 'release data bound query inventory changed')
    protected = result['protected_later_data_and_functional_clear_pins']
    unrelated_payload_exceptions = []
    for raw in sdc.splitlines():
        line = raw.strip()
        if not line.startswith('set_false_path'):
            continue
        for kind, body in re.findall(r'-to\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line):
            matched = {pin for pin in protected for selector in body.split()
                       if fnmatch.fnmatchcase(pin if kind == 'get_pins' else pin.rsplit('/', 1)[0], selector)}
            if not matched:
                continue
            # Existing held-payload get_regs selectors also name cells whose
            # CLEAR is protected. Prove their explicit FF-Q sources cannot
            # reach any protected pin; never treat a register-name match as
            # proof of a physical reset path or waive a real reset endpoint.
            origins = re.findall(r'-from\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]', line)
            source_regs = set()
            if len(origins) == 1:
                source_kind, source_body = origins[0]
                candidates = set(g.regs) if source_kind == 'get_regs' else {p + '/Q' for p in g.regs}
                selected = {p for selector in source_body.split() for p in candidates if fnmatch.fnmatchcase(p, selector)}
                if source_kind == 'get_pins':
                    actual = {p for selector in source_body.split() for p in pins if fnmatch.fnmatchcase(p, selector)}
                    require(actual == selected, 'protected exception source contains a non-FF-Q pin')
                source_regs = selected if source_kind == 'get_regs' else {p.rsplit('/', 1)[0] for p in selected}
            require(source_regs and not matched.intersection(complete_closure(n, g, source_regs)['ff_endpoints']),
                    'exception reaches later data or functional recovery/removal: ' + line)
            unrelated_payload_exceptions.append(line)
    return dict(exact_source_and_six_async_clear_pins=True,all_four_later_data_bounds_ns=2.0,
                functional_recovery_removal_exceptions_absent=True,
                explicit_payload_source_closure_excludes_protected_pins=unrelated_payload_exceptions,
                full_clock_exception_audit=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--netlist',type=Path,required=True)
    parser.add_argument('--mapping',choices=('synthesis','routed'),default='synthesis')
    parser.add_argument('--sdc',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    manifest=ROOT/'vendor/workstation_inputs.json'
    registered=json.loads(manifest.read_text())
    require(all(registered.get(name)==expected for name,expected in LOCKED.items()), 'frozen source registry changed')
    dependencies=[ROOT/name for name in ('tools/workstation_native_protocol_audit.py',
        'tools/workstation_runtime_pcm_cdc.py','tools/workstation_recording_phase1_cdc.py',
        'tools/workstation_synthesis_netlist.py')]
    inputs = [args.project / name for name in LOCKED] + [args.netlist,args.sdc,Path(__file__),manifest,*dependencies]
    before = {str(p):digest(p) for p in inputs}
    for name, expected in LOCKED.items():
        require(digest(args.project / name) == expected, 'frozen stream/UART input changed: ' + name)
    n = netlist(args.netlist.read_text(),mapping=args.mapping)
    result = audit(n,mapping=args.mapping)
    result.update(mapping=args.mapping,input_sha256=before,sdc=validate_sdc(args.sdc.read_text(),n,result),
                  installed_in_candidate=False,profile_changed=False,routed_timing_verified=False,
                  source_policy='exact frozen stream/UART source, actual netlist and external SDC proposal only')
    require(before == {str(p):digest(p) for p in inputs}, 'audit inputs changed during run')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(policy=POLICY,passed=True,mapping=args.mapping)))


if __name__ == '__main__':
    main()
