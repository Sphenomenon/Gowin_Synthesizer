"""Prepare an explicit physical experiment from an audited native netlist.

This does not change synthesis-only defaults, approve electrical safety, or
program hardware. Physical and deployment results require separate evidence.
"""

from pathlib import Path
from datetime import datetime
import argparse
import fnmatch
import json
import re
import shutil

from tools.stage_usb_firmware import sha
from tools.workstation_custom_board_audit import audit as audit_synthesis
from tools.workstation_pinout import digest, parse_locations
from tools.workstation_synthesis_netlist import SynthesisNetlist


BASE = 'custom_138k_integration'
TOP = 'workstation_custom_138k_top'
DEVICE = 'GW5AST-LV138PG484AC2/I1'
DDR_PHY = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
DDR_LAUNCH = DDR_PHY + '/ddr_init_internal_r_s0'
DDR_CAPTURE = DDR_PHY + '/wloadn_3_s0'
DDR_CAPTURE_REGION = 'R[40:50]C[70:90]'
DDR_CAPTURE_CONSTRAINT = f'INS_LOC "{DDR_CAPTURE}" {DDR_CAPTURE_REGION};'
DDR_MINIMUM = f'set_min_delay 0.800 -from [get_pins {{{DDR_LAUNCH}/Q}}] -to [get_pins {{{DDR_CAPTURE}/D}}]'
DDR_STRICT_MINIMUM = DDR_MINIMUM.replace('0.800', '3.500', 1)
DDR_LAUNCH_REGION = 'R[70:80]C[150:170]'
DDR_LAUNCH_CONSTRAINT = f'INS_LOC "{DDR_LAUNCH}" {DDR_LAUNCH_REGION};'
DDR_FAR_CAPTURE_REGION = 'R[2:10]C[2:20]'
DDR_FAR_LAUNCH_REGION = 'R[104:110]C[175:181]'
# DQS hard sites may use border row111; ordinary logic ends at row110.
DDR_DQS_HOLD_REGIONS = tuple(f'R[{104-10*lane}:{min(110,118-10*lane)}]C[2:30]' for lane in range(4))
REFERENCE_SOURCE_MONITORS = (
    ('reference_48_monitor', 'clk_12m288', 'R[54:54]C[64:84]'),
    ('reference_44_monitor', 'clk_16m9344', 'R[56:56]C[64:84]'))
REFERENCE_MONITOR_ROOT = 'u_managed/runtime/clocks/'


def implementation_script(user_code, place_option=2, route_option=0, replicate_resources=False):
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code):
        raise ValueError('a new eight-hex UserCode is required')
    if place_option not in range(5) or route_option not in (0, 1):
        raise ValueError('unsupported physical implementation algorithm')
    return (
        'set root [file normalize [file dirname [info script]]]\n'
        'cd $root\n'
        f'set_device {DEVICE} -device_version C\n'
        'set_option -synthesis_tool gowinsynthesis\n'
        f'set_option -top_module {TOP}\n'
        f'set_option -output_base_name {BASE}\n'
        'set_option -verilog_std sysv2017\n'
        'set_option -use_mspi_as_gpio 1\n'
        'set_option -use_cpu_as_gpio 1\n'
        'add_file -type cst [file join $root physical.cst]\n'
        'add_file -type sdc [file join $root physical.sdc]\n'
        f'add_file -type netlist [file join $root {BASE}.vg]\n'
        f'set_option -user_code {user_code.upper()}\n'
        'set_option -bit_security 0\n'
        'set_option -secure_mode 0\n'
        'set_option -bit_encrypt 0\n'
        'set_option -bit_compress 0\n'
        'set_option -gen_text_timing_rpt 1\n'
        'set_option -gen_sdf 1\n'
        'set_option -gen_verilog_sim_netlist 1\n'
        'set_option -timing_driven 1\n'
        'set_option -correct_hold_violation 1\n'
        f'set_option -place_option {place_option}\n'
        f'set_option -route_option {route_option}\n'
        f'set_option -replicate_resources {int(replicate_resources)}\n'
        'run pnr\n'
    )


def checked_copy(source, destination, expected):
    if sha(source) != expected:
        raise ValueError('physical input changed before copy: ' + str(source))
    shutil.copyfile(source, destination)
    if sha(destination) != expected:
        raise ValueError('physical input changed during copy: ' + str(source))


def paired_profile_input(source, metadata, audit):
    """Seal the selected paired profile without inheriting its failed gates."""
    if audit.get('paired_role') is None:
        return {}
    from tools.workstation_task3_paired_audit import PROFILES
    selected = metadata.get('workstation_profile', {})
    name = selected.get('name')
    if (name not in PROFILES or PROFILES[name][0] != audit['paired_role'] or
            audit.get('validation_stage') != 'task3_paired_synthesis_only' or
            audit.get('synthesis_audit_passed') is not True or
            audit.get('source_policy') != 'immutable_prepared_closure' or
            audit.get('audit_source_seal_before_and_after') is not True or
            selected.get('artifact') != 'workstation_profile.json' or
            selected.get('candidate_identity') != audit.get('candidate_identity') or
            audit.get('identity') != metadata.get('identity')):
        raise ValueError('paired physical parent profile/role linkage changed')
    path = Path(source) / selected['artifact']
    expected = selected.get('artifact_sha256')
    if not isinstance(expected, str) or sha(path) != expected:
        raise ValueError('paired physical profile artifact changed')
    return {'parent_workstation_profile.json': (path, expected)}


def reference_constraints(payload, netlist_text, excluded_ports=()):
    """Bind an explicit historical CST to this netlist, without PCB acceptance."""
    native = SynthesisNetlist(netlist_text, TOP)
    ports = set()
    for port in native.directions[TOP]:
        limits = native.ranges[TOP].get(port)
        ports.update([f'{port}[{i}]' for i in range(min(limits), max(limits)+1)] if limits else [port])
    if set(excluded_ports) & ports:
        raise ValueError('cannot exclude a port present in the current netlist')
    lines, omitted, instances = [], [], {}
    for line in payload.decode('utf-8').splitlines():
        match = re.match(r'(IO_LOC|IO_PORT|INS_LOC|CLOCK_LOC)\s+"([^"]+)"', line)
        if match:
            kind, name = match.groups()
            if kind.startswith('IO_') and name in excluded_ports:
                omitted.append(line)
                continue
            if kind.startswith('IO_') and name not in ports:
                raise ValueError('historical CST has an unreviewed absent port: ' + name)
            if kind == 'INS_LOC':
                if name in native.cells:
                    instances[name] = 'resolved_in_synthesis_netlist'
                elif name.startswith('u_memory/u_ddr3/gw3_top/u_ddr_phy_top/'):
                    instances[name] = 'encrypted_DDR_target_require_routed_resolution'
                else:
                    raise ValueError('historical CST has an absent instance: ' + name)
            if kind == 'CLOCK_LOC' and not any(
                    cell['kind'] in ('IBUF', 'BUFG') and cell['ports'].get('O') == name
                    for cell in native.modules[TOP].values()):
                raise ValueError('historical CST has an absent top-level global clock net: ' + name)
        lines.append(line)
    result = ('\n'.join(lines)+'\n').encode('utf-8')
    locations = parse_locations(result.decode('utf-8'))
    implicit = {}
    for port, balls in locations.items():
        if len(balls) == 2:
            negative = (port.replace('tmds_data_p', 'tmds_data_n').replace('tmds_clk_p', 'tmds_clk_n')
                        if port.startswith('tmds_') else port.replace('ddr_dqs', 'ddr_dqs_n').replace('ddr_ck', 'ddr_ck_n'))
            if negative == port or negative not in ports:
                raise ValueError('unresolved differential complement: ' + port)
            implicit[negative] = balls[1]
    if set(locations) | set(implicit) != ports:
        raise ValueError('historical CST does not cover every current top-level port bit')
    balls = [ball for values in locations.values() for ball in values]
    if len(set(balls)) != len(balls):
        raise ValueError('historical CST assigns a package ball more than once')
    return result, dict(port_bits=len(ports), explicit_locations=locations,
                        differential_complements=implicit, omitted=omitted, instance_locations=instances)


