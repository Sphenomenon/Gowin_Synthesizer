#!/usr/bin/env python3
"""Exact W9 flow-owner comparison against the frozen consumed RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import z3

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv'
REFERENCE = ROOT / 'sim/fixtures/workstation_hci_flow_owner_before_pool_compare.sv'
BENCH = ROOT / 'sim/tb_workstation_hci_flow_owner.sv'
REFERENCE_SHA = '8240975d4f1e119c86b7f5a0dd743f6db96dc67caa688c9992413a5a68e223e5'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('HCI pool comparison: ' + message)


def bench():
    header = REFERENCE.read_text().split(') (', 1)[1].split(');', 1)[0]
    header = re.sub(r'//[^\n]*', '', header)
    ports, wires, checks = [], [], []
    for direction, width, names in re.findall(
            r'\b(input|output)\s+(?:wire|reg)\s*(\[[^]]+\])?\s*([\w,\s]+?)(?=\binput|\boutput|$)', header):
        for name in names.strip().strip(',').split(','):
            name = name.strip()
            require(re.fullmatch(r'[A-Za-z_]\w*', name), 'unparsed port ' + name)
            ports.append('.' + name + '(' + ('ref_' if direction == 'output' else '') + name + ')')
            if direction == 'output':
                wires.append('wire ' + width.replace('HANDLE_SLOTS', '2') + ' ref_' + name + ';')
                checks.append(f'if({name} !== ref_{name})$fatal(1,"whole owner output {name} cycle=%0d",cycles);')
    require(len(ports) == 65 and len(checks) == 32, 'port inventory changed')
    scalars = ('br_capacity le_capacity br_length le_length shared_pool active is_le last_generation '
               'batch_unknown batch_pairs pending_opcode pending_owner lifecycle_slot free_slot '
               'acl_slot completion_slot br_return le_return completion_bad').split()
    checks.extend(f'if(dut.{name} !== reference.{name})$fatal(1,"whole owner state {name}");' for name in scalars)
    for array in ('numbers', 'generations', 'outstanding', 'returns'):
        for slot in range(2):
            checks.append(f'if(dut.{array}[{slot}] !== reference.{array}[{slot}])$fatal(1,"whole owner {array}[{slot}]");')
    extra = '\n'.join(wires) + '\nworkstation_hci_flow_owner_reference reference(' + ','.join(ports) + ');\n'
    extra += 'integer cycles=0,semantic_vectors=0,expected_error,expected_slot;\nalways @(posedge clk_i)begin #2;cycles=cycles+1;\n'
    extra += '\n'.join(checks) + '\nend\n'
    text = BENCH.read_text()
    require(text.count('workstation_hci_flow_owner dut(.*);') == 1, 'baseline instance drift')
    text = text.replace('workstation_hci_flow_owner dut(.*);', 'workstation_hci_flow_owner dut(.*);\n' + extra)
    require(text.count("dut.last_generation=32'hfffffffe;") == 1, 'rollover stimulus drift')
    text = text.replace("dut.last_generation=32'hfffffffe;", "dut.last_generation=32'hfffffffe;reference.last_generation=32'hfffffffe;")
    vectors = r'''
        for(integer shared=0;shared<2;shared=shared+1)begin
            reset_owner();configure(shared);open_handle(12'h031,1,le_gen);open_handle(12'h042,0,br_gen);
            acl_valid_i=1;acl_send_i=0;
            for(integer which=0;which<2;which=which+1)begin
                acl_handle_i=which ? 12'h042:12'h031;acl_generation_i=which ? br_gen:le_gen;
                for(integer count=0;count<65536;count=count+1)begin
                    acl_data_length_i=16'(count);#1;
                    expected_error=(count==0 || count>(which || shared ? 276:27)) ? 4:0;
                    if(acl_error_o!==3'(expected_error) || acl_invalid_o!==(expected_error!=0) ||
                       acl_ready_o!==(expected_error==0))$fatal(1,"independent pool oracle shared=%0d which=%0d count=%0d",shared,which,count);
                    semantic_vectors=semantic_vectors+1;
                end
            end
            acl_data_length_i=1;
            for(integer handle=0;handle<4096;handle=handle+1)begin
                acl_handle_i=12'(handle);handle_i=12'(handle);completion_handle_i=12'(handle);
                acl_generation_i=handle==49 ? le_gen:br_gen;#1;
                expected_slot=handle==49 ? 0:handle==66 ? 1:-1;
                expected_error=expected_slot==-1 ? 2:0;
                if(acl_error_o!==3'(expected_error) || dut.acl_slot!==expected_slot ||
                   dut.lifecycle_slot!==expected_slot || dut.completion_slot!==expected_slot)
                    $fatal(1,"independent handle oracle number=%0d",handle);
                semantic_vectors=semantic_vectors+1;
            end
            acl_valid_i=0;
        end
        if(semantic_vectors!=270336)$fatal(1,"semantic vector coverage changed");
        $display("PASS exact HCI comparison cycles=%0d public_outputs=32 internal_scalar_groups=19 array_groups=8 semantic_vectors=%0d",cycles,semantic_vectors);
'''
    anchor='        $display("PASS checks=%0d scenarios=%0d random_steps=10000",checks,scenarios);$finish;'
    require(text.count(anchor) == 1, 'baseline completion drift')
    return text.replace(anchor, vectors + '\n' + anchor)


def run(out, name, source):
    destination=out/name
    destination.mkdir()
    compile_args=['iverilog','-g2012','-s','tb_workstation_hci_flow_owner','-o',str(destination/'bench.vvp'),
                  str(source),str(out/'reference_source.sv'),str(out/'bench.sv')]
    compiled=subprocess.run(compile_args,text=True,capture_output=True,timeout=60)
    (destination/'compile.log').write_text(compiled.stdout+compiled.stderr)
    require(compiled.returncode==0,'compile failed: '+str(destination))
    result=subprocess.run(['vvp',str(destination/'bench.vvp')],text=True,capture_output=True,timeout=180)
    (destination/'simulation.log').write_text(result.stdout+result.stderr)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve()
    require(not out.exists(),'new output required')
    out.mkdir(parents=True)
    require(sha(REFERENCE)==REFERENCE_SHA,'frozen consumed W9 source changed')
    sources={str(p):sha(p) for p in (SOURCE,REFERENCE,BENCH,Path(__file__).resolve())}
    old=REFERENCE.read_text();current=SOURCE.read_text()
    require(old.count('acl_data_length_i > (is_le[acl_slot] && !shared_pool ? le_length : br_length)')==1,'old pool expression drift')
    for anchor in ('acl_data_length_i > br_length','acl_data_length_i > le_length',
                   '(is_le[acl_slot] && !shared_pool ? acl_exceeds_le : acl_exceeds_br)',
                   '!(|(numbers[at] ^ acl_handle_i))'):
        require(current.count(anchor)==1,'maintained expression drift: '+anchor)
    size,br,le=z3.BitVecs('size br le',16);selected=z3.Bool('selected')
    pool=z3.Solver();pool.add(z3.UGT(size,z3.If(selected,le,br)) !=
                             z3.If(selected,z3.UGT(size,le),z3.UGT(size,br)))
    a,b=z3.BitVecs('handle_a handle_b',12)
    handle=z3.Solver();handle.add((a==b)!=((a^b)==0))
    require(pool.check()==z3.unsat and handle.check()==z3.unsat,'Boolean proof mismatch')
    require(old.count('module workstation_hci_flow_owner #(')==1,'reference module anchor drift')
    (out/'reference_source.sv').write_text(old.replace('module workstation_hci_flow_owner #(',
        'module workstation_hci_flow_owner_reference #(',1))
    (out/'bench.sv').write_text(bench())
    baseline=run(out,'baseline',SOURCE)
    require(baseline.returncode==0 and 'PASS exact HCI comparison' in baseline.stdout,'whole-owner reference mismatch')
    mutations={
        'wrong_pool':('(is_le[acl_slot] && !shared_pool ? acl_exceeds_le : acl_exceeds_br)',
                      '(is_le[acl_slot] && !shared_pool ? acl_exceeds_br : acl_exceeds_le)'),
        'shared_le_uses_private_pool':('(is_le[acl_slot] && !shared_pool ? acl_exceeds_le : acl_exceeds_br)',
                                     '(is_le[acl_slot] ? acl_exceeds_le : acl_exceeds_br)'),
        'one_handle_bit_ignored':('!(|(numbers[at] ^ acl_handle_i))',
                                '!(|((numbers[at] ^ acl_handle_i) & 12\'hffe))'),
        'le_boundary_rejected':('acl_data_length_i > le_length','acl_data_length_i >= le_length'),
    }
    rejected={}
    for name,(before,after) in mutations.items():
        require(current.count(before)==1,'mutation anchor drift: '+name)
        source=out/(name+'_source.sv');source.write_text(current.replace(before,after))
        result=run(out,name,source)
        require(result.returncode!=0 and ('FATAL:' in result.stdout or 'FAIL ' in result.stdout),'mutant survived: '+name)
        rejected[name]=dict(rejected=True,source_sha256=sha(source),failure=next(x for x in result.stdout.splitlines() if 'FATAL:' in x or 'FAIL ' in x))
    require(all(sha(Path(p))==identity for p,identity in sources.items()),'source changed during verification')
    report=dict(schema=1,stage='hci_pool_and_handle_exact_combinational_rewrite',inputs_sha256=sources,
                frozen_reference_is_W9_consumed_source=True,whole_owner_summary=next(x for x in baseline.stdout.splitlines() if x.startswith('PASS exact')),
                independent_oracle_vectors=270336,full_length_domain_per_pool_and_handle=65536,full_handle_input_domain=4096,
                z3=dict(pool_free_bits=49,pool_comparison='UNSAT',handle_free_bits=24,handle_equality='UNSAT',version=z3.get_version_string()),
                mutants=rejected,source_seal_before_after=True,physical_resource_or_timing_gain_measured=False,hardware_tested=False)
    report['tools']={name:dict(path=shutil.which(name),sha256=sha(Path(shutil.which(name)))) for name in ('iverilog','vvp')}
    report['outputs_sha256']={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),summary=report['whole_owner_summary'],mutants=len(rejected),sha256=sha(out/'verification.json'))))


if __name__=='__main__':
    main()
