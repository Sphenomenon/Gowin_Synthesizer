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


def pll_inventory(cells, *, local_panel_enabled=True):
    """Require the whole seven/six PLL set before checking any shared tuple."""
    from workstation_runtime_clock_audit import PLL_PATHS
    if type(local_panel_enabled) is not bool:
        raise ValueError('PLL local-panel selection must be explicit boolean')
    expected = PLL_PATHS if local_panel_enabled else PLL_PATHS - {'u_lcd/u_pll/PLL_inst'}
    actual = {name for name, (kind, unused) in cells.items() if kind == 'PLL'}
    if actual != expected:
        raise ValueError('Selected PLL inventory changed: missing=' + str(sorted(expected - actual)) +
                         ' extra=' + str(sorted(actual - expected)))
    return sorted(actual)


def shared_clock_plls(sdf, netlist, routed_type, *, local_panel_enabled=True):
    """Preserve all ten-bit control tuples and the original 10ns budget."""
    evidence, errors = {}, []
    try:
        routed = routed_type(sdf, netlist)
        pll_inventory(routed.cells, local_panel_enabled=local_panel_enabled)
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


def source_context(physical, inputs, snapshot):
    """Bind explicit no-panel selection to this candidate's completed source seal.

    Missing profile metadata never selects the reduced inventory. Legacy
    physical manifests retain the seven-PLL/default LCD contract.
    """
    from workstation_runtime_clock_audit import verify_synthesis_identity
    from workstation_profile import R00_NO_LOCAL_PANEL_NAME, specification, identity_digest
    source = inputs.get('source', {})
    if 'synthesis' not in source:
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
    if profile.get('profile') == R00_NO_LOCAL_PANEL_NAME:
        spec = specification(R00_NO_LOCAL_PANEL_NAME)
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


def audit(physical, self_test=False, workspace=None, output=None):
    if not __debug__:
        raise ValueError('Validation requires normal Python execution; -O is forbidden')
    physical = Path(physical).resolve()
    base = physical / 'impl/pnr/custom_138k_integration'
    reference = ROOT / 'vendor/ddr3_reference/ddr3_memory_interface.vo'
    inputs, snapshot = physical_snapshot(physical, (
        Path(__file__), Path(__file__).with_name('workstation_serializer_startup_audit.py'),
        reference, base.with_suffix('.sdf'), base.with_suffix('.vo')))
    stage, parent, local_panel_enabled, selection = source_context(physical, inputs, snapshot)
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
    startup_errors, startup = inspect_serializer_startup(sdf, vo, ddr, sdc, lane_layout='native')
    video_errors, video = inspect_video_pll_init(sdf, vo, stage)
    shared_errors, shared = shared_clock_plls(sdf, vo, RoutedDesign, local_panel_enabled=local_panel_enabled)
    errors = ddr_errors + config_errors + startup_errors + video_errors + shared_errors
    negatives = {}
    if self_test:
        if errors:
            raise ValueError('Positive PLL gate must pass before negative mutation checks: ' + str(errors))
        for kind, name, pin, reason in (
                ('OSER10', 'u_video/u_dvi/clock_lane/serializer', 'D0', 'clock word'),
                ('ELVDS_OBUF', 'u_video/u_dvi/clock_lane/differential', 'I', 'directly drives'),
                ('PLL', 'u_usb_pll/PLL_inst', 'RESET', 'PLL control constant changed')):
            match = re.search(r'^' + kind + r'\s+\\' + re.escape(name) + r'\s*\((.*?)^\);', vo, re.M | re.S)
            if match is None:
                raise ValueError('Negative mutation target missing: ' + name)
            changed, count = re.subn(r'(\.' + pin + r'\()([^)]*)',
                                     r'\g<1>' + ('VCC' if kind == 'PLL' else 'GND'), match[0])
            if count != 1 or changed == match[0]:
                raise ValueError('Negative mutation is not exact: ' + name)
            broken = vo[:match.start()] + changed + vo[match.end():]
            bad, unused = (shared_clock_plls(sdf, broken, RoutedDesign, local_panel_enabled=local_panel_enabled) if kind == 'PLL' else
                           inspect_serializer_startup(sdf, broken, ddr, sdc, lane_layout='native'))
            if not bad or not any(reason in message for message in bad):
                raise ValueError('Negative mutation did not fail its gate: ' + name + ' ' + str(bad))
            negatives[name + '/' + pin] = bad
    evidence = {str(path): digest for path, digest in snapshot.items()}
    evidence.update({str(path): sha(path) for path in outputs.glob('*.json')})
    verify_unchanged(snapshot)
    return dict(schema=1, recorded_at=datetime.now().astimezone().isoformat(), identity=inputs['identity'],
                scope='Complete maintained native PLL/startup subgate; not full STA/CDC/electrical or board acceptance',
                pll_gate_passed=not errors, errors=errors, ddr_source=ddr, ddr_configuration=config,
                serializer_startup=startup, video_pll=video, shared_clock_plls=shared,
                profile_selection=selection, expected_pll_count=7 if local_panel_enabled else 6,
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
