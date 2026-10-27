"""Reuse locked DDR/video checks for the isolated native display hierarchy."""

from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.audit_clk50_timing import TimingTables
from tools.audit_workstation_timing import audit as audit_timing


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(physical):
    manifest = json.loads((physical / 'inputs.json').read_text())
    for name, expected in manifest['input_sha256'].items():
        if sha(physical / name) != expected:
            raise ValueError('isolated input drift: ' + name)
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    if baseline.evidence() != manifest['source_baseline']:
        raise ValueError('isolated baseline identity changed')
    view = physical / 'verification/routed_audit'
    (view / 'scripts').mkdir(parents=True, exist_ok=False)
    (view / 'vendor').symlink_to(physical / 'vendor', target_is_directory=True)
    (view / 'reference').mkdir()
    reference = view / 'reference/ddr3_memory_interface.vo'
    reference.symlink_to(ROOT / 'vendor/ddr3_reference/ddr3_memory_interface.vo')
    reference.with_suffix('.v').symlink_to(physical / 'vendor/gowin_ddr3/ddr3_memory_interface.v')
    names = ('audit_ddr_reset_sequence.py', 'audit_ddr_configuration_paths.py', 'gowin_paths.py',
             'check_video_pll_init.py', 'check_serializer_startup.py')
    for name in names:
        (view / 'scripts' / name).write_bytes(baseline.read_bytes('scripts/' + name))
    environment = dict(os.environ, PRJ1_DDR_REFERENCE=str(reference))
    for script, output in (('audit_ddr_reset_sequence.py', 'ddr_reset.json'),
                           ('audit_ddr_configuration_paths.py', 'ddr_configuration.json')):
        result = subprocess.run([sys.executable, str(view / 'scripts' / script), '--output', str(view / output)],
                                env=environment, text=True, capture_output=True, timeout=120)
        (view / (script + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    pnr = physical / 'impl/pnr/hdmi_isolation'
    original_vo = pnr.with_suffix('.vo').read_text()
    original_sdf = pnr.with_suffix('.sdf').read_text()
    original_sdc = (physical / 'display.sdc').read_text()
    netlist, sdf, sdc = (text.replace('u_display/', '').replace('u_display\\/', '')
                         for text in (original_vo, original_sdf, original_sdc))
    video = runpy.run_path(str(view / 'scripts/check_video_pll_init.py'), run_name='isolated_video_check')
    pll_errors, pll = video['inspect_video_pll_init'](sdf, netlist, physical)
    source = view / 'scripts/check_serializer_startup.py'
    text = source.read_text()
    adaptations = (
        ('u_video/u_dvi/clock_phy/tmds_serdes_inst0', 'u_video/u_dvi/clock_lane/serializer'),
        ('u_video/u_dvi/gen_enc[{i}].dvi_tx_tmds_phy_inst/tmds_serdes_inst0', 'u_video/u_dvi/data_lanes[{i}].serializer/serializer'),
        ('+ "/tmds_bufds_isnt0"', '+ "/differential"'),
        ('(ground if bit < 5 else power)', '(power if bit < 5 else ground)'),
        ("10'b1111100000 clock word", "10'b0000011111 clock word"),
        ('"word_d9_to_d0": "1111100000"', '"word_d9_to_d0": "0000011111"'),
    )
    for original, replacement in adaptations:
        if text.count(original) != 1:
            raise ValueError('native serializer checker anchor changed: ' + original)
        text = text.replace(original, replacement)
    namespace = dict(__file__=str(source), __name__='isolated_serializer_check')
    exec(compile(text, str(source) + ':native-lanes', 'exec'), namespace)
    startup_errors, startup = namespace['inspect_serializer_startup'](
        sdf, netlist, json.loads((view / 'ddr_reset.json').read_text()), sdc)
    design = SynthesisNetlist(original_vo, manifest['top_module'])
    registers = [name for name, cell in design.cells.items() if cell['kind'].startswith('DFF')]
    pins = [name + '/' + port for name, cell in design.cells.items() for port in cell['ports']]
    selectors = {}
    for kind, query in set(re.findall(r'\[get_(pins|regs)\s+\{([^}]+)\}\]', original_sdc)):
        for selector in query.split():
            matches = [name for name in (pins if kind == 'pins' else registers)
                       if fnmatch.fnmatchcase(name, selector)]
            if not matches:
                raise ValueError('unresolved routed CDC/clock selector: ' + selector)
            selectors[kind + ' ' + selector] = len(matches)
    tables = TimingTables()
    tables.feed(physical.joinpath('impl/pnr/hdmi_isolation_tr_content.html').read_text())
    clocks = {}
    for _, rows in tables.tables:
        if rows and 'Period' in rows[0] and 'Clock Name' in rows[0]:
            clocks.update({row[1]: dict(period_ns=float(row[3]), object=row[-1]) for row in rows[1:]})
    required = dict(clk_50m=20.0, ddr_mem400=2.5, ddr_ui100=10.0,
                    video_ref49=1000 / 49.5, video_serial742=1000 / 742.5, video_pixel148=1000 / 148.5,
                    tck_pad_i=50.0)
    if clocks.keys() != required.keys() or any(abs(clocks[name]['period_ns'] - period) > .001
                                             for name, period in required.items()):
        raise ValueError('isolated implemented clock inventory/frequencies changed')
    if clocks['tck_pad_i']['object'] != 'tck_ibuf/I':
        raise ValueError('extra clock is not the GAO JTAG input')
    timing = audit_timing(physical, report_path=physical / 'impl/pnr/hdmi_isolation_tr_content.html',
                          targets={'clk_50m': 50.0, 'ddr_mem400': 400.0,
                                   'ddr_ui100': 100.0, 'video_pixel148': 148.5})
    result = dict(identity=manifest['identity'], passed=not (pll_errors + startup_errors) and timing['timing_closed'],
                  errors=pll_errors + startup_errors, timing=timing, video_pll=pll, serializer_ddr_startup=startup,
                  ddr_configuration=json.loads((view / 'ddr_configuration.json').read_text()),
                  resolved_routed_selectors=selectors, implemented_clocks=clocks,
                  scope='isolated native UI/DDR; no full-workstation or board acceptance',
                  hardware_tested=False, sram_programmed=False, flash_programmed=False, release_ready=False,
                  checker_sha256=sha(Path(__file__)), source_checker_sha256={name: sha(view / 'scripts' / name) for name in names},
                  hierarchy_normalization='remove the sole u_display/ wrapper from VO/SDF/SDC audit views, not implementation',
                  serializer_adaptations=adaptations,
                  adapted_checker_sha256=hashlib.sha256(text.encode()).hexdigest(),
                  adapter_exit_plan='Move native serializer hierarchy/polarity parameters into a shared versioned checker.',
                  bitstream_sha256=sha(physical / 'impl/pnr/ao_0.fs'))
    (view / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    arguments = parser.parse_args()
    result = check(arguments.build.resolve())
    print(json.dumps({name: result[name] for name in ('identity', 'passed', 'errors', 'bitstream_sha256')}))
    raise SystemExit(0 if result['passed'] else 1)
