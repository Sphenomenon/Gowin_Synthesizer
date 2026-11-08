"""Partial actual DIRECT TF frame CDC/RAM closure audit; no source or SDC edit.

This verifies mapped synchronizer topology/reset/next-Q, explicit aliases,
actual distributed FIFO RAM wiring and complete asynchronous-data consumers.
Gray-producing arithmetic, FIFO ownership/stability, RAM timing models and
physical timing remain separate gates. Missing RAM finite paths are reported,
never removed, false-pathed, or treated as accepted by this partial policy.
"""
import bisect
import fnmatch
import re

from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import BooleanDiagram, COMB, Graph

POLICY = 'task3-direct-tf-frame-partial-cdc-v1'
B = 'u_tf_audio/frames'
F = B + '/frames_0'
HELD_BITS = (*range(34), 36, *range(40, 48), 49, *range(54, 118))


def require(condition, message):
    if not condition:
        raise ValueError('task3 TF frame CDC audit: ' + message)


def ram_output_closure(n, g, rams, roots):
    """Follow actual RAM DO nets, accounting for the known RAM output port.

Graph intentionally treats unknown primitive ports as terminals. Only these
exact RAM16SDP4/DO output terminals are skipped; every other primitive endpoint
and every top export remains visible, exactly as in complete_closure.
"""
    top_outputs = {n.canonical('', bit): name for name, direction in
        n.directions['workstation_custom_138k_top'].items() if direction in ('output', 'inout')
        for bit in g.binding_bits('', name)}
    todo, seen, ends, primitives, comb, exports = list(roots), set(), {}, {}, set(), {}
    while todo:
        net = todo.pop()
        if net in seen:
            continue
        seen.add(net)
        if net in top_outputs:
            exports[top_outputs[net]] = net
        for path, pin, role in g.fan[net]:
            if path in rams and pin == 'DO':
                continue
            if role == 'ff':
                ends[path + '/' + pin] = n.pin(path, 'CLK')
            elif role == 'comb':
                comb.add(path)
                todo.extend(n.pin(path, output) for output in COMB[n.cells[path]['kind']])
            else:
                primitives[path + '/' + pin] = dict(kind=n.cells[path]['kind'])
    return dict(ff_endpoints=dict(sorted(ends.items())), primitive_endpoints=dict(sorted(primitives.items())),
                combinational_cells=len(comb), top_output_endpoints=dict(sorted(exports.items())))


