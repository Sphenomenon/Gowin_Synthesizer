"""Explicit USB2 owner reset-chain audit, independent of recording/shared CDC.

This accepts only source structure and installed pin scope. It cannot establish
reset pulse width, metastability margin, routed recovery/removal or deployment.
"""

from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.workstation_runtime_clock_audit import VG_RELATIVE, verify_synthesis_identity
from tools.workstation_ble_ddr_cdc_scope import (SCOPE as BLE_DDR_SCOPE, LEGACY_SCOPE,
    validate_profile as validate_ble_ddr_profile)
from tools.workstation_runtime_pcm_cdc import COMB, Graph, PcmNetlist, TOP

POLICY = 'usb2-owner-audio-reset-source-v1'
# Gowin represents this generate scope with a literal dot. A new actual VG
# must establish these names; never fall back to a guessed slash/alias scope.
STEM = 'u_native_usb/audio_owner_reset.release_q'
SELECTORS = tuple(STEM + '_' + str(i) + '_s*/CLEAR' for i in range(3))
SDC = 'set_false_path -to [get_pins {' + ' '.join(SELECTORS) + '}]\n'
NO_LOCAL_PANEL_PROFILE = 'custom138k-workstation-r00-no-local-panel-v1'
NO_LOCAL_PANEL_SOURCE = 'boards/custom_138k/workstation_profile_r00_no_local_panel_v1.json'
NO_LOCAL_PANEL_CONFIGURATION_SHA256 = 'fe57acb99ab96c773148a10bd41401eaa55ca069f2ff9d1def1daa254dd5d241'
PROFILES = ('custom138k-workstation-no-cnn-v1', 'custom138k-workstation-r00-v1', NO_LOCAL_PANEL_PROFILE)
PROFILE_SOURCES = {
    PROFILES[0]: 'boards/custom_138k/workstation_profile_no_cnn_v1.json',
    PROFILES[1]: 'boards/custom_138k/workstation_profile_r00_v1.json',
    NO_LOCAL_PANEL_PROFILE: NO_LOCAL_PANEL_SOURCE,
}
SOURCE_FILES = ('rtl/workstation/workstation_usb2_input.sv',
                'rtl/workstation/gw138k_push_workstation_top.v',
                'rtl/push2_usb_a_control.sv')
AUDIT_FILES = (*SOURCE_FILES, 'tools/workstation_usb2_owner_reset.py',
               'tools/workstation_runtime_pcm_cdc.py',
               'tools/workstation_synthesis_netlist.py',
               'tools/workstation_runtime_clock_audit.py',
               'boards/custom_138k/workstation_profile_no_cnn_v1.json',
               'boards/custom_138k/workstation_profile_r00_v1.json')


class OwnerResetNetlist(PcmNetlist):
    """Resolve only the observed new escaped [2:2] owner input formal.

    The existing parser does not handle a bit select on an escaped formal with
    a dot. This explicit adapter is used only by the optional reset audit; it
    neither rewrites VG bytes nor changes generic/shared parser behavior.
    """
    def canonical(self, scope, net, seen=()):
        if scope == 'u_native_usb/input_owner' and net.startswith('\\audio_owner_reset.release_q '):
            require(net == '\\audio_owner_reset.release_q [2]', 'owner reset formal bit changed')
            frame = self.frames[scope]
            formal = 'audio_owner_reset.release_q'
            require(self.ranges[frame['kind']].get(formal) == (2, 2) and formal in frame['ports'],
                    'owner reset formal range/binding changed')
            key = scope, net
            require(key not in seen, 'cyclic owner reset formal')
            return self.canonical(self.scopes[scope], frame['ports'][formal], (*seen, key))
        return super().canonical(scope, net, seen)


