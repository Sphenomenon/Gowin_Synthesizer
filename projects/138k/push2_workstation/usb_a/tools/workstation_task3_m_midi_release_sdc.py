"""Check the batch M MIDI reset owner before accepting an SDC alias.

The observer lease reset and the original MIDI root reset no longer coalesce.
A selector which merely finds three CLEAR pins is therefore insufficient.
The pure transform serves review and the explicitly selected batch-reset
profile. It never mutates prepared candidates, historical inventory seals,
or timing budgets; the mapped audit separately checks the installed SDC.
"""
import fnmatch
import hashlib

from tools.workstation_runtime_pcm_cdc import BooleanDiagram, Graph
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_task3_native_held import release_from_clear
from tools.workstation_task3_peripheral_releases_audit import zero_async_ff
from tools.workstation_task3_root_reset_audit import (
    M_PHONE_BATCH_PROVIDER, POLICY as ROOT_POLICY, validate_root_publisher)

POLICY = 'task3_m_batch_midi_actual_root_release_sdc_v1'
FUNCTIONAL_SCOPE = 'u_managed/midi_bytes'
ACTUAL_OWNER = 'u_task3_m_panic_epoch'
ACTUAL_STEM = 'source_release'
OBSERVER_OWNER = 'u_task3_m_pcm_commands'
OBSERVER_STEM = 'a_release'
STALE_SELECTOR = OBSERVER_OWNER + '/a_release_*_s*/CLEAR'
CORRECT_SELECTOR = ACTUAL_OWNER + '/source_release_*_s*/CLEAR'
COMMAND = 'set_false_path -to [get_pins {{{}}}]'
OTHER_RELEASE_SELECTORS = (
    'u_tf_audio/source_release_*_s*/CLEAR',
    'u_tf_audio/compute_release_*_s*/CLEAR',
    'u_tf_audio/frames/source_release_*_s*/CLEAR',
    'u_tf_audio/frames/compute_release_*_s*/CLEAR',
    'u_task3_m_final_tap/source_release_*_s*/CLEAR',
)


def release_command(selector):
    return COMMAND.format(' '.join((*OTHER_RELEASE_SELECTORS, selector)))


def require(ok, message):
    if not ok:
        raise ValueError('M MIDI release SDC audit: ' + message)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def project_midi_release_sdc(sdc):
    """Return one exact substitution and receipt; no file or profile mutation."""
    before, after = (release_command(p) for p in (STALE_SELECTOR, CORRECT_SELECTOR))
    require(sdc.splitlines().count(before) == 1 and sdc.count(STALE_SELECTOR) == 1,
            'exact stale MIDI selector anchor absent/duplicated')
    require(CORRECT_SELECTOR not in sdc, 'corrected selector already present')
    projected = sdc.replace(before, after, 1)
    return projected, dict(policy=POLICY, input_sha256=digest(sdc),
        projected_sha256=digest(projected), before=before, after=after,
        added_exceptions=0, timing_budgets_changed=False,
        candidate_modified=False,
        in_memory_transform_only=True, physical_recovery_removal_verified=False)


def restore_midi_release_sdc(sdc, evidence):
    before, after = (release_command(p) for p in (STALE_SELECTOR, CORRECT_SELECTOR))
    require(sdc.splitlines().count(after) == 1 and sdc.count(CORRECT_SELECTOR) == 1 and
            STALE_SELECTOR not in sdc, 'exact corrected MIDI selector anchor absent/duplicated')
    restored = sdc.replace(after, before, 1)
    selected, expected = project_midi_release_sdc(restored)
    require(selected == sdc and evidence == expected, 'MIDI selector reconstruction evidence drift')
    return restored


def _final_reset_consumers(n, g, last, clear):
    """Enumerate actual source-owned reset state, without a new hash seal."""
    families = (
        ('u_managed/display', 'held_data', (*range(73), *range(105, 203), *range(206, 221),
                                          *range(235, 257), *range(270, 283), *range(291, 299), 307)),
        ('u_managed/display', 'drop_count', 32),
        ('u_managed/health_snapshot', 'destination_data', tuple(range(32, 64))),
        ('u_managed/midi_drops', 'meta', 32),
        ('u_managed/midi_drops', 'sync_value', 32),
        ('u_managed/observation/drops', 'meta', 32),
        ('u_managed/observation/drops', 'sync_value', 32),
        ('u_managed/pc_bytes', 'destination_data', 8),
        ('u_managed/runtime/g_direct_tf.transport_health_mailbox', 'destination_data', 64),
        (ACTUAL_OWNER, 'held_data', 10),
    )
    controls = (
        ('u_managed/display', ('ack_meta', 'ack_sync', 'request_toggle')),
        ('u_managed/health_snapshot', ('acknowledge_toggle', 'req_meta', 'req_settled', 'req_sync')),
        (FUNCTIONAL_SCOPE, ('acknowledge_toggle', 'req_meta', 'req_settled', 'req_sync')),
        ('u_managed/pc_bytes', ('acknowledge_toggle', 'destination_valid', 'req_meta', 'req_settled', 'req_sync')),
        ('u_managed/runtime/g_direct_tf.transport_health_mailbox',
         ('acknowledge_toggle', 'destination_valid', 'req_meta', 'req_settled', 'req_sync')),
        (ACTUAL_OWNER, ('ack_meta', 'ack_sync', 'request_toggle')),
    )
    registers = []
    for scope, stem, bits in families:
        if isinstance(bits, int):
            registers.extend(g.group(scope, stem, bits))
        else:
            registers.extend(g.register(scope, stem, bit) for bit in bits)
    registers.extend(g.register(scope, stem) for scope, stems in controls for stem in stems)
    require(len(registers) == len(set(registers)) == 528, 'MIDI final reset owner inventory aliases')
    closure = complete_closure(n, g, [last])
    require(closure['ff_endpoints'] == {p + '/CLEAR': 'audio_clk' for p in registers} and
            not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
            'MIDI final release has missing/extra/non-reset consumers')
    for path in registers:
        zero_async_ff(n, path, clock='audio_clk', clear=clear)
    return closure