def task3_pin_collections(payload, netlist_text):
    """Express the same DIRECT r3 pin sets in Gowin's physical selector syntax.

    Gowin rejects the numeric character class accepted by our lexical audit,
    and requires a collection for RAM16SDP4 vector ports. Materialize only the
    exact fifteen reviewed scalar producers and two RAM vector queries. Every
    native endpoint set and all non-query bytes must remain unchanged. This
    does not prove routed vector arcs, the FIFO contract, or physical CDC.
    """
    from tools.workstation_task3_tf_direct import new_constraints
    text = payload.decode('utf-8')
    query = re.compile(r'\[get_pins\s+\{([^{}]+)\}\]')
    reviewed = {selector for match in query.finditer(new_constraints(revision=3))
                for selector in match[1].split() if '[0-9]' in selector}
    if len(reviewed) != 15:
        raise ValueError('reviewed DIRECT r3 scalar selector inventory changed')
    n = SynthesisNetlist(netlist_text, TOP)
    pins = {path + '/' + pin for path, cell in n.cells.items() for pin in cell['ports']}
    ram = 'u_tf_audio/frames/frames_0/g_small_head.memory_g_small_head.memory_0_*_s'
    vectors = {ram + '/DO', ram + '/RAD'}
    selected, changes = [], []

    def convert(match):
        result, changed = [], False
        for selector in match[1].split():
            after = [selector]
            if selector in reviewed or selector in vectors:
                endpoints = sorted(pin for pin in pins if fnmatch.fnmatchcase(pin, selector))
                if not endpoints or selector in selected:
                    raise ValueError('missing/duplicated physical pin selector: ' + selector)
                if selector in reviewed:
                    if any(not pin.endswith('/Q') or
                           n.cells[pin.rsplit('/', 1)[0]]['kind'] not in
                           ('DFFCE', 'DFFRE', 'DFFPE') for pin in endpoints):
                        raise ValueError('scalar selector no longer names reviewed FF Qs')
                    after = endpoints
                    kind = 'explicit_scalar_FF_Q'
                else:
                    if any(n.cells[pin.rsplit('/', 1)[0]]['kind'] != 'RAM16SDP4' or
                           set(n.cells[pin.rsplit('/', 1)[0]]['ports']) !=
                           {'DO', 'CLK', 'WRE', 'WAD', 'DI', 'RAD'} for pin in endpoints):
                        raise ValueError('vector collection requires exact RAM16SDP4 ports')
                    after = [selector + '*']
                    kind = 'RAM16SDP4_vector_collection'
                actual = {pin for replacement in after for pin in pins
                          if fnmatch.fnmatchcase(pin, replacement)}
                if actual != set(endpoints):
                    raise ValueError('physical selector changes native endpoint set')
                selected.append(selector)
                changes.append(dict(before=selector, after=after, kind=kind,
                                    native_endpoints=endpoints,
                                    **(dict(vector_width=4) if selector in vectors else {})))
                changed = True
            elif '[0-9]' in selector:
                raise ValueError('unreviewed numeric character class in physical SDC')
            result.extend(after)
        return '[get_pins {' + ' '.join(result) + '}]' if changed else match[0]

    adapted = query.sub(convert, text)
    if set(selected) != reviewed | vectors or len(selected) != 17:
        raise ValueError('incomplete DIRECT r3 physical selector inventory')
    if query.sub('PIN_QUERY', adapted) != query.sub('PIN_QUERY', text):
        raise ValueError('physical pin adaptation changed a clock/budget/exception command')
    result = adapted.encode('utf-8')
    return result, dict(policy='task3_direct_r3_Gowin_pin_collections_v1',
        input_sha256=digest(payload), output_sha256=digest(result), changes=changes,
        logical_native_endpoint_sets_unchanged=True, non_query_bytes_unchanged=True,
        clocks_or_budgets_or_exception_scope_relaxed=False,
        routed_vector_arcs_verified=False, whole_CDC_accepted=False,
        physical_timing_verified=False, hardware_tested=False, deployment_allowed=False)


def preboard_constraint_selection(stage,metadata,audit,cst,base_sdc,netlist_text,*,
                                  task3_pins=False,preboard_releases=False,
                                  primary_clk50=False,ddr_reference=None):
    """Reconstruct exact paired preboard adaptations for prepare and re-audit."""
    pin_adaptation = None
    physical_sdc = None
    if task3_pins:
        if audit.get('paired_role') != 'M' or audit.get('validation_stage') != 'task3_paired_synthesis_only':
            raise ValueError('task3 physical pin collections require an explicit paired M audit')
        physical_sdc, pin_adaptation = task3_pin_collections(
            base_sdc, netlist_text)
    release_proof=None
    held_proofs=None
    ddr_proof=None
    m_critical=metadata.get('m_critical_locality')
    if m_critical is not None:
        from tools.workstation_task3_m_critical_locality import POLICY as critical_policy
        if audit.get('paired_role')!='M' or m_critical.get('policy')!=critical_policy:
            raise ValueError('unreviewed M critical physical policy')
    if preboard_releases:
        from tools.workstation_native_protocol_audit import protocol_netlist
        from tools.workstation_preboard_physical_boundaries import audit as prove_releases
        release_proof,extra=prove_releases(
            protocol_netlist(netlist_text,mapping='synthesis'),
            role=audit.get('paired_role'),stage=stage)
        parent_sdc=physical_sdc if physical_sdc is not None else base_sdc
        physical_sdc=parent_sdc+extra.encode()
        release_proof.update(parent_sdc_sha256=digest(parent_sdc),
            selected_sdc_sha256=digest(physical_sdc),
            proof_tool_sha256=sha(Path(__file__).with_name('workstation_preboard_physical_boundaries.py')))
        from tools.workstation_task3_preboard_held_timing import audit as paired_held, placement as place_held
        n=protocol_netlist(netlist_text,mapping='synthesis')
        role=audit['paired_role']
        held_proofs={}
        held_proofs['paired'],extra=paired_held(n,role=role)
        physical_sdc+=extra.encode()
        cst,held_proofs['paired_placement']=place_held(cst,held_proofs['paired'],m_v40_locality=bool(m_critical))
        if role=='M':
            physical_sdc,held_proofs['M_PLL_control_limits']=m_preboard_pll_control_limits(physical_sdc,netlist_text,
                diagnosed_v40=bool(m_critical))
            if m_critical:
                from tools.workstation_task3_m_critical_locality import placement as place_m_critical
                cst,held_proofs['M_v40_critical_locality']=place_m_critical(cst,n)
            from tools.workstation_task3_m_session_boundary import audit as specific_held
        else:
            from tools.workstation_task3_w_raw_command_capture import audit as specific_held
        held_proofs['role_specific'],extra=specific_held(n,**(
            {'publication':bool(metadata.get('raw_completion_publication')),
             'fetch_end_capture':metadata.get('raw_fetch_range',{}).get('added_state_bits')==33,
             'generation_match':bool(metadata.get('raw_generation_match'))}if role=='W'else {}))
        physical_sdc+=extra.encode()
        if role=='W':
            from tools.workstation_task3_preboard_held_timing import w_native_placement
            from tools.workstation_task3_w_delay_locality import arithmetic_layout
            from tools.workstation_w_identity_bytes import MANIFEST as key_manifest, MANIFEST_SHA256 as key_manifest_sha
            key_path=Path(stage)/key_manifest
            key_bytes=False
            if key_path.is_file():
                if sha(key_path)!=key_manifest_sha:
                    raise ValueError('W physical identity-byte manifest drift')
                key_rows=json.loads(key_path.read_text())['sources']
                key_bytes=all(sha(Path(stage)/row['source'])==row['native_sha256']for row in key_rows)
                if not key_bytes:
                    raise ValueError('W physical identity-byte source selection drift')
            cst,held_proofs['W_native_placement']=w_native_placement(cst,n,
                publication=bool(metadata.get('raw_completion_publication')),
                terminal=bool(metadata.get('raw_terminal_cofactor')),
                tuple_cofactor=bool(metadata.get('raw_terminal_tuple')),
                pack_cofactor=bool(metadata.get('raw_pack_cofactor')),
                native_fault_cofactor=bool(metadata.get('native_fault_cofactor')),
                identity_bytes=key_bytes,
                fetch_range=bool(metadata.get('raw_fetch_range')),
                fetch_end_capture=metadata.get('raw_fetch_range',{}).get('added_state_bits')==33,
                registered_tx_class=metadata.get('w_tx_class',{}).get('policy')=='task3_W_registered_normal_tx_preference_v1',
                fifo_compare_first=metadata.get('fifo_full_compare',{}).get('policy')=='task3_W_large_FIFO_compare_before_write_select_v1',
                arithmetic_repair=arithmetic_layout(metadata),
                generation_match=bool(metadata.get('raw_generation_match')),
                cancel_ready_cofactor=bool(metadata.get('w_tx_class',{}).get('record_cancel_ready')),
                combined_admission=metadata.get('combined_event_admission',{}).get('policy')=='task3_W_combined_sample_event_admission_v1',
                cnn_retirement=bool(metadata.get('cnn_staging_retirement')),
                dma_ready_cofactor=bool(metadata.get('w_delay_ready')))
    if ddr_reference is not None:
        if not preboard_releases or not primary_clk50:
            raise ValueError('preboard DDR timing requires proved paired releases and primary clock placement')
        prior=Path(ddr_reference).resolve()
        prior_meta=json.loads((prior/'parent_integration_inputs.json').read_text())
        ddr={p:h for p,h in metadata['staged_input_sha256'].items()if p.startswith('vendor/gowin_ddr3/')}
        if not ddr or any(prior_meta['staged_input_sha256'].get(p)!=h for p,h in ddr.items()):
            raise ValueError('preboard DDR routed reference uses different encrypted inputs')
        vo=prior/'impl/pnr/custom_138k_integration.vo'
        cst,placement=ddr_launch_capture_region_constraints(cst,physical_sdc,vo.read_text(),far_regions=True)
        from tools.workstation_preboard_ddr_timing import tighten
        cst,physical_sdc,ddr_proof=tighten(cst,physical_sdc,vo.read_text(),role=audit['paired_role'],
            dqs_hold_locality=bool(metadata.get('m_pcm_overflow')),hold_i_locality=bool(m_critical))
        ddr_proof.update(routed_reference=str(vo),routed_reference_sha256=sha(vo),
            same_encrypted_DDR_input_sha256=ddr,placement=placement)
    return cst,physical_sdc,pin_adaptation,release_proof,held_proofs,ddr_proof


