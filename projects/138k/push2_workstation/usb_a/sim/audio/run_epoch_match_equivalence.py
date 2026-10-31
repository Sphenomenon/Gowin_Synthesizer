#!/usr/bin/env python3
"""Exhaustively compare the native epoch-match next state to old equality.

The projection compiles the exact reset/update statements read from maintained
RTL. The oracle independently advances the old counter and request snapshot.
The full runtime-service test separately checks the real cancellation pulse,
counter, snapshot and cancelled formula on both sides of every clock edge.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(text, pattern):
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError('epoch-match projection anchor missing or duplicated: ' + pattern)
    return matches[0]


TESTBENCH = r'''
`timescale 1ns/1ps
module tb_epoch_match;
  reg clk_i=0,rst_ni=1,accepted=0,panic_accept=0;
  reg [9:0] panic_epoch_o=0,request_cancel_epoch=0;
  wire match_o;
  epoch_match_projection dut(.*);
  integer cases=0,restored=0,simultaneous=0,wraps=0;
  task automatic trial(input integer epoch,snapshot,flags);
    integer next_epoch,next_snapshot;
    begin
      panic_epoch_o=10'(epoch);request_cancel_epoch=10'(snapshot);
      accepted=1'(flags);panic_accept=1'(flags>>1);
      // Establish every reachable old proof state; no assumed history length.
      dut.request_epoch_match=epoch==snapshot;
      next_epoch=panic_accept ? (epoch==1023 ? 0 : epoch+1) : epoch;
      next_snapshot=accepted ? epoch : snapshot;
      #1;clk_i=1;#1;
      if(match_o!==(next_epoch==next_snapshot))
        $fatal(1,"old-equality mismatch epoch=%0d snapshot=%0d accepted=%0d panic=%0d actual=%0d expected=%0d",
          epoch,snapshot,accepted,panic_accept,match_o,next_epoch==next_snapshot);
      if(accepted && panic_accept)simultaneous=simultaneous+1;
      if(!accepted && panic_accept && epoch!=snapshot && next_epoch==snapshot)restored=restored+1;
      if(epoch==1023 && panic_accept)wraps=wraps+1;
      cases=cases+1;clk_i=0;
    end
  endtask
  initial begin
    #1;rst_ni=0;#1;if(match_o!==1)$fatal(1,"reset proof must equal zero epoch / zero snapshot");
    rst_ni=1;
    // Put each intended negative control's discriminating state first.
    trial(0,0,3);trial(0,1,2);trial(1023,0,2);
    for(integer epoch=0;epoch<1024;epoch=epoch+1)
      for(integer snapshot=0;snapshot<1024;snapshot=snapshot+1)
        for(integer flags=0;flags<4;flags=flags+1)trial(epoch,snapshot,flags);
    #1;rst_ni=0;#1;if(match_o!==1)$fatal(1,"asynchronous reset did not restore proof");
    if(cases!=4194307 || restored<1024 || simultaneous<1048576 || wraps<2048)
      $fatal(1,"missing complete next-state coverage");
    $display("PASS epoch_match_next_state: cases=%0d restored=%0d simultaneous=%0d wraps=%0d",cases,restored,simultaneous,wraps);
    $finish;
  end
endmodule
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--runtime-verification', type=Path,
                        help='Passed full real-service verification.json; also run a real-service boundary positive and mutant')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    service = ROOT / 'rtl/audio/workstation_audio_render_service.sv'
    event = ROOT / 'rtl/audio/gw138k_event_workstation.sv'
    text = service.read_text()
    declaration = extract(text, r'(    reg request_epoch_match;)')
    next_epoch = extract(text, r'(    wire \[9:0\] next_cancel_epoch=[^\n]+;)')
    reset = extract(text, r'(            request_epoch_match<=1;)')
    update = extract(text, r'(            if\(accepted\)request_epoch_match<=[^\n]+;\n'
                          r'            else if\(panic_accept\)request_epoch_match<=[^\n]+;)')
    projection = ('module epoch_match_projection(input wire clk_i,rst_ni,accepted,panic_accept,\n'
                  'input wire [9:0] panic_epoch_o,request_cancel_epoch,output wire match_o);\n' +
                  declaration + '\n' + next_epoch + '\nassign match_o=request_epoch_match;\n'
                  'always @(posedge clk_i or negedge rst_ni)begin\nif(!rst_ni)begin\n' + reset +
                  '\nend else begin\n' + update + '\nend\nend\nendmodule\n')
    mutants = {
        'accepted_panic_ignored': projection.replace('<=!panic_accept;', "<=1'b1;"),
        'sticky_cancel': projection.replace('<=next_cancel_epoch==request_cancel_epoch;', "<=1'b0;"),
        'lost_modulo_wrap': projection.replace('[9:0] next_cancel_epoch=panic_epoch_o+10\'d1;',
                                               '[10:0] next_cancel_epoch={1\'b0,panic_epoch_o}+11\'d1;'),
    }
    if any(value == projection for value in mutants.values()):
        raise ValueError('negative-control exact mutation anchor drift')
    sources = [service, event, Path(__file__).resolve(),
               ROOT / 'sim/audio/tb_workstation_runtime_render_service.sv']
    hashes = {str(path): digest(path) for path in sources}
    report = dict(schema=1, identity='native-request-epoch-match-next-state-v1', passed=False,
                  hardware_tested=False, routed_timing_tested=False,
                  scope='All 1024 counter values x 1024 snapshots x 4 accepted/PANIC inputs; asynchronous reset; three semantic negative controls',
                  projection_policy='Exact native reset/update statements compiled without behavioral edits; independent old counter/snapshot oracle',
                  extracted_native_statements=dict(declaration=declaration, next_epoch=next_epoch,
                                                   reset=reset, update=update),
                  input_sha256=hashes, runs={})
    try:
        for name, body in {'production': projection, **mutants}.items():
            folder = output / name
            folder.mkdir()
            source = folder / 'epoch_match_projection.sv'
            source.write_text(body + TESTBENCH)
            executable = folder / 'simulation'
            command = ['iverilog', '-g2012', '-s', 'tb_epoch_match', '-o', str(executable), str(source)]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            (folder / 'compile.log').write_text(compiled.stdout + compiled.stderr)
            if compiled.returncode:
                raise ValueError('projection compile failed: ' + name)
            run = subprocess.run(['vvp', str(executable)], text=True, capture_output=True, timeout=90)
            (folder / 'run.log').write_text(run.stdout + run.stderr)
            report['runs'][name] = dict(returncode=run.returncode, log_sha256=digest(folder / 'run.log'))
            if name == 'production':
                if run.returncode or run.stdout.count('PASS epoch_match_next_state:') != 1:
                    raise ValueError('production next-state comparison failed')
                report['metrics'] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', run.stdout)}
                print(run.stdout, end='')
            elif not run.returncode or 'old-equality mismatch' not in run.stdout:
                raise ValueError('semantic negative control did not fail for expected reason: ' + name)
        if args.runtime_verification:
            reference_path = args.runtime_verification.resolve()
            reference = json.loads(reference_path.read_text())
            if not reference['passed'] or not reference['inputs_unchanged_during_run']:
                raise ValueError('full runtime-service verification must have passed')
            if reference['input_sha256'][str(service)] != digest(service):
                raise ValueError('full runtime-service evidence used another native service')
            for path, identity in reference['input_sha256'].items():
                if digest(Path(path)) != identity:
                    raise ValueError('full runtime-service evidence input drifted: ' + path)
            hashes.update(reference['input_sha256'])
            hashes[str(reference_path)] = digest(reference_path)
            fixture_path = ROOT / 'sim/audio/tb_workstation_runtime_render_service.sv'
            fixture = fixture_path.read_text()
            anchor = '    configure(0,0);send(2,16,127);send(2,81,7);send(1,69,100);'
            if fixture.count(anchor) != 1:
                raise ValueError('real-service quick-boundary anchor drift')
            quick = '''    wait(ready);@(negedge clk);request=1;rate=0;event_valid=1;event_data={4'd15,7'd0,7'd0};
    @(posedge clk);if(!ready || !dut.panic_accept)$fatal(1,"real-service negative fixture missed accepted/PANIC edge");
    @(negedge clk);request=0;event_valid=0;
    repeat(20)@(negedge clk);
    $display("PASS real_service_epoch_boundary_positive");$finish;
'''
            report['full_runtime_reference'] = dict(path=str(reference_path), sha256=digest(reference_path),
                                                     metrics=reference['metrics'])
            for name, payload in {'real_service_positive': text,
                                  'real_service_accepted_panic_mutant': text.replace(
                                      'if(accepted)request_epoch_match<=!panic_accept;',
                                      "if(accepted)request_epoch_match<=1'b1;")}.items():
                folder = output / name
                folder.mkdir()
                source, tb = folder / service.name, folder / fixture_path.name
                source.write_text(payload)
                tb.write_text(fixture.replace(anchor, quick + anchor))
                command = list(reference['compile_argv'])
                command[command.index('--Mdir') + 1] = str(folder / 'obj')
                command[command.index(str(service))] = str(source)
                command[command.index(str(fixture_path))] = str(tb)
                with (folder / 'compile.log').open('w') as stream:
                    compiled = subprocess.run(command, cwd=reference['project'], stdout=stream,
                                              stderr=subprocess.STDOUT, timeout=300)
                if compiled.returncode or '%Warning-UNOPTFLAT:' in (folder / 'compile.log').read_text():
                    raise ValueError('real-service boundary compile failed or admission loop: ' + name)
                with (folder / 'run.log').open('w') as stream:
                    run = subprocess.run([str(folder / 'obj/Vtb_workstation_runtime_render_service'),
                                          '+TRACE=' + str(folder / 'pcm.txt')], cwd=reference['project'],
                                         stdout=stream, stderr=subprocess.STDOUT, timeout=30)
                log = (folder / 'run.log').read_text()
                report['runs'][name] = dict(returncode=run.returncode, log_sha256=digest(folder / 'run.log'),
                    service_sha256=digest(source), fixture_sha256=digest(tb), compile_argv=command,
                    fixture_adaptation='Insert one real accepted request / USB lifecycle edge then stop; all original real-engine, DDR and epoch-oracle fixtures retained')
                if name == 'real_service_positive':
                    if run.returncode or 'PASS real_service_epoch_boundary_positive' not in log:
                        raise ValueError('real service boundary positive failed')
                elif not run.returncode or 'registered epoch proof differs from original next-state cancellation formula' not in log:
                    raise ValueError('real service did not reject accepted/PANIC mutant for epoch-oracle reason')
        report['inputs_unchanged_during_run'] = hashes == {path: digest(Path(path)) for path in hashes}
        if not report['inputs_unchanged_during_run']:
            raise ValueError('native epoch inputs changed during verification')
        report['passed'] = True
        print('PASS epoch_match_negative_controls:', ', '.join(mutants))
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
