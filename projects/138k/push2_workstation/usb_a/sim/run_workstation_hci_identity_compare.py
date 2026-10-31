#!/usr/bin/env python3
"""Whole HCI modules versus W10 bytes, plus grouped identity relations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import itertools
import z3
from run_workstation_hci_action_drift import apply_action_transform, reverse_action_transform

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / 'rtl/bluetooth/hci_owner'
FIXTURE = ROOT / 'sim/fixtures'
SHAS = {'host_rx_owner': '82ff377a3516d3be912cb98eedf5ef904d3720a69aedf673644bc63ede6a9105',
        'native_transport': 'a151aa426f4880dbcbf85239688ec910e8f43a2c2fb240e52161e166f029a10a'}
CHANGES = {
    'host_rx_owner': [
        ('    always @* begin', '    // Keep identity tests as bitwise trees, including the late disconnect\n    // generation, rather than a serial equality carry chain after selection.\n    always @* begin', 2, 1),
        ('tokens[at]==release_lease_i', '!(|(tokens[at]^release_lease_i))', 1, 1),
        ("{4'd0,known_handles_i[12*at+:12]}==rx_handle_i", "!(|({4'd0,known_handles_i[12*at+:12]}^rx_handle_i))", 1, 1),
        ('handles[at]==disconnect_handle_i', '!(|(handles[at]^disconnect_handle_i))', 2, 2),
        ('generations[at]==disconnect_generation_i', '!(|(generations[at]^disconnect_generation_i))', 2, 2),
        ('handles[at]==lease_handles[release_slot]', '!(|(handles[at]^lease_handles[release_slot]))', 1, 1),
        ('generations[at]==lease_generations[release_slot]', '!(|(generations[at]^lease_generations[release_slot]))', 1, 1),
        ('handles[at]!=known_handles_i[12*at+:12]', '(|(handles[at]^known_handles_i[12*at+:12]))', 1, 1),
        ('generations[at]!=known_generations_i[32*at+:32]', '(|(generations[at]^known_generations_i[32*at+:32]))', 1, 1),
        ('lease_handles[index]==disconnect_handle_i', '!(|(lease_handles[index]^disconnect_handle_i))', 1, 1),
        ('lease_generations[index]==disconnect_generation_i', '!(|(lease_generations[index]^disconnect_generation_i))', 1, 1),
        ('offer_handle==disconnect_handle_i', '!(|(offer_handle^disconnect_handle_i))', 1, 1),
        ('offer_generation==disconnect_generation_i', '!(|(offer_generation^disconnect_generation_i))', 1, 1),
    ],
    'native_transport': [
        ('    assign tx_handle={tx_header[1][3:0],tx_header[0]};', '    assign tx_handle={tx_header[1][3:0],tx_header[0]};\n    // Preserve the existing last-match priority while mapping handle tests\n    // as bitwise reductions before the selected generation fans out.', 1, 1),
        ('known_handles[12*at+:12]==tx_handle', '!(|(known_handles[12*at+:12]^tx_handle))', 1, 1),
        ('known_handles[12*at+:12]==decoder_handle', '!(|(known_handles[12*at+:12]^decoder_handle))', 1, 1),
        ('known_handles[12*at+:12]==rx_wire_handle[11:0]', '!(|(known_handles[12*at+:12]^rx_wire_handle[11:0]))', 1, 1),
    ]}

GROUPED_HOST = '''    // Preserve eight-bit boundaries: a full-width XOR reduction is otherwise
    // recognized as another equality carry chain by the device mapper.
    (* syn_keep=1 *) wire [HANDLE_SLOTS*4-1:0] disconnect_generation_changed_groups;
    wire [HANDLE_SLOTS-1:0] disconnect_generation_changed;
    for(genvar identity_handle=0;identity_handle<HANDLE_SLOTS;identity_handle=identity_handle+1)begin:disconnect_identity
        for(genvar identity_group=0;identity_group<4;identity_group=identity_group+1)begin:g_generation
            assign disconnect_generation_changed_groups[identity_handle*4+identity_group]=
                |(generations[identity_handle][identity_group*8+:8]^disconnect_generation_i[identity_group*8+:8]);
        end
        assign disconnect_generation_changed[identity_handle]=
            |disconnect_generation_changed_groups[identity_handle*4+:4];
    end
'''
GROUPED_NATIVE = '''    // Keep eight-bit compare groups separate from the final reduction so
    // the mapper cannot rebuild a full-width equality carry chain.
    (* syn_keep=1 *) wire [3:0] close_handle_changed_groups;
    wire [1:0] close_handle_changed;
    for(genvar identity_handle=0;identity_handle<2;identity_handle=identity_handle+1)begin:close_identity
        assign close_handle_changed_groups[identity_handle*2]=
            |(known_handles[identity_handle*12+:8]^decoder_handle[0+:8]);
        assign close_handle_changed_groups[identity_handle*2+1]=
            |(known_handles[identity_handle*12+8+:4]^decoder_handle[8+:4]);
        assign close_handle_changed[identity_handle]=|close_handle_changed_groups[identity_handle*2+:2];
    end
'''
GROUPED = {'host_rx_owner': GROUPED_HOST, 'native_transport': GROUPED_NATIVE}
for _name, _anchor, _before, _after, _count in (
        ('host_rx_owner', '    always @* begin\n        rx_owner=-1;',
         '!(|(generations[at]^disconnect_generation_i))', '!disconnect_generation_changed[at]', 2),
        ('native_transport', '    always @* begin\n        br_slot=-1;',
         '!(|(known_handles[12*at+:12]^decoder_handle))', '!close_handle_changed[at]', 1)):
    CHANGES[_name] += [(_anchor, GROUPED[_name] + _anchor, 1, 1),
                       (_before, _after, _count, _count)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('HCI exact identity comparison: ' + message)


def module(name):
    return 'workstation_hci_' + name


def reference(name):
    return FIXTURE / (module(name) + '_before_identity_compare.sv')


def ports(text):
    header = re.sub(r'//[^\n]*', '', text.split(') (', 1)[1].split(');', 1)[0])
    result = {}
    for direction, width, names in re.findall(r'\b(input|output)\s+(?:wire|reg)\s*(\[[^]]+\])?\s*([\w,\s]+?)(?=\binput|\boutput|$)', header):
        for name in names.strip().strip(',').split(','):
            name = name.strip()
            require(re.fullmatch(r'[A-Za-z_]\w*', name), 'port ' + name)
            result[name] = (direction, width.replace('HANDLE_SLOTS', '2').replace('RX_SLOTS', '4'))
    return result


def state_checks(text, prefix=''):
    body = text.split(');', 1)[1]
    result = []
    for names in re.findall(r'^\s*(?:\(\*[^*]*\*\)\s*)?(?:reg|integer)\s*(?:\[[^]]+\])?\s*([^;]+);', body, re.M):
        for entry in names.split(','):
            match = re.fullmatch(r'\s*(\w+)\s*(?:\[0:([^]]+)\])?\s*', entry)
            require(match is not None, 'state declaration ' + entry)
            name, upper = match.groups()
            count = {'RX_SLOTS-1': 4, 'HANDLE_SLOTS-1': 2, '5': 6, '3': 4, '279': 280, '2047': 2048}.get(upper, 1)
            require(upper is None or upper in ('RX_SLOTS-1', 'HANDLE_SLOTS-1', '5', '3', '279', '2047'), 'state array bound ' + entry)
            result += [prefix + name + ('[' + str(i) + ']' if upper is not None else '') for i in range(count)]
    return result


def twin_bench(name, reference_path=None):
    source = (reference_path or reference(name)).read_text()
    spec = ports(source)
    text = (ROOT / 'sim' / ('tb_' + module(name) + '.sv')).read_text()
    declarations = ['wire ' + width + ' reference_' + port + ';'
                    for port, (direction, width) in spec.items() if direction == 'output']
    if name == 'host_rx_owner':
        anchor = module(name) + ' dut(.*);'
        require(text.count(anchor) == 1, 'host RX instance')
        bindings = ['.' + port + '(' + ('reference_' if direction == 'output' else '') + port + ')'
                    for port, (direction, _) in spec.items()]
        instance = module(name) + '_reference reference(' + ','.join(bindings) + ');'
        text = text.replace(anchor, anchor + '\n' + '\n'.join(declarations) + '\n' + instance)
        anchor = "dut.last_lease=32'hfffffffe;"
        require(text.count(anchor) == 1, 'host RX rollover stimulus')
        text = text.replace(anchor, anchor + "reference.last_lease=32'hfffffffe;")
    else:
        match = re.search(r'^\s*' + module(name) + r'\s*#\((.*?)\)\s+dut\s*\((.*?)\);', text, re.S | re.M)
        require(match is not None, 'native instance')
        bindings = re.findall(r'\.(\w+)\(([^()]*)\)', match[2])
        require({port for port, _ in bindings} == set(spec), 'native named port inventory')
        body = ','.join('.' + port + '(' + ('reference_' + port if spec[port][0] == 'output' else value) + ')'
                        for port, value in bindings)
        instance = module(name) + '_reference #(' + match[1] + ') reference(' + body + ');'
        text = text[:match.end()] + '\n' + '\n'.join(declarations) + '\n' + instance + text[match.end():]
    states = state_checks(source)
    if name == 'native_transport':
        states += state_checks(reference('host_rx_owner').read_text(), 'host_rx.')
    checks = [('dut.' + port, 'reference_' + port) for port, (direction, _) in spec.items() if direction == 'output']
    checks += [('dut.' + state, 'reference.' + state) for state in states]
    sampler = 'integer identity_cycles=0;\nalways @(posedge dut.clk_i)begin #2;identity_cycles=identity_cycles+1;\n'
    sampler += '\n'.join('if(' + a + ' !== ' + b + ')$fatal(1,"IDENTITY TWIN ' + a + ' cycle=%0d",identity_cycles);' for a, b in checks)
    sampler += '\nend\nfinal $display("IDENTITY TWIN cycles=%0d outputs=' + str(len(spec) - sum(v[0] == 'input' for v in spec.values())) + ' states=' + str(len(states)) + '",identity_cycles);\n'
    require(text.count('endmodule') == 1, 'one test module required')
    return text.replace('endmodule', sampler + '\nendmodule'), dict(outputs=sum(v[0] == 'output' for v in spec.values()), states=len(states))


def simulate(out, name, sources, bench):
    dest = out / name
    dest.mkdir()
    (dest / 'bench.sv').write_text(bench)
    args = ['iverilog', '-g2012', '-s', 'tb_' + ('workstation_hci_host_rx_owner' if 'host_rx' in name else 'workstation_hci_native_transport'),
            '-o', str(dest / 'bench.vvp'), *map(str, sources), str(dest / 'bench.sv')]
    compile_result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    (dest / 'compile.log').write_text(compile_result.stdout + compile_result.stderr)
    require(compile_result.returncode == 0, 'compile ' + name)
    result = subprocess.run(['vvp', str(dest / 'bench.vvp')], capture_output=True, text=True, timeout=180)
    (dest / 'simulation.log').write_text(result.stdout + result.stderr)
    return result


def grouped_contract(name, text):
    require(text.count(GROUPED[name]) == 1, 'kept eight-bit grouped source boundary: ' + name)


def four_state_groups(out):
    """Exercise the actual captured group expressions, including X/Z dominance."""
    blocks = {}
    for name, expected in GROUPED.items():
        text = (OWNER / (module(name) + '.sv')).read_text()
        grouped_contract(name, text)
        start = text.index(expected)
        blocks[name] = text[start:start + len(expected)]
    declarations = '''module grouped_host(input [31:0] a,b,output [1:0] same);
localparam HANDLE_SLOTS=2;
wire [31:0] generations[0:1];
wire [31:0] disconnect_generation_i=b;
assign generations[0]=a;assign generations[1]=~a;
''' + blocks['host_rx_owner'] + '''assign same=~disconnect_generation_changed;endmodule
module grouped_native(input [11:0] a,b,output [1:0] same);
wire [23:0] known_handles={~a,a};wire [11:0] decoder_handle=b;
''' + blocks['native_transport'] + '''assign same=~close_handle_changed;endmodule
module tb_grouped_identity;
reg [31:0] a32,b32;reg [11:0] a12,b12;wire [1:0] same32,same12;
grouped_host host(a32,b32,same32);grouped_native native(a12,b12,same12);
integer checks=0;
task check32(input [31:0] a,b);begin a32=a;b32=b;#1;
if(same32!=={(~a==b),(a==b)})$fatal(1,"grouped32 a=%b b=%b",a,b);
checks=checks+1;end endtask
task check12(input [11:0] a,b);begin a12=a;b12=b;#1;
if(same12!=={(~a==b),(a==b)})$fatal(1,"grouped12 a=%b b=%b",a,b);
checks=checks+1;end endtask
initial begin
'''
    vectors = {}
    for width in (12, 32):
        rows = set()
        for a, b in itertools.product('01xz', repeat=2):
            rows.add((a * width, b * width))
        for fill, bit, a, b in itertools.product('01', range(width), '01xz', '01xz'):
            left, right = [fill] * width, [fill] * width
            left[width - 1 - bit], right[width - 1 - bit] = a, b
            rows.add((''.join(left), ''.join(right)))
        for boundary in range(8, width, 8):
            for values in itertools.product('01xz', repeat=4):
                left, right = ['0'] * width, ['0'] * width
                left[width - boundary], right[width - boundary] = values[:2]
                left[width - boundary - 1], right[width - boundary - 1] = values[2:]
                rows.add((''.join(left), ''.join(right)))
        vectors[width] = sorted(rows)
    bench = declarations + '\n'.join(
        f"check{width}({width}'b{a},{width}'b{b});" for width, rows in vectors.items() for a, b in rows)
    bench += '\n$display("PASS grouped finite four-state checks=%0d",checks);$finish;end\nendmodule\n'
    directory = out / 'grouped-four-state'; directory.mkdir()
    source, executable = directory / 'bench.sv', directory / 'bench.vvp'
    source.write_text(bench)
    compile_result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_grouped_identity', '-o', str(executable), str(source)],
                                    capture_output=True, text=True, timeout=60)
    (directory / 'compile.log').write_text(compile_result.stdout + compile_result.stderr)
    require(compile_result.returncode == 0, 'four-state group compilation')
    result = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=60)
    (directory / 'simulation.log').write_text(result.stdout + result.stderr)
    require(result.returncode == 0 and 'PASS grouped finite four-state' in result.stdout, 'four-state grouped relation')
    mutants = {}
    for name in GROUPED:
        current = (OWNER / (module(name) + '.sv')).read_text()
        for label, before, after in (
                ('keep_removed', '(* syn_keep=1 *)', '(* syn_keep=0 *)'),
                ('group_boundary_changed', '+:8]', '+:7]')):
            altered = current.replace(before, after, 1)
            require(altered != current, 'source negative anchor')
            try:
                grouped_contract(name, altered)
            except ValueError:
                mutants[name + '_' + label] = dict(rejected=True, scope='source boundary contract')
            else:
                require(False, 'grouped source negative survived')
    for name, before, after in (
            ('host', 'disconnect_generation_i[identity_group*8+:8]', "{1'b0,disconnect_generation_i[identity_group*8+:7]}"),
            ('native', 'decoder_handle[8+:4]', "{1'b0,decoder_handle[8+:3]}")):
        require(bench.count(before) == 1, 'functional group negative anchor')
        changed = directory / (name + '-ignored-high-bit.sv'); changed.write_text(bench.replace(before, after))
        binary = directory / (name + '-ignored-high-bit.vvp')
        compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_grouped_identity', '-o', str(binary), str(changed)],
                                     capture_output=True, text=True, timeout=60)
        require(compilation.returncode == 0, 'group negative compilation')
        failed = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=60)
        (directory / (name + '-ignored-high-bit.log')).write_text(failed.stdout + failed.stderr)
        require(failed.returncode != 0 and 'FATAL:' in failed.stdout, 'ignored group bit negative survived')
        mutants[name + '_ignored_high_bit'] = dict(rejected=True, scope='actual grouped four-state function',
            failure=next(line for line in failed.stdout.splitlines() if 'FATAL:' in line))
    return dict(vectors_by_width={str(width): len(rows) for width, rows in vectors.items()},
                comparisons_per_vector=2, summary=result.stdout.strip(), source_boundaries_from_actual_RTL=True), mutants


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    require(not out.exists(), 'new independent output required')
    out.mkdir(parents=True)
    inputs = {str(path): sha(path) for path in [*(OWNER / (module(name) + '.sv') for name in SHAS),
        *(reference(name) for name in SHAS), ROOT / 'sim/tb_workstation_hci_host_rx_owner.sv',
        ROOT / 'sim/tb_workstation_hci_native_transport.sv',
        ROOT / 'sim/run_workstation_hci_action_drift.py', Path(__file__).resolve()]}
    for name, identity in SHAS.items():
        require(sha(reference(name)) == identity, 'W10 reference changed: ' + name)
        expected = reference(name).read_text()
        for before, after, count, replacements in CHANGES[name]:
            require(expected.count(before) == count, 'exact source anchor ' + before)
            expected = expected.replace(before, after, replacements)
        if name == 'host_rx_owner':
            pre_action = expected
            expected = apply_action_transform(pre_action)
            require(reverse_action_transform(expected) == pre_action, 'exact reviewed action drift inverse')
        require(expected == (OWNER / (module(name) + '.sv')).read_text(), 'bytes changed outside reviewed identity expressions: ' + name)
        grouped_contract(name, expected)
        text = reference(name).read_text().replace(module(name) + ' #(', module(name) + '_reference #(', 1)
        if name == 'native_transport':
            text = text.replace('workstation_hci_host_rx_owner host_rx (', 'workstation_hci_host_rx_owner_reference host_rx (')
        (out / (module(name) + '_reference.sv')).write_text(text)
    laws, mutants = {}, {}
    for width in (12, 16, 32):
        a, b = z3.BitVecs('identity_a_' + str(width) + ' identity_b_' + str(width), width)
        s = z3.Solver()
        s.add(z3.Or((a == b) != ((a ^ b) == 0), (a != b) != ((a ^ b) != 0)))
        require(s.check() == z3.unsat, 'identity law ' + str(width))
        laws[str(width)] = dict(result='UNSAT', free_bits=width * 2)
        grouped_mismatch = z3.Or(*(z3.Extract(min(first + 7, width - 1), first, a ^ b) != 0
                                  for first in range(0, width, 8)))
        s = z3.Solver(); s.add((a != b) != grouped_mismatch)
        require(s.check() == z3.unsat, 'grouped identity law ' + str(width))
        laws[str(width)]['eight_bit_groups'] = 'UNSAT'
        s = z3.Solver()
        s.add((a == b) != (((a ^ b) & z3.BitVecVal((1 << width) - 2, width)) == 0))
        require(s.check() == z3.sat, 'missing-bit negative did not fail')
        mutants['ignored_bit_' + str(width)] = dict(rejected=True, counterexample={str(x): s.model().eval(x).as_long() for x in (a, b)})
    modules = [OWNER / (module(name) + '.sv') for name in ('native_transport', 'flow_owner', 'event_decoder',
               'host_rx_owner', 'host_bootstrap', 'cpu_mailbox', 'ble_queue')]
    refs = [out / (module(name) + '_reference.sv') for name in SHAS]
    four_state, group_mutants = four_state_groups(out)
    mutants.update(group_mutants)
    report = dict(stage='W10_complete_HCI_grouped_identity_comparison', inputs_sha256=inputs, exact_bytes_outside_reviewed_comparisons=True,
                  action_drift_reviewed_transform=True, original_full_drift_and_sequential_bytes_preserved=True,
                  relation_laws=laws, z3_version=z3.get_version_string(), whole_modules={}, mutants=mutants,
                  finite_four_state_grouped_relations=four_state,
                  new_registers_or_cycles=0, priorities_and_credit_owner_unchanged=True, physical_gain_measured=False, hardware_tested=False)
    for name in SHAS:
        bench, coverage = twin_bench(name)
        sources = [OWNER / 'workstation_hci_flow_owner.sv', OWNER / (module(name) + '.sv'), refs[0]] if name == 'host_rx_owner' else [*modules, *refs, OWNER / 'workstation_hci_ble_bridge.v']
        result = simulate(out, name, sources, bench)
        require(result.returncode == 0 and 'IDENTITY TWIN cycles=' in result.stdout and 'PASS ' in result.stdout, 'whole module mismatch ' + name)
        report['whole_modules'][name] = dict(coverage, summaries=[line for line in result.stdout.splitlines() if line.startswith(('PASS ', 'IDENTITY TWIN '))])
        before, after = ('!(|(tokens[at]^release_lease_i))', "1'b1") if name == 'host_rx_owner' else ('close_generation=known_generations[32*at+:32];', "close_generation=32'd0;")
        current = (OWNER / (module(name) + '.sv')).read_text()
        require(current.count(before) == 1, 'whole module mutant anchor')
        mutant = out / (module(name) + '_mutant.sv')
        mutant.write_text(current.replace(before, after))
        altered = [mutant if path == OWNER / (module(name) + '.sv') else path for path in sources]
        result = simulate(out, name + '_mutant', altered, bench)
        require(result.returncode != 0 and 'IDENTITY TWIN ' in result.stdout, 'whole module mutant survived ' + name)
        report['mutants']['whole_' + name] = dict(rejected=True, failure=next(line for line in result.stdout.splitlines() if 'FATAL:' in line))
    require({path: sha(path) for path in inputs} == inputs, 'input bytes changed during verification')
    report['outputs_sha256'] = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(output=str(out),whole_modules=report['whole_modules'],mutants=len(report['mutants']),sha256=sha(out/'verification.json'))))


if __name__ == '__main__':
    main()