def prepare_reference(source, output, user_code, reference_cst, reference_sha256, excluded_ports=(),
                      place_option=2, route_option=0, task3_pins=False, preboard_releases=False,
                      primary_clk50=False, preboard_ddr_reference=None, w_delay_locality=False,
                      replicate_resources=False):
    """Offline experiment using a hash-pinned reference; never board validation."""
    source, output, reference_cst = map(lambda p: Path(p).resolve(), (source, output, reference_cst))
    script = implementation_script(user_code, place_option, route_option, replicate_resources)
    if output.exists() or source in output.parents:
        raise ValueError('physical output must be new and outside its parent candidate')
    if not re.fullmatch('[0-9a-f]{64}', reference_sha256) or sha(reference_cst) != reference_sha256:
        raise ValueError('historical physical constraint identity changed')
    audit = audit_synthesis(source)
    if audit.get('paired_role') is not None:
        # Preserve independent gate failures before refusing physical prepare.
        # This sibling report is evidence, outside the immutable source stage.
        report=output.with_name(output.name+'.synthesis-audit.json')
        with report.open('x') as stream:stream.write(json.dumps(audit,indent=2)+'\n')
        if audit.get('synthesis_audit_passed') is not True:
            failures={name:gate.get('error')for name,gate in audit.get('gates',{}).items()if not gate.get('passed')}
            raise ValueError('paired physical prepare requires complete synthesis gates: '+json.dumps(failures))
    metadata = json.loads((source / 'integration_inputs.json').read_text())
    if metadata['top_module'] != TOP:
        raise ValueError('native top identity changed')
    stage = source / 'workstation/Prj1'
    vg = stage / f'impl/gwsynthesis/{BASE}.vg'
    cst, binding = reference_constraints(reference_cst.read_bytes(), vg.read_text(), excluded_ports)
    clock_placement=None
    if primary_clk50:
        cst,clock_placement=primary_clk50_constraints(cst,vg.read_text())
        if preboard_releases and audit.get('paired_role')=='M':
            cst,clock_placement['M_clock_priority']=m_preboard_clock_priority(cst,vg.read_text(),
                watchdog_retime=bool(metadata.get('delay_watchdog_retime')))
    inputs = {
        BASE+'.vg': (vg, audit['netlist_sha256']),
        'reference.cst': (reference_cst, reference_sha256),
        'physical.sdc': (stage / 'constraints/custom_138k.sdc',
                         metadata['staged_input_sha256']['constraints/custom_138k.sdc']),
        'parent_integration_inputs.json': (source / 'integration_inputs.json', audit['integration_inputs_sha256']),
    }
    inputs.update(paired_profile_input(source, metadata, audit))
    cst,physical_sdc,pin_adaptation,release_proof,held_proofs,ddr_proof=preboard_constraint_selection(
        stage,metadata,audit,cst,inputs['physical.sdc'][0].read_bytes(),vg.read_text(),
        task3_pins=task3_pins,preboard_releases=preboard_releases,
        primary_clk50=primary_clk50,ddr_reference=preboard_ddr_reference)
    locality=None
    if w_delay_locality:
        if not preboard_releases or audit.get('paired_role')!='W':
            raise ValueError('diagnosed delay locality requires explicit preboard W')
        from tools.workstation_task3_w_delay_locality import placement, arithmetic_layout
        from tools.workstation_native_protocol_audit import protocol_netlist
        cst,locality=placement(cst,protocol_netlist(vg.read_text(),mapping='synthesis'),
            registered_tx_class=metadata.get('w_tx_class',{}).get('policy')=='task3_W_registered_normal_tx_preference_v1',
                fifo_compare_first=metadata.get('fifo_full_compare',{}).get('policy')=='task3_W_large_FIFO_compare_before_write_select_v1',
                arithmetic_repair=arithmetic_layout(metadata),
                cancel_ready_cofactor=bool(metadata.get('w_tx_class',{}).get('record_cancel_ready')),
                combined_admission=metadata.get('combined_event_admission',{}).get('policy')=='task3_W_combined_sample_event_admission_v1',
                cnn_retirement=bool(metadata.get('cnn_staging_retirement')),
                dma_ready_cofactor=bool(metadata.get('w_delay_ready')))
        locality.update(source_candidate=audit['candidate_identity'],VG_sha256=sha(vg),
            SDC_sha256=digest(physical_sdc if physical_sdc is not None else inputs['physical.sdc'][0].read_bytes()))
    output.mkdir(parents=True)
    for name, (path, expected) in inputs.items():
        checked_copy(path, output/name, expected)
    (output/'physical.cst').write_bytes(cst)
    if physical_sdc is not None:
        (output/'physical.sdc').write_bytes(physical_sdc)
    (output/'run.tcl').write_text(script)
    (output/'parent_synthesis_audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    if release_proof is not None:
        (output/'physical_release_proof.json').write_text(json.dumps(release_proof,indent=2)+'\n')
    if held_proofs is not None:
        (output/'physical_held_proof.json').write_text(json.dumps(held_proofs,indent=2)+'\n')
    if ddr_proof is not None:
        (output/'physical_ddr_proof.json').write_text(json.dumps(ddr_proof,indent=2)+'\n')
    if locality is not None:
        (output/'diagnosed-locality.json').write_text(json.dumps(locality,indent=2)+'\n')
    result = dict(schema=1, identity='custom138k-resource-physical-'+user_code.upper(),
        prepared_at=datetime.now().astimezone().isoformat(),
        validation_stage='offline_physical_experiment_prepared',
        source_policy=('audited_native_netlist_with_hash_pinned_CST_and_exact_task3_pin_collections'
                       if task3_pins else 'audited_native_netlist_with_hash_pinned_historical_CST_and_unchanged_SDC'),
        parent_candidate=str(source), parent_identity=audit['identity'],
        **(dict(paired_role=audit['paired_role'], parent_candidate_identity=audit['candidate_identity'])
           if audit.get('paired_role') is not None else {}),
        preparer_sha256=sha(__file__), user_code='0x'+user_code.upper(), top_module=TOP, device=DEVICE,
        constraint_reference=dict(path=str(reference_cst), sha256=reference_sha256, binding=binding),
        electrical_status='historical_reference_only_no_current_PCB_netlist_check',
        board_netlists_checked=False, board_programming_authorized=False,
        clocks_or_exceptions_relaxed=False, features_removed=False,
        place_option=place_option, route_option=route_option, replicate_resources=replicate_resources,
        task3_pin_adaptation=pin_adaptation,
        preboard_release_adaptation=release_proof,
        preboard_held_adaptation=held_proofs,
        preboard_ddr_adaptation=ddr_proof,
        primary_clk50_adaptation=clock_placement,
        **(dict(diagnosed_locality=locality) if locality is not None else {}),
        input_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file()},
        timing_closed=False, physical_gates_passed=False, hardware_tested=False,
        deployment_allowed=False, release_ready=False, bitstream_sha256=None,
        sram_programmed=False, flash_programmed=False, remaining_gaps=metadata['remaining_gaps'])
    (output/'physical_inputs.json').write_text(json.dumps(result, indent=2)+'\n')
    return result



def m_preboard_pll_control_limits(sdc,netlist_text,*,diagnosed_v40=False):
    """Tighten actual A14 registered control flights; retain the full 10ns audit.

    These 4.5ns Q-to-PLL data bounds reserve propagation for the real clk50
    input/clock-tree/CLK-Q budget. Constants and video reset logic stay under
    their existing source and routed gates. No exception or clock is changed.
    """
    from tools.workstation_native_protocol_audit import protocol_netlist
    from tools.workstation_runtime_pcm_cdc import Graph
    n=protocol_netlist(netlist_text,mapping='synthesis');g=Graph(n);rows=[];lines=[]
    prefixes=('u_cpu_pll','u_video/u_clock/g_hardware.u_pll/u_reference')
    if diagnosed_v40:
        prefixes+=('u_usb_pll','u_video/u_clock/g_hardware.u_pll/u_tmds')
    for prefix in prefixes:
        direct=prefix in ('u_cpu_pll','u_usb_pll')
        path=prefix+'/PLL_inst';cell=n.cells.get(path,{})
        if cell.get('kind')!='PLL':raise ValueError('M PLL control target absent '+path)
        for bus,width,start in [('ICPSEL',6,3),('LPFRES',3,0),('RESET',1,9)]:
            if not direct and bus=='RESET':continue
            scope=n.scopes[path];bits=g.binding_bits(scope,cell['ports'][bus])
            if len(bits)!=width:raise ValueError('M PLL control width changed')
            for index,raw in enumerate(bits):
                net=n.canonical(scope,raw)
                static_from=1 if prefix.endswith('/u_tmds') else 2
                if not direct and bus=='ICPSEL' and index>=static_from:
                    if net not in g.low:raise ValueError('M video PLL static control changed')
                    continue
                drivers=g.drivers[net]
                if len(drivers)!=1:raise ValueError('M PLL control is not unique')
                source,pin=drivers[0]
                pattern=(re.escape(prefix+'/pll_control_'+str(start+index))+r'_s\d+' if direct
                    else re.escape(prefix+'/u_pll_init/RomDreg_'+str(index if bus=='ICPSEL' else index+8))+r'_s\d+')
                if not re.fullmatch(pattern,source) or pin!='Q' or not n.cells[source]['kind'].startswith('DFF') or n.pin(source,'CLK')!='clk_50m':
                    raise ValueError('M PLL control publisher/clock changed '+source)
                endpoint=path+'/'+(bus if bus=='RESET' else bus+'['+str(index)+']')
                command=f'set_max_delay 4.500 -from [get_pins {{{source}/Q}}] -to [get_pins {{{endpoint}}}]'
                if command.encode() in sdc:raise ValueError('M PLL limit already installed')
                lines.append(command);rows.append(dict(source=source+'/Q',endpoint=endpoint,maximum_ns=4.5))
    if len(rows)!=(29 if diagnosed_v40 else 15):raise ValueError('M PLL exact registered control inventory changed')
    result=sdc+('\n# task3 M A14 PLL registered control route budgets\n'+'\n'.join(lines)+'\n').encode()
    return result,dict(policy=('task3_M_v40_29_PLL_controls_max4p5_v3'if diagnosed_v40 else
        'task3_M_A14_registered_PLL_controls_max4p5_v2'),paths=rows,
        full_routed_propagation_budget_ns=10.0,parent_sdc_sha256=digest(sdc),selected_sdc_sha256=digest(result),
        timing_relaxed=False,clock_periods_changed=False,routed_timing_verified=False)


