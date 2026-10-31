#!/usr/bin/env python3
"""Whole HCI modules versus W10 bytes, plus exact identity relations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import z3

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


def twin_bench(name):
    source = reference(name).read_text()
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    require(not out.exists(), 'new independent output required')
    out.mkdir(parents=True)
    inputs = {str(path): sha(path) for path in [*(OWNER / (module(name) + '.sv') for name in SHAS),
        *(reference(name) for name in SHAS), ROOT / 'sim/tb_workstation_hci_host_rx_owner.sv',
        ROOT / 'sim/tb_workstation_hci_native_transport.sv', Path(__file__).resolve()]}
    for name, identity in SHAS.items():
        require(sha(reference(name)) == identity, 'W10 reference changed: ' + name)
        expected = reference(name).read_text()
        for before, after, count, replacements in CHANGES[name]:
            require(expected.count(before) == count, 'exact source anchor ' + before)
            expected = expected.replace(before, after, replacements)
        require(expected == (OWNER / (module(name) + '.sv')).read_text(), 'bytes changed outside reviewed identity expressions: ' + name)
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
        s = z3.Solver()
        s.add((a == b) != (((a ^ b) & z3.BitVecVal((1 << width) - 2, width)) == 0))
        require(s.check() == z3.sat, 'missing-bit negative did not fail')
        mutants['ignored_bit_' + str(width)] = dict(rejected=True, counterexample={str(x): s.model().eval(x).as_long() for x in (a, b)})
    modules = [OWNER / (module(name) + '.sv') for name in ('native_transport', 'flow_owner', 'event_decoder',
               'host_rx_owner', 'host_bootstrap', 'cpu_mailbox', 'ble_queue')]
    refs = [out / (module(name) + '_reference.sv') for name in SHAS]
    report = dict(stage='W10_complete_HCI_identity_comparison', inputs_sha256=inputs, exact_bytes_outside_reviewed_comparisons=True,
                  relation_laws=laws, z3_version=z3.get_version_string(), whole_modules={}, mutants=mutants,
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
