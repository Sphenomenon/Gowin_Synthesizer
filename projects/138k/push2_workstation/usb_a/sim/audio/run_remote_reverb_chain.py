#!/usr/bin/env python3
"""Exercise the actual partitioned chain and W reverb against the independent model."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
import test_workstation_runtime_effects as reference

ROOT = reference.ROOT
BENCH = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
BENCH_SHA256 = '5c7fb85775b9d5b365428c6c2f578fa37587aea4d034b57c5b105f2a21e3ec58'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def partition_bench(payload):
    if sha(payload) != BENCH_SHA256:
        raise ValueError('Original complete-chain testbench identity changed')
    text = payload.decode()
    declarations = '''  wire req_valid,req_ready,req_rate,req_enabled,req_reset_gain;
  wire [31:0] req_session,req_generation,req_sequence;
  wire signed [31:0] req_left,req_right;
  wire rsp_valid,rsp_ready,rsp_rate,rsp_active,rsp_clip,rsp_error;
  wire [31:0] rsp_session,rsp_generation,rsp_sequence;
  wire signed [31:0] rsp_left,rsp_right;
  wire [31:0] fallback_count,rejected_count,w_rejected_count,w_timeout_count;
  reg tail_check_pending=0,tail_before=0;
  integer active_tail_checks=0;
'''
    ports = '''      .remote_reverb_link_ready_i(1'b1),.remote_reverb_link_session_i(32'h13830001),
      .remote_reverb_req_valid_o(req_valid),.remote_reverb_req_ready_i(req_ready),
      .remote_reverb_req_session_o(req_session),.remote_reverb_req_generation_o(req_generation),.remote_reverb_req_sequence_o(req_sequence),
      .remote_reverb_req_rate_44100_o(req_rate),.remote_reverb_req_enabled_o(req_enabled),.remote_reverb_req_reset_gain_o(req_reset_gain),
      .remote_reverb_req_left_o(req_left),.remote_reverb_req_right_o(req_right),
      .remote_reverb_rsp_valid_i(rsp_valid),.remote_reverb_rsp_ready_o(rsp_ready),
      .remote_reverb_rsp_session_i(rsp_session),.remote_reverb_rsp_generation_i(rsp_generation),.remote_reverb_rsp_sequence_i(rsp_sequence),
      .remote_reverb_rsp_rate_44100_i(rsp_rate),.remote_reverb_rsp_active_i(rsp_active),
      .remote_reverb_rsp_clip_i(rsp_clip),.remote_reverb_rsp_error_i(rsp_error),
      .remote_reverb_rsp_left_i(rsp_left),.remote_reverb_rsp_right_i(rsp_right),
      .remote_reverb_fallback_count_o(fallback_count),.remote_reverb_rejected_count_o(rejected_count),
'''
    worker = '''
  workstation_remote_reverb_w worker(
      .clk_i(aclk),.rst_ni(arst_n),.link_ready_i(1'b1),.link_session_i(32'h13830001),
      .req_valid_i(req_valid),.req_ready_o(req_ready),.req_session_i(req_session),
      .req_generation_i(req_generation),.req_sequence_i(req_sequence),.req_rate_44100_i(req_rate),
      .req_enabled_i(req_enabled),.req_reset_gain_i(req_reset_gain),.req_left_i(req_left),.req_right_i(req_right),
      .rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready),.rsp_session_o(rsp_session),
      .rsp_generation_o(rsp_generation),.rsp_sequence_o(rsp_sequence),.rsp_rate_44100_o(rsp_rate),
      .rsp_active_o(rsp_active),.rsp_clip_o(rsp_clip),.rsp_error_o(rsp_error),.rsp_left_o(rsp_left),.rsp_right_o(rsp_right),
      .rejected_count_o(w_rejected_count),.timeout_count_o(w_timeout_count));
  // Ordinary rate/history barriers preserve the existing wet-gain tail.
  // PANIC clears it separately. Check before the next maintenance response
  // can repair a spuriously cleared M selection state.
  always @(posedge aclk)begin
    tail_check_pending=arst_n && !clear_i && (u_dut.config_accept || u_dut.history_accept);
    if(tail_check_pending)tail_before=u_dut.remote_reverb.reverb_stage.remote_active;
  end
  always @(negedge aclk)if(tail_check_pending && !clear_i)begin
    if(u_dut.remote_reverb.reverb_stage.remote_active!==tail_before)
      $fatal(1,"normal rate/history barrier changed active reverb tail");
    if(tail_before)active_tail_checks=active_tail_checks+1;
  end
'''
    edits = [
        ('  workstation_runtime_stereo_effects #(.VECTOR_ENABLE(1),.TRANSACTION_TIMEOUT_CYCLES(2048),.PEER_TIMEOUT_CYCLES(512)) u_dut(\n',
         declarations + '  workstation_runtime_stereo_effects #(.VECTOR_ENABLE(1),.TRANSACTION_TIMEOUT_CYCLES(2048),.PEER_TIMEOUT_CYCLES(512),.REMOTE_REVERB_ENABLE(1),.REMOTE_REVERB_DEADLINE_CYCLES(512)) u_dut(\n' + ports),
        ('`ifdef RUNTIME_REVERB_SCRATCH_REFERENCE\n', worker + '`ifdef RUNTIME_REVERB_SCRATCH_REFERENCE\n'),
        ('while(!valid_o && latency<250)', 'while(!valid_o && latency<1000)'),
        ('compare48=scenario==0;', 'compare48=0;'),
        ('if(scenario==0)compare48=1;', 'if(scenario==0)compare48=0;'),
        ('u_dut.reverb_stage.gain!=0', 'u_dut.remote_reverb.reverb_stage.remote_active!=0'),
        ('      if(fault || outputs==0)$fatal(1,"full-chain vector fault");',
         '      if(fault || outputs==0 || fallback_count!=0 || rejected_count!=0 || w_rejected_count!=0 || w_timeout_count!=0)\n'
         '        $fatal(1,"partition chain fault/fallback/rejection/timeout");'),
        ('      $fclose(fd);',
         '      $fclose(fd);\n'
         '      if(scenario==2 && active_tail_checks<3)$fatal(1,"missing active-tail barrier coverage");\n'
         '      $display("tail_preservation_checks=%0d",active_tail_checks);'),
    ]
    for before,after in edits:
        if text.count(before) != 1:
            raise ValueError('Partition testbench anchor drift: ' + before)
        text = text.replace(before, after)
    return text, edits


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    captured = []
    native_run = subprocess.run

    def capture(command, *args, **kwargs):
        if isinstance(command, list) and command[:2] == ['verilator', '--binary']:
            captured.append(list(command))
        return native_run(command, *args, **kwargs)

    class Chain(reference.RuntimeEffectsTest):
        pass

    subprocess.run = capture
    try:
        Chain.setUpClass()
    finally:
        subprocess.run = native_run
    try:
        if len(captured) != 1:
            raise ValueError('Original full-chain compile command not uniquely captured')
        bench, edits = partition_bench(BENCH.read_bytes())
        target = Chain.stage / 'remote_partition_chain.sv'
        target.write_text(bench)
        (output / 'testbench.sv').write_text(bench)
        command = captured[0]
        command[command.index(str(BENCH))] = str(target)
        command[command.index('--Mdir') + 1] = str(Chain.stage / 'remote_obj')
        command[command.index('-o') + 1] = 'remote_chain'
        command += ['-DWORKSTATION_REMOTE_REVERB_PARTITION',
                    str(ROOT / 'rtl/audio/workstation_remote_reverb_m.sv'),
                    str(ROOT / 'rtl/audio/workstation_remote_reverb_w.sv')]
        remote_sources = [ROOT / 'rtl/audio/workstation_remote_reverb_m.sv',
                          ROOT / 'rtl/audio/workstation_remote_reverb_w.sv', Path(__file__)]
        remote_hashes = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in remote_sources}
        result = native_run(command, cwd=Chain.stage, capture_output=True, text=True, timeout=180)
        (output / 'compile.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(result.stdout[-2000:] + result.stderr[-6000:])
        warnings = {}
        for line in result.stderr.splitlines():
            if line.startswith('%Warning-'):
                key = line.split(':', 1)[0][9:]
                warnings[key] = warnings.get(key, 0) + 1
        if warnings != {'TIMESCALEMOD': 1, 'WIDTHEXPAND': 55, 'WIDTHTRUNC': 16}:
            raise RuntimeError('Partition compile warning drift: ' + json.dumps(warnings))
        instance = Chain()
        binary = Chain.stage / 'remote_obj/remote_chain'
        cases = []
        def run_case(number, rows):
            path = instance.fixture(number, rows)
            result = native_run([str(binary), f'+SCENARIO={number}', '+VECTOR_FILE=' + str(path)],
                                cwd=Chain.stage, capture_output=True, text=True, timeout=90)
            (output / f'scenario{number}.log').write_text(result.stdout + result.stderr)
            if result.returncode or 'PASS runtime full effects' not in result.stdout:
                raise RuntimeError(result.stdout + result.stderr)
            match = re.search(r'frames=(\d+).*max_latency=(\d+)', result.stdout)
            if not match:
                raise RuntimeError('Missing complete-chain frame/deadline evidence')
            case = dict(scenario=number, frames=int(match[1]), max_latency_cycles=int(match[2]),
                        vectors_sha256=sha(path.read_bytes()), stdout=result.stdout.strip())
            tail_match = re.search(r'tail_preservation_checks=(\d+)', result.stdout)
            case['active_tail_barrier_checks'] = int(tail_match[1]) if tail_match else 0
            cases.append(case)
            print(result.stdout.strip(), flush=True)
        rows = instance.random_rows(3000, 7, 0x24)
        for permutation in itertools.permutations(range(3)):
            order = sum(value << (2 * slot) for slot,value in enumerate(permutation))
            for mask in range(8):
                rows += instance.random_rows(128, mask, order, 0x5918ab43 + 23*order + mask)
        run_case(0, rows + [instance.operation(4)] + instance.random_rows(3000, 7, 0x24))
        run_case(1, [instance.operation(1)] + rows)
        changing = instance.random_rows(3000, 7, 0x24)
        for operation in (3,1,2,4):
            # First frame after a live-tail history/rate transaction is fully
            # bypassed, before any W maintenance reply can restore M's state.
            changing += [instance.operation(operation)] + instance.random_rows(128, 0, 0x18, 0x1383a120)
            changing += instance.random_rows(3000, 7, 0x18, 0x28cb4511)
        changing += instance.random_rows(512, 0, 0x24)
        run_case(2, changing)
        for number in (3,4):
            result = native_run([str(binary), f'+SCENARIO={number}'], cwd=Chain.stage,
                                capture_output=True, text=True, timeout=90)
            (output / f'scenario{number}.log').write_text(result.stdout + result.stderr)
            if result.returncode or 'PASS runtime effects PANIC collision' not in result.stdout:
                raise RuntimeError(result.stdout + result.stderr)
            cases.append(dict(scenario=number, stdout=result.stdout.strip()))
            print(result.stdout.strip(), flush=True)
        evidence = dict(schema=1, passed=True, stage='actual partitioned effects-chain RTL simulation',
                        original_bench_sha256=BENCH_SHA256, adapted_bench_sha256=sha(bench.encode()),
                        checked_adaptation_count=len(edits), compile_warnings=warnings, cases=cases,
                        frames=sum(c.get('frames',0) for c in cases),
                        max_latency_cycles=max(c.get('max_latency_cycles',0) for c in cases),
                        real_W_reverb=True, independent_full_chain_PCM_model=True,
                        all_six_effect_orders=True, all_eight_masks=True, dual_rate=True,
                        DDR_delay_and_maintenance=True, local_sample_period_budget_cycles=1600,
                        immediate_post_barrier_bypass=True,
                        active_tail_barrier_checks=sum(c.get('active_tail_barrier_checks',0) for c in cases),
                        physical_transport_selected=False, physical_timing_verified=False, hardware_tested=False)
        sources = dict(Chain.source_hashes)
        for name,expected in remote_hashes.items():
            if sha((ROOT/name).read_bytes()) != expected:
                raise ValueError('Remote chain input changed during execution: '+name)
            sources[name] = expected
        evidence['source_sha256'] = sources
        (output / 'verification.json').write_text(json.dumps(evidence, indent=2)+'\n')
        return evidence
    finally:
        Chain.tearDownClass()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({key:result[key] for key in ('passed','frames','max_latency_cycles')}))