def m_preboard_clock_priority(payload,netlist_text,*,watchdog_retime=False):
    """Reserve LW8..10 for real clocks after A8 exhausted all long wires.

    A8 put eight functional clocks on PRIMARY and eight mixed reset/reference
    nets on LW, spilling ULPI and both DAC references to generic routing. The
    same-device syntax probe confirms BUFG[8] selects LW. Give clocks priority
    and reserve LW11 for the actual asserted memory reset after its A11
    recovery failure. SUG1018 section2.7 requires SR for CLEAR loads; the
    positive release Q only drives logic and its inverter. All timing checks
    remain required in the new physical run.
    """
    n=SynthesisNetlist(netlist_text,TOP);lines=[];inputs=[]
    for bit,port in enumerate(('usb2_ulpi_clk','clk_12m288','clk_16m9344'),8):
        name=port+'_ibuf';c=n.cells.get(name,{})
        if c.get('kind')!='IBUF' or c.get('ports')!={'I':port,'O':port+'_d'}:
            raise ValueError('M physical clock priority requires exact input buffer '+port)
        net=port+'_d'
        if re.search(r'CLOCK_LOC\s+"'+re.escape(net)+r'"',payload.decode()):
            raise ValueError('M physical clock already constrained '+net)
        lines.append(f'CLOCK_LOC "{net}" BUFG[{bit}] = CLK;')
        inputs.append(dict(port=port,buffer=name,net=net,global_wire=bit))
    reset_nets=[]
    for scope,stem,clock in [('u_managed/runtime','memory_release[2]','memory_clk'),
                       ('u_tf_audio','source_release[2]','clk_50m'),('u_video','memory_release[2]','memory_clk')]:
        net=n.canonical(scope,stem)
        if re.search(r'CLOCK_LOC\s+"'+re.escape(net)+r'"',payload.decode()):
            raise ValueError('M physical reset-distribution identity changed '+scope+'/'+stem)
        producers=[p for p,c in n.cells.items()if c['kind'].startswith('DFF')and n.pin(p,'Q')==net]
        # Synthesis may promote the TF release to a top-level net alias.
        # Follow that connection while retaining the exact owning publisher.
        publisher = (scope + '/u_runtime_display/memory_release_2_s0' if scope == 'u_video'
                     else scope + '/' + stem.replace('[2]', '_2_s0'))
        if producers != [publisher] or n.pin(publisher,'CLK')!=clock:
            raise ValueError('M local reset distribution requires one actual publisher in '+clock+' '+net)
        # Gowin unifies the positive source and its inverse for CLOCK_LOC.
        # Constrain this release only through the asserted SR net below.
        if scope!='u_managed/runtime':lines.append(f'CLOCK_LOC "{net}" LOCAL_CLOCK;')
        reset_nets.append(net)
    release=reset_nets[0]
    inverses=[p for p,c in n.cells.items() if c['kind']=='INV' and n.pin(p,'I')==release]
    if len(inverses)!=1:
        raise ValueError('M memory reset requires one exact release inverse')
    reset_net=n.pin(inverses[0],'O')
    loads=sorted((p,pin) for p,c in n.cells.items() if c['kind'] not in n.modules for pin in c['ports']
                 if n.pin(p,pin)==reset_net and not (p==inverses[0] and pin=='O'))
    ff_loads=[(p,pin) for p,pin in loads if n.cells[p]['kind'] in ('DFFCE','DFFPE')]
    ram_loads=[(p,pin) for p,pin in loads if n.cells[p]['kind']=='SDPX9B']
    if watchdog_retime:
        path='u_managed/runtime/delay_dma/watchdog_reset_delay_s0'
        cell=n.cells.get(path,{})
        if (cell.get('kind')!='DFFPE' or cell.get('parameters',{}).get('INIT',"1'b1")!="1'b1" or
            set(cell.get('ports',{}))!={'Q','D','CLK','PRESET','CE'} or
            n.pin(path,'CLK')!='memory_clk' or n.pin(path,'PRESET')!=reset_net or
            (path,'PRESET')not in ff_loads):
            raise ValueError('M watchdog delayed reset requires exact memory-clock preset publisher')
    extra=int(watchdog_retime)
    if (len(loads)!=897+extra or len(ff_loads)!=893+extra or len(ram_loads)!=4 or
        sum(pin=='CLEAR' for p,pin in ff_loads)!=891 or
        any(pin!=('CLEAR' if n.cells[p]['kind']=='DFFCE' else 'PRESET') or
            n.pin(p,'CLK')!='memory_clk' for p,pin in ff_loads) or
        any(pin!='RESET' for p,pin in ram_loads)):
        raise ValueError('M memory reset exact891 CLEAR,selected PRESET and4 RAM RESET consumers changed')
    if re.search(r'CLOCK_LOC\s+"'+re.escape(reset_net)+r'"',payload.decode()):
        raise ValueError('M memory asserted reset already constrained')
    lines.append(f'CLOCK_LOC "{reset_net}" BUFG[11] = SR;')
    adapted=payload+('\n# M A11 asserted memory reset LW11 SR priority; timing retained\n'+'\n'.join(lines)+'\n').encode()
    return adapted,dict(policy='task3_M_A14_real_clock_and_asserted_memory_reset_LW_priority_v4',clock_inputs=inputs,
        memory_reset=dict(release=release,inverter=inverses[0],net=reset_net,
                          signal_type='SR',global_wire=11,reset_loads=loads,watchdog_delayed_preset=watchdog_retime),
        reset_distribution_nets=reset_nets,commands=lines,before_sha256=digest(payload),
        after_sha256=digest(adapted),logic_unchanged=True,timing_constraints_unchanged=True,
        routed_clock_allocation_verified=False,hardware_tested=False)


def primary_clk50_constraints(payload, netlist_text):
    """Route the existing 50MHz input on PRIMARY, retaining every endpoint.

    A previous physical route used generic resources for ~29k clock loads.
    This placement constraint requests a real clock network, with no frequency,
    waveform, SDC or data-path exception change. Final routing must verify it.
    """
    n=SynthesisNetlist(netlist_text,TOP)
    cell=n.cells.get('clk_50m_ibuf',{})
    if cell.get('kind')!='IBUF' or cell['ports']!={'O':'clk_50m_d','I':'clk_50m'}:
        raise ValueError('PRIMARY clk50 requires exact top input buffer')
    if re.search(r'CLOCK_LOC\s+"clk_50m_d"',payload.decode()):
        raise ValueError('clk50 already has an explicit route assignment')
    clock=n.pin('clk_50m_ibuf','O')
    loads=sorted(p for p,c in n.cells.items() if c['kind'].startswith('DFF') and
                 n.pin(p,'CLK')==clock)
    if len(loads)<1000:
        raise ValueError('unexpected clk50 registered load inventory')
    command='CLOCK_LOC "clk_50m_d" BUFG = CLK;'
    selected=payload+('\n'+command+'\n').encode()
    return selected,dict(policy='actual_clk50_PRIMARY_network_v1',command=command,
        parent_sha256=digest(payload),selected_sha256=digest(selected),
        actual_clock_net=clock,registered_clock_loads=len(loads),
        SDC_unchanged=True,clock_frequency_changed=False,routed_clock_class_verified=False)


