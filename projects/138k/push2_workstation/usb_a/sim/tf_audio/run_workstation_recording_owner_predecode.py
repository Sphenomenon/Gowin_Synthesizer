#!/usr/bin/env python3
"""Check the live owner-veto predecode against the original four-state cone."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv'
LEGACY = ROOT / 'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv'
OLD = "    wire invalid_return_owner=count!=0 && (tags[read_pointer]==4'd3 || tags[read_pointer]>4'd8);\n"
FLAT = """    // Decode each authoritative tag before selecting the head's one-bit veto.
    // No shadow state: same-edge tag corruption and X/Z still reach the live
    // transport fault, including an unknown read index. Ownership/data retire
    // on the original edge; the four-bit response-owner read is unchanged.
    wire [DEPTH-1:0] invalid_owner_by_slot;
    for(genvar slot=0;slot<DEPTH;slot=slot+1)begin:g_invalid_owner
        assign invalid_owner_by_slot[slot]=tags[slot]==4'd3 || tags[slot]>4'd8;
    end
    wire invalid_return_owner=count!=0 && invalid_owner_by_slot[read_pointer];
"""

PREVIOUS_SHA256 = 'e4cd6d5e3e485659041015adcfbcdf34259e3e33240a4027bdf90e11467f655d'
NEW = "    // Decode the authoritative tags, then select through bounded four-way\n    // stages. Keep each stage so mapping cannot rebuild a serial owner mux.\n    // No shadow state: corruption reaches the same-edge transport fault.\n    // Unknown address bits still produce X as the original variable index.\n    // Response owner/data continue to retire on their original edge.\n    wire [DEPTH-1:0] invalid_owner_by_slot;\n    for(genvar slot=0;slot<DEPTH;slot=slot+1)begin:g_invalid_owner\n        assign invalid_owner_by_slot[slot]=tags[slot]==4'd3 || tags[slot]>4'd8;\n    end\n    localparam OWNER_VETO_LEVELS=(TAG_BITS+1)/2;\n    wire [DEPTH-1:0] owner_veto_tree[0:OWNER_VETO_LEVELS];\n    assign owner_veto_tree[0]=invalid_owner_by_slot;\n    for(genvar level=0;level<OWNER_VETO_LEVELS;level=level+1)begin:g_owner_veto_level\n        localparam INPUTS=DEPTH>>(level*2);\n        localparam OUTPUTS=(INPUTS+3)/4;\n        for(genvar group=0;group<DEPTH;group=group+1)begin:g_group\n            if(group<OUTPUTS)begin:g_live\n                reg selected /* synthesis syn_keep=1 */;\n                if(level*2+1<TAG_BITS)begin:g_four\n                    always @* case(read_pointer[level*2+:2])\n                        2'd0:selected=owner_veto_tree[level][group*4];\n                        2'd1:selected=owner_veto_tree[level][group*4+1];\n                        2'd2:selected=owner_veto_tree[level][group*4+2];\n                        2'd3:selected=owner_veto_tree[level][group*4+3];\n                        default:selected=1'bx;\n                    endcase\n                end else begin:g_two\n                    always @* case(read_pointer[level*2])\n                        1'b0:selected=owner_veto_tree[level][group*2];\n                        1'b1:selected=owner_veto_tree[level][group*2+1];\n                        default:selected=1'bx;\n                    endcase\n                end\n                assign owner_veto_tree[level+1][group]=selected;\n            end else begin:g_unused\n                assign owner_veto_tree[level+1][group]=1'b0;\n            end\n        end\n    end\n    wire invalid_return_owner=count!=0 && owner_veto_tree[OWNER_VETO_LEVELS][0];\n"

TB = r"""`timescale 1ns/1ps
`default_nettype none
module tb_owner_predecode;
    parameter integer BITS=5;
    localparam integer DEPTH=1<<BITS;
    reg clk=0,rstn=0,returned=0;
    wire transport_fault,sticky_fault,rec_resp,bist_resp,scan_resp,cpu_resp;
    wire audio_resp,music_resp,delay_resp,display_resp;
    wire [255:0] response_data;
    reg [255:0] data=0;
    workstation_recording_ddr_arbiter_pipeline #(.TAG_BITS(BITS),.RECORDING_ENABLE(1)) dut(
        .clk(clk),.reset_n(rstn),.bist_done(1'b1),.bist_valid(1'b0),.bist_write(1'b0),
        .bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(bist_resp),
        .scan_valid(1'b0),.scan_address(29'd0),.scan_ready(),.scan_response(scan_resp),
        .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(display_resp),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),.audio_ready(),.audio_response(audio_resp),
        .music_valid(1'b0),.music_write(1'b0),.music_address(29'd0),.music_data(256'd0),.music_mask(32'd0),.music_ready(),.music_response(music_resp),
        .delay_valid(1'b0),.delay_write(1'b0),.delay_address(29'd0),.delay_data(256'd0),.delay_ready(),.delay_response(delay_resp),
        .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),.writer_ready(),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(cpu_resp),
        .recording_valid(1'b0),.recording_write(1'b0),.recording_address(29'd0),.recording_data(256'd0),.recording_mask(32'd0),
        .recording_ready(),.recording_response(rec_resp),
        .app_cmd(),.app_en(),.app_wren(),.app_wend(),.app_address(),.app_data(),.app_mask(),
        .app_ready(1'b1),.app_write_ready(1'b1),.app_response(returned),.app_response_data(data),
        .response_data(response_data),.response_fault(sticky_fault),.core_accept_o(),.native_accept_o(),.transport_fault_o(transport_fault));
    function automatic reg digit(input integer code);
        case(code) 0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase
    endfunction
    function automatic [3:0] tag_value(input integer code);
        integer bitno;
        begin for(bitno=0;bitno<4;bitno=bitno+1)tag_value[bitno]=digit((code>>(2*bitno))&3);end
    endfunction
    function automatic [BITS-1:0] index_value(input integer code);
        integer bitno;
        begin for(bitno=0;bitno<BITS;bitno=bitno+1)index_value[bitno]=digit((code>>(2*bitno))&3);end
    endfunction
    integer checks=0,known_tag_checks=0,unknown_index_checks=0,qualifier_checks=0;
    reg expected_invalid,expected_now,expected_transport,expected_pop,expected_valid,expected_sticky;
    reg [3:0] expected_owner;
    reg [7:0] expected_responses;
    task check_edge;
        begin
            // The oracle is the original expression over the same live tags.
            // Direct corruption happens while clk is low, before this edge.
            #1;
            expected_invalid=dut.g_recording.count!=0 &&
                (dut.g_recording.tags[dut.g_recording.read_pointer]==4'd3 ||
                 dut.g_recording.tags[dut.g_recording.read_pointer]>4'd8);
            expected_now=returned && (dut.g_recording.count==0 || expected_invalid);
            expected_transport=sticky_fault || expected_now;
            expected_pop=returned && dut.g_recording.count!=0;
            expected_valid=expected_pop && !expected_invalid;
            expected_owner=dut.g_recording.response_owner;
            if(expected_pop)expected_owner=dut.g_recording.tags[dut.g_recording.read_pointer];
            expected_sticky=sticky_fault;
            if(expected_now)expected_sticky=1;
            if(dut.g_recording.invalid_return_owner!==expected_invalid ||
               dut.g_recording.response_fault_now!==expected_now || transport_fault!==expected_transport)
                $fatal(1,"live owner-veto four-state mismatch bits=%0d check=%0d",BITS,checks);
            clk=1;#1;
            expected_responses={expected_valid && expected_owner==8,expected_valid && expected_owner==7,
                expected_valid && expected_owner==6,expected_valid && expected_owner==5,
                expected_valid && expected_owner==4,expected_valid && expected_owner==2,
                expected_valid && expected_owner==1,expected_valid && expected_owner==0};
            if(dut.g_recording.response_valid!==expected_valid ||
               dut.g_recording.response_owner!==expected_owner || sticky_fault!==expected_sticky ||
               response_data!==data ||
               {rec_resp,display_resp,delay_resp,music_resp,audio_resp,cpu_resp,scan_resp,bist_resp}!==expected_responses)
                $fatal(1,"owner-veto retirement/NBA mismatch bits=%0d check=%0d",BITS,checks);
            clk=0;checks=checks+1;data=data+1'b1;
        end
    endtask
    task occupied;
        begin dut.g_recording.count=1;returned=1;dut.response_fault=0;end
    endtask
    integer slot,code,pattern,cc,rc,sc;
    reg [BITS-1:0] selector;
    initial begin
        // Exercise the actual reset before mutating the queue's private state.
        #1;clk=1;#1;clk=0;rstn=1;
        for(slot=0;slot<DEPTH;slot=slot+1)dut.g_recording.tags[slot]=4'(slot);
        // Every four-state owner value at every valid address. No clock is
        // needed to expose a newly corrupt tag in the immediate fault output.
        for(slot=0;slot<DEPTH;slot=slot+1)for(code=0;code<256;code=code+1)begin
            dut.g_recording.tags[slot]=tag_value(code);
            dut.g_recording.read_pointer=BITS'(slot);
            dut.g_recording.write_pointer=BITS'(slot+1);
            occupied();check_edge();known_tag_checks=known_tag_checks+1;
        end
        // Unknown packed bit selects must retain the memory-read X result,
        // even when every tag has the same legal or illegal owner predicate.
        for(pattern=0;pattern<4;pattern=pattern+1)begin
            for(slot=0;slot<DEPTH;slot=slot+1)
                case(pattern)0:dut.g_recording.tags[slot]=0;1:dut.g_recording.tags[slot]=3;
                    2:dut.g_recording.tags[slot]=4'bxxxx;3:dut.g_recording.tags[slot]=4'bzzzz;endcase
            for(code=0;code<(1<<(2*BITS));code=code+1)begin
                selector=index_value(code);
                if((^selector)===1'bx)begin
                    dut.g_recording.read_pointer=selector;occupied();check_edge();
                    unknown_index_checks=unknown_index_checks+1;
                end
            end
        end
        // Count qualification, response and sticky fault each include X/Z.
        // A count with a known one and another unknown bit is known nonzero.
        for(code=0;code<256;code=code+1)for(cc=0;cc<5;cc=cc+1)
        for(rc=0;rc<4;rc=rc+1)for(sc=0;sc<4;sc=sc+1)begin
            dut.g_recording.tags[0]=tag_value(code);dut.g_recording.read_pointer=0;
            case(cc)0:dut.g_recording.count=0;1:dut.g_recording.count=1;
                2:dut.g_recording.count='x;3:dut.g_recording.count='z;
                4:begin dut.g_recording.count='x;dut.g_recording.count[0]=1;end endcase
            returned=digit(rc);dut.response_fault=digit(sc);
            check_edge();qualifier_checks=qualifier_checks+1;
        end
        $display("PASS owner predecode bits=%0d checks=%0d known_tag=%0d unknown_index=%0d qualifiers=%0d",
            BITS,checks,known_tag_checks,unknown_index_checks,qualifier_checks);$finish;
    end
endmodule
`default_nettype wire
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('checked predecode anchor drift: ' + old)
    return text.replace(old, new)


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    source = CORE.read_text()
    previous = once(source, NEW, FLAT)
    if sha(previous.encode()) != PREVIOUS_SHA256:
        raise ValueError('change outside bounded owner-veto tree')
    original = once(previous, FLAT, OLD)
    fixture = out / 'tb_owner_predecode.sv'
    fixture.write_text(TB)
    original_path = out / 'arbiter-before-predecode.sv'
    original_path.write_text(original)
    inputs = [CORE, LEGACY, Path(__file__).resolve()]
    hashes = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in inputs}
    result = dict(passed=False, source_sha256=hashes, original_inverse_sha256=sha(original.encode()),
                  fixture_sha256=sha(TB.encode()), previous_flat_source_sha256=PREVIOUS_SHA256,
                  no_sequential_state_or_retirement_change=True, tree_fanin_max=4,
                  physical_timing_gain_claimed=False, cases={}, synthesis=False, pnr=False,
                  hardware_tested=False, sram_programmed=False, flash_written=False,
                  limits='Live owner-veto cone and response retirement only; native queue/bridge regressions, actual mapping, routed timing and hardware are separate checks.')

    def execute(name, bits, path, expected_failure=None):
        stage = out / name
        stage.mkdir()
        argv = ['iverilog', '-g2012', '-Wall', '-s', 'tb_owner_predecode',
                '-Ptb_owner_predecode.BITS=' + str(bits), '-o', str(stage / 'test.vvp'),
                str(LEGACY), str(path), str(fixture)]
        c = subprocess.run(argv, capture_output=True, text=True, timeout=45)
        (stage / 'compile.log').write_text(c.stdout + c.stderr)
        if c.returncode:
            raise RuntimeError(name + ' compile failed: ' + c.stdout + c.stderr)
        command = ['vvp', str(stage / 'test.vvp')]
        v = subprocess.run(command, capture_output=True, text=True, timeout=90)
        log = v.stdout + v.stderr
        (stage / 'run.log').write_text(log)
        case = dict(bits=bits, compile_argv=argv, run_argv=command, returncode=v.returncode,
                    source_sha256=sha(path.read_bytes()), run_log_sha256=sha(log.encode()), run_log=log)
        if expected_failure:
            case['expected_failure'] = expected_failure
            case['rejected'] = v.returncode != 0 and expected_failure in log
            if not case['rejected']:
                raise RuntimeError(name + ' negative control escaped: ' + log)
        elif v.returncode or 'PASS owner predecode ' not in log:
            raise RuntimeError(name + ' failed: ' + log)
        result['cases'][name] = case
        print(name + ': ' + log.splitlines()[0], flush=True)

    try:
        # The inverse is an exact pre-change module, not a second rephrasing of
        # the candidate predicate. Run both against the same four-state oracle.
        execute('original_bits2', 2, original_path)
        for bits in range(2, 9):
            execute('predecode_bits' + str(bits), bits, CORE)
        for name, old, new in [
            ('wrong_head', 'case(read_pointer[level*2+:2])', 'case(write_pointer[level*2+:2])'),
            ('unknown_collapsed', 'owner_veto_tree[OWNER_VETO_LEVELS][0];', "(owner_veto_tree[OWNER_VETO_LEVELS][0] === 1'b1);"),
            ('unknown_address_zeroed', "                        default:selected=1'bx;\n                    endcase\n                end else begin:g_two", "                        default:selected=1'b0;\n                    endcase\n                end else begin:g_two"),
            ('fault_delayed', 'assign transport_fault_o=response_fault || response_fault_now;', 'assign transport_fault_o=response_fault;'),
        ]:
            mutant = out / (name + '.sv')
            mutant.write_text(once(source, old, new))
            execute(name, 2, mutant, 'live owner-veto four-state mismatch')
        result['source_inputs_unchanged_during_run'] = hashes == {
            str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in inputs}
        if not result['source_inputs_unchanged_during_run']:
            raise ValueError('source changed during verification')
        result['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
