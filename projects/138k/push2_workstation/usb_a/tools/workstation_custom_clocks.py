"""Explicit native clock declarations and source-netlist topology checks."""

from fractions import Fraction
from pathlib import Path
import hashlib
import json
import re

from tools.stage_usb_firmware import sha
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_baselines import load_baseline
from tools.audit_clk50_timing import TimingTables
from tools.workstation_ae350_rtc import CLOCK_ENTRY as RTC_CLOCK_ENTRY, SDC as RTC_SDC, audit_synthesis_netlist as audit_rtc


PLAN_SOURCE = 'boards/custom_138k/clocks.json'
OPAQUE_DDR = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT'
EXPECTED_HZ = dict(clk_50m=50000000, ulpi_60m=60000000, audio_76m8=76800000, usb_48m=48000000,
                   ddr_mem400=400000000, ddr_ui100=100000000, video_ref49=49500000,
                   video_serial742=742500000, video_pixel148=148500000, cpu_ram50=50000000,
                   cpu_core100=100000000, dac_ref12m288=12288000,
                   lcd_pixel31m5=31500000)
DDR_CLOCK_SOURCES = ('src/memory/ddr3_platform.v', 'src/memory/ddr_recovery_guard.v',
    'vendor/gowin_ddr3/ddr3_memory_interface.v', 'vendor/gowin_ddr3/ddr3_pll.v',
    'vendor/gowin_ddr3/ddr3_pll_init.v', 'vendor/gowin_ddr3/ddr3_pll_primitive.v')
PARENT_SDC_SHA256 = 'cf7c8613444693570a531d6edf7c93dbb7f415b0b3ef5cfc026b6b74a2bf4f43'


def shared_cdc_bundle(stage):
    source = Path(stage) / 'constraints/tang_mega_138k.sdc'
    if sha(source) != PARENT_SDC_SHA256:
        raise ValueError('native shared CDC parent SDC changed')
    lines, omitted, adapted = [], [], []
    for line in source.read_text().splitlines():
        if not line.startswith(('set_false_path ', 'set_max_delay ')):
            if line.startswith('set_'):
                raise ValueError('native shared CDC parent command unsupported')
            continue
        if '[get_ports ' in line:
            omitted.append(dict(constraint=line, reason='retired Dock ports'))
            continue
        if 'u_managed/u_audio/u_midi_cdc/held_data*' in line:
            omitted.append(dict(constraint=line, reason='removed Dock MIDI input has constant payload'))
            continue
        if 'u_push/events/fifo/unbuffered/produce_' in line or 'u_push/events/fifo/unbuffered/consume_' in line:
            omitted.append(dict(constraint=line, reason='native event FIFO has separately audited pin-specific bounds'))
            continue
        replacement = line.replace('u_push/', 'u_native_usb/input_owner/').replace(
            'u_video/u_dvi/*/tmds_serdes_inst0/RESET',
            'u_video/u_dvi/data_lanes*.serializer/serializer/RESET u_video/u_dvi/clock_lane/serializer/RESET').replace(
            'u_managed/u_audio/u_midi_cdc/req_meta*/D u_managed/u_audio/u_midi_cdc/ack_meta*/D ', '')
        if replacement != line:
            adapted.append(dict(original=line, selected=replacement))
        lines.append(replacement)
    if len(lines) != 157 or len(omitted) != 9 or len(adapted) != 10:
        raise ValueError('native shared CDC adaptation inventory changed')
    return dict(source='constraints/tang_mega_138k.sdc', source_sha256=PARENT_SDC_SHA256,
                sdc='\n'.join(lines) + '\n', omitted=omitted, adapted=adapted)