def require(ok, message):
    if not ok:
        raise ValueError('USB2 owner reset audit: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def timing_boundary_policy():
    """Keep the asynchronous receiving chain separate from functional reset."""
    return dict(
        raw_to_chain_clear=dict(
            source='!(usb_reset_n && reset_n && memory_guard_started)',
            receiving_clock='audio_clk', fixed_release_phase=False,
            destination_selectors=list(SELECTORS), asynchronous_assertion=True,
            sta_policy='false_path_only_to_three_receiving_chain_CLEAR_pins',
            exception_checks=['setup', 'hold', 'recovery', 'removal'],
            pulse_width_verified=False, assertion_glitch_and_flight_verified=False,
            physical_reset_accepted=False),
        chain_q_to_next_d=dict(
            receiving_clock='audio_clk', sta_policy='retain_timed_shift_paths',
            inherited_max_delay_budget_ns=None, routed_timing_verified=False,
            metastability_margin_verified=False),
        final_q_to_functional_clear=dict(
            source_stage=2, receiving_clock='audio_clk', endpoint_count=12,
            endpoint_family='u_native_usb/input_owner/feedback_divider_*/CLEAR',
            sta_policy='retain_timed_recovery_and_removal',
            new_false_path_allowed=False, routed_recovery_verified=False,
            routed_removal_verified=False, physical_reset_accepted=False),
        final_q_to_existing_release_chains=dict(
            endpoint_count=11, new_exception_scope=False,
            existing_reset_policy_accepted_by_this_audit=False),
        basis=dict(
            existing_policy='cpu_release_q/session_release_q/feedback_release_q own CLEAR scope',
            tool_semantics='SUG940-2.0.1 PDF77 printed67 set_false_path',
            tool_semantics_note='default covers setup/hold/recovery/removal; -setup includes recovery; -hold includes removal'))


def audit_source_text(wrapper, top, owner):
    w, t, o = map(compact, (wrapper, top, owner))
    expected = compact('''generate if (AUDIO_OWNER_RESET_SYNC != 0) begin: audio_owner_reset
        wire qualified_n = reset_n && audio_reset_n;
        (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] release_q;
        always @(posedge clk_audio or negedge qualified_n)
            if (!qualified_n) release_q <= 0;
            else release_q <= {release_q[1:0], 1'b1};
        assign owner_audio_reset_n = release_q[2];
    end else begin: legacy_audio_owner_reset
        assign owner_audio_reset_n = audio_reset_n;
    end endgenerate''')
    require(w.count(expected) == 1 and len(re.findall(r'\brelease_q\b', wrapper)) == 5,
            'exact asynchronous three-stage release source changed')
    require('parameterintegerAUDIO_OWNER_RESET_SYNC=0' in w,
            'default reset selection changed')
    for fragment in ('wirefeedback_reset_n=FEEDBACK_AUDIO_DOMAIN!=0?owner_audio_reset_n:feedback_release_q[1];',
                     '.audio_reset_n(owner_audio_reset_n)', '.feedback_reset_n(feedback_reset_n)'):
        require(w.count(fragment) == 1, 'owner/feedback final-stage binding changed')
    require(w.count('owner_audio_reset_n') == 5,
            'unreviewed owner reset source fanout')
    require('wireruntime_reset_n=reset_n&&memory_guard_started;' in t,
            'runtime reset producer changed')
    require('`ifdefWORKSTATION_RUNTIME_NATIVE,.CNN_FOLLOW_ENABLE(RECOGNITION_ENABLED),.STOP_CLOCK_QUEUE_FENCE(1),.AUDIO_OWNER_RESET_SYNC(1)`endif)u_native_usb(' in t,
            'runtime-only reset opt-in changed')
    require('.reset_n(usb_reset_n),.audio_reset_n(runtime_reset_n),.uart_rx_i' in t,
            'platform/USB qualified source changed')
    require('wireevent_qualified=reset_n&&audio_reset_n;' in o and
            len(re.findall(r'\baudio_reset_n\b', owner)) == 2,
            'owner audio reset fanout changed')
    for fragment in ("reg[11:0]feedback_divider;",
                     "reg[2:0]event_release;", "reg[1:0]audio_release;",
                     "always@(posedgeclkornegedgeevent_qualified)if(!event_qualified)event_release<=0;elseevent_release<={event_release[1:0],1'b1};",
                     "always@(posedgeaudio_clkornegedgeevent_qualified)if(!event_qualified)audio_release<=0;elseaudio_release<={audio_release[0],1'b1};",
                     '.reset_n(reset_n&&feedback_reset_n),.source_clk(feedback_clk),.destination_clk(clk)'):
        require(o.count(fragment) == 1, 'downstream release source changed')
    require('always@(posedgefeedback_clkornegedgefeedback_reset_n)if(!feedback_reset_n)feedback_divider<=0;elsefeedback_divider<=feedback_divider+1\'b1;' in o and
            '.reset_n(reset_n&&feedback_reset_n)' in o and
            len(re.findall(r'\bfeedback_reset_n\b', owner)) == 4,
            'feedback reset fanout changed')
    return dict(policy=POLICY, stages=3, declaration_initial_value=None,
                asserted_value='000', release_sequence=['001', '011', '111'],
                raw_qualified_n='usb_reset_n && reset_n && memory_guard_started',
                only_final_stage_exported=True, default_opt_in=0,
                timing_boundary_policy=timing_boundary_policy(),
                behavioral_simulation_verified=False, physical_reset_verified=False)


def source_bundle(root):
    root = Path(root)
    texts = [(root / p).read_text() for p in SOURCE_FILES]
    proof = audit_source_text(*texts)
    return dict(sdc=SDC, selectors=list(SELECTORS), source_contract=proof,
                input_sha256={p: sha(root / p) for p in SOURCE_FILES},
                source='tools/workstation_usb2_owner_reset.py',
                source_sha256=sha(root / 'tools/workstation_usb2_owner_reset.py'),
                constraints_complete=False, full_reset_accepted=False)


def validate_installation(root, metadata, sdc):
    bundle = source_bundle(root)
    require(metadata == {k: v for k, v in bundle.items() if k != 'sdc'},
            'installed reset source policy metadata changed')
    require(sdc.splitlines().count(SDC.strip()) == 1,
            'exact three-CLEAR line missing/duplicated')
    return bundle


def _reg(n, g, stem):
    found = [p for p in g.regs if re.fullmatch(re.escape(stem) + r'_s\d+', p)]
    require(len(found) == 1, 'exact register missing/duplicate: ' + stem)
    p = found[0]
    require(g.drivers[n.pin(p, 'Q')] == [(p, 'Q')], 'ambiguous Q driver: ' + p)
    return p


def _closure(n, g, source):
    todo, seen, ends, comb = [n.pin(source, 'Q')], set(), {}, set()
    exports = {n.canonical('', bit) for name, direction in n.directions[TOP].items()
               if direction in ('output', 'inout') for bit in g.binding_bits('', name)}
    while todo:
        net = todo.pop()
        if net in seen:
            continue
        seen.add(net)
        require(net not in exports, 'reset Q exports to top output: ' + source)
        for p, pin, role in g.fan[net]:
            require(role != 'unsupported', 'reset Q reaches unsupported primitive: ' + p)
            if role == 'ff':
                ends[p + '/' + pin] = n.pin(p, 'CLK')
            else:
                comb.add(p)
                todo.extend(n.pin(p, out) for out in COMB[n.cells[p]['kind']])
    return dict(endpoints=dict(sorted(ends.items())), combinational_cells=sorted(comb))


def _validate_sdc(n, sdc, chain, functional):
    lines = sdc.splitlines()
    require(lines.count(SDC.strip()) == 1, 'exact three-CLEAR line missing/duplicated')
    pins = {p + '/' + pin for p, c in n.cells.items() if c['kind'] not in n.modules for pin in c['ports']}
    resolved = {}
    for selector, p in zip(SELECTORS, chain):
        actual = sorted(x for x in pins if fnmatch.fnmatchcase(x, selector))
        require(actual == [p + '/CLEAR'], 'selector is not one exact CLEAR: ' + selector)
        resolved[selector] = actual
    protected = {p + '/D' for p in chain[1:]} | {p + '/CLEAR' for p in functional}
    chain_clear = {p + '/CLEAR' for p in chain}
    for raw in lines:
        line = raw.strip()
        if not line.startswith(('set_false_path', 'set_max_delay', 'set_min_delay', 'set_clock_groups')):
            continue
        require(not any(c in line for c in (';', '$', '\\')) and not line.startswith('set_clock_groups'),
                'unsupported timing evaluation or clock-group cut')
        if line == SDC.strip():
            continue
        queries = re.findall(r'-to\s+\[(get_pins|get_regs|get_clocks|get_ports)\s+\{([^{}]+)\}\]', line)
        require(len(queries) == 1, 'timing exception needs one explicit target: ' + line)
        kind, body = queries[0]
        if kind == 'get_clocks':
            require(line in (
                'set_false_path -from [get_clocks {selected48}] -to [get_clocks {selected44}]',
                'set_false_path -from [get_clocks {selected44}] -to [get_clocks {selected48}]'),
                'unreviewed whole-clock timing exception')
            continue
        for p in protected | chain_clear:
            target = p if kind == 'get_pins' else p.rsplit('/', 1)[0]
            require(kind == 'get_ports' or not any(fnmatch.fnmatchcase(target, x) for x in body.split()),
                    'extra cut/delay masks chain or functional recovery/removal: ' + line)
    return dict(constraint=SDC.strip(), resolved_pin_selectors=resolved,
                protected_timed_pins=sorted(protected), tool_query_resolution_verified=False)


def audit_reset_structure(n, g, sdc):
    chain = [_reg(n, g, STEM + '_' + str(i)) for i in range(3)]
    require({p for p in g.regs if p.startswith(STEM)} == set(chain), 'reset chain inventory changed')
    raw = [_reg(n, g, x) for x in ('usb_release_3', 'u_reset/started', 'u_runtime_memory_guard/started_o')]
    require([n.pin(p, 'CLK') for p in raw] == ['usb_clk', 'clk_50m', 'clk_50m'],
            'reset source clock changed')
    clear = n.pin(chain[0], 'CLEAR')
    raw_q = [n.pin(p, 'Q') for p in raw]
    require(g.support(clear) == set(raw_q), 'reset assertion producer inventory changed')
    assertion = g.equivalent('owner reset qualified assertion', [clear, *raw_q],
                             lambda v: v[0] == (not (v[1] and v[2] and v[3])))
    stages, closures = [], []
    for i, p in enumerate(chain):
        c = n.cells[p]
        # Gowin gw5a prim_sim.v and prim_tsim.v both define DFFCE INIT=0.
        # Synthesis omits the defparam for that value; distinguish this from an
        # explicit netlist INIT and reject every nonzero/unknown value.
        require(c['kind'] == 'DFFCE' and set(c['ports']) == {'CLK', 'CE', 'CLEAR', 'D', 'Q'} and
                c['parameters'].get('INIT', "1'b0") == "1'b0",
                'reset FF kind/INIT changed: ' + p)
        require(n.pin(p, 'CLK') == 'audio_clk' and n.pin(p, 'CE') in g.high,
                'reset CLK/CE changed: ' + p)
        require(n.pin(p, 'CLEAR') == clear, 'reset CLEAR mismatch: ' + p)
        require(n.pin(p, 'D') in g.high if i == 0 else n.pin(p, 'D') == n.pin(chain[i-1], 'Q'),
                'reset D shift changed: ' + p)
        closure = _closure(n, g, p)
        if i < 2:
            require(closure['endpoints'] == {chain[i+1] + '/D': 'audio_clk'} and not closure['combinational_cells'],
                    'nonfinal Q complete fanout changed: ' + p)
        stages.append(dict(path=p, clock=n.pin(p, 'CLK'), clear=clear, d=n.pin(p, 'D'), q=n.pin(p, 'Q'),
                           init="1'b0", init_source='explicit_VG_parameter' if 'INIT' in c['parameters'] else 'Gowin_DFFCE_primitive_default'))
        closures.append(closure)
    cpu = _reg(n, g, 'u_native_usb/cpu_release_q_1')
    require(n.pin(cpu, 'CLK') == 'usb_clk', 'CPU reset source clock changed')
    counters = [_reg(n, g, 'u_native_usb/input_owner/feedback_divider_' + str(i)) for i in range(12)]
    releases = [(stem, count, clock) for stem, count, clock in (
        ('event_release', 3, 'usb_clk'), ('audio_release', 2, 'audio_clk'),
        ('feedback/source_release', 3, 'audio_clk'), ('feedback/destination_release', 3, 'usb_clk'))]
    expected = {p + '/CLEAR': 'audio_clk' for p in counters}
    proofs = []
    for stem, count, clock in releases:
        for i in range(count):
            p = _reg(n, g, 'u_native_usb/input_owner/' + stem + '_' + str(i))
            expected[p + '/CLEAR'] = clock
    require(closures[2]['endpoints'] == dict(sorted(expected.items())), 'final Q complete fanout changed')
    q, cpu_q = n.pin(chain[2], 'Q'), n.pin(cpu, 'Q')
    for pin, clock in expected.items():
        p = pin.rsplit('/', 1)[0]
        require(n.pin(p, 'CLK') == clock, 'downstream reset clock changed: ' + p)
        net = n.pin(p, 'CLEAR')
        inputs = [q] if p in counters else [q, cpu_q]
        require(g.support(net) == set(inputs), 'downstream reset producers changed: ' + p)
        proofs.append(g.equivalent('owner reset consumer ' + p, [net, *inputs],
                      lambda v: v[0] == (not all(v[1:]))))
    boundaries = timing_boundary_policy()
    boundaries['raw_to_chain_clear']['resolved_pins'] = [p + '/CLEAR' for p in chain]
    boundaries['chain_q_to_next_d']['resolved_paths'] = [
        dict(source=chain[i-1] + '/Q', destination=chain[i] + '/D') for i in (1, 2)]
    boundaries['final_q_to_functional_clear']['resolved_pins'] = [p + '/CLEAR' for p in counters]
    boundaries['final_q_to_existing_release_chains']['resolved_pins'] = sorted(
        set(expected) - {p + '/CLEAR' for p in counters})
    return dict(policy=POLICY, stages=stages, raw_reset_sources=raw, assertion_proof=assertion,
                complete_Q_fanout=closures, downstream_assertion_proofs=proofs,
                timing_boundaries=boundaries,
                sdc=_validate_sdc(n, sdc, chain, counters),
                source_netlist_endpoints_verified=True, full_reset_accepted=False,
                recording_cdc_accepted=False, shared_cdc_accepted=False,
                assertion_pulse_and_flight_verified=False, metastability_margin_verified=False,
                routed_recovery_removal_verified=False, constraints_complete=False,
                physical_cdc_accepted=False, hardware_tested=False, deployment_allowed=False)


def validate_profile(root, prepared, explicit_profile, *, scope=LEGACY_SCOPE):
    require(scope in (LEGACY_SCOPE, BLE_DDR_SCOPE), 'unknown explicit scope')
    if scope == BLE_DDR_SCOPE:
        require(explicit_profile == NO_LOCAL_PANEL_PROFILE, 'revision2 requires no-local-panel profile')
        validate_ble_ddr_profile(root, prepared)
        return
    require(explicit_profile in PROFILES and prepared.get('profile') == explicit_profile,
            'explicit prepared profile required')
    source = PROFILE_SOURCES[explicit_profile]
    no_panel = explicit_profile == NO_LOCAL_PANEL_PROFILE
    historical_digest = prepared.get('profile_sha256', '')
    digest_valid = (re.fullmatch(r'[0-9a-f]{64}', historical_digest) is not None if no_panel else
                    historical_digest == sha(Path(root) / source))
    require(prepared.get('schema') == 1 and prepared.get('profile_source') == source and
            digest_valid and
            prepared.get('configuration') == json.loads((Path(root) / source).read_text())['configuration'],
            'prepared profile configuration/source changed')
    if no_panel:
        configuration_digest = hashlib.sha256(json.dumps(prepared['configuration'], sort_keys=True,
                                                          separators=(',', ':')).encode()).hexdigest()
        require(configuration_digest == NO_LOCAL_PANEL_CONFIGURATION_SHA256,
                'no-local-panel supported configuration changed')


def installed_sources(root, stage):
    identities = source_bundle(root)
    require(all(sha(Path(stage) / p) == value for p, value in identities['input_sha256'].items()),
            'prepared reset source differs from reviewed root source')
    return identities


def run_audit(root, stage, evidence, *, explicit_profile, scope=LEGACY_SCOPE):
    root, stage = Path(root), Path(stage)
    prepared = json.loads((stage.parents[1] / 'workstation_profile.json').read_text())
    validate_profile(root, prepared, explicit_profile, scope=scope)
    if scope == BLE_DDR_SCOPE:
        validate_ble_ddr_profile(root, prepared, stage=stage)
    before = verify_synthesis_identity(stage, evidence)
    audit_files = tuple(dict.fromkeys((*AUDIT_FILES, 'tools/workstation_ble_ddr_cdc_scope.py', PROFILE_SOURCES[explicit_profile])))
    identities = {p: sha(root / p) for p in audit_files}
    sources = installed_sources(root, stage)
    n = OwnerResetNetlist((stage / VG_RELATIVE).read_text(), TOP)
    result = audit_reset_structure(n, Graph(n), (stage / 'constraints/custom_138k.sdc').read_text())
    if scope == BLE_DDR_SCOPE:
        validate_ble_ddr_profile(root, prepared, stage=stage)
    require(before == verify_synthesis_identity(stage, evidence) and
            identities == {p: sha(root / p) for p in audit_files}, 'review inputs changed')
    result.update(schema=1, scope=scope, explicit_profile=explicit_profile, synthesis=before, sources=sources,
                  audit_source_sha256=identities, source_seal_before_and_after=True,
                  eda_invoked=False, hardware_operated=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--synthesis-evidence', type=Path, required=True)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--scope', choices=(LEGACY_SCOPE, BLE_DDR_SCOPE), default=LEGACY_SCOPE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run_audit(ROOT, args.project, args.synthesis_evidence, explicit_profile=args.profile, scope=args.scope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('policy', 'explicit_profile', 'full_reset_accepted', 'recording_cdc_accepted', 'deployment_allowed')}))


if __name__ == '__main__':
    main()
