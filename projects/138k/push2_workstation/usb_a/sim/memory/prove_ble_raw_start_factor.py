#!/usr/bin/env python3
"""Prove accepted START factoring against the complete, immutable W11 raw store."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import z3

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'rtl/memory/workstation_ble_raw_ddr_store.sv'
REFERENCE = Path(__file__).with_name('fixtures') / 'workstation_ble_raw_ddr_store_before_start_factor.sv'
TB = Path(__file__).with_name('tb_ble_raw_ddr_store.sv')
BRIDGE = ROOT / 'rtl/memory/workstation_recording_ddr_native_bridge.sv'
OLD_SHA = 'ca212e5f93c9110ba63bb5c90399558bcb5edd8ed3d096d8d9ec5956c35363a7'
NEW_BLOCK = '''    wire start_context_bad=!memory_empty || !memory_closed || memory_active || memory_clear_pending ||
        memory_fetch_active || pack_frames!=0 || !memory_quiescent ||
        fifo_consumed!=command_event_target || command_generation!=memory_generation+1'b1 ||
        memory_generation==32'hffffffff;
    // Only a quiescent START uses this cofactor. The original expression is
    // retained for false/unknown quiescent, preserving procedural X behavior.
    reg start_fault_now,start_initialize;
    always @* begin
        start_fault_now=memory_fault_now;
        if(memory_quiescent)start_fault_now=transport_fault_i || native_protocol_fault_o ||
            unused_submitted || native_accept_i || read_response_i;
        start_initialize=0;
        // An occupied memory slot makes start_context_bad known true. Keep
        // its false and unknown cases explicit so binary mapping need not
        // share the complete command/read fault cone into wide START state.
        case(memory_quiescent)
            1'b0:begin end
            1'b1:begin
                if(memory_command_start)begin
                    if(memory_channel_fault || transport_fault_i || native_protocol_fault_o ||
                       unused_submitted || native_accept_i || read_response_i)begin end
                    else if(command_kind==CMD_START)begin
                        if(start_context_bad)begin end
                        else start_initialize=1;
                    end
                end
            end
            default:begin
                if(memory_command_start)begin
                    if(memory_channel_fault || start_fault_now)begin end
                    else if(command_kind==CMD_START)begin
                        if(start_context_bad)begin end
                        else start_initialize=1;
                    end
                end
            end
        endcase
    end
'''
NEW_INIT = '''            // Preserve the original START assignment priority, before CLEAR
            // completion. No request, acknowledgement or fault state moves.
            if(start_initialize)begin
                memory_generation<=command_generation;memory_next_index<=0;
                memory_committed<=0;write_address<=BASE_APP;
            end
'''
OLD_CONTEXT = '''if(!memory_empty || !memory_closed || memory_active || memory_clear_pending ||
                           memory_fetch_active || pack_frames!=0 || !memory_quiescent ||
                           fifo_consumed!=command_event_target || command_generation!=memory_generation+1'b1 ||
                           memory_generation==32'hffffffff)begin'''
OLD_INIT = '''memory_generation<=command_generation;memory_active<=1;memory_closed<=0;memory_empty<=0;
                            memory_next_index<=0;memory_committed<=0;write_address<=BASE_APP;completion_code<=0;'''
NEW_NARROW = 'memory_active<=1;memory_closed<=0;memory_empty<=0;completion_code<=0;'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('raw START factor: ' + message)


def replace_once(text, old, new):
    require(text.count(old) == 1, 'anchor drift: ' + old[:100])
    return text.replace(old, new)


def expression(text, name, declaration='wire'):
    found = re.search(r'\b' + declaration + r'\s*(?:\[[^]]+\]\s*)?' + name + r'\s*=([^;]+);', text)
    require(found is not None, 'missing actual equation ' + name)
    return ' '.join(found[1].split())


def source_equations(old, new):
    """All SAT abstractions are tied to exact source equations, never cell labels."""
    bridge = BRIDGE.read_text()
    equations = {
        'native_ready_o': expression(bridge, 'native_ready_o', 'assign'),
        'protocol_fault_now': expression(bridge, 'protocol_fault_now'),
        'transport_fault_o': expression(bridge, 'transport_fault_o', 'assign'),
    }
    expected = {
        'native_ready_o': 'native_accept_i && submitted_o',
        'protocol_fault_now': '(native_accept_i && (!submitted_o || !published_valid_i)) || (submitted_o && !published_valid_i)',
        'transport_fault_o': 'transport_fault_i || protocol_fault_o || protocol_fault_now',
        'native_commit': 'published_valid && native_ready',
        'native_read_commit': 'native_commit && !ddr_write_o',
        'command_expired': 'published_valid && !native_ready && command_wait>=COMMAND_TIMEOUT_CYCLES-1',
        'read_expired': 'read_outstanding && !read_response_i && read_wait>=READ_TIMEOUT_CYCLES-1',
        'response_bad': 'read_response_i && !read_outstanding && !native_read_commit',
        'memory_fault_now': 'bridge_fault || command_expired || read_expired || response_bad',
        'memory_quiescent': '!published_valid && !read_outstanding && !return_pending && !pack_word_valid',
        'memory_command_start': 'command_req_sync!=command_ack && !memory_command_active',
    }
    for name in expected:
        if name in equations:
            continue
        equations[name] = expression(new, name)
        require(equations[name] == expression(old, name), 'old/new actual equation differs ' + name)
    require(equations == expected, 'actual-source equation inventory drift')
    inverse = replace_once(new, NEW_BLOCK, '')
    inverse = replace_once(inverse, NEW_INIT, '')
    inverse = replace_once(inverse, 'if(start_context_bad)begin', OLD_CONTEXT)
    inverse = replace_once(inverse, NEW_NARROW, OLD_INIT)
    require(inverse == old, 'edits escape exact START factorization')
    # Moving the block crosses only one assignment to any moved target: the
    # mutually exclusive CMD_CLEAR generation assignment, with the same RHS.
    segment = old[old.index(OLD_INIT) + len(OLD_INIT):old.index('            if(memory_clear_pending && fifo_consumed==memory_clear_target')]
    crossed = re.findall(r'\b(memory_generation|memory_next_index|memory_committed|write_address)\s*<=\s*([^;]+);', segment)
    require(crossed == [('memory_generation', 'command_generation')], 'moved NBA crosses a differing write')
    require(new.index(NEW_INIT) < new.index('            if(memory_clear_pending && fifo_consumed==memory_clear_target'),
            'CLEAR completion priority changed')
    return dict(exact_full_source_inverse=True, source_equations=equations,
                crossed_assignments=crossed, reset_and_all_other_equations_byte_identical=True)


def symbolic():
    # Comparator results are independent predicates: all counter values, legal
    # and illegal, are covered without restricting reachable state.
    p, r, ret, pack, n, s, t, f, response, write, cb, rb, command, channel, bad = z3.Bools(
        'published read return_pending pack_word native submitted transport sticky response write command_limit read_limit command channel context_bad')
    kind = z3.BitVec('command_kind', 2)
    ready = z3.And(n, s)
    native = z3.And(p, ready)
    protocol = z3.Or(z3.And(n, z3.Or(z3.Not(s), z3.Not(p))), z3.And(s, z3.Not(p)))
    fault = z3.Or(t, f, protocol, z3.And(p, z3.Not(ready), cb),
                  z3.And(r, z3.Not(response), rb), z3.And(response, z3.Not(r), z3.Not(z3.And(native, z3.Not(write)))))
    quiet = z3.And(z3.Not(p), z3.Not(r), z3.Not(ret), z3.Not(pack))
    fast = z3.Or(t, f, s, n, response)
    selected = z3.If(quiet, fast, fault)
    # The complete source context includes !memory_quiescent. The other
    # comparisons remain one independent predicate, including illegal state.
    context_bad = z3.Or(bad, z3.Not(quiet))
    old_enable = z3.And(command, z3.Not(z3.Or(channel, fault)), kind == 0, z3.Not(context_bad))
    # Exact binary case(quiet): zero cannot initialize, one uses the cofactor;
    # the X/Z default is checked by the four-state complete-module proof.
    new_enable = z3.And(quiet, command, z3.Not(z3.Or(channel, fast)), kind == 0, z3.Not(context_bad))
    solver = z3.Solver()
    solver.add(z3.Or(fault != selected, old_enable != new_enable))
    require(solver.check() == z3.unsat, 'actual-source full-domain fault/START enable differs')
    # Earlier native/FIFO results and later CLEAR results are unrestricted.
    # The crossed CMD_CLEAR generation write has the identical RHS; all other
    # source assignments are byte-identical, as required by source_equations.
    before = [z3.BitVec('before_' + str(i), 32 if i < 3 else 29) for i in range(4)]
    gen = z3.BitVec('command_generation', 32)
    base = z3.BitVec('BASE_APP', 29)
    clear = z3.Bool('clear_completion')
    command_clear = z3.Bool('command_clear_accepted')
    init = [gen, z3.BitVecVal(0, 32), z3.BitVecVal(0, 32), base]
    old_next = [z3.If(old_enable, value, b) for b, value in zip(before, init)]
    new_before = [z3.If(command_clear, gen, before[0]), *before[1:]]
    old_next[0] = z3.If(command_clear, gen, old_next[0])
    new_next = [z3.If(new_enable, value, b) for b, value in zip(new_before, init)]
    # The two case arms cannot execute together; do not assume any other state.
    solver2 = z3.Solver()
    solver2.add(z3.Implies(command_clear, kind == 1))
    for values in (old_next, new_next):
        values[1] = z3.If(clear, 0, values[1])
        values[2] = z3.If(clear, 0, values[2])
    solver2.add(z3.Or(*[a != b for a, b in zip(old_next, new_next)]))
    require(solver2.check() == z3.unsat, 'four moved next-state values differ')
    return dict(fault_and_START_enable='UNSAT', four_moved_next_state_values='UNSAT',
                boolean_predicates=15, command_kind_bits=2, reachable_state_assumptions=False,
                earlier_values_and_CLEAR_completion_unrestricted=True, z3_version=z3.get_version_string())


def stripped(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def split_top(text):
    depth = 0
    start = 0
    parts = []
    for i, char in enumerate(text):
        if char in '([{': depth += 1
        elif char in ')]}': depth -= 1
        elif char == ',' and depth == 0:
            parts.append(text[start:i].strip()); start = i + 1
    parts.append(text[start:].strip())
    return parts


def inventories(text):
    text = stripped(text)
    header, body = text.split(') (', 1)[1].split(');', 1)
    ports = {}
    direction = None
    for token in split_top(header):
        match = re.match(r'(input|output)\s+(wire|reg)\s*(\[[^]]+\])?\s*(\w+)$', token)
        if match:
            direction, kind, width, name = match.groups()
        else:
            require(direction is not None and re.fullmatch(r'\w+', token), 'port parse ' + token)
            name = token
        ports[name] = (direction, kind, width or '')
    declarations = {}
    for match in re.finditer(r'\b(reg|wire)\s*(\[[^]]+\])?\s*([^;]+);', body):
        kind, width, names = match.groups()
        for token in split_top(names):
            name = re.match(r'(\w+)\s*(\[[^]]+\])?(?:\s*=.*)?$', token, flags=re.S)
            require(name is not None, 'body declaration parse ' + token)
            declarations[name[1]] = (kind, width or '', name[2] or '')
    states = sorted({name for name, (kind, _, _) in declarations.items() if kind == 'reg'} |
                    {name for name, (d, kind, _) in ports.items() if d == 'output' and kind == 'reg'})
    nets = sorted(name for name, (kind, _, array) in declarations.items() if kind == 'wire' and not array)
    return ports, states, nets


def checks_text(ports, states, nets):
    names = sorted(set(states + nets + [name for name, p in ports.items() if p[0] == 'output']))
    checks = ['if(dut.' + name + '!==reference.' + name + ')$fatal(1,"complete raw twin ' + name + ' case=%0d t=%0t",twin_case,$time);' for name in names]
    fifo = ['write_binary', 'write_gray', 'read_binary', 'read_gray', 'read_gray_meta', 'read_gray_sync', 'write_gray_meta', 'write_gray_sync']
    checks += ['if(dut.capture_fifo.' + name + '!==reference.capture_fifo.' + name + ')$fatal(1,"FIFO ' + name + '");' for name in fifo]
    checks += ['if(dut.native_bridge.' + name + '!==reference.native_bridge.' + name + ')$fatal(1,"native bridge ' + name + '");' for name in ('submitted_o', 'protocol_fault_o')]
    checks += ['if(dut.g_cache[' + str(bank) + '].' + half + '.data_q!==reference.g_cache[' + str(bank) + '].' + half + '.data_q)$fatal(1,"cache read state");' for bank in range(2) for half in ('low_half', 'high_half')]
    checks += ['if(dut.cache_low[' + str(bank) + ']!==reference.cache_low[' + str(bank) + '] || dut.cache_high[' + str(bank) + ']!==reference.cache_high[' + str(bank) + '])$fatal(1,"cache bank output");' for bank in range(2)]
    return '\n'.join(checks), names


def reference_instance(ports, connections, parameters):
    inputs = {name for name, info in ports.items() if info[0] == 'input'}
    require(inputs <= connections.keys(), 'unconnected input inventory')
    require(not (connections.keys() - ports.keys()), 'unknown bench connection')
    bindings = ['.' + name + '(' + (connections[name] if info[0] == 'input' else '') + ')' for name, info in ports.items()]
    return 'workstation_ble_raw_ddr_store_reference #(' + parameters + ') reference(' + ','.join(bindings) + ');\n'


def memory_checks():
    result = []
    for bank in range(2):
        for half in ('low_half', 'high_half'):
            path = 'g_cache[' + str(bank) + '].' + half + '.memory[twin_i]'
            result.append('for(twin_i=0;twin_i<1024;twin_i=twin_i+1)if(dut.' + path + '!==reference.' + path + ')$fatal(1,"complete cache contents");')
    return '\n'.join(result)


def twin_bench(old, ports, states, nets):
    text = TB.read_text()
    match = re.search(r'workstation_ble_raw_ddr_store #\((.*?)\) dut\((.*?)\);', text, re.S)
    require(match is not None, 'full bench instance')
    connections = dict(re.findall(r'\.(\w+)\(([^()]*)\)', match[2]))
    # Existing bench intentionally leaves only this output unconnected; compare
    # it hierarchically along with every declared output, including the last.
    require(ports.keys() - connections.keys() == {'native_protocol_fault_o'}, 'bench omitted-port inventory drift')
    extra = reference_instance(ports, connections, match[1])
    checks, compared = checks_text(ports, states, nets)
    extra += 'integer twin_edges=0,twin_case=0,twin_i;\n'
    extra += 'always @(posedge clk or negedge clk or posedge memory_clk or negedge memory_clk or rst_n)begin #0.01;twin_edges=twin_edges+1;\n' + checks + '\nend\n'
    extra += '''generate if(FIFO_BITS>=8)begin:twin_large
always @(posedge clk or negedge clk or posedge memory_clk or negedge memory_clk)begin #0.01;
if({dut.capture_fifo.g_large_head.full_q,dut.capture_fifo.g_large_head.even_q,dut.capture_fifo.g_large_head.odd_q,dut.capture_fifo.g_large_head.head_odd}!==
   {reference.capture_fifo.g_large_head.full_q,reference.capture_fifo.g_large_head.even_q,reference.capture_fifo.g_large_head.odd_q,reference.capture_fifo.g_large_head.head_odd})$fatal(1,"complete large FIFO head state");end
final begin
for(integer i=0;i<(1<<(FIFO_BITS-1));i=i+1)if(dut.capture_fifo.g_large_head.even_memory[i]!==reference.capture_fifo.g_large_head.even_memory[i] || dut.capture_fifo.g_large_head.odd_memory[i]!==reference.capture_fifo.g_large_head.odd_memory[i])$fatal(1,"complete large FIFO contents");end
end else begin:twin_small
final begin
for(integer i=0;i<(1<<FIFO_BITS);i=i+1)if(dut.capture_fifo.g_small_head.memory[i]!==reference.capture_fifo.g_small_head.memory[i])$fatal(1,"complete small FIFO contents");end
end endgenerate
'''
    extra += 'final begin\n' + memory_checks() + '\n$display("PASS complete W11 raw twin edges=%0d outputs=' + str(sum(p[0] == 'output' for p in ports.values())) + ' registers=' + str(len(states)) + ' compared_signals=' + str(len(compared)) + '",twin_edges);end\n'
    text = text[:match.end()] + '\n' + extra + text[match.end():]
    forces = re.findall(r'\bforce\s+dut\.(\w+)\s*=([^;]+);', text)
    releases = re.findall(r'\brelease\s+dut\.(\w+)\s*;', text)
    for name, value in set(forces):
        text = text.replace('force dut.' + name + '=' + value + ';', 'force dut.' + name + '=' + value + ';force reference.' + name + '=' + value + ';')
    for name in set(releases):
        text = text.replace('release dut.' + name + ';', 'release dut.' + name + ';release reference.' + name + ';')
    require(len(forces) == len(re.findall(r'\bforce\s+reference\.', text)), 'not every source force mirrored')
    require(len(releases) == len(re.findall(r'\brelease\s+reference\.', text)), 'not every source release mirrored')
    return text, dict(outputs=[name for name, p in ports.items() if p[0] == 'output'], registers=states,
                      compared_common_signals=compared, mirrored_forces=len(forces), mirrored_releases=len(releases),
                      final_RAM_cells=4096, real_FIFO_cache_native_bridge=True, no_unknown_mask=True)


def four_state_bench(equations, new):
    # Extract the actual definitions, substituting only names at the bridge
    # instance boundary and the two independent counter comparator predicates.
    eq = dict(equations)
    eq.pop('memory_command_start')
    bridge_names = {'native_ready_o':'native_ready', 'protocol_fault_now':'protocol_fault_now', 'transport_fault_o':'bridge_fault'}
    declaration = []
    for name, value in eq.items():
        if name in bridge_names:
            for before, after in [('published_valid_i','published_valid'), ('submitted_o','unused_submitted'), ('protocol_fault_o','native_protocol_fault_o')]:
                value = re.sub(r'\b' + before + r'\b', after, value)
            name = bridge_names[name]
        value = value.replace('command_wait>=COMMAND_TIMEOUT_CYCLES-1', 'command_limit')
        value = value.replace('read_wait>=READ_TIMEOUT_CYCLES-1', 'read_limit')
        declaration.append('wire ' + name + '=' + value + ';')
    guard = NEW_BLOCK[NEW_BLOCK.index('    reg start_fault_now'):]
    return '''`timescale 1ns/1ps
module four_state;
function automatic logic digit(input integer n);case(n)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase endfunction
reg published_valid,read_outstanding,return_pending,pack_word_valid,native_accept_i,unused_submitted,transport_fault_i,native_protocol_fault_o,read_response_i,ddr_write_o,command_limit,read_limit;
reg memory_command_start,memory_channel_fault,start_context_bad;
reg [1:0] command_kind;localparam [1:0] CMD_START=0;
''' + '\n'.join(declaration) + '\n' + guard + '''
reg old_initialize;integer vector_index,bit_index;reg [11:0] flags;integer guards=0;
initial begin
memory_command_start=0;memory_channel_fault=0;command_kind=0;start_context_bad=0;
for(vector_index=0;vector_index<16777216;vector_index=vector_index+1)begin
for(bit_index=0;bit_index<12;bit_index=bit_index+1)flags[bit_index]=digit((vector_index>>(2*bit_index))&3);
{published_valid,read_outstanding,return_pending,pack_word_valid,native_accept_i,unused_submitted,transport_fault_i,native_protocol_fault_o,read_response_i,ddr_write_o,command_limit,read_limit}=flags;
#0.001;
if(start_fault_now!==memory_fault_now)$fatal(1,"actual-source full four-state fault mismatch vector=%h q=%b old=%b new=%b",vector_index,memory_quiescent,memory_fault_now,start_fault_now);
end
// Guard proof is independent of context validity or reachability. Case and
// nested if semantics are compared including all sixteen X/Z kind encodings.
published_valid=0;read_outstanding=0;return_pending=0;pack_word_valid=0;unused_submitted=0;native_accept_i=0;transport_fault_i=0;read_response_i=0;
for(vector_index=0;vector_index<4096;vector_index=vector_index+1)begin
memory_command_start=digit(vector_index&3);memory_channel_fault=digit((vector_index>>2)&3);
start_context_bad=digit((vector_index>>4)&3);native_protocol_fault_o=digit((vector_index>>6)&3);
command_kind={digit((vector_index>>10)&3),digit((vector_index>>8)&3)};
#0.001;
old_initialize=0;
if(memory_command_start)begin
 if(memory_channel_fault || memory_fault_now)begin end
 else case(command_kind)
 CMD_START:begin if(start_context_bad)begin end else old_initialize=1;end
 default:begin end
 endcase
end
if(old_initialize!==start_initialize)$fatal(1,"procedural START guard mismatch vector=%h old=%b new=%b",vector_index,old_initialize,start_initialize);
guards=guards+1;
end
$display("PASS actual-source four-state fault combinations=16777216 predicates=12 procedural_guard_combinations=%0d",guards);$finish;
end endmodule
'''


def directed_bench(ports, states, nets):
    inputs = {name: ('clk' if name == 'clk_i' else 'memory_clk' if name == 'memory_clk_i' else 'rst_n' if name == 'rst_ni' else name) for name, p in ports.items() if p[0] == 'input'}
    declarations = '\n'.join('reg ' + p[2] + ' ' + inputs[name] + '=0;' for name, p in ports.items() if p[0] == 'input')
    bindings = ','.join('.' + name + '(' + (inputs[name] if p[0] == 'input' else '') + ')' for name, p in ports.items())
    parameters = ".BASE_APP(29'h0040000),.FIFO_ADDRESS_BITS(3),.COMMAND_TIMEOUT_CYCLES(2048),.READ_TIMEOUT_CYCLES(2048)"
    check, _ = checks_text(ports, states, nets)
    def both(name, value):
        return 'dut.' + name + '=' + value + ';reference.' + name + '=' + value + ';'
    zero = '\n'.join(both(name, "'0") for name in states)
    base = {'control_release':"2'b11", 'memory_release':"2'b11", 'command_req':"1'b1", 'command_req_meta':"1'b1", 'command_req_sync':"1'b1", 'command_generation':"32'd8", 'memory_generation':"32'd7", 'memory_empty':"1'b1", 'memory_closed':"1'b1", 'fifo_consumed':"4'd2", 'command_event_target':"4'd2", 'memory_clear_target':"4'd2", 'memory_next_index':"32'd23", 'memory_committed':"32'd19", 'write_address':"29'h0040058", 'completion_code':"4'hf"}
    base_text = '\n'.join(both(name, value) for name, value in base.items())
    cases = [
        ('accepted_start', {}, "if(dut.memory_generation!==8 || dut.memory_next_index!==0 || dut.memory_committed!==0 || dut.write_address!==29'h0040000 || dut.memory_active!==1)$fatal(1,\"accepted START must initialize\");"),
        ('native_write_retirement', {'published_valid':'1', 'native_bridge.submitted_o':'1', 'ddr_write_o':'1', 'published_frames':'3', 'native_accept_i':'1'}, "if(dut.memory_generation!==7 || dut.memory_committed!==22 || dut.write_address!==29'h0040060 || dut.memory_channel_fault!==1)$fatal(1,\"illegal START preserves native retirement\");"),
        ('native_read_and_response', {'published_valid':'1', 'native_bridge.submitted_o':'1', 'native_accept_i':'1', 'read_response_i':'1', 'memory_fetch_active':'1', 'published_generation':'7'}, "if(dut.memory_generation!==7 || dut.return_pending!==1 || dut.memory_channel_fault!==1)$fatal(1,\"same-edge real read response then illegal START\");"),
        ('clear_completion', {'memory_clear_pending':'1'}, "if(dut.memory_generation!==7 || dut.memory_next_index!==0 || dut.memory_committed!==0 || dut.completion_kind!==1 || dut.completion_generation!==7 || dut.completion_code!==0)$fatal(1,\"CLEAR completion retains last assignment priority\");"),
        ('cancel', {'cancel_sync':'1'}, "if(dut.memory_generation!==8 || dut.memory_fetch_cancel!==1 || dut.cancel_seen!==1)$fatal(1,\"START with cancellation\");"),
        ('spurious_native', {'native_accept_i':'1'}, "if(dut.memory_generation!==7 || dut.write_address!==29'h0040058 || dut.memory_channel_fault!==1)$fatal(1,\"spurious native veto\");"),
        ('stale_submitted', {'native_bridge.submitted_o':'1'}, "if(dut.memory_generation!==7 || dut.memory_channel_fault!==1)$fatal(1,\"stale submitted veto\");"),
        ('stray_response', {'read_response_i':'1'}, "if(dut.memory_generation!==7 || dut.memory_channel_fault!==1)$fatal(1,\"stray response veto\");"),
        ('X_context', {'memory_empty':"1'bx"}, "if(dut.memory_generation!==8 || dut.memory_next_index!==0)$fatal(1,\"X context takes procedural else\");"),
        ('Z_context', {'memory_empty':"1'bz"}, "if(dut.memory_generation!==8)$fatal(1,\"Z context takes procedural else\");"),
        ('X_channel', {'memory_channel_fault':"1'bx"}, "if(dut.memory_generation!==8)$fatal(1,\"X channel takes procedural else\");"),
        ('X_native', {'native_accept_i':"1'bx"}, "if(dut.memory_generation!==8)$fatal(1,\"X native fault takes procedural else\");"),
        ('Z_response', {'read_response_i':"1'bz"}, "if(dut.memory_generation!==8)$fatal(1,\"Z response fault takes procedural else\");"),
        ('X_quiescent_fallback', {'published_valid':"1'bx", 'native_bridge.submitted_o':'1'}, "if(dut.memory_generation!==8)$fatal(1,\"X quiescent retains full fault fallback\");"),
        ('Z_quiescent_fallback', {'published_valid':"1'bz", 'native_bridge.submitted_o':'1'}, "if(dut.memory_generation!==8)$fatal(1,\"Z publication retains full fault fallback\");"),
        ('X_command', {'command_req_sync':"1'bx"}, "if(dut.memory_generation!==7)$fatal(1,\"unknown command does not execute if\");"),
        ('X_kind', {'command_kind':"2'b0x"}, "if(dut.memory_generation!==7 || dut.memory_channel_fault!==1)$fatal(1,\"unknown kind selects case default\");"),
        ('generation_wrap', {'memory_generation':"32'hffffffff", 'command_generation':'0'}, "if(dut.memory_generation!==32'hffffffff || dut.memory_channel_fault!==1)$fatal(1,\"generation never wraps\");"),
    ]
    case_text = []
    for index, (name, values, assertion) in enumerate(cases, 1):
        assigns = []
        for signal, value in values.items():
            assigns.append(signal + '=' + value + ';' if signal in inputs else both(signal, value))
        case_text.append('set_base; twin_case=' + str(index) + ';\n' + '\n'.join(assigns) + '\nstep;\n' + assertion + '\n$display("PASS directed ' + name + '");')
    random_states = '\n'.join('random_bits=random_value();' + both(name, 'random_bits[$bits(dut.' + name + ')-1:0]') for name in states if name not in ('control_release', 'memory_release'))
    return '''`timescale 1ns/1ps
module directed;
''' + declarations + '\nworkstation_ble_raw_ddr_store #(' + parameters + ') dut(' + bindings + ');\n' + reference_instance(ports, inputs, parameters) + '''
integer twin_case=0,twin_edges=0,random_seed=32'h13861101;reg [255:0] random_bits;
function automatic [255:0] random_value;
integer chunk,bit_index;reg [31:0] low_bits,high_bits;begin
for(chunk=0;chunk<8;chunk=chunk+1)begin
low_bits=$random(random_seed);high_bits=$random(random_seed);
for(bit_index=0;bit_index<32;bit_index=bit_index+1)begin
case({high_bits[bit_index],low_bits[bit_index]})
0:random_value[chunk*32+bit_index]=0;1:random_value[chunk*32+bit_index]=1;
2:random_value[chunk*32+bit_index]=1'bx;3:random_value[chunk*32+bit_index]=1'bz;
endcase
end end end endfunction

task compare_all;begin
''' + check + '''
end endtask

task set_base;begin
memory_clk=0;rst_n=0;#1;rst_n=1;
''' + '\n'.join(name + "='0;" for name in inputs if name not in ('clk_i','memory_clk_i','rst_ni')) + '\n' + zero + '\n' + base_text + '\n' + both('native_bridge.submitted_o','0') + both('native_bridge.protocol_fault_o','0') + '''
#0.1;compare_all;
end endtask

task step;begin #1;memory_clk=1;#0.1;compare_all;twin_edges=twin_edges+1;memory_clk=0;#0.1;compare_all;end endtask
initial begin
''' + '\n'.join(case_text) + '''
// Every old register is independently randomized, including illegal lifecycle,
// descriptor, acknowledgement and generation combinations. No reachability
// filter, assumption or X mask is applied before or after the memory edge.
for(integer i=0;i<4096;i=i+1)begin
set_base;twin_case=100+i;
''' + random_states + '\n' + '\n'.join('random_bits=random_value();' + both('native_bridge.' + name, 'random_bits[0]') for name in ('submitted_o','protocol_fault_o')) + '\n' + '\n'.join('random_bits=random_value();' + name + '=random_bits[$bits(' + name + ')-1:0];' for name in ('slot_ready_i','native_accept_i','read_response_i','read_data_i','transport_fault_i')) + '''
#0.1;compare_all;step;
end
$display("PASS complete arbitrary-state raw twin directed_cases=''' + str(len(cases)) + ''' random_four_state_edges=4096 total_edges=%0d no_reachability_assumptions=1",twin_edges);$finish;
end endmodule
''', [name for name, _, _ in cases]


def simulate(output, name, sources, top, parameters=(), expected=None, timeout=60):
    compile_argv = ['iverilog', '-g2012', '-s', top, '-o', str(output / (name + '.vvp'))]
    compile_argv += ['-P' + top + '.' + key + '=' + str(value) for key, value in parameters]
    compile_argv += list(map(str, sources))
    compiled = subprocess.run(compile_argv, capture_output=True, text=True, timeout=30)
    compile_log = output / (name + '-compile.log'); compile_log.write_text(compiled.stdout + compiled.stderr)
    require(compiled.returncode == 0 and not compile_log.read_text().strip(), 'compile diagnostics ' + name + ': ' + compile_log.read_text())
    run = subprocess.run(['vvp', str(output / (name + '.vvp'))], capture_output=True, text=True, timeout=timeout)
    log = output / (name + '.log'); log.write_text(run.stdout + run.stderr)
    if expected:
        require(run.returncode != 0 and expected in log.read_text(), 'specific negative control escaped ' + name + ': ' + log.read_text())
    else:
        require(run.returncode == 0 and 'PASS ' in log.read_text(), name + ': ' + log.read_text())
    print(('PASS rejected ' if expected else 'PASS ') + name, flush=True)
    return dict(compile_argv=compile_argv, returncode=run.returncode, compile_log_sha256=sha(compile_log),
                run_log_sha256=sha(log), summary=log.read_text().strip(), expected_failure=expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    require(sha(REFERENCE) == OLD_SHA, 'complete W11 reference identity')
    clear_proof = Path(__file__).with_name('prove_ble_raw_clear_quiescent_case.py')
    clear_baseline = Path(__file__).with_name('fixtures') / 'workstation_ble_raw_ddr_store_before_clear_case.sv'
    clear_spec = importlib.util.spec_from_file_location('clear_inverse', clear_proof)
    clear = importlib.util.module_from_spec(clear_spec); clear_spec.loader.exec_module(clear)
    require(sha(clear_baseline) == clear.BASELINE_SHA256, 'immutable pre-CLEAR reference identity')
    old, new = REFERENCE.read_text(), clear.restore_before_clear(SOURCE.read_text())
    require(new == clear_baseline.read_text(), 'exact CLEAR inverse equals immutable W13 source')
    normalized = output / 'normalized-before-clear.sv'; normalized.write_text(new)
    structure = source_equations(old, new)
    proof = symbolic()
    ports, states, nets = inventories(old)
    reference_copy = output / 'reference.sv'
    reference_copy.write_text(replace_once(old, 'module workstation_ble_raw_ddr_store #(', 'module workstation_ble_raw_ddr_store_reference #('))
    twin, inventory = twin_bench(old, ports, states, nets)
    (output / 'twin.sv').write_text(twin)
    directed, directed_cases = directed_bench(ports, states, nets)
    (output / 'directed.sv').write_text(directed)
    (output / 'four-state.sv').write_text(four_state_bench(structure['source_equations'], new))
    deps = [ROOT / 'rtl/memory/workstation_sdp.sv', ROOT / 'rtl/music/music_async_fifo.sv', BRIDGE]
    source_paths = (SOURCE, REFERENCE, TB, BRIDGE, *deps[:2], Path(__file__).resolve(), clear_proof, clear_baseline)
    hashes = {str(path.relative_to(ROOT)):sha(path) for path in source_paths}
    result = dict(passed=False, complete_W11_source_structure=structure, full_domain_two_state=proof,
                  whole_twin_inventory=inventory, directed_cases=directed_cases, inputs_sha256=hashes,
                  maintained_source_sha256=sha(SOURCE), normalized_pre_CLEAR_sha256=sha(normalized),
                  exact_reviewed_CLEAR_inverse=True, source_implementation=True,
                  synthesis=False, pnr=False, hardware_tested=False, sram_programmed=False, flash_written=False,
                  timing_or_resource_improvement_claimed=False, cases={})
    try:
        for name, params in [('fifo8_async_memory', [('FIFO_BITS',8),('MEM_HALF',7)]), ('fifo3_100mhz_memory', [('FIFO_BITS',3),('MEM_HALF',5)])]:
            result['cases'][name] = simulate(output, name, [output/'twin.sv', normalized, reference_copy, *deps], 'tb_ble_raw_ddr_store', params)
        result['cases']['arbitrary_state'] = simulate(output, 'arbitrary-state', [output/'directed.sv', normalized, reference_copy, *deps], 'directed', timeout=180)
        mutants = [
            ('drop_native_veto', '                       unused_submitted || native_accept_i || read_response_i)begin end', '                       unused_submitted || read_response_i)begin end'),
            ('drop_submitted_veto', '                       unused_submitted || native_accept_i || read_response_i)begin end', '                       native_accept_i || read_response_i)begin end'),
            ('drop_response_veto', '                       unused_submitted || native_accept_i || read_response_i)begin end', '                       unused_submitted || native_accept_i)begin end'),
            ('omit_unknown_quiescent_fallback', 'if(memory_quiescent)start_fault_now=', 'start_fault_now='),
            ('positive_guard_changes_X_else', "                        else start_initialize=1;\n                    end\n                end\n            end\n            default:", "                        else start_initialize=!start_context_bad;\n                    end\n                end\n            end\n            default:"),
            ('wrong_generation', 'memory_generation<=command_generation;memory_next_index<=0;', "memory_generation<=command_generation+1'b1;memory_next_index<=0;"),
            ('missing_committed_reset', 'memory_committed<=0;write_address<=BASE_APP;\n            end', 'write_address<=BASE_APP;\n            end'),
        ]
        for name, anchor, replacement in mutants:
            path = output / (name + '.sv'); path.write_text(replace_once(new, anchor, replacement))
            result['cases'][name] = simulate(output, name, [output/'directed.sv', path, reference_copy, *deps], 'directed', expected='complete raw twin')
        result['cases']['four_state'] = simulate(output, 'four-state', [output/'four-state.sv'], 'four_state', timeout=300)
        require(hashes == {str(path.relative_to(ROOT)):sha(path) for path in source_paths}, 'source drift during proof')
        result['passed'] = True
    finally:
        (output/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS complete START factor proof and regressions', flush=True)


if __name__ == '__main__':
    main()
