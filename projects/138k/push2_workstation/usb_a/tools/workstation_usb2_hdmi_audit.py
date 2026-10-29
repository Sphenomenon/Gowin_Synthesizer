"""Audit actual combined routing while retaining the D5 video and USB subtree checks."""

from pathlib import Path
import argparse
import fnmatch
import json
import os
import re
import runpy
import shutil
import subprocess
import sys

from tools import workstation_usb2_hdmi as integration
from tools import workstation_usb2_hotplug as usb
from tools.audit_clk50_timing import TimingTables
from tools.audit_workstation_timing import audit as audit_timing
from tools.stage_usb_firmware import sha
from tools.workstation_baselines import load_baseline
from tools.workstation_synthesis_netlist import SynthesisNetlist


ROOT = Path(__file__).resolve().parents[1]
SERIALIZER_ADAPTATIONS = (
    ('u_video/u_dvi/clock_phy/tmds_serdes_inst0', 'u_video/u_dvi/clock_lane/serializer'),
    ('u_video/u_dvi/gen_enc[{i}].dvi_tx_tmds_phy_inst/tmds_serdes_inst0',
     'u_video/u_dvi/data_lanes[{i}].serializer/serializer'),
    ('+ "/tmds_bufds_isnt0"', '+ "/differential"'),
    ('(ground if bit < 5 else power)', '(power if bit < 5 else ground)'),
    ("10'b1111100000 clock word", "10'b0000011111 clock word"),
    ('"word_d9_to_d0": "1111100000"', '"word_d9_to_d0": "0000011111"'),
)
FREQUENCIES = dict(clk_50m=50.0, ulpi_60m=60.0, usb_48m=48.0, audio_76m8=76.8,
                   ddr_mem400=400.0, ddr_ui100=100.0, video_ref49=49.5,
                   video_serial742=742.5, video_pixel148=148.5)
TIMING_TARGETS = {name: frequency for name, frequency in FREQUENCIES.items()
                  if name not in ('video_ref49', 'video_serial742')} | dict(tck_pad_i=20.0)


def usb_primary_bindings(netlist):
    primary_nets = dict(clk_50m='clk_50m_d', ulpi_60m='usb2_ulpi_clk_d')
    for entry in usb.clock_bundle(ROOT)['plan']['primary']:
        if entry['name'] in primary_nets and netlist.canonical('u_usb', primary_nets[entry['name']]) != entry['port']:
            raise ValueError('USB subtree primary clock is not bound to its board input: ' + entry['name'])
    return primary_nets