def audit_tf_frame_cdc(n, *, sdc, stage=None, root=None):
    g = Graph(n)
    require(n.frames.get(B, {}).get('kind') == 'workstation_tf_frame_bridge_v2',
            'actual bridge is not frame_bridge_v2')
    root_q = n.pin(g.register('u_reset', 'started'), 'Q')
    common = n.pin(g.register(B, 'source_release', 0), 'CLEAR')
    local_compute=None
    if stage is not None:
        from tools.workstation_tf_compute_local_release import audit_mapped
        local_compute=audit_mapped(n,stage=stage,root=root)
    source_release = g.group(B, 'source_release', 3)
    compute_release = g.group(B, 'compute_release', 3)
    write_reset, read_reset = (n.pin(group[2], 'Q') for group in (source_release, compute_release))
    write_clear = n.pin(g.register(F, 'read_gray_meta', 0), 'CLEAR')
    read_clear = n.pin(g.register(F, 'write_gray_meta', 0), 'CLEAR')
    compute_clear=read_clear if local_compute is not None else common
    compute_reset_q=read_reset if local_compute is not None else root_q
    reset_rows = []
    for name, clear, publisher in (('root', common, root_q),
                                    ('write', write_clear, write_reset), ('read', read_clear, read_reset)):
        bd = BooleanDiagram([publisher])
        require(g.support(clear) == {publisher} and
                bd.net(g, clear) == bd.invert(bd.inputs[publisher]),
                'actual ' + name + ' async CLEAR is not inverse reviewed reset publisher')
        reset_rows.append(dict(id=name, clear=clear, reset_q=publisher, exact_inversion=True))

    def ff(path, clock, clear):
        cell = n.cells[path]
        require(cell['kind'] == 'DFFCE' and
                set(cell['ports']) == {'Q', 'D', 'CLK', 'CE', 'CLEAR'} and
                cell['parameters'].get('INIT', "1'b0") == "1'b0" and
                n.pin(path, 'CLK') == clock and n.pin(path, 'CLEAR') == clear,
                'zero async FF/clock/reset changed: ' + path)
        return dict(register=path, **{pin.lower(): n.pin(path, pin) for pin in ('Q','D','CLK','CE','CLEAR')},
                    primitive='DFFCE', effective_init=0)

    def sync_next(path, upstream, reset_q):
        bd = BooleanDiagram([reset_q, n.pin(upstream, 'Q'), n.pin(path, 'Q')])
        require(n.pin(path, 'CE') in g.high, 'synchronizer CE not high: ' + path)
        actual = bd.choose(bd.net(g, n.pin(path, 'CLEAR')), 0,
            bd.choose(bd.net(g, n.pin(path, 'CE')), bd.net(g, n.pin(path, 'D')),
                      bd.inputs[n.pin(path, 'Q')]))
        require(actual == bd.both(bd.inputs[reset_q], bd.inputs[n.pin(upstream, 'Q')]),
                'reset-inclusive synchronizer next-Q changed: ' + path)
        return dict(register=path, actual_upstream=upstream, reset_inclusive_next_q_exact=True,
                    contract='reset_q & exact upstream Q', exhaustive_assignments=8)

    # Verify the local reset chains without claiming their final consumers.
    release_rows = []
    for group, clock in ((source_release, 'clk_50m'), (compute_release, 'audio_clk')):
        for bit, path in enumerate(group):
            ff(path, clock, common)
            require(n.pin(path, 'CE') in g.high and
                    (n.pin(path, 'D') in g.high if bit == 0 else
                     n.pin(path, 'D') == n.pin(group[bit-1], 'Q')),
                    'frame local release shift/CE changed')
            if bit < 2:
                closure = complete_closure(n, g, [path])
                require(closure['ff_endpoints'] == {group[bit+1] + '/D': clock} and
                        not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                        'frame early release has extra consumer')
            release_rows.append(dict(register=path, clock=clock, zero_init=True,
                                     async_root_clear_verified=True, exact_shift=True))
    buses = []
    specs = (
        ('generation', B, 'generation_meta', 'generation_sync',
         [(B, 'source_generation_gray', bit) for bit in range(31)] + [(B, 'source_generation_o', 31)],
         'clk_50m', 'audio_clk', common, compute_clear, compute_reset_q, 20.000),
        ('ack', B, 'ack_meta', 'ack_sync',
         [(B, 'ack_gray', bit) for bit in range(31)] + [(B, 'ack_binary', 31)],
         'audio_clk', 'clk_50m', compute_clear, common, root_q, 13.020),
        ('write-pointer', F, 'write_gray_meta', 'write_gray_sync',
         [(F, 'write_gray', bit) for bit in range(5)],
         'clk_50m', 'audio_clk', write_clear, read_clear, read_reset, 20.000),
        ('read-pointer', F, 'read_gray_meta', 'read_gray_sync',
         [(F, 'read_gray', bit) for bit in range(4)] + [(F, 'read_binary', 4)],
         'audio_clk', 'clk_50m', read_clear, write_clear, write_reset, 13.020),
    )
    for name, scope, first_stem, second_stem, aliases, launch_clock, clock, producer_clear, clear, reset_q, budget in specs:
        first = g.group(scope, first_stem, len(aliases))
        second = g.group(scope, second_stem, len(aliases))
        producers, next_rows = [], []
        for meta, sync, alias in zip(first, second, aliases):
            # Follow the actual D driver before checking the reviewed alias.
            drivers = g.drivers[n.pin(meta, 'D')]
            require(len(drivers) == 1 and drivers[0][1] == 'Q' and drivers[0][0] in g.regs,
                    'Gray first D does not have exactly one registered publisher')
            producer = drivers[0][0]
            require(producer == g.register(*alias), 'unreviewed actual Gray publisher alias: ' + producer)
            producers.append(producer)
            ff(producer, launch_clock, producer_clear)
            ff(meta, clock, clear); ff(sync, clock, clear)
            require(n.pin(sync, 'D') == n.pin(meta, 'Q'), 'Gray meta-to-sync bit mapping changed')
            next_rows.extend((sync_next(meta, producer, reset_q), sync_next(sync, meta, reset_q)))
        first_closure = complete_closure(n, g, first)
        require(first_closure['ff_endpoints'] == {p + '/D': clock for p in second} and
                not first_closure['primitive_endpoints'] and not first_closure['top_output_endpoints'],
                'Gray meta-stage complete consumer closure changed: ' + name)
        producer_closure = complete_closure(n, g, producers)
        remote = {p: domain for p, domain in producer_closure['ff_endpoints'].items() if domain != launch_clock}
        require(remote == {p + '/D': clock for p in first} and not producer_closure['top_output_endpoints'],
                'Gray producer has extra remote/top consumer: ' + name)
        require(all(row['clock_pins'] and all(value==launch_clock for value in row['clock_pins'].values())
                    for row in producer_closure['primitive_endpoints'].values()),
                'Gray producer reaches an unreviewed opaque clock domain: '+name)
        buses.append(dict(id=name, width=len(aliases), source_pins=[p+'/Q' for p in producers],
            first_pins=[p+'/D' for p in first], meta_q_pins=[p+'/Q' for p in first],
            second_pins=[p+'/D' for p in second], producer_clock=launch_clock, destination_clock=clock,
            required_launch_max_ns=budget, meta_to_sync_max_ns=2.000, next_q=next_rows,
            first_complete_closure=first_closure, producer_complete_closure=producer_closure,
            local_producer_primitive_endpoints_proven=False,
            producer_gray_encoding_and_one_step_transition_proven=False))
    # Existing single-bit control chains, including the real merged alive FF.
    single = []
    for stem, alias, launch_clock, clock in (
        ('source_alive_sync', ('u_usb_pll/u_pll_init','enable_r',0), 'clk_50m','audio_clk'),
        ('expected_valid_sync', (B,'expected_generation_valid_o',None), 'audio_clk','clk_50m'),
        ('quiesce_sync', ('u_tf_audio','source_quiesce_level',None), 'clk_50m','audio_clk'),
        ('quiet_sync', (B,'quiet_published',None), 'audio_clk','clk_50m'),
        ('quiesce_return_sync', (B,'quiesce_sync',1), 'audio_clk','clk_50m'),
    ):
        first, second = g.group(B, stem, 2)
        producer = g.register(*alias)
        require(g.drivers[n.pin(first,'D')] == [(producer,'Q')] and
                n.pin(producer,'CLK') == launch_clock and n.pin(second,'D') == n.pin(first,'Q'),
                'single-bit actual publisher/bit mapping changed: ' + stem)
        clear=compute_clear if clock=='audio_clk' else common
        reset_q=compute_reset_q if clock=='audio_clk' else root_q
        ff(first, clock, clear); ff(second, clock, clear)
        closure = complete_closure(n,g,[first])
        require(closure['ff_endpoints'] == {second+'/D':clock} and
                not closure['primitive_endpoints'] and not closure['top_output_endpoints'],
                'single-bit first-stage consumer changed: ' + stem)
        producer_closure=complete_closure(n,g,[producer])
        require({p:d for p,d in producer_closure['ff_endpoints'].items() if d!=launch_clock}
                == {first+'/D':clock} and not producer_closure['top_output_endpoints'],
                'single-bit producer extra remote/top consumer: '+stem)
        single.append(dict(id=stem, source=producer+'/Q', first=first+'/D', second=second+'/D',
            next_q=[sync_next(first,producer,reset_q),sync_next(second,first,reset_q)],
            first_complete_closure=closure,producer_complete_closure=producer_closure,
            producer_primitive_endpoint_semantics_proven=False,producer_functional_semantics_proven=False))
    # Actual small-head FIFO: 27 asynchronous-read 16x4 memories, 108 live bits.
    rams = {p:c for p,c in n.cells.items() if p.startswith(F+'/') and c['kind']=='RAM16SDP4'}
    require(len(rams)==27 and not any(p.startswith(F+'/') and c['kind'] in ('SDPB','DPB','SDPX9')
                                    for p,c in n.cells.items()), 'FIFO storage primitive inventory changed')
    write_binary = g.group(F,'write_binary',4)
    read_binary = g.group(F,'read_binary',5)
    held = [g.register(B,'held_packet',bit) for bit in HELD_BITS]
    require({p for p in g.regs if re.fullmatch(re.escape(B)+r'/held_packet_\d+_s\d+',p)} == set(held),
            'retained held-packet bit inventory changed')
    held_valid = g.register(B,'held_valid')
    for p in [*held,held_valid]: ff(p,'audio_clk',compute_clear)
    roots, ram_rows = [], []
    # The binary LSB uses CE=1 plus XOR hold logic in this actual mapping.
    # The registered Gray publisher retains the real write-commit CE.
    write_ce = n.pin(g.register(F,'write_gray',0),'CE')
    for p in write_binary: ff(p,'clk_50m',write_clear)
    for p in read_binary: ff(p,'audio_clk',read_clear)
    for path,cell in sorted(rams.items()):
        require(set(cell['ports']) == {'DO','CLK','WRE','WAD','DI','RAD'} and
                n.pin(path,'CLK')=='clk_50m' and n.pin(path,'WRE')==write_ce,
                'FIFO RAM port/clock/common write commit changed: '+path)
        scope = n.scopes[path]
        vectors={pin:[n.canonical(scope,bit) for bit in g.binding_bits(scope,cell['ports'][pin])]
                 for pin in ('DI','DO','WAD','RAD')}
        require(all(len(values)==4 for values in vectors.values()) and
                vectors['WAD']==[n.pin(p,'Q') for p in write_binary] and
                vectors['RAD']==[n.pin(p,'Q') for p in read_binary[:4]],
                'FIFO RAM actual data/address bit inventory changed: '+path)
        roots.extend(vectors['DO'])
        ram_rows.append(dict(instance=path,primitive='RAM16SDP4',clock='clk_50m',
                             write_commit=write_ce,**vectors))
    require(len(roots)==len(set(roots))==108 and
            set(roots)=={n.pin(p,'D') for p in held} and
            all(n.pin(p,'D')==n.canonical(B,'read_data['+str(bit)+']') for bit,p in zip(HELD_BITS,held)),
            'actual RAM DO-to-held data mapping changed')
    data_closure=ram_output_closure(n,g,rams,roots)
    expected_data={p+'/'+pin:'audio_clk' for p in [*held,held_valid] for pin in ('D','CE')}
    require(data_closure['ff_endpoints']==expected_data and
            not data_closure['primitive_endpoints'] and not data_closure['top_output_endpoints'],
            'FIFO async data complete D/CE consumer closure changed')
    address_closure=complete_closure(n,g,read_binary[:4])
    require(set(address_closure['primitive_endpoints'])=={p+'/RAD' for p in rams} and
            all(d=='audio_clk' for d in address_closure['ff_endpoints'].values()) and
            not address_closure['top_output_endpoints'],
            'FIFO read-address actual consumer closure changed')
    finite = _audit_sdc(n,sdc,buses,single,rams,held,held_valid,read_binary)
    return dict(policy=POLICY,structural_checks_passed=True,partial=True,
        reset_inversions=reset_rows,compute_functional_reset=local_compute,
        real_root_startup_proven_by_this_audit=False,
        local_release_registers=release_rows,gray_buses=buses,
        single_bit_chains=single,retained_fifo_width=108,nominal_fifo_width=118,fifo_depth=16,
        retained_held_bits=list(HELD_BITS),ram_instances=ram_rows,
        ram_data_complete_closure=data_closure,read_address_complete_closure=address_closure,
        **finite,unproven=['producer binary/Gray arithmetic and at-most-one-bit transitions',
            'FIFO full/empty arithmetic, memory ownership, overwrite/read stability and cancel sequencing',
            'source RAM DI data semantics and RAM write/read visibility, collision and timing model',
            'local producer primitive consumers and all second-stage business semantics',
            'STA RAM vector-port query resolution and recovery/removal; routed delays and skew',
            'physical-tail request/reply/sequence and complete TF CDC'],
        constraints_complete=False,complete_tf_cdc_accepted=False,physical_cdc_accepted=False,
        physical_tail_proven=False,hardware_tested=False,release_ready=False,deployment_allowed=False)