def ulpi_bypass_constraints(payload, plan):
    if plan.get('ulpi_bypass') != {'U4': 'not_fitted_short', 'U5': 'not_fitted_short'}:
        raise ValueError('ULPI IO standard requires the reviewed complete bypass declaration')
    electrical = plan.get('electrical_check', {})
    supplies = {entry['part']: entry for entry in electrical.get('translators', [])}
    if (electrical.get('status') != 'no_voltage_domain_conflict_detected' or
            electrical.get('actual_board_measured') is not False or
            electrical.get('full_electrical_acceptance') is not False or electrical.get('findings') != [] or
            len(electrical.get('translators', [])) != 2 or set(supplies) != {'U4', 'U5'} or any(
                entry.get('nominal_mv') != 3300 or entry.get('phy_side') != 'B' or
                entry.get('assembly') != 'not_fitted_short' or entry.get('supply_network') != '3V3_USB3300' or
                entry.get('supply_node') != {'U4': 'U4.19', 'U5': 'U5.14'}[part]
                for part, entry in supplies.items())):
        raise ValueError('ULPI IO standard requires reviewed nominal 3V3 B-side evidence')
    text = payload.decode('utf-8')
    locations = parse_locations(text)
    ports = tuple('usb2_ulpi_data[' + str(index) + ']' for index in range(8)) + (
        'usb2_ulpi_clk', 'usb2_ulpi_dir', 'usb2_ulpi_nxt', 'usb2_ulpi_stp')
    if {port for port in locations if port.startswith('usb2_ulpi_')} != set(ports):
        raise ValueError('ULPI IO location inventory changed')
    for port in ports:
        if plan.get('ports', {}).get(port, {}).get('balls') != locations[port]:
            raise ValueError('ULPI IO location differs from the audited pinout: ' + port)
    if re.search(r'^\s*IO_PORT\s+"usb2_ulpi_', text, re.M):
        raise ValueError('ULPI IO standard already specified; refusing an implicit override')
    suffix = ('' if text.endswith('\n') else '\n') + ''.join(
        'IO_PORT "' + port + '" IO_TYPE=LVCMOS33;\n' for port in ports)
    adapted = payload + suffix.encode('utf-8')
    if parse_locations(adapted.decode('utf-8')) != locations:
        raise ValueError('ULPI IO standard adaptation changed locations')
    evidence = dict(scope='nominal_ULPI_IO_standard_only_not_external_timing_or_electrical_acceptance',
                    before_sha256=digest(payload), after_sha256=digest(adapted), io_type='LVCMOS33',
                    ports={port: locations[port] for port in ports}, locations_unchanged=True,
                    actual_board_measured=False, full_electrical_acceptance=False,
                    external_io_timing_complete=False)
    return adapted, evidence


def ddr_capture_region_constraints(payload, sdc, routed_netlist, *, strict_minimum=False):
    """Check the observed encrypted-DDR boundary, then append one placement.

    The synthesis VG contains encrypted DDR. Its hash-bound previous route VO
    supplies structural evidence; this does not claim that a new route passes.
    """
    text = payload.decode('utf-8')
    if DDR_CAPTURE in text:
        raise ValueError('DDR capture target already appears in the parent CST')
    required = (
        'INS_LOC "u_memory/u_pll/u_pll_0/PLL_inst" PLL_L[0];',
        f'INS_LOC "{DDR_PHY}/u_dll" DDRDLLM_BL;',
        f'INS_LOC "{DDR_PHY}/fclkdiv" LEFTSIDE[4];')
    if any(text.splitlines().count(line) != 1 for line in required):
        raise ValueError('DDR hard-resource locations changed')
    related = [line for line in sdc.decode('utf-8').splitlines()
               if re.match(r'\s*set_min_delay\b', line) and
               (DDR_LAUNCH in line or DDR_CAPTURE in line)]
    minimum = DDR_STRICT_MINIMUM if strict_minimum else DDR_MINIMUM
    if related != [minimum]:
        raise ValueError('DDR capture requires the unique exact ' +
                         ('3.500' if strict_minimum else '0.800') + 'ns minimum-delay constraint')
    netlist = SynthesisNetlist(routed_netlist, TOP)
    required_cells = (DDR_LAUNCH, DDR_CAPTURE, DDR_PHY + '/fclkdiv', 'clk_50m_ibuf')
    if any(name not in netlist.cells for name in required_cells):
        raise ValueError('DDR capture observed routed boundary is missing')
    launch, capture, divider, ibuf = (netlist.cells[name] for name in required_cells)
    if any(cell['kind'] != 'DFFCE' or cell['parameters'].get('INIT') != "1'b0" or
           set(cell['ports']) != {'D', 'Q', 'CLK', 'CE', 'CLEAR'} for cell in (launch, capture)):
        raise ValueError('DDR capture observed FF type/INIT/pins changed')
    power = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    if (netlist.pin(DDR_LAUNCH, 'Q') != netlist.pin(DDR_CAPTURE, 'D') or
            netlist.pin(DDR_LAUNCH, 'CLEAR') != netlist.pin(DDR_CAPTURE, 'CLEAR') or
            any(netlist.pin(name, 'CE') not in power for name in (DDR_LAUNCH, DDR_CAPTURE))):
        raise ValueError('DDR capture observed direct data/reset/enable topology changed')
    if (divider['kind'] != 'CLKDIV' or divider['parameters'].get('DIV_MODE') != '"4"' or
            launch['ports']['CLK'] != divider['ports'].get('CLKOUT') or
            ibuf['kind'] != 'IBUF' or ibuf['ports'].get('I') != 'clk_50m' or
            capture['ports']['CLK'] != ibuf['ports'].get('O')):
        raise ValueError('DDR capture observed UI divide4/direct50MHz clock boundary changed')
    adapted = payload + ('\n' + DDR_CAPTURE_CONSTRAINT + '\n').encode('utf-8')
    if not adapted.startswith(payload) or parse_locations(adapted.decode('utf-8')) != parse_locations(text):
        raise ValueError('DDR capture placement unexpectedly changed parent constraints or IO locations')
    return adapted, dict(
        instance=DDR_CAPTURE, region=DDR_CAPTURE_REGION, constraint=DDR_CAPTURE_CONSTRAINT,
        before_sha256=digest(payload), after_sha256=digest(adapted),
        exact_appended_bytes_hex=adapted[len(payload):].hex(),
        parent_bytes_preserved=True, io_locations_unchanged=True, hard_locations_unchanged=True,
        minimum_delay_ns=3.5 if strict_minimum else 0.8,
        minimum_delay_constraint=minimum, sdc_unchanged=True,
        observed_topology=dict(launch=DDR_LAUNCH, capture=DDR_CAPTURE,
                               launch_clock=launch['ports']['CLK'], capture_clock=capture['ports']['CLK'],
                               launch_clock_divide=4, capture_clock_mhz=50, direct_Q_to_D=True),
        topology_evidence_scope='hash_bound_previous_route_VO_of_same_encrypted_synthesis_VG',
        new_route_verified=False, new_hold_slack_ns=None)


def ddr_launch_capture_region_constraints(payload, sdc, routed_netlist, *, far_regions=False):
    """Place both observed ends while preserving the current 3.500ns policy."""
    if DDR_LAUNCH in payload.decode('utf-8'):
        raise ValueError('DDR launch target already appears in the parent CST')
    adapted, evidence = ddr_capture_region_constraints(
        payload, sdc, routed_netlist, strict_minimum=True)
    capture_region = DDR_FAR_CAPTURE_REGION if far_regions else DDR_CAPTURE_REGION
    launch_region = DDR_FAR_LAUNCH_REGION if far_regions else DDR_LAUNCH_REGION
    capture_constraint = f'INS_LOC "{DDR_CAPTURE}" {capture_region};'
    launch_constraint = f'INS_LOC "{DDR_LAUNCH}" {launch_region};'
    adapted = payload + ('\n' + capture_constraint + '\n' + launch_constraint + '\n').encode()
    evidence.update(region=capture_region, constraint=capture_constraint,
                    launch_instance=DDR_LAUNCH, launch_region=launch_region,
                    launch_constraint=launch_constraint, far_regions=far_regions,
                    after_sha256=digest(adapted),
                    exact_appended_bytes_hex=adapted[len(payload):].hex())
    return adapted, evidence


