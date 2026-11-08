#!/usr/bin/env python3
"""Check exact plot arithmetic and the real PCM/FFT/image publication path."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_plot_coordinates as plot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, out = args.project.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = (ROOT / plot.SOURCE).read_text()
    selected = plot.adapt(original)
    assert plot.restore(selected) == original
    assert not plot.configured({})
    for configuration in ({plot.KEY: 'unknown'},
                          {plot.KEY: plot.POLICY, 'demo_role': 'W', 'display_metadata_minor': 1}):
        try:
            plot.configured(configuration)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid profile selected')
    for operation, text in ((plot.adapt, original + '\n'), (plot.restore, selected + '\n')):
        try:
            operation(text)
        except ValueError:
            pass
        else:
            raise AssertionError('source drift accepted')
    candidate = out / 'output_audio_analysis.v'
    candidate.write_text(selected)
    start = original.index('    wire [3:0] image_shift=')
    end = original.index('    wire [IMAGE_ADDR_BITS-1:0] image_clear_index=', start)
    # Compile the actual original and selected expressions, including the
    # original signed widths. No test transcription of the optimized cone.
    reference_logic = original[start:end].replace('image_x', 'old_x').replace('image_y', 'old_y')
    adapted_logic = plot.manifest()['edits'][0]['after']
    bench = '''module tb;
reg signed [16:0] plot_side,plot_mid;
reg [2:0] work_image_gain;
''' + reference_logic + adapted_logic + '''
integer g,v,b,values=0,unknowns=0;
reg [36:0] known;
task check; begin
    #1;
    if(image_x !== old_x || image_y !== old_y)
        $fatal(1,"coordinate mismatch gain=%h side=%h mid=%h",work_image_gain,plot_side,plot_mid);
end endtask
initial begin
    // The axes are independent. Each sees every signed17 input at each gain.
    for(g=0;g<8;g=g+1)for(v=-65536;v<65536;v=v+1)begin
        work_image_gain=g;plot_side=v;plot_mid=v;check();values=values+1;
    end
    for(unknowns=0;unknowns<10000;unknowns=unknowns+1)begin
        known={$random,$random};{plot_side,plot_mid,work_image_gain}=known;
        b=unknowns%37;
        if(b<17)plot_side[b]=unknowns[0] ? 1'bx : 1'bz;
        else if(b<34)plot_mid[b-17]=unknowns[0] ? 1'bx : 1'bz;
        else work_image_gain[b-34]=unknowns[0] ? 1'bx : 1'bz;
        check();
    end
    $display("PASS plot coordinates values=%0d unknowns=%0d",values,unknowns);$finish;
end
endmodule
'''
    (out / 'coordinates.sv').write_text(bench)
    sources = [ROOT / 'rtl/display_data_layout_pkg.svh',
               ROOT / 'rtl/display_data/display_data_writer.v',
               ROOT / 'rtl/display_data/display_data_reader.v',
               ROOT / 'rtl/display_data/display_data_analysis_source.sv',
               ROOT / 'rtl/display_data/feedback_capture.v', candidate]
    sources += [project / ('src/video/' + name) for name in (
        'output_audio_capture.v', 'audio_analysis_rom.v', 'feedback_wave_align.v')]
    sources += [Path(__file__).with_name('tb_display_analysis_context.sv')]
    inputs = list(dict.fromkeys(sources + [ROOT / plot.SOURCE, ROOT / plot.TOOL,
                                          ROOT / plot.MANIFEST, Path(__file__).resolve()]))
    hashes = {str(p): sha(p) for p in inputs}
    result = dict(passed=False, input_sha256=hashes, source_policy=plot.POLICY,
                  physical_timing_verified=False, hardware_tested=False,
                  added_state_bits=0, added_cycles=0, commands={})

    def run(name, command, timeout=120):
        result['commands'][name] = list(map(str, command))
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)
        return (out / (name + '.log')).read_text()

    try:
        binary = out / 'coordinates.vvp'
        run('coordinates_compile', ['iverilog', '-g2012', '-s', 'tb', '-o', binary, out / 'coordinates.sv'])
        log = run('coordinates_run', ['vvp', binary])
        assert 'PASS plot coordinates values=1048576 unknowns=10000' in log
        # The same exhaustive oracle must catch a real gain/bit-selection error.
        anchor = '~plot_side[16],plot_side[15:9]'
        assert bench.count(anchor) == 2  # positive and negative saturation arms
        mutant = out / 'coordinates_bad_bit.sv'
        mutant.write_text(bench.replace(anchor, 'plot_side[16],plot_side[15:9]', 1))
        run('negative_compile', ['iverilog', '-g2012', '-s', 'tb', '-o', out / 'bad.vvp', mutant])
        negative = subprocess.run(['vvp', str(out / 'bad.vvp')], cwd=project,
                                  capture_output=True, text=True, timeout=30)
        (out / 'negative_run.log').write_text(negative.stdout + negative.stderr)
        assert negative.returncode != 0 and 'coordinate mismatch' in negative.stdout
        compile_log = run('analysis_compile', ['verilator', '--binary', '--timing', '-j', '4',
            '-Wno-fatal', '--top-module', 'tb_display_analysis_context', '--Mdir', out / 'obj',
            '-I' + str(project), *sources], 300)
        assert '%Warning-UNOPTFLAT' not in compile_log
        log = run('analysis_run', [out / 'obj/Vtb_display_analysis_context'], 180)
        assert 'PASS display_analysis_context: published=3 physical_wave_samples=1536 xy_pixels=196608 fft_columns=1536' in log
        assert all(sha(p) == h for p, h in hashes.items()), 'input drift'
        result.update(passed=True, exhaustive_values=1048576, four_state_cases=10000,
                      negative_control_rejected=True, real_analysis_log=log)
        print(log, end='')
    finally:
        result['logs_sha256'] = {p.name: sha(p) for p in out.glob('*.log')}
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
