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


DEMO_TIMING_POLICY = 'independent-demo-runtime-timing-v2'
DEMO_TIMING_LEGACY_POLICY = 'independent-demo-runtime-timing-v1'
W_RETURN_TIMING_POLICY = 'independent-demo-w-return-mailbox-timing-v3'
DEMO_HELD_TIMING_POLICIES = (DEMO_TIMING_POLICY, W_RETURN_TIMING_POLICY)
DEMO_TIMING_TOOL = 'tools/workstation_performance_reset.py'


def demo_clock_reports():
    # Global worst-path limits can otherwise hide the much shorter 50 MHz
    # failures behind thousands of audio-domain paths. These only report.
    return '\n'.join(
        f'report_timing -{kind} {origin}-to_clock [get_clocks {{clk_50m}}] '
        '-max_paths 100 -max_common_paths 1'
        for origin in ('-from_clock [get_clocks {clk_50m}] ', '')
        for kind in ('setup', 'hold')) + '\n'


def demo_timing_lines(role, *, policy=DEMO_TIMING_POLICY):
    require(role in ('M', 'W'), 'unknown DEMO timing role')
    require(policy in DEMO_HELD_TIMING_POLICIES, 'unknown DEMO timing policy revision')
    extra = ''
    if policy == W_RETURN_TIMING_POLICY:
        require(role == 'W', 'W return timing policy requires W role')
        from tools.workstation_w_return_mailbox_cdc import constraints
        extra = constraints()
    return ((proposed_constraints() if role == 'W' else '') + demo_clock_reports() +
            demo_held_handshake_constraints() + extra).splitlines()


def demo_held_handshake_constraints():
    """Only explicit DEMO selections gain the reviewed 8/49-bit held bounds."""
    lines = []
    for scope, source, destination in (
            ('u_managed/pc_bytes', 'held_data', 'destination_data'),
            ('u_managed/control_cdc', 'request_held', 'request_local')):
        path = (f'-from [get_pins {{{scope}/{source}_*_s*/Q}}] '
                f'-to [get_pins {{{scope}/{destination}_*_s*/D}}]')
        lines.extend(('set_max_delay 13.020 ' + path, 'set_false_path -hold ' + path))
    for scope, source, first, second in (
            ('u_managed/pc_bytes', 'request_toggle', 'req_meta', 'req_sync'),
            ('u_managed/control_cdc', 'request_toggle', 'req_meta', 'req_sync'),
            ('u_managed/control_cdc', 'acknowledge_toggle', 'ack_meta', 'ack_sync')):
        lines.extend((f'set_false_path -from [get_pins {{{scope}/{source}_s*/Q}}] '
                      f'-to [get_pins {{{scope}/{first}_s*/D}}]',
                      f'set_max_delay 2.000 -from [get_pins {{{scope}/{first}_s*/Q}}] '
                      f'-to [get_pins {{{scope}/{second}_s*/D}}]'))
    return '\n'.join(lines) + '\n'


def demo_timing_metadata(role, source_sha256, *, legacy=False, policy=None, return_mailbox=None):
    policy = policy or (DEMO_TIMING_LEGACY_POLICY if legacy else DEMO_TIMING_POLICY)
    require(policy in (*DEMO_HELD_TIMING_POLICIES, DEMO_TIMING_LEGACY_POLICY),
            'unknown DEMO timing policy revision')
    require(not legacy or policy == DEMO_TIMING_LEGACY_POLICY, 'legacy timing policy mismatch')
    legacy = policy == DEMO_TIMING_LEGACY_POLICY
    lines = (((proposed_constraints() if role == 'W' else '') + demo_clock_reports()).splitlines()
             if legacy else demo_timing_lines(role, policy=policy))
    result = dict(policy=policy,
        role=role, source=DEMO_TIMING_TOOL, source_sha256=source_sha256, added_lines=lines,
        performance_release_selected=role == 'W',
        synchronizer_clear_exception_count=6 if role == 'W' else 0,
        routed_timing_verified=False)
    if legacy:
        result['clock_or_business_exceptions_added'] = False
    else:
        result.update(whole_clock_exceptions_added=False, held_handshake_constraints_added=True,
            held_handshake_payload_bits=dict(pc_request=8, apb_request=49),
            held_handshake_setup_budget_ns=13.020, held_handshake_only_hold_waived=True,
            toggle_first_stage_exception_count=3, toggle_second_stage_max_delay_ns=2.0)
    if policy == W_RETURN_TIMING_POLICY:
        require(isinstance(return_mailbox, dict), 'W return mailbox source selection missing')
        result['return_mailbox'] = return_mailbox
    else:
        require(return_mailbox is None, 'old timing policy cannot acquire W return selection')
    return result


def select_demo_timing(stage, sdc, role, *, policy=DEMO_TIMING_POLICY):
    """Explicit DEMO-only additions; historical and accepted profiles stay out."""
    lines = demo_timing_lines(role, policy=policy)
    require(all(line not in sdc.splitlines() for line in lines), 'DEMO timing lines already installed')
    source = Path(stage) / DEMO_TIMING_TOOL
    result = sdc + ('' if not sdc or sdc.endswith('\n') else '\n') + '\n'.join(lines) + '\n'
    return_mailbox = None
    if policy == W_RETURN_TIMING_POLICY:
        from tools.workstation_w_return_mailbox_cdc import selection_metadata
        return_mailbox = selection_metadata(stage)
    return result, demo_timing_metadata(role, digest(source), policy=policy, return_mailbox=return_mailbox)