def video_checks(output, directory):
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    directory.mkdir(parents=True)
    scripts = directory / 'scripts'
    scripts.mkdir()
    (directory / 'vendor').symlink_to(output / 'hdmi/vendor', target_is_directory=True)
    reference = directory / 'reference/ddr3_memory_interface.vo'
    reference.parent.mkdir()
    reference.symlink_to(ROOT / 'vendor/ddr3_reference/ddr3_memory_interface.vo')
    reference.with_suffix('.v').symlink_to(output / 'hdmi/vendor/gowin_ddr3/ddr3_memory_interface.v')
    names = ('audit_ddr_reset_sequence.py', 'audit_ddr_configuration_paths.py', 'gowin_paths.py',
             'check_video_pll_init.py', 'check_serializer_startup.py')
    for name in names:
        (scripts / name).write_bytes(baseline.read_bytes('scripts/' + name))
    environment = dict(os.environ, PRJ1_DDR_REFERENCE=str(reference))
    for script, destination in (('audit_ddr_reset_sequence.py', 'ddr_reset.json'),
                                ('audit_ddr_configuration_paths.py', 'ddr_configuration.json')):
        result = subprocess.run([sys.executable, str(scripts / script), '--output', str(directory / destination)],
                                env=environment, text=True, capture_output=True, timeout=120)
        (directory / (script + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError('frozen DDR check failed: ' + script)
    pnr = output / 'impl/pnr'
    normalize = lambda text: text.replace('u_hdmi/u_display/', '').replace(r'u_hdmi\/u_display\/', '')
    netlist = normalize((pnr / (integration.BASE + '.vo')).read_text())
    sdf = normalize((pnr / (integration.BASE + '.sdf')).read_text())
    sdc = normalize((output / 'integration.sdc').read_text())
    video = runpy.run_path(str(scripts / 'check_video_pll_init.py'), run_name='USB2_HDMI_PLL_check')
    pll_errors, pll = video['inspect_video_pll_init'](sdf, netlist, directory)
    source = scripts / 'check_serializer_startup.py'
    text = source.read_text()
    for original, replacement in SERIALIZER_ADAPTATIONS:
        if text.count(original) != 1:
            raise ValueError('native serializer checker anchor changed: ' + original)
        text = text.replace(original, replacement)
    namespace = dict(__file__=str(source), __name__='USB2_HDMI_serializer_check')
    exec(compile(text, str(source) + ':native-lanes', 'exec'), namespace)
    startup_errors, startup = namespace['inspect_serializer_startup'](
        sdf, netlist, json.loads((directory / 'ddr_reset.json').read_text()), sdc)
    return dict(errors=pll_errors + startup_errors, video_pll=pll, serializer_startup=startup,
                ddr_configuration=json.loads((directory / 'ddr_configuration.json').read_text()),
                source_checker_sha256={name: sha(scripts / name) for name in names},
                serializer_adaptations=SERIALIZER_ADAPTATIONS,
                hierarchy_normalization='remove u_hdmi/u_display/ only in checker views')


def phy_probe_bindings(netlist, profile):
    if profile == 'owner':
        return {}
    reference = {'reference_heartbeat', 'clock_supervisor_state', 'clock_failure',
                 'reference_reset_released', 'reference_enabled'}
    cpu = {'destination_reset_released', 'link_destination_released', 'link_acknowledge'}
    combinational = {'raw_phy_ready', 'raw_direction', 'raw_next', 'raw_stop', 'raw_data'}
    drivers = {}
    for path, cell in netlist.cells.items():
        if cell['kind'].startswith('DFF'):
            drivers.setdefault(netlist.pin(path, 'Q'), []).append(path)
    bindings = {}
    fields = integration.PHY_FIELDS + (integration.PORT_FIELDS if profile == 'port' else ())
    for name, signal, width, low in fields:
        if name in combinational:
            continue
        clock = 'clk_50m' if name in reference else 'u_usb/usb_clk' if name in cpu else 'usb2_ulpi_clk'
        registers = []
        for bit in range(low, low + width):
            source = signal if width == 1 and low == 0 else f'{signal}[{bit}]'
            cells = drivers.get(source, [])
            if len(cells) != 1 or netlist.pin(cells[0], 'CLK') != clock:
                raise ValueError('PHY observer register or clock binding changed: ' + source)
            registers.extend(cells)
        bindings[name] = dict(clock=clock, registers=registers)
    return bindings


def audit(output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    if manifest.get('source_policy') != 'byte_identical_accepted_D5_display_plus_native_USB2_hotplug':
        raise ValueError('not an explicit D5/USB2 integration')
    for name, expected in manifest['input_sha256'].items():
        path = output / name
        if not path.resolve().is_relative_to(output) or sha(path) != expected:
            raise ValueError('integration input changed: ' + name)
    if integration.constraints(output) != ((output / 'integration.cst').read_text(),
                                           (output / 'integration.sdc').read_text()):
        raise ValueError('integration constraints differ from the checked composition')
    if integration.gao_configuration(manifest['user_code'][2:], manifest.get('observer_profile', 'owner'),
                                     manifest.get('observer_trigger', 'reset')) != (output / 'integration.gao').read_text():
        raise ValueError('integration observer layout changed')
    verification = output / 'verification'
    verification.mkdir(exist_ok=False)
    synthesis = output / f'impl/gwsynthesis/{integration.BASE}.vg'
    netlist = SynthesisNetlist(synthesis.read_text(), integration.TOP)
    phy_bindings = phy_probe_bindings(netlist, manifest.get('observer_profile', 'owner'))
    for bit in range(96, 128):
        target = netlist.canonical('u_usb/u_native_usb/input_owner/led', f'telemetry[{bit}]')
        if target != f'u_usb/telemetry_0[{bit}]':
            raise ValueError('GAO commands synthesis alias changed')
    reset_cells = [name for name in netlist.cells if name.startswith('u_usb/usb_release_3_s')]
    if len(reset_cells) != 1 or netlist.pin(reset_cells[0], 'Q') != 'u_usb/usb_release[3]':
        raise ValueError('GAO reset synthesis alias changed')
    routed = SynthesisNetlist((output / f'impl/pnr/{integration.BASE}.vo').read_text(), integration.TOP)
    pins = [name + '/' + pin for name, cell in routed.cells.items() for pin in cell['ports']]
    registers = [name for name, cell in routed.cells.items() if cell['kind'].startswith('DFF')]
    sdc = (output / 'integration.sdc').read_text()
    selectors = {}
    for kind, query in set(re.findall(r'\[get_(pins|regs)\s+\{([^}]+)\}\]', sdc)):
        for selector in query.split():
            count = sum(fnmatch.fnmatchcase(name, selector) for name in (pins if kind == 'pins' else registers))
            if not count:
                raise ValueError('unresolved combined clock/CDC selector: ' + selector)
            selectors[kind + ' ' + selector] = count
    report = output / f'impl/pnr/{integration.BASE}_tr_content.html'
    tables = TimingTables()
    tables.feed(report.read_text())
    clocks = {}
    for _, rows in tables.tables:
        if rows and 'Period' in rows[0] and 'Clock Name' in rows[0]:
            clocks.update({row[1]: dict(period_ns=float(row[3]), object=row[-1]) for row in rows[1:]})
    required = {name: 1000 / frequency for name, frequency in FREQUENCIES.items()} | dict(tck_pad_i=50.0)
    if (clocks.keys() != required.keys() or
            any(abs(clocks[name]['period_ns'] - period) > .001 for name, period in required.items()) or
            clocks['tck_pad_i']['object'] != 'tck_ibuf/I'):
        raise ValueError('combined implemented clock inventory or frequency changed')
    subtree = verification / 'usb_subtree'
    subtree.mkdir()
    for name in ('hotplug_inputs.json', *json.loads((output / 'usb/hotplug_inputs.json').read_text())['staged_input_sha256']):
        destination = subtree / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output / 'usb' / name, destination)
    for source, name in ((synthesis, 'impl/gwsynthesis/usb2_hotplug.vg'),
                         (report, 'impl/pnr/usb2_hotplug_tr_content.html'),
                         (output / 'impl/pnr/ao_0.fs', 'impl/pnr/usb2_hotplug.fs')):
        destination = subtree / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source)
    primary_nets = usb_primary_bindings(netlist)
    native = usb.audit(ROOT, subtree, primary_nets=primary_nets)
    video = video_checks(output, verification / 'video')
    timing = audit_timing(output, report_path=report, targets=TIMING_TARGETS)
    result = dict(identity=manifest['identity'], structural_checks_passed=not video['errors'],
                  video=video, usb_subtree=native, usb_primary_bindings=primary_nets,
                  phy_observer_bindings=phy_bindings,
                  timing=timing, implemented_clocks=clocks,
                  resolved_selectors=selectors, bitstream_sha256=sha(output / 'impl/pnr/ao_0.fs'),
                  synthesis_sha256=sha(synthesis), checker_sha256=sha(Path(__file__)),
                  input_manifest_sha256=sha(output / 'inputs.json'), hardware_tested=False,
                  audit_scope='actual combined clocks/selectors/STA; original USB module as structural subtree root')
    (output / 'integration_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    result = audit(arguments.output)
    print(json.dumps(dict(identity=result['identity'], structural_checks_passed=result['structural_checks_passed'],
                          timing_closed=result['timing']['timing_closed'],
                          worst_ns=result['timing']['global_worst_ns'], bitstream_sha256=result['bitstream_sha256']), indent=2))
    raise SystemExit(0 if result['structural_checks_passed'] else 1)