def audit_midi_release_sdc(n, sdc, *, root):
    require(root.get('policy') == ROOT_POLICY and
            root.get('selected_provider') == M_PHONE_BATCH_PROVIDER and
            root.get('all_state_assignments_proven') is True and
            root.get('actual_state_bits') == 35,
            'verified actual batch M root required')
    require(root.get('batch_mapped_structure', {}).get('mapped_structure_verified') is True and
            root['batch_mapped_structure'].get('policy') == 'task3_m_batch_mapped_command_snapshot_v1',
            'verified actual batch mapped boundary required')
    g = Graph(n)
    root_q = validate_root_publisher(n, g, root)
    functional = g.register(FUNCTIONAL_SCOPE, 'acknowledge_toggle')
    clear = n.pin(functional, 'CLEAR')
    zero_async_ff(n, functional, clock='audio_clk', clear=clear)
    # Trace from the real functional reset rather than from a selected name.
    release = release_from_clear(n, g, clear, root_q, 'audio_clk', paired=True, batch=True)
    expected = g.group(ACTUAL_OWNER, ACTUAL_STEM, 3)
    require(release['stages'] == expected, 'original MIDI root release owner changed')
    observer = g.group(OBSERVER_OWNER, OBSERVER_STEM, 3)
    require(set(expected).isdisjoint(observer), 'observer lease and MIDI root chains alias')
    common = n.pin(expected[0], 'CLEAR')
    require(n.pin(observer[0], 'CLEAR') != common,
            'observer lease unexpectedly shares original MIDI root assertion')
    named = [root_q, *(n.pin(p, 'Q') for p in expected)]
    require(len(named) == len(set(named)), 'MIDI root/release state aliases')
    bd = BooleanDiagram(named)
    rows = []
    for bit, p in enumerate(expected):
        zero_async_ff(n, p, clock='audio_clk', clear=common)
        actual = bd.choose(bd.net(g, common), 0, bd.choose(
            bd.net(g, n.pin(p, 'CE')), bd.net(g, n.pin(p, 'D')), bd.inputs[n.pin(p, 'Q')]))
        wanted = bd.both(bd.inputs[root_q], 1 if bit == 0 else bd.inputs[n.pin(expected[bit-1], 'Q')])
        require(actual == wanted, 'reset-inclusive MIDI release next-Q changed: ' + p)
        rows.append(dict(register=p, clock='audio_clk', effective_init=0,
            reset_before_enable=True, reset_inclusive_next_q_exact=True))
    final = _final_reset_consumers(n, g, expected[-1], clear)
    all_pins = {p + '/' + pin for p, cell in n.cells.items() for pin in cell['ports']}
    selected = {pin for pin in all_pins if fnmatch.fnmatchcase(pin, CORRECT_SELECTOR)}
    require(selected == {p + '/CLEAR' for p in expected},
            'corrected selector does not resolve to exactly the actual three MIDI release CLEARs')
    command = release_command(CORRECT_SELECTOR)
    require(sdc.splitlines().count(command) == 1 and sdc.count(CORRECT_SELECTOR) == 1 and
            STALE_SELECTOR not in sdc,
            'original MIDI root CLEARs are not selected; stale observer lease selector cannot substitute: ' +
            STALE_SELECTOR + ' -> ' + CORRECT_SELECTOR)
    return dict(policy=POLICY, selected_provider=root['selected_provider'],
        actual_functional_register=functional, functional_clear=clear,
        root_q=root_q, actual_release=release, release_next_q=rows,
        boolean_assignments_proven=1 << len(named),
        exact_installed_command=command, exact_release_CLEAR_pins=sorted(selected),
        observer_lease_release_registers=observer,
        observer_assertion_differs_from_root_assertion=True,
        original_MIDI_reset_owner_and_SDC_target_verified=True,
        complete_final_reset_consumer_inventory_proven=True,
        final_reset_consumer_count=len(final['ff_endpoints']), final_reset_consumer_closure=final,
        whole_MIDI_handshake_proven=False, physical_recovery_removal_verified=False,
        routed_timing_verified=False, hardware_tested=False, deployment_allowed=False)