def audit_shared_cdc(stage, netlist_text):
    bundle = shared_cdc_bundle(stage)
    netlist = SynthesisNetlist(netlist_text, 'workstation_custom_138k_top')
    registers = [name for name, cell in netlist.cells.items() if cell['kind'].startswith('DFF')]
    pins = [name + '/' + port for name, cell in netlist.cells.items() for port in cell['ports']]
    resolved, deferred = {}, []
    for kind, selectors in re.findall(r'\[(get_regs|get_pins) \{([^}]+)\}\]', bundle['sdc']):
        key = kind + ' {' + selectors + '}'
        if key in resolved or key in deferred:
            continue
        if all(selector.startswith('u_memory/u_ddr3/gw3_top/') for selector in selectors.split()):
            deferred.append(key)
            continue
        matches = set()
        for selector in selectors.split():
            pattern = re.compile('^' + re.escape(selector).replace(r'\*', '.*').replace(r'\?', '.') + '$')
            selected = {name for name in (registers if kind == 'get_regs' else pins) if pattern.fullmatch(name)}
            if not selected and kind == 'get_pins' and selector.endswith('/D'):
                raise ValueError('native shared CDC selector is empty: ' + selector)
            matches.update(selected)
        if not matches:
            raise ValueError('native shared CDC selector is empty: ' + key)
        resolved[key] = len(matches)
    return dict(parent_sdc_sha256=bundle['source_sha256'], constraints=157,
                resolved_selectors=resolved, deferred_opaque_ddr_selectors=deferred,
                physical_timing_verified=False)


def clock_bundle(root, hdmi_mode='1080p60', local_panel_enabled=True, hdmi_enabled=True):
    if type(local_panel_enabled) is not bool:
        raise ValueError('native local-panel selection must be boolean')
    if type(hdmi_enabled) is not bool:
        raise ValueError('native HDMI selection must be boolean')
    source = Path(root) / PLAN_SOURCE
    plan = json.loads(source.read_text())
    if plan.get('schema') != 1 or plan.get('identity') != 'custom138k-native-clocks-20261031-v5':
        raise ValueError('native clock plan identity changed')
    if plan.get('fabric_generated') != [RTC_CLOCK_ENTRY]:
        raise ValueError('native independent RTC timing-bound inventory changed')
    entries = [*plan['primary'], *plan['generated']]
    if (len(entries) != len(EXPECTED_HZ) or {entry['name']: entry['frequency_hz'] for entry in entries} != EXPECTED_HZ or
            len({entry.get('pin', entry.get('port')) for entry in entries}) != len(entries)):
        raise ValueError('native clock frequency or target inventory changed')
    if {entry['name']: entry['port'] for entry in plan['primary']} != dict(
            clk_50m='clk_50m', ulpi_60m='usb2_ulpi_clk', dac_ref12m288='clk_12m288'):
        raise ValueError('native primary clock ports changed')
    if hdmi_mode not in ('1080p60', '720p30', '720p60'):
        raise ValueError('unsupported native HDMI clock mode')
    # Validate the complete reviewed plan before selecting out an absent owner.
    # The original plan and every surviving clock retain their exact frequency.
    if not local_panel_enabled:
        plan['generated'] = [entry for entry in plan['generated'] if entry['name'] != 'lcd_pixel31m5']
    if not hdmi_enabled:
        plan['generated'] = [entry for entry in plan['generated'] if not entry['name'].startswith('video_')]
    pixel_clock_name = 'video_pixel148'
    if hdmi_mode in ('720p30', '720p60'):
        renames = dict(video_serial742='video_serial371', video_pixel148='video_pixel74')
        for entry in plan['generated']:
            if entry['name'] in renames:
                entry['frequency_hz'] //= 2
                entry['name'] = renames[entry['name']]
            entry['source'] = renames.get(entry['source'], entry['source'])
        pixel_clock_name = 'video_pixel74'
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
            if entry['name'] != pixel_clock_name or entry['edges'] != [1, 7, 11] or ratio != Fraction(1, 5):
                raise ValueError('native pixel /5 60/40 waveform changed')
            transform = '-edges {1 7 11}'
        else:
            if entry['name'] == pixel_clock_name:
                raise ValueError('native pixel clock lost explicit 60/40 waveform')
            transform = f'-multiply_by {ratio.numerator} -divide_by {ratio.denominator}'
        if 'opaque_ip_prefix' in entry and (entry['pin'] != OPAQUE_DDR or entry['opaque_ip_prefix'] != 'u_memory/u_ddr3/gw3_top'):
            raise ValueError('native unexpected opaque clock target')
        query = f"[get_pins {{{entry['pin']}}}]"
        lines.append(f"create_generated_clock -name {entry['name']} -source {parent['query']} -master_clock {entry['source']} {transform} {query}")
        clocks[entry['name']] = dict(query=query, **entry)
    lines.append(RTC_SDC.rstrip('\n'))
    return dict(source=PLAN_SOURCE, source_sha256=sha(source), plan=plan, sdc='\n'.join(lines) + '\n')


