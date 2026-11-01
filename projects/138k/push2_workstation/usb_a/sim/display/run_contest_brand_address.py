#!/usr/bin/env python3
"""Compare maintained brand, complete dashboards and real paired raster RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SHA256 = 'f5d330b625ea5bc545d1e6c3b9e844a7cc23ba2c4e0b6549e035cffd47d18275'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-brand', type=Path, required=True)
    parser.add_argument('--support-project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-coordinate', action='store_true')
    parser.add_argument('--unit-only', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = args.reference_brand.resolve()
    assert sha(reference) == REFERENCE_SHA256, 'sealed original brand source drift'
    project = args.support_project.resolve()
    display = ROOT / 'rtl/display_data'
    current = display / 'workstation_contest_brand.sv'
    selected = current
    if args.negative_coordinate:
        text = current.read_text()
        anchor = "glyph_decode[9:2] + {6'd0,glyph_row_eighth};"
        assert text.count(anchor) == 1
        selected = out / 'mutant_brand.sv'
        selected.write_text(text.replace(anchor, "glyph_decode[9:2] + {6'd0,glyph_row_eighth} + 8'd1;"))
    old = out / 'reference_brand.sv'
    old.write_text(reference.read_text().replace('module workstation_contest_brand (', 'module reference_workstation_contest_brand (', 1))
    dashboard = display / 'feedback_dashboard.v'
    renderer = display / 'feedback_renderer.v'
    old_dashboard = out / 'reference_dashboard.v'
    old_dashboard.write_text(dashboard.read_text().replace('module feedback_dashboard #(', 'module reference_feedback_dashboard #(', 1)
                             .replace('workstation_contest_brand brand(', 'reference_workstation_contest_brand brand(', 1))
    old_renderer = out / 'reference_renderer.v'
    old_renderer.write_text(renderer.read_text().replace('module feedback_renderer #(', 'module reference_feedback_renderer #(', 1)
                            .replace('feedback_dashboard #(', 'reference_feedback_dashboard #('))
    bench = Path(__file__).with_name('tb_contest_brand_address.sv')
    font = project / 'src/video/video_font_5x7.v'
    assets = sorted((display / 'assets').iterdir())
    inputs = list(dict.fromkeys([current, reference, selected, dashboard, renderer, bench, font, Path(__file__).resolve(),
                                  *[path for path in assets if path.is_file()]]))
    before = {str(path): sha(path) for path in inputs}
    shutil.copytree(display / 'assets', out / 'rtl/display_data/assets')
    common = [selected, old, bench]
    suites = [('unit', 'tb_contest_brand_unit', common)]
    if not args.unit_only and not args.negative_coordinate:
        suites.append(('dashboard', 'tb_contest_brand_dashboard', [*common, dashboard, old_dashboard, font]))
        support = [display / 'feedback_capture.v', project / 'src/video/feedback_wave_align.v',
                   project / 'src/video/output_audio_capture.v']
        suites.append(('renderer', 'tb_contest_brand_renderer', [*common, dashboard, old_dashboard, font,
            renderer, old_renderer, *support]))
        before.update({str(path): sha(path) for path in support})
    results = []
    for name, top, sources in suites:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal', '--top-module', top,
                   '--Mdir', str(out / (name + '_obj')), *map(str, sources)]
        with (out / (name + '_compile.log')).open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        run_command = [str(out / (name + '_obj') / ('V' + top))]
        if name == 'unit' and not args.negative_coordinate:
            run_command.append('+CHECK_ADDRESS=1')
        with (out / (name + '_run.log')).open('w') as log:
            run = subprocess.run(run_command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        text = (out / (name + '_run.log')).read_text()
        if args.negative_coordinate:
            assert run.returncode != 0 and 'brand pixel mismatch' in text, text
        else:
            assert run.returncode == 0 and 'PASS brand ' in text, text
        results.append(dict(suite=name, compile_command=command, run_command=run_command,
                            output_log_sha256=sha(out / (name + '_run.log')), output=text))
        print(text, end='', flush=True)
    assert before == {path: sha(path) for path in before}, 'brand/renderer/source/asset drift'
    evidence = dict(passed=True, negative_coordinate_rejected=args.negative_coordinate,
        reference_brand_sha256=REFERENCE_SHA256, input_sha256=before, suites=results,
        scope='Actual maintained brand, complete four-configuration dashboard and paired 1080p/720p renderer RTL; unchanged enabled latency and stalls',
        original_assets_unchanged=True, input_bytes_stable_before_after=True,
        physical_timing_verified=False, hardware_tested=False)
    (out / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