def ddr_dqs_hold_region_constraints(payload, sdc, routed_netlist, *, lut_only=False):
    """Keep the vendor logic intact and place four observed HOLD boundaries.

    This follows the exact previous-route FF -> LUT2 -> DQS topology. It
    neither declares these paths static nor changes their timing exceptions.
    """
    text = payload.decode('utf-8')
    if text.splitlines().count(DDR_CAPTURE_CONSTRAINT) != 1:
        raise ValueError('DQS HOLD experiment requires the original capture-region constraint')
    # Reuse the complete hard-resource/min-delay/clock boundary check without
    # appending another capture constraint or changing the original payload.
    ddr_capture_region_constraints(text.replace(DDR_CAPTURE_CONSTRAINT, '').encode(), sdc, routed_netlist)
    netlist = SynthesisNetlist(routed_netlist, TOP)
    power = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    lanes, constraints = [], []
    for lane, region in enumerate(DDR_DQS_HOLD_REGIONS):
        config = f'{DDR_PHY}/u_ddr_init/read_rclksel_conf_{lane}_s0'
        gate = f'{DDR_PHY}/u_ddr_init/hold_Z_{lane}_s'
        dqs = f'{DDR_PHY}/u_ddr_phy_wds/data_lane_gen[{lane}].u_ddr_phy_data_lane/u_ddr_phy_data_io/u_dqs'
        if any(name in text for name in (config, gate)):
            raise ValueError('DQS HOLD target already appears in the parent CST')
        if any(name not in netlist.cells for name in (config, gate, dqs)):
            raise ValueError('DQS HOLD observed boundary is missing')
        register, lut, hard = (netlist.cells[name] for name in (config, gate, dqs))
        if (register['kind'] != 'DFFCE' or register['parameters'].get('INIT') != "1'b0" or
                set(register['ports']) != {'D', 'Q', 'CLK', 'CE', 'CLEAR'} or
                netlist.pin(config, 'D') not in power or
                lut['kind'] != 'LUT2' or lut['parameters'].get('INIT') != "4'h4" or
                set(lut['ports']) != {'I0', 'I1', 'F'} or hard['kind'] != 'DQS' or
                hard['parameters'].get('DQS_MODE') != '"X4"'):
            raise ValueError('DQS HOLD observed FF/LUT/DQS type or configuration changed')
        if (netlist.pin(config, 'Q') != netlist.pin(gate, 'I0') or
                netlist.pin(gate, 'F') != netlist.pin(dqs, 'HOLD') or
                netlist.pin(config, 'CLEAR') != netlist.pin(dqs, 'RESET') or
                netlist.pin(config, 'CLK') != netlist.pin(dqs, 'PCLK') or
                netlist.pin(config, 'CLK') != netlist.pin(DDR_PHY + '/fclkdiv', 'CLKOUT')):
            raise ValueError('DQS HOLD observed data/reset/UI clock topology changed')
        constraints += [f'INS_LOC "{name}" {region};' for name in ((gate,) if lut_only else (config, gate))]
        lanes.append(dict(lane=lane, register=config, gate=gate, dqs=dqs, region=region,
                          clock=netlist.pin(config, 'CLK'), observed_FF_LUT_DQS=True,
                          register_constrained=not lut_only, gate_constrained=True))
    adapted = payload + ('\n' + '\n'.join(constraints) + '\n').encode()
    if parse_locations(adapted.decode()) != parse_locations(text):
        raise ValueError('DQS HOLD placement unexpectedly changed IO locations')
    return adapted, dict(lanes=lanes, constraints=constraints,
        mode='LUT_only' if lut_only else 'FF_and_LUT',
        unconstrained_config_registers=[lane['register'] for lane in lanes] if lut_only else [],
        before_sha256=digest(payload), after_sha256=digest(adapted),
        exact_appended_bytes_hex=adapted[len(payload):].hex(), parent_bytes_preserved=True,
        io_locations_unchanged=True, hard_locations_unchanged=True, sdc_unchanged=True,
        vendor_logic_unchanged=True, timing_exceptions_unchanged=True,
        topology_evidence_scope='hash_bound_previous_route_VO_of_same_encrypted_synthesis_VG',
        new_route_verified=False)


def reference_monitor_source_region_constraints(payload, sdc, routed_netlist):
    """Place the complete observed 128-FF source banks, with no clock edits.

    This experiment fixes the two actual 32-bit binary/Gray source banks.
    It deliberately does not infer a width or include the selected monitor.
    """
    text = payload.decode('utf-8')
    # Reuse the strict DDR boundary audit while retaining every parent byte,
    # including an existing far launch/capture placement, in the real payload.
    validation_lines = [line for line in text.splitlines() if not any(
        re.match(r'\s*INS_LOC\s+"' + re.escape(name) + r'"\s', line)
        for name in (DDR_CAPTURE, DDR_LAUNCH))]
    ddr_capture_region_constraints(('\n'.join(validation_lines) + '\n').encode(),
                                   sdc, routed_netlist, strict_minimum=True)
    netlist = SynthesisNetlist(routed_netlist, TOP)
    power = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    monitors, constraints = [], []
    for monitor, port, region in REFERENCE_SOURCE_MONITORS:
        stem = REFERENCE_MONITOR_ROOT + monitor
        names = {f'{stem}/source_{bank}_{bit}_s0'
                 for bank in ('binary', 'gray') for bit in range(32)}
        observed = {name for name in netlist.cells if name.startswith(stem + '/source_binary_') or
                    name.startswith(stem + '/source_gray_')}
        if observed != names:
            raise ValueError('reference monitor complete fixed 32-bit binary/Gray inventory changed: ' + monitor)
        if any(name in text for name in names):
            raise ValueError('reference monitor source target already appears in the parent CST')
        ibuf = netlist.cells.get(port + '_ibuf', {})
        if (ibuf.get('kind') != 'IBUF' or ibuf.get('ports') != {'I': port, 'O': port + '_d'}):
            raise ValueError('reference monitor direct IBUF clock identity changed: ' + monitor)
        registers = []
        for bank in ('binary', 'gray'):
            for bit in range(32):
                name = f'{stem}/source_{bank}_{bit}_s0'
                cell = netlist.cells[name]
                if (cell['kind'] != 'DFFCE' or cell['parameters'] != {'INIT': "1'b0"} or
                        set(cell['ports']) != {'D', 'Q', 'CLK', 'CE', 'CLEAR'}):
                    raise ValueError('reference monitor source FF type/INIT/pins changed: ' + name)
                compact = lambda net: re.sub(r'\s+', '', net).removeprefix('\\')
                if (cell['ports']['CLK'] != port + '_d' or netlist.pin(name, 'CE') not in power or
                        compact(cell['ports']['CLEAR']) != stem + '/n60_6' or
                        compact(cell['ports']['Q']) != f'{stem}/source_{bank}[{bit}]'):
                    raise ValueError('reference monitor source clock/enable/reset/output topology changed: ' + name)
                constraints.append(f'INS_LOC "{name}" {region};')
                registers.append(dict(instance=name, kind=cell['kind'], parameters=cell['parameters'],
                                      ports=cell['ports']))
        monitors.append(dict(monitor=stem, binary_bits=32, gray_bits=32, register_count=64,
                             clock_input=port, clock_ibuf=ibuf, region=region,
                             registers=registers))
    adapted = payload + ('\n' + '\n'.join(constraints) + '\n').encode()
    if not adapted.startswith(payload) or parse_locations(adapted.decode()) != parse_locations(text):
        raise ValueError('reference monitor placement unexpectedly changed parent constraints or IO locations')
    return adapted, dict(monitors=monitors, register_count=128, constraints=constraints,
        fixed_width_inventory=True, selected_monitor_constrained=False,
        before_sha256=digest(payload), after_sha256=digest(adapted),
        exact_appended_bytes_hex=adapted[len(payload):].hex(), parent_bytes_preserved=True,
        io_locations_unchanged=True, hard_locations_unchanged=True, sdc_unchanged=True,
        minimum_delay_ns=3.5, minimum_delay_constraint=DDR_STRICT_MINIMUM,
        logic_unchanged=True, clocks_unchanged=True, timing_exceptions_unchanged=True,
        topology_evidence_scope='hash_bound_previous_route_VO_of_same_synthesis_VG',
        new_route_verified=False)