def audit_clocks(root, stage, netlist_text, extra_sdc='', hdmi_mode='1080p60', local_panel_enabled=True, hdmi_enabled=True):
    bundle = clock_bundle(root, hdmi_mode, local_panel_enabled, hdmi_enabled)
    if not local_panel_enabled and ('u_lcd/' in extra_sdc or 'lcd_pixel31m5' in extra_sdc):
        raise ValueError('disabled native local-panel constraint remains in SDC')
    if (Path(stage) / 'constraints/custom_138k.sdc').read_text() != bundle['sdc'] + extra_sdc:
        raise ValueError('native staged SDC differs from the explicit clock plan')
    netlist = SynthesisNetlist(netlist_text, 'workstation_custom_138k_top')
    cells, canonical = netlist.cells, netlist.canonical
    if not hdmi_enabled and ('u_video/' in extra_sdc or any('video_' in line for line in extra_sdc.splitlines())):
        raise ValueError('disabled native HDMI constraint remains in SDC')
    if not hdmi_enabled and any(name == 'u_video' or name.startswith('u_video/')
                                for name in (*netlist.frames, *cells)):
        raise ValueError('disabled native HDMI hierarchy remains in synthesis')
    if not local_panel_enabled and any(name == 'u_lcd' or name.startswith('u_lcd/')
                                       for name in (*netlist.frames, *cells)):
        raise ValueError('disabled native local-panel hierarchy remains in synthesis')

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
            observer_cells = [name for name, cell in cells.items() if cell['kind'].startswith('DFF')
                              and re.fullmatch(r'u_memory/ui_reset_sync_\d+_s\d+', name)]
            observers = {int(re.search(r'ui_reset_sync_(\d+)', name)[1]): name for name in observer_cells}
            if len(observer_cells) != 3 or set(observers) != {0, 1, 2}:
                raise ValueError('native DDR UI clock observers changed')
            observed = {netlist.pin(name, 'CLK') for name in observers.values()}
            if len(observed) != 1 or parent['net'] in observed:
                raise ValueError('native DDR UI clock is not the distinct wrapper output')
            output_net = observed.pop()
            wrapper = entry['opaque_ip_prefix'].rpartition('/')[0]
            frame = netlist.frames[wrapper]
            outputs = [port for port in frame['ports'] if netlist.directions[frame['kind']].get(port) == 'output'
                       and netlist.pin(wrapper, port) == output_net]
            opaque_ports = [port for port in opaque['ports'] if netlist.pin(entry['opaque_ip_prefix'], port) == output_net]
            if len(outputs) != 1 or len(opaque_ports) != 1:
                raise ValueError('native DDR UI net does not resolve through the opaque wrapper output')
            deferred.append(entry['pin'])
            clocks[entry['name']] = dict(net=output_net, frequency_hz=entry['frequency_hz'], verified=False,
                source_boundary_verified=True, wrapper_output_port=outputs[0], opaque_port=opaque_ports[0],
                clock_observer_registers=observers)
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
            if not 19000000 <= parent['frequency_hz'] / int(parameters['IDIV_SEL']) <= 81250000:
                raise ValueError('native PLL PFD frequency outside the GW5AST physical range')
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
    rtc = audit_rtc(netlist_text)
    clocks[RTC_CLOCK_ENTRY['name']] = dict(**RTC_CLOCK_ENTRY, connectivity=rtc, verified=True)
    return dict(plan_source=bundle['source'], plan_sha256=bundle['source_sha256'], clocks=clocks,
                deferred_opaque_ip_targets=deferred, source_netlist_verified=not deferred,
                routed_timing_verified=False, constraints_complete=False)