def _audit_sdc(n,sdc,buses,single,rams,held,held_valid,read_binary):
    """Exact existing finite sets; report missing asynchronous RAM boundaries."""
    pins=sorted(p+'/'+port for p,c in n.cells.items() for port in c['ports'])
    def resolve(body,kind='get_pins'):
        result=set()
        for pattern in body.split():
            prefix=pattern[:next((i for i,c in enumerate(pattern) if c in '*?['),len(pattern))]
            a,b=bisect.bisect_left(pins,prefix),bisect.bisect_right(pins,prefix+'\U0010ffff')
            result.update(pin for pin in pins[a:b] if fnmatch.fnmatchcase(
                pin.rsplit('/',1)[0] if kind=='get_regs' else pin,pattern))
        return result
    commands=[]
    from tools.workstation_runtime_cdc import MODE_EXCLUSIONS
    for number,raw in enumerate(sdc.splitlines(),1):
        line=raw.strip()
        if line.startswith('set_clock_groups'):
            require(False,'unreviewed whole-clock groups in frame constraints')
        if not line.startswith(('set_max_delay','set_false_path')): continue
        require('-through ' not in line,'unreviewed through exception in frame constraints')
        if 'get_clocks' in line:
            require(line in MODE_EXCLUSIONS,'unreviewed whole-clock setup exception')
            continue
        queries={side:resolve(body,kind) for side,kind,body in re.findall(
            r'-(from|to)\s+\[(get_pins|get_regs)\s+\{([^}]+)\}\]',line)}
        maximum=re.match(r'set_max_delay\s+([0-9.]+)\s',line)
        commands.append(dict(line=number,text=line,source=queries.get('from'),target=queries.get('to'),
            maximum=float(maximum[1]) if maximum else None,hold=line.startswith('set_false_path -hold'),
            false=line.startswith('set_false_path')))
    installed,allowed_false,finite_lines,protected=[],set(),set(),set()
    protected_producers=set()
    def boundary(name,source,target,budget,*,hold=False,optional=False):
        source,target=set(source),set(target)
        protected_producers.update(source)
        protected.update(target)
        overlap=[c for c in commands if c['maximum'] is not None and
                 (c['source'] is None or c['source'] & source) and c['target'] is not None and c['target'] & target]
        if optional and not overlap:
            return dict(id=name,source_pins=sorted(source),capture_pins=sorted(target),
                required_conservative_max_ns=budget,finite_budget_present=False,
                minimum_data_stability_or_RAM_timing_basis_proven=False)
        require(len(overlap)==1 and overlap[0]['source']==source and overlap[0]['target']==target
                and overlap[0]['maximum']==budget,'missing/weakened/extra finite pin inventory: '+name)
        finite_lines.add(overlap[0]['line'])
        installed.append(dict(id=name,line=overlap[0]['line'],constraint=overlap[0]['text'],
                              source_pins=sorted(source),capture_pins=sorted(target)))
        if hold:
            holds=[c for c in commands if c['hold'] and c['source']==source and c['target']==target]
            require(len(holds)==1,'exact scoped hold exception missing/duplicated: '+name)
            allowed_false.add(holds[0]['line'])
        return None
    for bus in buses:
        boundary(bus['id']+'-first',bus['source_pins'],bus['first_pins'],bus['required_launch_max_ns'],hold=True)
        boundary(bus['id']+'-second',bus['meta_q_pins'],bus['second_pins'],2.000)
    for row in single:
        protected_producers.add(row['source'])
        cuts=[c for c in commands if c['false'] and not c['hold'] and
              c['source']=={row['source']} and c['target']=={row['first']}]
        require(len(cuts)==1,'single-bit first-stage producer query changed: '+row['id'])
        allowed_false.add(cuts[0]['line']);protected.add(row['first'])
        boundary(row['id']+'-second',[row['first'].rsplit('/',1)[0]+'/Q'],[row['second']],2.000)
    gaps=[]
    for gap in (
        boundary('fifo-async-RAM-data',[p+'/DO' for p in rams],
                 [p+'/'+pin for p in [*held,held_valid] for pin in ('D','CE')],13.020,optional=True),
        boundary('fifo-read-address-to-asynchronous-RAD',[p+'/Q' for p in read_binary[:4]],
                 [p+'/RAD' for p in rams],13.020,optional=True),
    ):
        if gap:gaps.append(gap)
    for command in commands:
        if command['target'] is None and command['source'] is not None:
            require(not (command['source'] & protected_producers),
                    'source-only setup cut/bound reaches protected frame producer')
        if command['target'] is not None and command['target'] & protected:
            if command['false']:
                require(command['line'] in allowed_false,'setup/hold cut reaches protected frame data or later state')
            if command['maximum'] is not None:
                require(command['line'] in finite_lines,'unreviewed overlapping/weaker finite constraint')
        if 'get_regs' in command['text'] and command['target'] is not None and command['target'] & protected:
            require(False,'unreviewed register-level frame constraint query')
    return dict(installed_frame_constraints=installed,existing_gray_and_second_stage_sdc_exact=True,
        protected_producer_pins=sorted(protected_producers),
        source_only_and_through_exceptions_rejected=True,
        missing_finite_boundaries=gaps,RAM_vector_port_STA_resolution_verified=False,
        missing_finite_query_cross_product_pairs=sum(len(g['source_pins'])*len(g['capture_pins']) for g in gaps))