def verify_demo_timing(stage, sdc, role, evidence):
    lines = demo_timing_lines(role)
    # Old M/W candidates must not import or stage the new W-only helper.
    # Recognize its qualification scope without copying its constraints.
    def has_return_qualification():
        for line in sdc.splitlines():
            if 'recording_ble_store/return_generation_' not in line:
                continue
            if any('recording_ble_store/' + stem in line for stem in (
                    'return_ack_', 'unpack_active_', 'unpack_data_', 'unpack_word_', 'unpack_index_')):
                return True
            if 'recording_ble_store/unpack_generation_' in line and '/CE' in line:
                return True
        return False
    if evidence is None:
        require(all(line not in sdc.splitlines() for line in lines) and not has_return_qualification(),
                'DEMO timing additions lack sealed selection evidence')
        return dict(mode='sealed_legacy_without_demo_timing_additions')
    require(evidence.get('source') == DEMO_TIMING_TOOL, 'DEMO timing source changed')
    require(evidence.get('source_sha256') == digest(Path(stage) / DEMO_TIMING_TOOL),
            'DEMO timing sealed source identity changed')
    require(evidence.get('policy') in (*DEMO_HELD_TIMING_POLICIES, DEMO_TIMING_LEGACY_POLICY),
            'unknown DEMO timing policy revision')
    legacy = evidence['policy'] == DEMO_TIMING_LEGACY_POLICY
    return_mailbox = None
    if evidence['policy'] == W_RETURN_TIMING_POLICY:
        require(role == 'W', 'W return timing policy requires W role')
        from tools.workstation_w_return_mailbox_cdc import verify_selection
        return_mailbox = verify_selection(stage, evidence.get('return_mailbox'))
    else:
        require(not has_return_qualification(),
                'old DEMO timing cannot acquire unsealed W return constraints')
    expected = demo_timing_metadata(role, evidence['source_sha256'], legacy=legacy,
        policy=evidence['policy'], return_mailbox=return_mailbox)
    lines = expected['added_lines']
    require(evidence == expected, 'DEMO timing selection metadata changed')
    require(all(sdc.splitlines().count(line) == 1 for line in lines),
            'DEMO timing selected line absent or duplicated')
    if legacy:
        require(not any(line in sdc.splitlines() for line in demo_held_handshake_constraints().splitlines()),
                'legacy DEMO timing cannot acquire unsealed held-handshake constraints')
    return dict(evidence, installed_lines_verified=True)


def audit_demo_held_handshakes(stage, sdc, role, evidence, n, *, mapping, netlist_text=None):
    """One selected gate shared by strict synthesis and actual routed entry."""
    selected = verify_demo_timing(stage, sdc, role, evidence)
    if selected.get('policy') not in DEMO_HELD_TIMING_POLICIES:
        return dict(gate_applied=False, policy=selected.get('policy'),
                    scope='sealed legacy without new DEMO held-handshake policy')
    # The caller has already sealed the complete candidate input closure.
    # Bind the extra constant-reset proof to the actual consumed composition.
    top_path = Path(stage) / 'rtl/workstation/gw138k_push_workstation_top.v'
    controlled_path = Path(stage) / 'rtl/workstation/workstation_runtime_controlled.sv'
    top, controlled = top_path.read_text(), controlled_path.read_text()
    instance = re.search(r'workstation_runtime_controlled\s*#\(.*?\)\s*u_managed\s*\(.*?\);', top, re.S)
    require(top.count("wire button1_n=1'b1;") == 1 and instance is not None and
            instance[0].count('.SEPARATE_COMMON_RESET(1)') == 1 and
            instance[0].count('.common_reset_ni(button1_n)') == 1,
            'DEMO PC custom-top raw button binding changed')
    require(re.search(r'wire\s+common_reset_n\s*=\s*SEPARATE_COMMON_RESET\s*\?\s*common_reset_ni\s*:\s*rst_ni\s*;', controlled) and
            re.search(r'gw138k_stream_cdc\s*#\(\.WIDTH\(8\)\)\s*pc_bytes\s*\(\s*\.reset_n\(common_reset_n\)', controlled),
            'DEMO PC source common-reset selection changed')
    from tools.workstation_native_protocol_audit import (
        audit_native_protocol, audit_demo_held_boundaries, validate_native_protocol_sdc)
    result = audit_native_protocol(n, profile='m-demo-base' if role == 'M' else 'w-demo-d', mapping=mapping)
    result['demo_held_handshakes'] = audit_demo_held_boundaries(n, result)
    result['installed_local_sdc'] = validate_native_protocol_sdc(sdc, n, result,
        demo_held_handshakes=demo_held_handshake_constraints())
    mailbox = {}
    if selected['policy'] == W_RETURN_TIMING_POLICY:
        require(isinstance(netlist_text, str), 'actual W return netlist text required')
        from tools.workstation_w_return_mailbox_cdc import audit as audit_return
        mailbox['actual_w_return_mailbox'] = audit_return(n, stage=stage, sdc=sdc,
            mapping=mapping, netlist_text=netlist_text)
    return dict(gate_applied=True, selection=selected, actual_native_protocol=result, **mailbox,
                reset_source_slice_sha256={str(p): digest(p) for p in (top_path, controlled_path)},
                actual_pc_reset_scope='power_up_only', reusable_module_reset_simulation=False,
                physical_timing_verified=False, hardware_tested=False)


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