def ddr_probe_sdc(root):
    lines = [line for line in clock_bundle(root)['sdc'].splitlines() if any(
        '-name ' + name + ' ' in line for name in ('clk_50m', 'ddr_mem400', 'ddr_ui100'))]
    if len(lines) != 3:
        raise ValueError('isolated DDR clock declarations changed')
    for kind in ('setup', 'hold'):
        lines.append(f'report_timing -{kind} -from_clock [get_clocks {{ddr_ui100}}] '
                     '-to_clock [get_clocks {ddr_ui100}] -max_paths 100')
        lines.append(f'report_timing -{kind} -from [get_regs {{ui_counter*}}] '
                     '-to [get_regs {ui_counter*}] -max_paths 100')
    return '\n'.join(lines) + '\n'


def audit_implemented_ddr_clock(root, stage, netlist_text=None):
    root, stage = Path(root), Path(stage)
    if (stage / 'probe.sdc').read_text() != ddr_probe_sdc(root):
        raise ValueError('isolated DDR SDC differs from the native clock plan')
    baseline = load_baseline(root, 'resource_rework_route0')
    for relative in DDR_CLOCK_SOURCES:
        if (stage / relative).read_bytes() != baseline.read_bytes(relative):
            raise ValueError('isolated DDR input differs from selected locked source: ' + relative)
    text = netlist_text if netlist_text is not None else (stage / 'impl/pnr/ddr_clock_probe.vo').read_text()
    netlist = SynthesisNetlist(text, 'workstation_ddr_clock_probe')
    divider_path, _, port = OPAQUE_DDR.rpartition('/')
    divider = netlist.cells.get(divider_path)
    if not divider or divider['kind'] != 'CLKDIV' or port not in divider['ports']:
        raise ValueError('implemented DDR UI target not resolved')
    if divider['parameters'].get('DIV_MODE') != '"4"':
        raise ValueError('implemented DDR UI divider changed')
    pll_path = 'u_memory/u_pll/u_pll_0/PLL_inst'
    pll = netlist.cells.get(pll_path)
    if not pll or pll['kind'] != 'PLL' or netlist.pin(pll_path, 'CLKIN') != 'clk_50m':
        raise ValueError('implemented DDR memory PLL input changed')
    parameters = pll['parameters']
    if (parameters.get('IDIV_SEL') != '1' or parameters.get('FBDIV_SEL') != '1' or
            parameters.get('FCLKIN') != '"50"' or parameters.get('CLKFB_SEL') != '"INTERNAL"' or
            parameters.get('CLKOUT2_EN') != '"TRUE"' or any(parameters.get(name) != '"FALSE"' for name in (
                'DYN_FBDIV_SEL', 'DYN_IDIV_SEL', 'DYN_MDIV_SEL', 'DYN_ODIV2_SEL',
                'DYN_DPA_EN', 'DYN_PE2_SEL', 'DYN_DT2_SEL')) or
            any(parameters.get('CLKOUT2_' + suffix) != '0' for suffix in ('PE_COARSE', 'PE_FINE', 'DT_STEP'))):
        raise ValueError('implemented DDR memory PLL mode changed')
    multiplier = Fraction(int(parameters['MDIV_SEL'])) + Fraction(int(parameters.get('MDIV_FRAC_SEL', '0')), 8)
    divisor = Fraction(int(parameters['ODIV2_SEL'])) + Fraction(int(parameters.get('ODIV2_FRAC_SEL', '0')), 8)
    if 50000000 * multiplier / divisor != EXPECTED_HZ['ddr_mem400']:
        raise ValueError('implemented DDR memory PLL frequency changed')
    if netlist.pin(divider_path, 'HCLKIN') != netlist.pin(pll_path, 'CLKOUT2'):
        raise ValueError('implemented DDR divider source wiring changed')
    consumers = {name: cell for name, cell in netlist.cells.items() if re.fullmatch(r'ui_counter_\d+_s\d+', name)
                 and cell['kind'].startswith('DFF')}
    if len(consumers) != 8 or any(netlist.pin(name, 'CLK') != netlist.pin(divider_path, port) for name in consumers):
        raise ValueError('implemented DDR UI consumer clock changed')
    report = stage / 'impl/pnr/ddr_clock_probe_tr_content.html'
    parser = TimingTables()
    parser.feed(report.read_text())
    summary, paths = {}, dict(setup=[], hold=[])
    for command, rows in parser.tables:
        if rows and 'Period' in rows[0]:
            summary.update({row[1]: row for row in rows[1:] if len(row) >= 9})
        if not rows or rows[0][0] != 'Path Number' or '-from [get_regs {ui_counter*}]' not in command:
            continue
        kind = next((kind for kind in paths if '-' + kind in command), None)
        if kind:
            paths[kind].extend(row for row in rows[1:] if len(row) == 9 and row[2].startswith('ui_counter_')
                               and row[3].startswith('ui_counter_'))
    for name, period, source, master, target in (
            ('ddr_mem400', '2.500', 'clk_50m', 'clk_50m', pll_path + '/CLKOUT2'),
            ('ddr_ui100', '10.000', pll_path + '/CLKOUT2', 'ddr_mem400', OPAQUE_DDR)):
        row = summary.get(name, [])
        if not row or row[3] != period or row[-3:] != [source, master, target]:
            raise ValueError('implemented DDR clock report differs from native plan: ' + name)
    for kind, entries in paths.items():
        relation = '10.000' if kind == 'setup' else '0.000'
        if not entries or any(row[4].split(':')[0] != 'ddr_ui100' or row[5].split(':')[0] != 'ddr_ui100'
                              or row[6] != relation for row in entries):
            raise ValueError('implemented DDR UI consumer timing coverage missing: ' + kind)
    return dict(scope='isolated_selected_ddr_ip_clock_topology_and_constraint_consumption_not_native_board_timing',
                clock_plan_sha256=sha(root / PLAN_SOURCE), divider=divider_path, divide_by=4,
                memory_clock_hz=400000000, ui_clock_hz=100000000, ui_net=netlist.pin(divider_path, port),
                consumer_registers=sorted(consumers), clock_report={name:summary[name] for name in ('ddr_mem400','ddr_ui100')},
                consumer_timing=paths, routed_netlist_sha256=sha(stage / 'impl/pnr/ddr_clock_probe.vo'),
                consumer_timing_summary={kind:dict(paths=len(entries), wns_ns=min(float(row[1]) for row in entries),
                    negative_paths=sum(float(row[1]) < 0 for row in entries)) for kind, entries in paths.items()},
                analyzed_text_sha256=hashlib.sha256(text.encode()).hexdigest(), netlist_text_override=netlist_text is not None,
                timing_report_sha256=sha(report), ip_input_sha256={name:sha(stage / name) for name in DDR_CLOCK_SOURCES},
                opaque_target_resolved_in_probe=True, native_routed_timing_verified=False,
                ddr_data_path_verified=False, hardware_tested=False, deployment_allowed=False, release_ready=False)