def derive_ddr_capture_region(source, output, user_code, parent_evidence,
                              expected_parent_evidence_sha256, acknowledge_electrical_risk=False,
                              *, dqs_hold_regions=False, dqs_hold_lut_only=False,
                              launch_capture_regions=False, launch_capture_far_regions=False,
                              reference_monitor_source_regions=False):
    """Prepare only a hash-locked physical child; never audit mutable current RTL."""
    if dqs_hold_regions and dqs_hold_lut_only:
        raise ValueError('DQS HOLD FF/LUT and LUT-only modes are mutually exclusive')
    dqs_regions = dqs_hold_regions or dqs_hold_lut_only
    if reference_monitor_source_regions and (dqs_regions or launch_capture_regions or launch_capture_far_regions):
        raise ValueError('reference monitor and DDR placement modes are mutually exclusive')
    if ((dqs_regions and (launch_capture_regions or launch_capture_far_regions)) or
            (launch_capture_regions and launch_capture_far_regions)):
        raise ValueError('DQS HOLD and launch/capture placement modes are mutually exclusive')
    source, output, parent_evidence = (Path(path).resolve() for path in (source, output, parent_evidence))
    script = implementation_script(user_code)
    if not acknowledge_electrical_risk:
        raise ValueError('explicit acknowledgement of unresolved electrical risk is required')
    if output.exists() or source in output.parents or output in source.parents:
        raise ValueError('a new independent physical output is required')
    if (not re.fullmatch(r'[0-9a-f]{64}', expected_parent_evidence_sha256 or '') or
            sha(parent_evidence) != expected_parent_evidence_sha256):
        raise ValueError('parent physical evidence identity changed')
    evidence = json.loads(parent_evidence.read_bytes())
    previous = json.loads((source / 'physical_inputs.json').read_bytes())
    if evidence.get('stage') == 'full_physical_implementation_measurement':
        if (evidence.get('schema') != 1 or Path(evidence.get('directory', '')).resolve() != source or
                evidence.get('candidate_identity') != previous.get('parent_candidate_identity') or
                evidence.get('user_code', '').lower() != previous['user_code'].removeprefix('0x').lower() or
                evidence.get('physical_input_inventory_reverified_after_pnr') is not True or
                evidence.get('pnr_completed') is not True or evidence.get('process_exit_code') != 0 or
                evidence.get('source_and_output_sha256', {}).get('physical_inputs.json') !=
                sha(source / 'physical_inputs.json')):
            raise ValueError('measured parent identity/preparation evidence changed')
        # Keep the original measured evidence bytes in the child. Only adapt
        # its representation in memory for the same strict per-file checks.
        seals = evidence['source_and_output_sha256']
        if any(Path(name).is_absolute() or '..' in Path(name).parts or
               not (source / name).is_file() for name in seals):
            raise ValueError('measured parent evidence file inventory changed')
        evidence = dict(physical_identity=previous['identity'], preparation=previous,
            source_commit=None, profile_revision=None, profile_identity=evidence['candidate_identity'],
            status={key: evidence[key] for key in ('timing_closed', 'hardware_tested', 'release_ready')},
            evidence={name: dict(sha256=value, bytes=(source / name).stat().st_size)
                      for name, value in seals.items()})
    if (previous['user_code'].lower() == ('0x' + user_code).lower() or
            previous['identity'] != evidence['physical_identity'] or
            previous != evidence['preparation']):
        raise ValueError('a new UserCode and matching original parent preparation evidence are required')
    if (previous.get('top_module') != TOP or previous.get('device') != DEVICE or
            previous.get('place_option') != 2 or previous.get('route_option') != 0 or
            previous.get('replicate_resources') is not False or
            previous.get('electrical_risk_explicitly_acknowledged') is not True or
            not isinstance(previous.get('electrical_blocked'), bool)):
        raise ValueError('parent physical options/electrical identity changed')
    verified_evidence = {}
    for relative, identity in evidence['evidence'].items():
        path = source / relative
        if (Path(relative).is_absolute() or '..' in Path(relative).parts or
                not path.is_file() or path.stat().st_size != identity['bytes'] or
                sha(path) != identity['sha256']):
            raise ValueError('parent physical evidence drifted: ' + relative)
        verified_evidence[relative] = identity['sha256']
    inputs = previous['input_sha256']
    required = {BASE + '.vg', 'physical.cst', 'physical.sdc', 'run.tcl',
                'parent_synthesis_audit.json', 'parent_integration_inputs.json'}
    if not required.issubset(inputs) or 'physical_inputs.json' not in verified_evidence:
        raise ValueError('parent physical input inventory changed')
    for name, expected in inputs.items():
        if Path(name).name != name or sha(source / name) != expected:
            raise ValueError('parent physical input drifted: ' + name)
        if name in verified_evidence and verified_evidence[name] != expected:
            raise ValueError('parent physical evidence/input hash disagreement: ' + name)
    if (source / 'run.tcl').read_text() != implementation_script(previous['user_code'].removeprefix('0x')):
        raise ValueError('parent physical script changed from automatic hold repair and fixed algorithms')
    audit = json.loads((source / 'parent_synthesis_audit.json').read_bytes())
    if (sha(source / 'parent_integration_inputs.json') != audit['integration_inputs_sha256'] or
            sha(source / (BASE + '.vg')) != audit['netlist_sha256']):
        raise ValueError('parent synthesis manifest/netlist binding changed')
    routed_name = f'impl/pnr/{BASE}.vo'
    if routed_name not in verified_evidence:
        raise ValueError('parent route VO needs original hash-bound physical evidence')
    arguments = ((source / 'physical.cst').read_bytes(), (source / 'physical.sdc').read_bytes(),
                 (source / routed_name).read_text())
    if reference_monitor_source_regions:
        adapted, placement = reference_monitor_source_region_constraints(*arguments)
    elif launch_capture_regions or launch_capture_far_regions:
        adapted, placement = ddr_launch_capture_region_constraints(
            *arguments, far_regions=launch_capture_far_regions)
    elif dqs_regions:
        adapted, placement = ddr_dqs_hold_region_constraints(*arguments, lut_only=dqs_hold_lut_only)
    else:
        adapted, placement = ddr_capture_region_constraints(*arguments)
    placement['observed_route_vo_sha256'] = verified_evidence[routed_name]
    output.mkdir(parents=True)
    for name, expected in inputs.items():
        if name != 'run.tcl':
            checked_copy(source / name, output / name, expected)
    # A child may itself carry an older parent's snapshot. Keep every byte of
    # that closure instead of overwriting it with the immediate parent's file.
    snapshot_prefix = ('parent_' + previous['user_code'].removeprefix('0x')
                       if 'parent_physical_inputs.json' in inputs else 'parent_physical')
    parent_manifest_copy = snapshot_prefix + '_inputs.json'
    parent_evidence_copy = snapshot_prefix + '_evidence.json'
    if any(name in inputs for name in (parent_manifest_copy, parent_evidence_copy)):
        raise ValueError('physical ancestor snapshot name collides with an existing input')
    checked_copy(source / 'physical_inputs.json', output / parent_manifest_copy,
                 verified_evidence['physical_inputs.json'])
    checked_copy(parent_evidence, output / parent_evidence_copy, expected_parent_evidence_sha256)
    (output / 'physical.cst').write_bytes(adapted)
    (output / 'run.tcl').write_text(script)
    for name, expected in inputs.items():
        copied_expected = (placement['after_sha256'] if name == 'physical.cst' else
                           digest(script.encode()) if name == 'run.tcl' else expected)
        if sha(source / name) != expected or sha(output / name) != copied_expected:
            raise ValueError('physical input changed during floorplan preparation: ' + name)
    if (sha(parent_evidence) != expected_parent_evidence_sha256 or
            sha(source / 'physical_inputs.json') != verified_evidence['physical_inputs.json'] or
            sha(source / routed_name) != verified_evidence[routed_name]):
        raise ValueError('parent evidence changed during floorplan preparation')
    result = dict(previous)
    result.update(
        identity='custom138k-native-physical-' + user_code.upper(), user_code='0x' + user_code.upper(),
        prepared_at=datetime.now().astimezone().isoformat(),
        validation_stage='offline_physical_variant_prepared_no_EDA',
        source_policy=('hash_locked_previous_physical_VG_and_SDC_with_only_explicit_reference_monitor_source_regions_CST_append'
                       if reference_monitor_source_regions else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_launch_capture_far_regions_CST_append'
                       if launch_capture_far_regions else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_launch_capture_regions_CST_append'
                       if launch_capture_regions else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_DQS_HOLD_LUT_only_regions_CST_append'
                       if dqs_hold_lut_only else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_DQS_HOLD_regions_CST_append'
                       if dqs_hold_regions else
                       'hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_capture_region_CST_append'),
        parent_physical_identity=previous['identity'], parent_physical_directory=str(source),
        parent_physical_manifest_sha256=verified_evidence['physical_inputs.json'],
        parent_physical_evidence_sha256=expected_parent_evidence_sha256,
        parent_physical_manifest_copy=parent_manifest_copy,
        parent_physical_evidence_copy=parent_evidence_copy,
        parent_physical_evidence_verified_sha256=verified_evidence,
        synthesis_parent_identity=audit['identity'],
        synthesis_source_identity={key: evidence[key] for key in ('source_commit', 'profile_revision', 'profile_identity')},
        current_working_tree_RTL_used=False, new_synthesis_run=False, EDA_started=False,
        preparer_sha256=sha(Path(__file__)), parent_input_sha256=dict(inputs),
        automatic_hold_repair=True,
        full_timing_gates_required=True,
        parent_failed_physical_status=evidence['status'],
        input_sha256={path.name: sha(path) for path in output.iterdir() if path.is_file()},
        physical_gates_passed=False, timing_closed=False, deployment_allowed=False, release_ready=False,
        hardware_tested=False, board_programming_authorized=False, bitstream_sha256=None,
        sram_programmed=False, flash_programmed=False)
    result['reference_monitor_source_regions_adaptation' if reference_monitor_source_regions else
           'ddr_launch_capture_far_regions_adaptation' if launch_capture_far_regions else
           'ddr_launch_capture_regions_adaptation' if launch_capture_regions else
           'ddr_dqs_hold_regions_adaptation' if dqs_regions else 'ddr_capture_region_adaptation'] = placement
    (output / 'physical_inputs.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def prepare(source, output, user_code, acknowledge_electrical_risk=False, ulpi_bypass_lvcmos33=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not acknowledge_electrical_risk:
        raise ValueError('explicit acknowledgement of unresolved electrical risk is required')
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code):
        raise ValueError('a new eight-hex UserCode is required')
    if output.exists():
        raise FileExistsError('physical output already exists: ' + str(output))
    if source in output.parents:
        raise ValueError('physical output must not modify the parent candidate')
    audit = audit_synthesis(source)
    if audit['top_module'] != TOP or not isinstance(audit['electrical_blocked'], bool):
        raise ValueError('unexpected native synthesis/electrical identity')
    manifest = source / 'integration_inputs.json'
    if sha(manifest) != audit['integration_inputs_sha256']:
        raise ValueError('parent manifest changed after synthesis audit')
    metadata = json.loads(manifest.read_text())
    stage = source / 'workstation/Prj1'
    inputs = {
        BASE + '.vg': (stage / f'impl/gwsynthesis/{BASE}.vg', audit['netlist_sha256']),
        'physical.cst': (stage / 'constraints/custom_138k.cst',
                         metadata['staged_input_sha256']['constraints/custom_138k.cst']),
        'physical.sdc': (stage / 'constraints/custom_138k.sdc',
                         metadata['staged_input_sha256']['constraints/custom_138k.sdc']),
        'parent_integration_inputs.json': (manifest, audit['integration_inputs_sha256']),
    }
    if audit.get('demo_role') in ('M', 'W'):
        if (audit.get('validation_stage') != 'demo_full_profile_synthesis_only' or
                audit.get('visible_sdc_selector_audit', {}).get('all_visible_selector_members_resolved') is not True or
                audit.get('constraint_retirement_audit', {}).get('every_retired_selector_proven_absent') is not True or
                audit.get('features', {}).get('role_retirement_verified') is not True):
            raise ValueError('DEMO retained/retired source and selector gates are incomplete')
        selected = metadata.get('workstation_profile', {})
        if selected.get('candidate_identity') != audit.get('candidate_identity'):
            raise ValueError('DEMO physical parent candidate identity changed')
        inputs['parent_workstation_profile.json'] = (
            source / selected['artifact'], selected['artifact_sha256'])
    inputs.update(paired_profile_input(source, metadata, audit))
    if ulpi_bypass_lvcmos33:
        pinout_identity = metadata.get('pinout_sha256')
        if not isinstance(pinout_identity, str) or not re.fullmatch(r'[0-9a-f]{64}', pinout_identity):
            raise ValueError('ULPI IO standard requires an audited pinout identity')
        inputs['parent_pinout.json'] = (source / 'pinout/pinout.json', pinout_identity)
    for name, (path, expected) in inputs.items():
        if sha(path) != expected:
            raise ValueError('audited physical input changed: ' + name)
    adapted_cst = None
    ulpi_adaptation = None
    if ulpi_bypass_lvcmos33:
        plan = json.loads(inputs['parent_pinout.json'][0].read_bytes())
        adapted_cst, ulpi_adaptation = ulpi_bypass_constraints(inputs['physical.cst'][0].read_bytes(), plan)
    output.mkdir(parents=True)
    for name, (path, expected) in inputs.items():
        checked_copy(path, output / name, expected)
    if adapted_cst is not None:
        (output / 'physical.cst').write_bytes(adapted_cst)
    (output / 'parent_synthesis_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    script = implementation_script(user_code)
    (output / 'run.tcl').write_text(script)
    for name, (path, expected) in inputs.items():
        copied_expected = ulpi_adaptation['after_sha256'] if name == 'physical.cst' and ulpi_adaptation else expected
        if sha(path) != expected or sha(output / name) != copied_expected:
            raise ValueError('physical input changed after preparation: ' + name)
    result = dict(
        schema=1, identity='custom138k-native-physical-' + user_code.upper(),
        prepared_at=datetime.now().astimezone().isoformat(),
        validation_stage='offline_physical_experiment_prepared',
        source_policy=('audited_native_synthesis_netlist_with_explicit_ULPI_IO_type_only_and_unchanged_SDC'
                       if ulpi_adaptation else 'audited_native_synthesis_netlist_with_unchanged_CST_and_SDC'),
        parent_candidate=str(source), parent_identity=audit['identity'],
        **({'parent_candidate_identity': audit['candidate_identity'], 'demo_role': audit['demo_role']}
           if audit.get('demo_role') in ('M', 'W') else {}),
        **({'parent_candidate_identity': audit['candidate_identity'], 'paired_role': audit['paired_role']}
           if audit.get('paired_role') is not None else {}),
        preparer_sha256=sha(Path(__file__)), user_code='0x' + user_code.upper(),
        top_module=TOP, device=DEVICE, electrical_blocked=audit['electrical_blocked'],
        electrical_risk_explicitly_acknowledged=True,
        acknowledgement_scope='offline physical experiment only; not board programming authorization or electrical acceptance',
        board_programming_authorized=False, ulpi_io_type_adaptation=ulpi_adaptation,
        parent_input_sha256={name: expected for name, (_, expected) in inputs.items()},
        clocks_or_exceptions_relaxed=False, features_removed=False,
        place_option=2, route_option=0, replicate_resources=False,
        input_sha256={path.name: sha(path) for path in output.iterdir() if path.is_file()},
        timing_closed=False, physical_gates_passed=False, hardware_tested=False,
        deployment_allowed=False, release_ready=False, bitstream_sha256=None,
        sram_programmed=False, flash_programmed=False,
        remaining_gaps=metadata['remaining_gaps'],
    )
    (output / 'physical_inputs.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--user-code', required=True)
    parser.add_argument('--acknowledge-electrical-risk', action='store_true')
    parser.add_argument('--ulpi-bypass-lvcmos33', action='store_true',
                        help='Add only reviewed bypass ULPI IO standards; no electrical or external timing acceptance')
    parser.add_argument('--ddr-capture-region-parent-evidence', '--ddr-floorplan-parent-evidence', type=Path,
                        help='Derive from the hash-bound original physical evidence, keeping the previous VG and SDC')
    dqs_mode = parser.add_mutually_exclusive_group()
    dqs_mode.add_argument('--ddr-dqs-hold-regions', action='store_true',
                        help='Append only the reviewed four-lane FF/LUT placement regions to a capture-region parent')
    dqs_mode.add_argument('--ddr-dqs-hold-lut-only', action='store_true',
                          help='Constrain only the four reviewed HOLD LUTs; leave config registers free')
    dqs_mode.add_argument('--ddr-launch-capture-regions', action='store_true',
                          help='Place both observed initialization ends; requires unchanged 3.500ns minimum')
    dqs_mode.add_argument('--ddr-launch-capture-far-regions', action='store_true',
                          help='Use the explicit opposite-corner initialization regions; keeps 3.500ns minimum')
    dqs_mode.add_argument('--reference-monitor-source-regions', action='store_true',
                          help='Place only the fixed 128 FFs in the two observed reference source banks')
    parser.add_argument('--expected-parent-evidence-sha256',
                        help='Required explicit identity when deriving the DDR capture-region experiment')
    parser.add_argument('--reference-cst', type=Path, help='Explicit offline historical pin/floorplan reference')
    parser.add_argument('--reference-sha256')
    parser.add_argument('--task3-pin-collections', action='store_true',
                        help='Express the same reviewed paired M DIRECT r3 pin sets for Gowin P&R')
    parser.add_argument('--preboard-releases',action='store_true',
                        help='Prove exact paired preboard synchronizers and held data, retaining payload hold checks')
    parser.add_argument('--primary-clk50',action='store_true',
                        help='Place the actual primary clock input on its reviewed clock resource')
    parser.add_argument('--preboard-ddr-reference',type=Path,
                        help='Prior routed DDR evidence with identical encrypted inputs; tighten init hold and reset recovery')
    parser.add_argument('--w-delay-locality',action='store_true',
                        help='Reproduce the diagnosed W DMA/FIFO logic regions; retain hard RAM placement and all timing')
    parser.add_argument('--exclude-reference-port', action='append', default=[])
    parser.add_argument('--place-option', type=int, choices=range(5), default=2)
    parser.add_argument('--route-option', type=int, choices=(0, 1), default=0)
    parser.add_argument('--replicate-resources', action='store_true',
                        help='Explicit reference experiment: let the physical tool replicate high-fanout logic')
    args = parser.parse_args()
    reference_options = bool(args.reference_sha256 or args.exclude_reference_port or args.task3_pin_collections or
                             args.preboard_releases or args.primary_clk50 or args.preboard_ddr_reference or args.w_delay_locality or
                             args.place_option != 2 or args.route_option != 0 or args.replicate_resources)
    derivation_options = bool(args.ddr_capture_region_parent_evidence or args.ddr_dqs_hold_regions or
        args.ddr_dqs_hold_lut_only or args.ddr_launch_capture_regions or
        args.ddr_launch_capture_far_regions or args.reference_monitor_source_regions or
        args.expected_parent_evidence_sha256)
    if args.reference_cst:
        if args.ulpi_bypass_lvcmos33 or derivation_options or not args.reference_sha256:
            parser.error('reference mode requires its hash and cannot mix board/derivation adaptations')
        result = prepare_reference(args.source, args.output, args.user_code, args.reference_cst,
                                   args.reference_sha256, args.exclude_reference_port,
                                   args.place_option, args.route_option, args.task3_pin_collections,
                                   args.preboard_releases,args.primary_clk50,args.preboard_ddr_reference,args.w_delay_locality,
                                   args.replicate_resources)
    elif reference_options:
        parser.error('reference constraint options require --reference-cst')
    elif args.ddr_capture_region_parent_evidence:

        if args.ulpi_bypass_lvcmos33:
            parser.error('the derived parent already fixes ULPI; a second adaptation is not allowed')
        result = derive_ddr_capture_region(args.source, args.output, args.user_code,
                                          args.ddr_capture_region_parent_evidence,
                                          args.expected_parent_evidence_sha256,
                                          args.acknowledge_electrical_risk,
                                          dqs_hold_regions=args.ddr_dqs_hold_regions,
                                          dqs_hold_lut_only=args.ddr_dqs_hold_lut_only,
                                          launch_capture_regions=args.ddr_launch_capture_regions,
                                          launch_capture_far_regions=args.ddr_launch_capture_far_regions,
                                          reference_monitor_source_regions=args.reference_monitor_source_regions)
    else:
        if (args.ddr_dqs_hold_regions or args.ddr_dqs_hold_lut_only or
                args.ddr_launch_capture_regions or args.ddr_launch_capture_far_regions or
                args.reference_monitor_source_regions):
            parser.error('DQS HOLD placement modes require an explicit floorplan parent evidence')
        if args.expected_parent_evidence_sha256:
            parser.error('--expected-parent-evidence-sha256 requires the explicit DDR derivation')
        result = prepare(args.source, args.output, args.user_code, args.acknowledge_electrical_risk,
                         args.ulpi_bypass_lvcmos33)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
