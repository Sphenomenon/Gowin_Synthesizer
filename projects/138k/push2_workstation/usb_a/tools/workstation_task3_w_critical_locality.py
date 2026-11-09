"""Constrain the actual W v38 failing causal paths, without changing logic/SDC.

The v123 mapped source/target inventories are exact. The old tag-return and
held-data placements take precedence; this adds only unconstrained members.
Retire this recipe after a routed replacement demonstrates the same boundaries.
"""
from collections import Counter
import hashlib
import re
from tools.workstation_runtime_pcm_cdc import Graph, COMB
from tools.workstation_pinout import parse_locations


def require(ok, message):
    if not ok:
        raise ValueError('W critical locality: '+message)


def placement(cst, n):
    g = Graph(n)
    def group(scope, stem):
        pattern = re.escape(scope+'/'+stem)+r'_\d+_s\d+'
        return sorted(p for p in g.regs if re.fullmatch(pattern,p))
    def causal(sources, targets):
        forward, seen, todo = set(), set(), list(sources)
        while todo:
            net=todo.pop()
            if net in seen:continue
            seen.add(net)
            for p,pin,role in g.fan[net]:
                if role=='comb':
                    forward.add(p)
                    todo.extend(n.pin(p,out)for out in COMB[n.cells[p]['kind']])
        backward,seen,todo=set(),set(),[n.pin(p,pin)for p in targets
            for pin in ('D','CE')if pin in n.cells[p]['ports']]
        while todo:
            net=todo.pop()
            if net in seen:continue
            seen.add(net)
            for p,pin in g.drivers[net]:
                kind=n.cells[p]['kind']
                if kind in COMB:
                    backward.add(p)
                    todo.extend(n.pin(p,port)for port in n.cells[p]['ports']if port not in COMB[kind])
        return forward&backward
    raw='u_task3_media/raw_store'
    ingress='u_task3_bus_endpoint/recording_ingress'
    recording='u_bluetooth/u_core/application/command_endpoint/recording'
    endpoint='u_task3_bus_endpoint'
    tags=sorted(p for p in g.regs if p.startswith(
        'u_task3_media/memory/u_arbiter/g_recording.u_core/g_recording.tags['))
    sync=group(raw+'/capture_fifo','write_gray_sync')
    meta=group(raw+'/capture_fifo','write_gray_meta')
    raw_targets=group(raw,'completion_generation')+group(raw,'fetch_address')+[
        g.register(raw,'memory_fetch_active')]
    key_regs=[]
    for stem in ('session_o','generation_o','physical_epoch_o','expected_sequence'):
        key_regs+=group(ingress,stem)
    keys=[n.pin(p,'Q')for p in key_regs]+[n.canonical('',s+'['+str(bit)+']')
        for s in ('task3_pair_session','task3_pair_peer_boot')for bit in range(32)]
    result_regs=group(recording,'result_payload')
    tx_regs=group(endpoint,'tx_payload_o')
    rows=[
        ('tag_raw',[n.pin(p,'Q')for p in tags],raw_targets,100,
         {'LUT3':39,'MUX2_LUT6':8,'LUT4':34,'MUX2_LUT5':18,'LUT2':1},[],
         'R[60:85]C[65:90]','memory_clk'),
        ('capture_fetch',[n.pin(p,'Q')for p in sync],raw_targets,166,
         {'LUT3':108,'LUT4':36,'ALU':9,'LUT2':13},sync+meta+raw_targets,
         'R[60:85]C[65:90]','memory_clk'),
        ('record_key_result',keys,result_regs,392,
         {'ALU':228,'LUT4':52,'LUT3':34,'LUT2':78},key_regs+result_regs,
         'R[55:85]C[115:145]','clk_50m'),
        ('peer_endpoint_TX',keys,tx_regs,1995,
         {'LUT3':839,'LUT4':823,'ALU':240,'LUT2':93},tx_regs,
         'R[55:85]C[115:145]','clk_50m')]
    # Both complete-cone encodings exceeded 12GiB before placement. Retain
    # their full proof inventories, but constrain only the causal spines of
    # the five actual failing v38 source/target pairs and the named targets.
    tag='u_task3_media/memory/u_arbiter/g_recording.u_core/g_recording.tags[9]_1_s0'
    spines={
        'tag_raw':[(tag,raw+'/completion_generation_0_s0',9,
                    dict(LUT3=4,MUX2_LUT5=2,MUX2_LUT6=1,LUT4=2)),
                   (tag,raw+'/memory_fetch_active_s1',11,
                    dict(LUT3=4,MUX2_LUT5=2,LUT4=3,MUX2_LUT6=1,LUT2=1))],
        'capture_fetch':[(raw+'/capture_fifo/write_gray_sync_0_s0',raw+'/fetch_address_27_s0',27,
                          dict(LUT3=3,LUT4=7,LUT2=8,ALU=9))],
        'record_key_result':[('u_task3_pair_link/config_owner/session_o_24_s1',
                              recording+'/result_payload_72_s1',65,
                              dict(LUT4=28,LUT2=2,ALU=29,LUT3=6))],
        'peer_endpoint_TX':[('u_task3_pair_link/config_owner/peer_boot_o_10_s1',
                             endpoint+'/tx_payload_o_55_s0',136,
                             dict(LUT4=44,ALU=54,LUT3=30,LUT2=8))]}
    require((len(tags),len(sync),len(meta),len(raw_targets),len(keys),len(result_regs),len(tx_regs))
            ==(128,9,9,58,160,77,256),'complete v123 source/target inventory changed')
    text=cst.decode()
    existing=set(re.findall(r'^INS_LOC "([^"]+)" ',text,re.M))
    existing.update(p for line in text.splitlines()if line.startswith('GROUP ')
                    for p in re.findall(r'"([^"]+)"',line))
    selected,proofs={},[]
    for label,sources,targets,count,kinds,registers,region,clock in rows:
        cone=causal(sources,targets)
        require(len(cone)==count and dict(Counter(n.cells[p]['kind']for p in cone))==kinds,
                'actual causal cone changed: '+label)
        require(all(n.pin(p,'CLK')==clock for p in registers),'target/register clock changed: '+label)
        # Earlier exact held endpoints and shared logic keep their placement.
        physical=set();spine_proofs=[]
        for source,target,expected_count,expected_kinds in spines[label]:
            require(source in g.regs and target in g.regs,'actual failing endpoint disappeared: '+label)
            narrow=causal([n.pin(source,'Q')],[target])
            require(len(narrow)==expected_count and
                    dict(Counter(n.cells[p]['kind']for p in narrow))==expected_kinds,
                    'actual failing path causal spine changed: '+label)
            physical.update(narrow)
            spine_proofs.append(dict(source=source,target=target,cells=sorted(narrow),
                                     exact_primitive_inventory=expected_kinds))
        require(physical<=cone,'failing spine leaves full causal inventory')
        wanted=(physical|set(registers))-existing
        conflict={p for p in wanted if p in selected and selected[p]!=region}
        # Shared raw/recording completion control keeps its first causal region.
        for p in sorted(wanted-set(selected)):selected[p]=region
        proofs.append(dict(path=label,source_nets=sources,target_registers=targets,
            causal_cells=sorted(cone),exact_primitive_inventory=kinds,region=region,
            actual_failing_path_spines=spine_proofs,
            earlier_constraints_preserved=sorted((physical|set(registers))&existing),
            shared_prior_causal_region_preserved=sorted(conflict)))
    for p in sync+meta:
        if p not in existing:selected[p]='R[70:72]C[70:75]'
    lines=[];groups=[]
    for index,region in enumerate(sorted(set(selected.values()))):
        name='task3_w_v38_critical_'+str(index)
        require(name not in text,'duplicate recipe')
        members=sorted(p for p,r in selected.items()if r==region)
        # The first grouped representation exceeded 12GiB while Gowin was
        # reading CST, before placement. Express the same allowed region per
        # primitive; there are no relative-location/group-shape constraints.
        # Keep the causal inventories and earlier placements identical.
        lines += [f'INS_LOC "{p}" {region};'for p in members]
        groups.append(dict(name=name,region=region,members=members))
    result=cst+('\n# W v38 diagnosed causal-path locality; all timing retained\n'+
                '\n'.join(lines)+'\n').encode()
    require(parse_locations(result.decode())==parse_locations(text),'IO locations changed')
    sha=lambda b:hashlib.sha256(b).hexdigest()
    return result,dict(policy='task3_W_v38_five_failing_path_spines_locality_v3',
        source_target_cones=proofs,groups=groups,selected_count=len(selected),
        constraint_representation='per_primitive_INS_LOC',
        before_CST_sha256=sha(cst),after_CST_sha256=sha(result),
        logic_changed=False,clocks_changed=False,timing_exceptions_changed=False,
        held_constraints_preserved=True,routed_timing_verified=False,hardware_tested=False)
