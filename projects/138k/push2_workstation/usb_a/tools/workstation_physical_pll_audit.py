"""Maintained complete native PLL/startup gate; no runtime source overlays.

Uses the parent's hash-locked DDR/video auditors and the maintained structural
serializer audit. Historical physical reports and checkers are never rewritten.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from workstation_serializer_startup_audit import inspect_serializer_startup
from workstation_ae350_clock_placement import audit_routed as audit_ae350_clock
from workstation_ae350_rtc import (verify_prepared as verify_ae350_rtc, audit_netlist as audit_rtc,
                                  validate_constraints as validate_rtc_constraints,
                                  SOURCE as RTC_SOURCE, SHARED_TOP as RTC_TOP)

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_unchanged(snapshot):
    for path, expected in snapshot.items():
        if sha(path) != expected:
            raise ValueError('PLL audit input changed during audit: ' + str(path))


def physical_snapshot(physical, additional=()):
    """Bind the exact manifest bytes, every declared input and routed evidence."""
    manifest = physical / 'physical_inputs.json'
    manifest_bytes = manifest.read_bytes()
    inputs = json.loads(manifest_bytes)
    snapshot = {manifest: hashlib.sha256(manifest_bytes).hexdigest()}
    for name, expected in inputs['input_sha256'].items():
        relative = Path(name)
        if (relative.is_absolute() or '..' in relative.parts or
                not (physical / relative).resolve().is_relative_to(physical.resolve()) or
                sha(physical / relative) != expected):
            raise ValueError('Physical input drift: ' + name)
        snapshot[physical / name] = expected
    for path in additional:
        if path not in snapshot:
            snapshot[path] = sha(path)
    return inputs, snapshot


def pll_inventory(cells, *, local_panel_enabled=True, worker_headless=False):
    """Require the whole seven/six PLL set before checking any shared tuple."""
    from workstation_runtime_clock_audit import PLL_PATHS
    if type(local_panel_enabled) is not bool:
        raise ValueError('PLL local-panel selection must be explicit boolean')
    expected = PLL_PATHS if local_panel_enabled else PLL_PATHS - {'u_lcd/u_pll/PLL_inst'}
    if type(worker_headless) is not bool or worker_headless and local_panel_enabled:
        raise ValueError('Headless W PLL selection requires no local panel')
    if worker_headless:
        expected=expected-{'u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst',
                           'u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst'}
        if any(name.startswith(('u_video/','u_lcd/')) or kind=='OSER10'
               for name,(kind,ports) in cells.items()):
            raise ValueError('Headless W retains retired video hardware')
    actual = {name for name, (kind, unused) in cells.items() if kind == 'PLL'}
    if actual != expected:
        raise ValueError('Selected PLL inventory changed: missing=' + str(sorted(expected - actual)) +
                         ' extra=' + str(sorted(actual - expected)))
    return sorted(actual)


def shared_clock_plls(sdf, netlist, routed_type, *, local_panel_enabled=True, worker_headless=False):
    """Preserve all ten-bit control tuples and the original 10ns budget."""
    evidence, errors = {}, []
    try:
        routed = routed_type(sdf, netlist)
        pll_inventory(routed.cells, local_panel_enabled=local_panel_enabled,worker_headless=worker_headless)
        prefixes = ('u_audio_clock/g_hardware.u_pll', 'u_usb_pll', 'u_cpu_pll')
        if local_panel_enabled:
            prefixes += ('u_lcd/u_pll',)
        for prefix in prefixes:
            instance = prefix + '/PLL_inst'
            kind, ports = routed.cells[instance]
            assert kind == 'PLL', instance
            paths = []
            for bus, width, first_bit in (('ICPSEL', 6, 3), ('LPFRES', 3, 0), ('RESET', 1, 9)):
                bits = routed.bits(ports[bus])
                assert len(bits) == width, (instance, bus)
                for index, net in enumerate(reversed(bits)):
                    endpoint = instance + '/' + (bus if bus == 'RESET' else bus + '[' + str(index) + ']')
                    if net in routed.constants:
                        assert routed.constants[net] == 0, ('PLL control constant changed', endpoint)
                        paths.append(dict(endpoint=endpoint, constant=0, total_ns=0))
                        continue
                    driver, output_pin = routed.drivers[net]
                    pattern = re.escape(prefix + '/pll_control_' + str(first_bit + index)) + r'_s\d+'
                    assert re.fullmatch(pattern, driver), (endpoint, driver)
                    driver_kind, driver_ports = routed.cells[driver]
                    assert driver_kind.startswith('DFF') and output_pin == 'Q', driver
                    assert driver_ports['CLK'] == routed.clock_net, ('PLL control clock changed', driver)
                    flight = (routed.input_delay + routed.route('clk_50m_ibuf/O', driver + '/CLK') +
                              routed.arc(driver, 'CLK', 'Q') + routed.route(driver + '/Q', endpoint))
                    assert flight <= 10, (endpoint, flight, '10ns PLL control budget')
                    paths.append(dict(endpoint=endpoint, source=driver, total_ns=flight))
            evidence[prefix] = dict(paths=paths, maximum_propagation_ns=max(p['total_ns'] for p in paths),
                                    bound_ns=10, complete_tuple_directly_registered=True)
    except (AssertionError, KeyError, ValueError) as error:
        errors.append(str(error))
    return errors, evidence


def role_source_context(physical, inputs, snapshot, *, paired=False):
    """Recheck an explicit immutable role closure, without rewriting its manifest.

    These candidates use the custom-board preparer's hash-bound Gowin log,
    profile and synthesis audit rather than the runtime driver's process seal.
    Neither evidence format is represented as the other.
    """
    if paired:
        from tools.workstation_task3_paired_audit import verify_prepared, PROFILES
    else:
        from tools.workstation_demo_audit import verify_prepared, PROFILES
    label = 'paired' if paired else 'DEMO'
    role_field = 'paired_role' if paired else 'demo_role'
    required = {'parent_workstation_profile.json', 'parent_integration_inputs.json',
                'parent_synthesis_audit.json', 'custom_138k_integration.vg', 'physical.sdc'}
    if not required <= inputs.get('input_sha256', {}).keys():
        raise ValueError(label + ' PLL source metadata is not sealed')
    source = Path(inputs['parent_candidate']).resolve()
    parent_path = physical / 'parent_integration_inputs.json'
    profile_path = physical / 'parent_workstation_profile.json'
    parent = json.loads(parent_path.read_text())
    profile = json.loads(profile_path.read_text())
    audit = json.loads((physical / 'parent_synthesis_audit.json').read_text())
    selected = parent.get('workstation_profile', {})
    if selected.get('name') not in PROFILES or inputs.get(role_field) not in ('M', 'W'):
        raise ValueError(label + ' PLL source requires an explicit registered role/profile')
    for copied, original in ((parent_path, source / 'integration_inputs.json'),
                             (profile_path, source / 'workstation_profile.json')):
        if copied.read_bytes() != original.read_bytes():
            raise ValueError(label + ' PLL copied metadata differs: ' + str(copied))
        snapshot[original] = sha(original)
    role, verified_profile, stage = verify_prepared(source, parent)[:3]
    if paired:
        selected_gates = ('feature_structure', 'port_coverage', 'visible_SDC_members',
                          'constraint_retirement_and_rebinding')
        source_gates_passed = all(audit.get('gates', {}).get(name, {}).get('passed') is True
                                  for name in selected_gates)
    else:
        source_gates_passed = (audit.get('features', {}).get('role_retirement_verified') is True and
            audit.get('visible_sdc_selector_audit', {}).get('all_visible_selector_members_resolved') is True and
            audit.get('constraint_retirement_audit', {}).get('every_retired_selector_proven_absent') is True)
    if (profile != verified_profile or role != inputs[role_field] or audit.get(role_field) != role or
            audit.get('candidate_identity') != profile['candidate_identity'] or
            inputs.get('parent_candidate_identity') != profile['candidate_identity'] or
            inputs.get('parent_identity') != audit.get('identity') or
            audit.get('identity') != parent.get('identity') or
            audit.get('validation_stage') != ('task3_paired_synthesis_only' if paired else 'demo_full_profile_synthesis_only') or
            audit.get('source_policy') != 'immutable_prepared_closure' or
            audit.get('audit_source_seal_before_and_after') is not True or
            not source_gates_passed):
        raise ValueError(label + ' PLL candidate/synthesis source linkage differs')
    outputs = {'integration_inputs_sha256': source / 'integration_inputs.json',
               'netlist_sha256': stage / 'impl/gwsynthesis/custom_138k_integration.vg',
               'synthesis_log_sha256': source / 'synthesis.log',
               'resource_report_sha256': stage / 'impl/gwsynthesis/custom_138k_integration_syn_rsc.xml'}
    for field, path in outputs.items():
        if audit.get(field) != sha(path):
            raise ValueError(label + ' PLL synthesis evidence differs: ' + field)
        snapshot[path] = sha(path)
    log = outputs['synthesis_log_sha256'].read_text()
    if re.search(r'(?m)^ERROR\b', log) or log.count('GowinSynthesis finish') != 1:
        raise ValueError(label + ' PLL Gowin emitted log is not a completed synthesis')
    preboard_sdc=None
    if paired and inputs.get('preboard_release_adaptation') is not None:
        from tools.workstation_custom_board_implementation import (
            reference_constraints,primary_clk50_constraints,preboard_constraint_selection)
        if selected['name']!='custom138k-workstation-task3-'+role.lower()+'-preboard-v1':
            raise ValueError('preboard physical constraints require explicit role profile')
        reference=physical/'reference.cst'
        if sha(reference)!=inputs['constraint_reference']['sha256'] or inputs['constraint_reference']['binding']['omitted']:
            raise ValueError('preboard physical CST reference differs or excludes a port')
        vg_text=outputs['netlist_sha256'].read_text()
        cst,binding=reference_constraints(reference.read_bytes(),vg_text)
        if binding!=inputs['constraint_reference']['binding']:
            raise ValueError('preboard physical CST binding differs')
        cst,clock=primary_clk50_constraints(cst,vg_text)
        if role=='M' and 'M_clock_priority' in inputs.get('primary_clk50_adaptation',{}):
            from tools.workstation_custom_board_implementation import m_preboard_clock_priority
            cst,clock['M_clock_priority']=m_preboard_clock_priority(cst,vg_text)
        ddr=inputs.get('preboard_ddr_adaptation')
        if ddr is None:raise ValueError('preboard DDR physical proof absent')
        routed_reference=Path(ddr['routed_reference'])
        if sha(routed_reference)!=ddr['routed_reference_sha256']:
            raise ValueError('preboard DDR routed reference differs')
        snapshot[routed_reference]=sha(routed_reference)
        prior_metadata=routed_reference.parents[2]/'parent_integration_inputs.json'
        snapshot[prior_metadata]=sha(prior_metadata)
        cst,preboard_sdc,pins,releases,held,ddr_actual=preboard_constraint_selection(
            stage,parent,audit,cst,(stage/'constraints/custom_138k.sdc').read_bytes(),vg_text,
            task3_pins=role=='M',preboard_releases=True,primary_clk50=True,
            ddr_reference=routed_reference.parents[2])
        for key,actual in [('task3_pin_adaptation',pins),('primary_clk50_adaptation',clock),
            ('preboard_release_adaptation',releases),('preboard_held_adaptation',held),('preboard_ddr_adaptation',ddr_actual)]:
            if inputs.get(key)!=json.loads(json.dumps(actual)):
                raise ValueError('preboard physical proof differs: '+key)
        locality = inputs.get('diagnosed_locality')
        if locality is not None:
            from tools.workstation_task3_w_delay_locality import reconstruct
            from tools.workstation_native_protocol_audit import protocol_netlist
            if role != 'W' or locality.get('source_candidate') != profile['candidate_identity']:
                raise ValueError('diagnosed locality requires its exact W source candidate')
            if (sha(physical/'custom_138k_integration.vg') != locality.get('VG_sha256') or
                    sha(physical/'physical.sdc') != locality.get('SDC_sha256')):
                raise ValueError('diagnosed W locality netlist/SDC identity differs')
            cst = reconstruct(cst, protocol_netlist(vg_text, mapping='synthesis'), locality,
                registered_tx_class=parent.get('w_tx_class',{}).get('policy')=='task3_W_registered_normal_tx_preference_v1',
                fifo_compare_first=parent.get('fifo_full_compare',{}).get('policy')=='task3_W_large_FIFO_compare_before_write_select_v1')
        if (physical/'physical.cst').read_bytes()!=cst:
            raise ValueError('preboard reconstructed physical CST differs')
    for physical_name, original in (('custom_138k_integration.vg', outputs['netlist_sha256']),
                                     ('physical.sdc', stage / 'constraints/custom_138k.sdc')):
        expected = original.read_bytes()
        if physical_name=='physical.sdc' and preboard_sdc is not None:
            expected=preboard_sdc
        elif paired and physical_name == 'physical.sdc' and inputs.get('task3_pin_adaptation') is not None:
            from tools.workstation_custom_board_implementation import task3_pin_collections
            expected, binding = task3_pin_collections(expected, outputs['netlist_sha256'].read_text())
            if binding != inputs['task3_pin_adaptation']:
                raise ValueError('paired PLL physical pin collection binding differs')
        if (inputs['input_sha256'][physical_name] != hashlib.sha256(expected).hexdigest() or
                (physical / physical_name).read_bytes() != expected):
            raise ValueError(label + ' PLL physical/synthesis input differs: ' + physical_name)
    panel = parent.get('local_panel', {})
    if (panel.get('enabled') is not False or panel.get('sources') != [] or panel.get('sdc') != '' or
            panel.get('touch_input_selected') is not False or
            panel.get('output_behavior') != 'all_21_lcd_output_bits_static_low_backlight_off'):
        raise ValueError(label + ' PLL explicit no-local-panel scope differs')
    for relative, expected in profile['staged_input_sha256'].items():
        snapshot[stage / relative] = expected
    for relative, expected in (
            ('parent_prepare_metadata.json', parent['parent_prepare_metadata_sha256']),
            ('pinout/pinout.json', parent['pinout_sha256']),
            ('workstation/resource_rework_overlays.json', profile['resource_overlays_sha256'])):
        snapshot[source / relative] = expected
    firmware = parent['ae350_firmware']
    for relative, expected in firmware['artifacts_sha256'].items():
        snapshot[source / firmware['evidence_directory'] / relative] = expected
    return stage, parent, False, dict(policy=('sealed_immutable_paired_profile_source' if paired else 'sealed_immutable_demo_profile_source'),
        candidate_identity=profile['candidate_identity'], **{role_field: role},
        prepared_profile_sha256=sha(profile_path), vg_sha256=audit['netlist_sha256'],
        synthesis_evidence_scope='hash_bound_Gowin_emitted_log_not_driver_stdout',
        synthesis_log_sha256=audit['synthesis_log_sha256'],
        parent_synthesis_audit_sha256=sha(physical / 'parent_synthesis_audit.json'),
        local_panel_enabled=False, acceptance_inherited=False)


def demo_source_context(physical, inputs, snapshot):
    return role_source_context(physical, inputs, snapshot)


def source_context(physical, inputs, snapshot):
    """Bind explicit no-panel selection to this candidate's completed source seal.

    Missing profile metadata never selects the reduced inventory. Legacy
    physical manifests retain the seven-PLL/default LCD contract.
    """
    from workstation_runtime_clock_audit import verify_synthesis_identity
    from workstation_profile import (R00_NO_LOCAL_PANEL_NAME, LOCAL_BOOT64_NAME,
                                     CPU_BUSINESS_NAME, specification, identity_digest)
    source = inputs.get('source', {})
    if 'paired_role' in inputs and ('synthesis' in source or 'demo_role' in inputs):
        raise ValueError('paired PLL competing physical source evidence')
    if 'synthesis' not in source:
        if 'paired_role' in inputs:
            return role_source_context(physical, inputs, snapshot, paired=True)
        if inputs.get('demo_role') in ('M', 'W') or 'parent_workstation_profile.json' in inputs.get('input_sha256', {}):
            return demo_source_context(physical, inputs, snapshot)
        parent_path = physical / 'parent_integration_inputs.json'
        if parent_path not in snapshot:
            snapshot[parent_path] = sha(parent_path)
        return (Path(inputs['parent_candidate']) / 'workstation/Prj1',
                json.loads(parent_path.read_text()), True,
                dict(policy='legacy_default_LCD_required', local_panel_enabled=True))
    sealed = source['synthesis']
    stage = Path(sealed['stage']).resolve()
    actual = verify_synthesis_identity(stage, Path(sealed['process_evidence']))
    if actual != sealed or source.get('candidate_identity') != sealed['candidate_identity']:
        raise ValueError('Physical/source synthesis identity differs')
    paths = {'profile': 'parent/workstation_profile.json', 'metadata': 'parent/integration_inputs.json',
             'process': 'parent_synthesis_process.json'}
    if any(name not in inputs['input_sha256'] for name in paths.values()):
        raise ValueError('Physical/source profile metadata is not sealed')
    profile_path = physical / paths['profile']
    metadata_path = physical / paths['metadata']
    original_profile = Path(sealed['prepared_profile'])
    original_metadata = stage.parents[1] / 'integration_inputs.json'
    process_path = Path(sealed['process_evidence'])
    for copied, original in ((profile_path, original_profile), (metadata_path, original_metadata),
                             (physical / paths['process'], process_path)):
        if copied.read_bytes() != original.read_bytes():
            raise ValueError('Physical/source copied metadata differs: ' + str(copied))
        snapshot[original] = sha(original)
    profile = json.loads(profile_path.read_text())
    parent = json.loads(metadata_path.read_text())
    profile_hash = identity_digest(dict(profile_sha256=profile['profile_sha256'],
        staged_input_sha256=profile['staged_input_sha256'], source_snapshot_sha256=profile['source_snapshot_sha256'],
        firmware=profile['firmware'], ae350_firmware=profile['ae350_firmware']))
    if (profile.get('candidate_identity') != sealed['candidate_identity'] or
            profile.get('candidate_input_sha256') != profile_hash or
            profile['candidate_identity'] != profile['profile'] + '-' + profile_hash[:16] or
            profile.get('integration_metadata_sha256') != identity_digest(
                {k: v for k, v in parent.items() if k != 'workstation_profile'}) or
            profile['staged_input_sha256'] != parent.get('staged_input_sha256') or
            source.get('staged_input_sha256') != profile['staged_input_sha256'] or
            inputs['input_sha256'].get('custom_138k_integration.vg') != sealed['vg_sha256']):
        raise ValueError('Physical/source candidate metadata linkage differs')
    for name, expected in profile['staged_input_sha256'].items():
        snapshot[stage / name] = expected
    local_panel_enabled = True
    if profile.get('profile') in (R00_NO_LOCAL_PANEL_NAME, LOCAL_BOOT64_NAME, CPU_BUSINESS_NAME):
        spec = specification(profile['profile'])
        if (profile.get('configuration') != spec['configuration'] or profile.get('revision') != spec['revision'] or
                profile.get('profile_source') != spec['config'] or
                parent.get('local_panel', {}).get('enabled') is not False or
                parent['local_panel'].get('sources') != [] or parent['local_panel'].get('sdc') != '' or
                parent['local_panel'].get('touch_input_selected') is not False or
                parent['local_panel'].get('output_behavior') != 'all_21_lcd_output_bits_static_low_backlight_off'):
            raise ValueError('Explicit no-local-panel profile scope differs')
        local_panel_enabled = False
    elif profile.get('configuration', {}).get('local_panel_policy') == 'disabled_local_lcd_touch_v1':
        raise ValueError('No-local-panel policy requires its explicit profile')
    return stage, parent, local_panel_enabled, dict(policy='sealed_completed_profile_source',
        candidate_identity=sealed['candidate_identity'], process_sha256=sealed['process_sha256'],
        vg_sha256=sealed['vg_sha256'], prepared_profile_sha256=sha(profile_path),
        local_panel_enabled=local_panel_enabled, acceptance_inherited=False)


def rtc_gate(root, stage, parent, sdc, vo, *, sealed_source):
    """Fresh sealed native sources require RTC proof; old evidence stays labelled."""
    if not sealed_source and 'ae350_rtc' not in parent:
        return dict(scope='historical_inputs_without_native_rtc', gate_applied=False,
                    hardware_tested=False, physical_timing_verified=False)
    evidence = verify_ae350_rtc(root, stage, parent.get('ae350_rtc'))
    return dict(gate_applied=True, prepared=evidence,
                constraint=validate_rtc_constraints(sdc), connectivity=audit_rtc(vo),
                sta_verified=False, physical_timing_verified=False, hardware_tested=False)


def checked_link(target, source):
    if target.exists() or target.is_symlink():
        if target.resolve() != source.resolve():
            raise ValueError('Audit view points to another input: ' + str(target))
    else:
        target.symlink_to(source, target_is_directory=source.is_dir())


def audit_workspace(physical, stage, local_panel_enabled, workspace):
    physical, stage = Path(physical).resolve(), Path(stage).resolve()
    if workspace is None:
        if not local_panel_enabled:
            raise ValueError('No-local-panel audit requires a new external --workspace')
        return physical / 'maintained-pll-audit-view'
    view = Path(workspace).resolve()
    if (view.exists() or view.is_relative_to(physical) or physical.is_relative_to(view) or
            view.is_relative_to(stage.parents[1]) or stage.parents[1].is_relative_to(view)):
        raise ValueError('PLL workspace must be new and separate from physical/source inputs')
    return view


def audit_output_path(physical, stage, output):
    path = Path(output).resolve()
    if (path.exists() or path.is_relative_to(Path(physical).resolve()) or
            path.is_relative_to(Path(stage).resolve().parents[1])):
        raise ValueError('External PLL audit JSON must be new and outside physical/source inputs')
    return path


def routed_worker_retained(vo,parent,audit):
    """Recheck actual flat W mailboxes and resets with the sealed real root.

    A retired display is not replaced with an unrelated live mailbox. The
    source proof binds the root policy; its publisher and every retained
    mailbox are rechecked on this routed VO.
    """
    from tools.workstation_native_protocol_audit import (protocol_netlist,
        audit_control_boundaries,audit_timing_boundaries)
    from tools.workstation_runtime_pcm_cdc import Graph
    from tools.workstation_task3_w_paired_cdc_audit import _mailboxes,_held_resets
    n=protocol_netlist(vo,mapping='routed');g=Graph(n)
    gate=audit['gates']['native_held_handshakes']
    if gate['passed'] is not True or parent.get('local_stream_release') is None:
        raise ValueError('W routed proof requires passed sealed source/reset policy')
    result=dict(mapping='routed',mailboxes=_mailboxes(n,g),
        control_boundaries=audit_control_boundaries(n,g,profile='w-demo-d'),
        timing_boundaries=audit_timing_boundaries(n,g,profile='w-demo-d'),
        local_stream_release=parent['local_stream_release'])
    result['retained_held_handshakes']=_held_resets(n,g,result,gate['evidence']['actual_root_startup'])
    return dict(gate_applied=True,actual_native_protocol=result,
        scope='actual retained W mailbox, first-stage consumer and reset subgates; not full physical CDC',
        retired_display_and_TF_owners_absent=True,hardware_tested=False)



def routed_m_retained(vo,parent,audit,stage):
    """Recheck flat M retained mailboxes/reset equations against sealed root.

    Hierarchy-only TF FIFO/tail and whole-root synthesis proofs are never
    replayed as routed acceptance. This is the PLL gate's actual retained
    mailbox/reset subgate; full routed CDC and STA remain separate.
    """
    from tools.workstation_native_protocol_audit import (protocol_netlist,
        audit_native_protocol,validate_native_protocol_sdc)
    from tools.workstation_task3_native_held import audit_direct_held_boundaries
    from tools.workstation_task3_paired_board import restore_constraints
    from tools.workstation_task3_w_usb_retirement import restore_selected_sdc
    gate=audit['gates']['native_held_handshakes']
    if gate.get('passed') is not True or not parent.get('task3_tf_direct_cdc'):
        raise ValueError('M routed retained proof requires sealed passed DIRECT held gate')
    root=audit['gates']['M_paired_release_CDC']['evidence']['actual_root_startup']
    n=protocol_netlist(vo,mapping='routed')
    result=audit_native_protocol(n,profile='m-task3-direct',mapping='routed',stage=stage,root=root)
    result['demo_held_handshakes']=audit_direct_held_boundaries(n,result,root=root)
    from tools.workstation_performance_reset import demo_held_handshake_constraints
    sdc=restore_constraints(stage,restore_selected_sdc(
        (stage/'constraints/custom_138k.sdc').read_text(),parent),parent['task3_paired_sdc'])
    result['installed_local_sdc']=validate_native_protocol_sdc(sdc,n,result,
        demo_held_handshakes=demo_held_handshake_constraints())
    return dict(gate_applied=True,actual_native_protocol=result,
        actual_root_startup=root,
        full_peripheral_and_TF_FIFO_tail_routed_CDC_required=True,
        scope='actual retained M mailbox, first-stage consumer and reset subgates; not full physical CDC',
        physical_timing_verified=False,hardware_tested=False)


def audit(physical, self_test=False, workspace=None, output=None):
    if not __debug__:
        raise ValueError('Validation requires normal Python execution; -O is forbidden')
    physical = Path(physical).resolve()
    base = physical / 'impl/pnr/custom_138k_integration'
    reference = ROOT / 'vendor/ddr3_reference/ddr3_memory_interface.vo'
    inputs, snapshot = physical_snapshot(physical, (
        Path(__file__), Path(__file__).with_name('workstation_serializer_startup_audit.py'),
        Path(__file__).with_name('workstation_ae350_clock_placement.py'),
        Path(__file__).with_name('workstation_ae350_rtc.py'), ROOT / RTC_SOURCE, ROOT / RTC_TOP,
        Path(__file__).with_name('workstation_performance_reset.py'),
        Path(__file__).with_name('workstation_native_protocol_audit.py'),
        Path(__file__).with_name('workstation_runtime_pcm_cdc.py'),
        Path(__file__).with_name('workstation_synthesis_netlist.py'),
        Path(__file__).with_name('workstation_recording_phase1_cdc.py'),
        Path(__file__).with_name('workstation_task3_root_reset_audit.py'),
        Path(__file__).with_name('workstation_task3_tf_startup_audit.py'),
        Path(__file__).with_name('workstation_runtime_profile.py'),
        Path(__file__).with_name('workstation_runtime_cdc.py'),
        reference, physical / 'physical.cst', base.with_suffix('.sdf'), base.with_suffix('.vo'), base.with_suffix('.tr')))
    stage, parent, local_panel_enabled, selection = source_context(physical, inputs, snapshot)
    from tools.workstation_performance_reset import W_RETURN_TIMING_POLICY
    if (parent.get('demo_runtime_timing') or {}).get('policy') == W_RETURN_TIMING_POLICY:
        # The helper is lazily imported after the initial snapshot. Bind both
        # its reviewed implementation and the candidate's sealed input now.
        for helper in ('tools/workstation_w_return_mailbox_cdc.py',
                       'tools/workstation_bluetooth_ddr.py'):
            snapshot[ROOT / helper] = sha(ROOT / helper)
            snapshot[stage / helper] = parent['staged_input_sha256'][helper]
    if workspace is not None and output is not None:
        audit_output_path(physical, stage, output)
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(ROOT) and Path(path).suffix == '.py':
            path = Path(path).resolve()
            snapshot.setdefault(path, sha(path))
    names = ('scripts/check_video_pll_init.py', 'scripts/check_build.py',
             'scripts/gowin_paths.py', 'scripts/check_serializer_startup.py',
             'scripts/audit_ddr_reset_sequence.py', 'scripts/audit_ddr_configuration_paths.py',
             'vendor/sipeed_dvi/video_pll_1080p_gw5a.v', 'vendor/sipeed_dvi/video_pll_init.v',
             'vendor/gowin_ddr3/ddr3_memory_interface.v')
    dependencies = {stage / name: parent['staged_input_sha256'][name] for name in names}
    for path, expected in dependencies.items():
        if sha(path) != expected:
            raise ValueError('Parent PLL/DDR dependency drift: ' + str(path))
    snapshot.update(dependencies)
    view = audit_workspace(physical, stage, local_panel_enabled, workspace)
    (view / 'reference').mkdir(parents=True, exist_ok=True)
    for name in ('scripts', 'vendor'):
        checked_link(view / name, stage / name)
    checked_link(view / 'reference/ddr3_memory_interface.vo', reference)
    checked_link(view / 'reference/ddr3_memory_interface.v', stage / names[-1])
    os.environ['PRJ1_DDR_REFERENCE'] = str(view / 'reference/ddr3_memory_interface.vo')
    sys.path.insert(0, str(stage / 'scripts'))
    import check_build
    from check_video_pll_init import inspect_video_pll_init, RoutedDesign
    for module in ('check_build', 'check_video_pll_init', 'gowin_paths',
                   'check_serializer_startup', 'audit_ddr_reset_sequence'):
        if Path(sys.modules[module].__file__).resolve() != (stage / 'scripts' / (module + '.py')).resolve():
            raise ValueError('PLL auditor loaded from another parent: ' + module)
    if sha(reference) != check_build.EXPECTED_NETLIST_SHA256:
        raise ValueError('DDR reference identity drift')
    outputs = view / 'docs/evidence'
    outputs.mkdir(parents=True, exist_ok=True)
    for script, name in (('audit_ddr_reset_sequence.py', 'ddr_reset_sequence.json'),
                         ('audit_ddr_configuration_paths.py', 'ddr_configuration_paths.json')):
        # Re-execute each source proof for this candidate; never reuse a prior
        # success bit or silently consume an old physical audit's result.
        subprocess.run([sys.executable, '-B', str(stage / 'scripts' / script), '--output', str(outputs / name)],
                       capture_output=True, text=True, check=True, timeout=180)
    check_build.ROOT = view
    ddr_errors, ddr = check_build.inspect_ddr_audit()
    config_errors, config = check_build.inspect_ddr_configuration_audit()
    sdf, vo, sdc = (path.read_text() for path in (base.with_suffix('.sdf'), base.with_suffix('.vo'), physical / 'physical.sdc'))
    demo_role = selection.get('demo_role') or selection.get('paired_role')
    worker_headless=(selection.get('paired_role')=='W' and
        parent.get('worker_media',{}).get('policy')=='task3_w_paired_exact_top_composition_v1')
    paired_direct_root = None
    if selection.get('paired_role') == 'M' and parent.get('task3_tf_direct_cdc'):
        sealed_audit = json.loads((physical/'parent_synthesis_audit.json').read_text())
        release_gate = sealed_audit['gates']['M_paired_release_CDC']
        if release_gate.get('passed') is not True:
            raise ValueError('paired DIRECT routed startup requires passed sealed root/release proof')
        paired_direct_root = release_gate['evidence']['actual_root_startup']
    demo_held_handshakes, demo_held_errors = {}, []
    if worker_headless:
        try:
            demo_held_handshakes=routed_worker_retained(vo,parent,
                json.loads((physical/'parent_synthesis_audit.json').read_text()))
        except (ValueError,KeyError,OSError) as error:
            demo_held_errors.append(str(error))
    if paired_direct_root is not None:
        try:
            demo_held_handshakes=routed_m_retained(vo,parent,
                json.loads((physical/'parent_synthesis_audit.json').read_text()),stage)
        except (ValueError,KeyError,OSError) as error:
            demo_held_errors.append(str(error))
    if demo_role and not worker_headless and paired_direct_root is None:
        from tools.workstation_performance_reset import (
            audit_demo_held_handshakes, DEMO_HELD_TIMING_POLICIES)
        from tools.workstation_native_protocol_audit import protocol_netlist
        evidence = parent.get('demo_runtime_timing')
        try:
            # v1 candidates keep their sealed evidence and do not acquire
            # the v2 mailbox policy by re-running a maintained auditor.
            if evidence and evidence.get('policy') in DEMO_HELD_TIMING_POLICIES:
                demo_held_handshakes = audit_demo_held_handshakes(stage, sdc, demo_role, evidence,
                    protocol_netlist(vo, mapping='routed'), mapping='routed', netlist_text=vo,
                    **({'native_protocol_profile': 'm-task3-independent'}
                       if parent.get('workstation_profile', {}).get('name') ==
                       'custom138k-workstation-task3-m-independent-ddr-map-v1' else {}))
            else:
                demo_held_handshakes = dict(gate_applied=False, scope='sealed legacy DEMO timing policy')
        except (ValueError, KeyError, OSError) as error:
            demo_held_errors.append(str(error))
    tf_disabled_m_core = parent.get('workstation_profile', {}).get('name') == \
        'custom138k-workstation-task3-m-independent-ddr-map-v1'
    startup_errors, startup = inspect_serializer_startup(sdf, vo, ddr, sdc, lane_layout='native',
        startup_grant_role=demo_role, tf_disabled_m_core=tf_disabled_m_core,worker_headless=worker_headless,
        paired_direct_root=paired_direct_root)
    video_errors, video = ([],dict(retired=True,headless_W=True)) if worker_headless else inspect_video_pll_init(sdf, vo, stage)
    shared_errors, shared = shared_clock_plls(sdf, vo, RoutedDesign, local_panel_enabled=local_panel_enabled,
                                             worker_headless=worker_headless)
    core_clock, core_errors = {}, []
    cst = (physical / 'physical.cst').read_text()
    timing_report = base.with_suffix('.tr').read_text()
    try:
        core_clock = audit_ae350_clock(cst, timing_report, vo)
    except (ValueError, KeyError) as error:
        core_errors.append(str(error))
    rtc, rtc_errors = {}, []
    rtc_source_root = stage if demo_role else ROOT
    try:
        rtc = rtc_gate(rtc_source_root, stage, parent, sdc, vo,
                       sealed_source=bool(demo_role) or 'synthesis' in inputs.get('source', {}))
    except (ValueError, KeyError, OSError) as error:
        rtc_errors.append(str(error))
    errors = (ddr_errors + config_errors + startup_errors + video_errors + shared_errors + core_errors +
              rtc_errors + demo_held_errors)
    negatives = {}
    if self_test:
        if errors:
            raise ValueError('Positive PLL gate must pass before negative mutation checks: ' + str(errors))
        targets=[('PLL','u_usb_pll/PLL_inst','RESET','PLL control constant changed')]
        if not worker_headless:
            targets[:0]=[('OSER10','u_video/u_dvi/clock_lane/serializer','D0','clock word'),
                        ('ELVDS_OBUF','u_video/u_dvi/clock_lane/differential','I','directly drives')]
        for kind,name,pin,reason in targets:
            match = re.search(r'^' + kind + r'\s+\\' + re.escape(name) + r'\s*\((.*?)^\);', vo, re.M | re.S)
            if match is None:
                raise ValueError('Negative mutation target missing: ' + name)
            changed, count = re.subn(r'(\.' + pin + r'\()([^)]*)',
                                     r'\g<1>' + ('VCC' if kind == 'PLL' else 'GND'), match[0])
            if count != 1 or changed == match[0]:
                raise ValueError('Negative mutation is not exact: ' + name)
            broken = vo[:match.start()] + changed + vo[match.end():]
            bad, unused = (shared_clock_plls(sdf, broken, RoutedDesign, local_panel_enabled=local_panel_enabled,
                                             worker_headless=worker_headless) if kind == 'PLL' else
                           inspect_serializer_startup(sdf, broken, ddr, sdc, lane_layout='native',
                               startup_grant_role=demo_role, tf_disabled_m_core=tf_disabled_m_core,
                               worker_headless=worker_headless,paired_direct_root=paired_direct_root))
            if not bad or not any(reason in message for message in bad):
                raise ValueError('Negative mutation did not fail its gate: ' + name + ' ' + str(bad))
            negatives[name + '/' + pin] = bad
        for name, changed_cst, changed_report in (
                ('AE350/requested_site', cst.replace('"u_cpu_pll/PLL_inst" PLL_R[0]',
                                                   '"u_cpu_pll/PLL_inst" PLL_B[2]'), timing_report),
                ('AE350/actual_site', cst, timing_report.replace('PLL_R[0]', 'PLL_B[2]'))):
            try:
                audit_ae350_clock(changed_cst, changed_report, vo)
            except ValueError as error:
                negatives[name] = [str(error)]
            else:
                raise ValueError('Dedicated core PLL negative mutation did not fail: ' + name)
        if rtc.get('gate_applied'):
            broken_vo, count = re.subn(r'(\.RTC_CLK\()([^)]*)(\))', r'\g<1>clk_50m\g<3>', vo)
            if count != 1 or broken_vo == vo:
                raise ValueError('RTC direct connection negative mutation target is not unique')
            for name, broken_sdc, broken in (
                    ('AE350/RTC_minimum_period', sdc.replace('-divide_by 1524 ', '-divide_by 1526 '), vo),
                    ('AE350/RTC_direct_connection', sdc, broken_vo)):
                try:
                    rtc_gate(rtc_source_root, stage, parent, broken_sdc, broken, sealed_source=True)
                except ValueError as error:
                    negatives[name] = [str(error)]
                else:
                    raise ValueError('Independent RTC negative mutation did not fail: ' + name)
    evidence = {str(path): digest for path, digest in snapshot.items()}
    evidence.update({str(path): sha(path) for path in outputs.glob('*.json')})
    verify_unchanged(snapshot)
    return dict(schema=1, recorded_at=datetime.now().astimezone().isoformat(), identity=inputs['identity'],
                scope='Maintained native PLL/startup and selected role held-mailbox subgates; not full STA/CDC/electrical or board acceptance',
                pll_gate_passed=not errors, errors=errors, ddr_source=ddr, ddr_configuration=config,
                serializer_startup=startup, video_pll=video, shared_clock_plls=shared,
                ae350_dedicated_core_clock=core_clock, ae350_dedicated_core_clock_errors=core_errors,
                ae350_rtc=rtc, ae350_rtc_errors=rtc_errors,
                demo_held_handshake_audit=demo_held_handshakes, demo_held_handshake_errors=demo_held_errors,
                demo_held_handshake_gate_passed=(not demo_held_errors
                    if demo_held_handshakes.get('gate_applied') or demo_held_errors else None),
                profile_selection=selection, expected_pll_count=4 if worker_headless else 7 if local_panel_enabled else 6,
                expected_shared_tuple_count=4 if local_panel_enabled else 3,
                audit_workspace=str(view),
                negative_checks=negatives, evidence_sha256=evidence,
                input_snapshot_sha256={str(path): digest for path, digest in snapshot.items()},
                physical_inputs_unchanged=True, routed_inputs_unchanged=True,
                audit_dependencies_unchanged=True,
                source_proofs_reexecuted=True, runtime_text_overlays=False, thresholds_relaxed=False,
                historical_audits_changed=False, full_physical_acceptance=False,
                hardware_tested=False, sram_programmed=False, flash_programmed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--workspace', type=Path, help='new external audit workspace; required for no-local-panel')
    args = parser.parse_args()
    try:
        if args.workspace is not None and args.json.resolve().is_relative_to(args.physical.resolve()):
            raise ValueError('External PLL audit JSON must be outside physical inputs')
        result = audit(args.physical, args.self_test, args.workspace, args.json)
        with args.json.open('x' if args.workspace is not None else 'w') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
    except (OSError, ValueError, KeyError, AssertionError, subprocess.SubprocessError) as error:
        parser.exit(2, 'Maintained PLL audit failed: ' + str(error) + '\n')
    print(json.dumps({key: result[key] for key in ('identity', 'pll_gate_passed', 'errors', 'negative_checks')}, indent=2))
    return 0 if result['pll_gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
