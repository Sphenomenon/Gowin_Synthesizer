#!/usr/bin/env python3
"""Verify private return-mailbox preload against the complete immutable W15 store.

Publication stays on its original edge. Only unpublished payload may differ;
this is a legal-protocol ownership proof, not arbitrary internal-state equality.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SHA256 = 'b654b55a47e017aec5f3c386f26cb2aac34f311bdb564852cf047c24dc1c3809'
MAINTAINED_SHA256 = 'd2e39654e16fde55c13b231ef672162fb2b2b6bdfa3740d4b7ac25bb95f8c38d'
PRIVATE_PAYLOAD = {'return_data', 'return_generation', 'return_word'}
OLD_PAYLOAD_WRITE = '''                    return_data<=read_data_i;return_generation<=response_generation;return_word<=response_word;
'''

PRELOAD_BLOCK = '''            // The return payload is private until the original narrow request
            // publication below. Preload only while no acknowledged consumer
            // owns the mailbox; pending freezes every payload field until ACK.
            if(!return_pending)begin
                return_data<=read_data_i;return_generation<=response_generation;return_word<=response_word;
            end
'''

RESPONSE_ANCHOR = '''            if(read_response_i && (read_outstanding || native_read_commit))begin'''

OWNERSHIP_MONITOR = '''
integer mailbox_publications=0,mailbox_pending_edges=0,private_different_edges=0,cache_write_edges=0,complete_ack8=0,discard_ack=0;
reg [298:0] mailbox_before;reg mailbox_was_pending;integer mailbox_cache_writes=0;reg ack_before;
always @(posedge memory_clk)begin
 mailbox_before={dut.return_data,dut.return_generation,dut.return_word};mailbox_was_pending=dut.return_pending;
 if(reference.memory_reset_n && reference.read_response_i && (reference.read_outstanding || reference.native_read_commit) && reference.memory_fetch_active && !reference.memory_fetch_cancel && !reference.cancel_now && !reference.memory_channel_fault && !reference.memory_fault_now && reference.response_generation==reference.memory_generation)begin
  if(reference.return_pending!==0)$fatal(1,"legal new publication overlaps pending mailbox");
  mailbox_publications=mailbox_publications+1;
 end
 #0.01;
 if(reference.memory_reset_n && reference.return_pending)begin
  mailbox_pending_edges=mailbox_pending_edges+1;
  if({dut.return_data,dut.return_generation,dut.return_word}!=={reference.return_data,reference.return_generation,reference.return_word})$fatal(1,"valid mailbox payload mismatch");
 end else if(reference.memory_reset_n && {dut.return_data,dut.return_generation,dut.return_word}!=={reference.return_data,reference.return_generation,reference.return_word})private_different_edges=private_different_edges+1;
 if(dut.memory_reset_n && mailbox_was_pending && {dut.return_data,dut.return_generation,dut.return_word}!==mailbox_before)$fatal(1,"pending mailbox payload overwritten");
end
always @(posedge clk)begin
 if(!reference.control_reset_n)mailbox_cache_writes=0;
 else begin
  ack_before=reference.return_ack;
  if(reference.cache_write)begin cache_write_edges=cache_write_edges+1;mailbox_cache_writes=mailbox_cache_writes+1;end
  if(reference.unpack_active && reference.unpack_index==7 && !reference.clear_pending && !reference.clear_fire && !reference.fault_o)begin
   if(mailbox_cache_writes!=8)$fatal(1,"ACK did not follow all eight live cache writes");
   complete_ack8=complete_ack8+1;
  end
  #0.01;
  if(reference.return_ack!==ack_before)begin if(mailbox_cache_writes==0)discard_ack=discard_ack+1;mailbox_cache_writes=0;end
 end
end
final $display("PASS return mailbox ownership publications=%0d pending_edges=%0d private_different_edges=%0d cache_writes=%0d ack_after8=%0d discarded_ack=%0d",mailbox_publications,mailbox_pending_edges,private_different_edges,cache_write_edges,complete_ack8,discard_ack);
'''

DIRECTED_BODY = '''    integer saved,saved_reads,tail_len,at;
    task prepare_eight;
        begin reset_all;begin_capture;for(n=0;n<8;n=n+1)send_frame(n);end_capture;wait_drained;end
    endtask
    initial begin
        for(n=0;n<2048;n=n+1)memory[n]={32{8'hcd}};
        $display("directed phase pending payload freeze and all8 ACK");
        prepare_eight;fill_cache(0,32);for(n=0;n<8;n=n+1)read_sample(n,pattern(n));
        $display("directed phase same-edge transport fault and read response");
        prepare_eight;response_enable=0;request_fetch(0,32);
        wait(model_read && read_delay==0);@(posedge memory_clk);#1;transport_fault=1;response_enable=1;
        @(posedge memory_clk);#0.1;
        check(!dut.return_pending && dut.return_req==0,"live transport fault cannot publish return token");
        transport_fault=0;wait_channel_fault;repeat(20)@(negedge clk);
        check(!cache_valid && channel_fault,"faulted late return cannot publish cache");
        $display("directed phase same-edge native protocol fault and response");
        prepare_eight;response_enable=0;request_fetch(0,32);
        wait(model_read && read_delay==0);@(posedge memory_clk);#1;force_native=1;response_enable=1;
        @(posedge memory_clk);#0.1;
        check(!dut.return_pending && dut.return_req==0,"live unexpected native fault cannot publish return token");
        force_native=0;wait_channel_fault;repeat(20)@(negedge clk);
        $display("directed phase synchronized cancel and response on same edge");
        prepare_eight;response_enable=0;request_fetch(0,32);wait(model_read && read_delay==0);
        @(negedge clk);clear=1;@(negedge clk);clear=0;
        wait(dut.cancel_now===1'b1);#0.1;response_enable=1;
        @(posedge memory_clk);#0.1;
        check(!dut.return_pending && dut.return_req==0,"same-edge cancel cannot publish return token");
        repeat(40)@(negedge clk);check(!cache_valid && !fault && start_ready,"cancelled return drains then CLEAR completes");
        $display("directed phase pending mailbox common reset with paused memory clock");
        prepare_eight;request_fetch(0,32);wait(dut.return_pending===1'b1);
        @(negedge memory_clk);memory_run=0;@(negedge clk);rst_n=0;
        repeat(5)@(negedge clk);rst_n=1;repeat(12)@(negedge clk);
        check(!cache_valid && !start_ready,"paused memory reset has no public payload");
        memory_run=1;repeat(25)@(negedge clk);check(start_ready && drained && !fault,"common reset releases empty mailbox");
        $display("PASS return mailbox directed protocol boundaries");$finish;
    end
    initial begin #10000000;$fatal(1,"directed mailbox watchdog");end
endmodule
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('raw return-mailbox preload: ' + message)


def replace_once(text, anchor, replacement):
    require(text.count(anchor) == 1, 'source anchor drift: ' + anchor[:80])
    return text.replace(anchor, replacement, 1)


def normalize_before_failure_final_ce(text):
    """Keep the newer private failure-register change out of this older proof."""
    helper_path = Path(__file__).with_name('ble_raw_failure_ce_sources.py')
    require(sha(helper_path) ==
            '40a700472f82ebc92387214782a580442d223bd5e05c5f29cde6439205b62d66',
            'final failure CE inverse helper changed')
    spec = importlib.util.spec_from_file_location('raw_failure_ce_inverse', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if hashlib.sha256(text.encode()).hexdigest() == helper.BASELINE_SHA256:
        return text
    return helper.restore_before_failure_final_ce(text)


def restore_before_return_preload(text):
    """Strict inverse for old proofs; it proves no new private-state contract."""
    text = normalize_before_failure_final_ce(text)
    require(hashlib.sha256(text.encode()).hexdigest() == MAINTAINED_SHA256,
            'maintained source identity changed')
    restored = replace_once(text, PRELOAD_BLOCK, '')
    publication = '                    return_req<=~return_req;return_pending<=1;'
    restored = replace_once(restored, publication, OLD_PAYLOAD_WRITE + publication)
    require(hashlib.sha256(restored.encode()).hexdigest() == BASELINE_SHA256,
            'complete pre-preload reconstruction changed')
    return restored


def load_helper(path):
    spec = importlib.util.spec_from_file_location('raw_return_helpers', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def source_structure(old, new):
    require(hashlib.sha256(old.encode()).hexdigest() == BASELINE_SHA256, 'fixture identity')
    generated = replace_once(old, OLD_PAYLOAD_WRITE, '')
    generated = replace_once(generated, RESPONSE_ANCHOR, PRELOAD_BLOCK + RESPONSE_ANCHOR)
    require(generated == new and restore_before_return_preload(new) == old,
            'change escapes exact payload movement')
    nbas = lambda text: re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);', text)
    before, after = nbas(old), nbas(new)
    require([row for row in before if row[0] not in PRIVATE_PAYLOAD] ==
            [row for row in after if row[0] not in PRIVATE_PAYLOAD],
            'nonprivate NBA RHS or order changed')
    for name in PRIVATE_PAYLOAD:
        require([rhs for target, rhs in before if target == name] ==
                [rhs for target, rhs in after if target == name], 'payload RHS drift ' + name)
    controls = {}
    for name, mutant in [
            ('preload_guard', replace_once(new, 'if(!return_pending)begin\n                return_data',
                                          "if(1'b1)begin\n                return_data")),
            ('publication', replace_once(new, 'return_req<=~return_req;return_pending<=1;',
                                        'return_req<=return_req;return_pending<=1;')),
            ('other_state', replace_once(new,
                'read_outstanding<=0;\n                if(memory_fetch_active',
                'read_outstanding<=1;\n                if(memory_fetch_active'))]:
        try:
            restore_before_return_preload(mutant)
        except ValueError:
            controls[name] = 'rejected'
        else:
            raise ValueError('inverse accepted mutation ' + name)
    return dict(exact_complete_source_inverse=True, all_nonprivate_NBA_RHS_order_unchanged=True,
                private_payload_NBA_RHS_unchanged=True, structural_negative_controls=controls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/memory/workstation_ble_raw_ddr_store.sv'
    fixture = Path(__file__).with_name('fixtures') / 'workstation_ble_raw_ddr_store_before_return_preload.sv'
    helper_source = Path(__file__).with_name('prove_ble_raw_start_factor.py')
    tb_source = Path(__file__).with_name('tb_ble_raw_ddr_store.sv')
    dependencies = [ROOT / relative for relative in (
        'rtl/memory/workstation_sdp.sv', 'rtl/music/music_async_fifo.sv',
        'rtl/memory/workstation_recording_ddr_native_bridge.sv')]
    failure_helper = Path(__file__).with_name('ble_raw_failure_ce_sources.py')
    paths = [source, fixture, helper_source, tb_source, *dependencies,
             Path(__file__).resolve(), failure_helper]
    original_hashes = {str(path): sha(path) for path in paths}
    snapshots = {}
    for path in paths:
        target = out / 'inputs' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        require(sha(target) == original_hashes[str(path)], 'input changed during snapshot')
        snapshots[path] = target
    old = snapshots[fixture].read_text()
    new = normalize_before_failure_final_ce(snapshots[source].read_text())
    structure = source_structure(old, new)
    helper = load_helper(snapshots[helper_source])
    ports, states, nets = helper.inventories(old)
    require(helper.inventories(new) == (ports, states, nets), 'port/state/net inventory changed')
    compared_states = [name for name in states if name not in PRIVATE_PAYLOAD]
    variant = out / 'normalized-before-final-failure-ce.sv'
    variant.write_text(new)
    reference = out / 'reference.sv'
    reference.write_text(replace_once(old, 'module workstation_ble_raw_ddr_store #(',
                                     'module workstation_ble_raw_ddr_store_reference #('))
    (out / 'proposed.patch').write_text(''.join(difflib.unified_diff(
        old.splitlines(True), new.splitlines(True), fromfile='before-return-preload.sv',
        tofile='maintained-return-preload.sv')))

    def twin_for(tb, name):
        helper.TB = tb
        text, inventory = helper.twin_bench(old, ports, compared_states, nets)
        text = replace_once(text, 'integer twin_edges=0,twin_case=0,twin_i;',
                            OWNERSHIP_MONITOR + '\ninteger twin_edges=0,twin_case=0,twin_i;')
        path = out / name
        path.write_text(text)
        return path, inventory

    full, inventory = twin_for(snapshots[tb_source], 'full-twin.sv')
    text = snapshots[tb_source].read_text()
    anchor = '    integer saved,saved_reads,tail_len,at;'
    require(text.count(anchor) == 1, 'directed protocol bench anchor drift')
    directed_source = out / 'directed-source.sv'
    directed_source.write_text(text[:text.index(anchor)] + DIRECTED_BODY)
    directed, _ = twin_for(directed_source, 'directed-twin.sv')
    deps = [snapshots[path] for path in dependencies]
    result = dict(schema=1, passed=False, source_implementation=True,
                  source_sha256=sha(variant), baseline_sha256=sha(snapshots[fixture]),
                  maintained_source_sha256=sha(snapshots[source]),
                  exact_reviewed_final_failure_ce_inverse=True,
                  source_structure=structure, logical_payload_bits=299,
                  added_registers=0, added_latency=0, whole_twin_inventory=inventory,
                  allowed_private_difference=sorted(PRIVATE_PAYLOAD), cases={}, negative_controls={},
                  input_sha256=original_hashes,
                  actual_input_snapshots={str(path): dict(path=str(copy), sha256=sha(copy))
                                          for path, copy in snapshots.items()},
                  synthesis=False, pnr=False, hardware_tested=False,
                  timing_or_resource_gain_claimed=False,
                  proof_scope='Public protocol and effective mailbox payload equivalence with unchanged live fault, cancel, token, ACK and native retirement; unpublished private payload may differ. Not arbitrary internal-state equality or an inductive sequential formal proof.')
    try:
        for label, params in [('fifo8_async_memory', [('FIFO_BITS', 8), ('MEM_HALF', 7)]),
                              ('fifo3_100mhz_memory', [('FIFO_BITS', 3), ('MEM_HALF', 5)])]:
            result['cases'][label] = helper.simulate(
                out, label, [full, variant, reference, *deps], 'tb_ble_raw_ddr_store', params, timeout=150)
        for label, params in [('directed_fifo8', [('FIFO_BITS', 8), ('MEM_HALF', 7)]),
                              ('directed_fifo3', [('FIFO_BITS', 3), ('MEM_HALF', 5)])]:
            result['cases'][label] = helper.simulate(
                out, label, [directed, variant, reference, *deps], 'tb_ble_raw_ddr_store', params, timeout=80)
        mutants = {
            'pending_overwrite': replace_once(new, 'if(!return_pending)begin\n                return_data',
                                              "if(1'b1)begin\n                return_data"),
            'early_token': replace_once(new, RESPONSE_ANCHOR,
                '            if(read_outstanding && !return_pending)begin return_req<=~return_req;return_pending<=1;end\n' + RESPONSE_ANCHOR),
            'drop_live_fault': replace_once(new,
                '!memory_channel_fault && !memory_fault_now && response_generation==memory_generation',
                '!memory_channel_fault && response_generation==memory_generation'),
            'drop_same_edge_cancel': replace_once(new,
                'if(memory_fetch_active && !memory_fetch_cancel && !cancel_now &&\n                   !memory_channel_fault',
                'if(memory_fetch_active && !memory_fetch_cancel &&\n                   !memory_channel_fault'),
            'payload_one_cycle_late': replace_once(new, 'if(!return_pending)begin\n                return_data',
                                                   'if(return_pending)begin\n                return_data'),
        }
        for name, text in mutants.items():
            mutant = out / (name + '.sv')
            mutant.write_text(text)
            compile_argv = ['iverilog', '-g2012', '-s', 'tb_ble_raw_ddr_store',
                            '-o', str(out / (name + '.vvp')), str(directed), str(mutant),
                            str(reference), *map(str, deps)]
            compiled = subprocess.run(compile_argv, capture_output=True, text=True, timeout=30)
            compile_log = out / (name + '-compile.log')
            compile_log.write_text(compiled.stdout + compiled.stderr)
            require(compiled.returncode == 0 and not compile_log.read_text().strip(),
                    'negative control compile diagnostics ' + name)
            run_argv = ['vvp', str(out / (name + '.vvp'))]
            run = subprocess.run(run_argv, capture_output=True, text=True, timeout=80)
            log = out / (name + '.log')
            log.write_text(run.stdout + run.stderr)
            expected = ('complete raw twin', 'valid mailbox payload mismatch',
                        'pending mailbox payload overwritten', 'live transport fault cannot',
                        'same-edge cancel cannot')
            require(run.returncode != 0 and any(marker in log.read_text() for marker in expected),
                    'negative control escaped ' + name + ': ' + log.read_text())
            result['negative_controls'][name] = dict(
                rejected=True, returncode=run.returncode, compile_argv=compile_argv,
                run_argv=run_argv, compile_log_sha256=sha(compile_log),
                run_log_sha256=sha(log), summary=log.read_text().strip())
            print('PASS rejected ' + name, flush=True)
        require(original_hashes == {str(path): sha(path) for path in paths},
                'maintained input changed during validation')
        result['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS maintained return mailbox preload', sha(variant), flush=True)


if __name__ == '__main__':
    main()
