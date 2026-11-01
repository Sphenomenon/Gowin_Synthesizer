"""Explicit full W-media board profile, separate from immutable W21.

Headless retires graphics and TF only. Full native HCI/GATT, real CNN and the
single map-sized recording object remain. Exact inverse adapters preserve the
old composition as the input to existing strict provenance validators.
"""
from pathlib import Path
import hashlib,json,re
from tools.workstation_task3_w_media import SOURCES as MEDIA_SOURCES,recording_geometry

POLICY='task3_w_media_headless_board_v1'
FIRMWARE_POLICY='task3_w_headless_media_single_recording_60s_v1'
NAME='custom138k-workstation-task3-w-media-v1'
PROVIDER='rtl/workstation/workstation_profile_task3_w_media.sv'
REFERENCE='rtl/workstation/workstation_task3_w_media_top_reference.json'
BOARD='rtl/workstation/workstation_task3_media_board.svh'
APB='rtl/services/workstation_task3_media_apb_service.sv'
CONTROLLED='rtl/workstation/workstation_worker_runtime_controlled.sv'
PRIMITIVES='rtl/workstation/workstation_worker_audio_primitives.sv'
SOURCES=(*MEDIA_SOURCES,APB,CONTROLLED)
DEPENDENCIES=('tools/workstation_task3_w_media_profile.py',REFERENCE,BOARD,PRIMITIVES,'rtl/ddr_address_map.vh',
 'tools/workstation_task3_w_media.py','tools/workstation_task3_w_media_firmware.py',
 'tools/workstation_task3_w_media_firmware_review.json',
 'rtl/workstation/workstation_runtime_controlled.sv','rtl/audio/workstation_observation_consumers.sv',
 'rtl/workstation/WORKSTATION_TASK3_W_MEDIA_CONTRACT.md',
 'rtl/workstation/WORKSTATION_TASK3_W_MEDIA_BOARD_CONTRACT.md')
TOP='rtl/workstation/gw138k_push_workstation_top.v'
PARENT_TOP_SHA256='2bd14a9c81c28817dc0fd2bf39a87d208f0344f7f1c8f06571953bc2550f3cd0'
REFERENCE_SHA256='ca2dc65f6e958f0730642a980fd591612bde3edbdbad45f0d8dc0d3b63bcfa1a'
RETIRED_PREFIXES=('rtl/display_data/','src/video/','src/storage/','rtl/tf_audio/',
 'vendor/sipeed_dvi/','rtl/push2/','src/usb_a/push2_screen_')
VIDEO_GSC_SHA256='cf2ce8bcbc84e619dcc974bcfae01ce3b9c2b328a4a51d2419b3bdc770e9d448'
RETIRED_SOURCES=('constraints/p11.gsc','legacy_audio.sv','src/memory/display_data_layout_pkg.sv',
 'rtl/workstation/workstation_runtime_controlled.sv','rtl/audio/workstation_observation_consumers.sv',
 'src/memory/ddr_frame_writer.v','src/platform/video_clock.v','src/platform/video_clock_1080p.v',
 'src/ae350/gw138k_ui_services.sv','src/ae350/gw138k_ui_workstation_top.v',
 'src/ae350/gw138k_view_select.sv','src/ae350/gw138k_ahb_ddr.sv',
 'src/memory/tf_audio_ddr_command_buffer.sv','rtl/workstation/workstation_profile_hdmi.sv',
 'rtl/audio/workstation_runtime_oscillator_engine.sv','rtl/audio/workstation_runtime_scope_vec.sv',
 'rtl/audio/workstation_runtime_render_engines.sv','rtl/audio/workstation_rate_pitch_expression.sv',
 'rtl/audio/workstation_runtime_div147.sv','rtl/audio/scope_vec/scope_control_player.sv',
 'rtl/audio/scope_vec/scope_vec_engine.sv','rtl/audio/scope_vec/scope_dac_select.sv',
 'rtl/audio/scope_vec/scope_tf_control.sv','rtl/audio/scope_vec/scope_tf_transport.sv',
 'rtl/runtime_replacements/scope_tf_transport.sv','rtl/music/tf_playlist_bridge.sv',
 'rtl/services/workstation_playback_service.sv')
RETIRED_SELECTORS=('u_video/','u_ui_control/','u_ui_services/','u_cpu_ddr/',
 'u_managed/display/','u_managed/display_observation_health/','u_ble_pcm_cdc/',
 'recording_authority/','recording_owner8/','recording_memory_release',
 'recording_channel_meta','recording_channel_ready50')
REBIND=(('u_video/u_bist/','u_task3_media/memory/u_bist/'),
 ('u_video/u_arbiter/','u_task3_media/memory/u_arbiter/'),
 ('u_video/flags_meta','u_task3_media/memory/flags_meta'),
 ('u_video/flags_sync','u_task3_media/memory/flags_sync'),
 ('recording_ble_store/','u_task3_media/raw_store/'))
QUERY=re.compile(r'\[(get_regs|get_pins|get_ports|get_clocks) \{([^{}]+)\}\]')

def digest(s):return hashlib.sha256(s.encode()if isinstance(s,str)else s).hexdigest()
def sha(p):return digest(Path(p).read_bytes())
def inverse_top(root,text):
    """Full identity plus unique anchors, reverse and forward round trip."""
    if 'WORKSTATION_TASK3_W_MEDIA' not in text:return text
    payload=(Path(root)/REFERENCE).read_bytes()
    if digest(payload)!=REFERENCE_SHA256:raise ValueError('task3 W top adaptation identity drift')
    d=json.loads(payload)
    if d.get('parent_sha256')!=PARENT_TOP_SHA256:raise ValueError('task3 W top locked parent drift')
    if d.get('policy')!='task3_w_media_exact_top_composition_v1' or digest(text)!=d['selected_sha256']:
        raise ValueError('task3 W top selected identity drift')
    result=text
    for row in reversed(d['edits']):
        if result.count(row['selected'])!=1:raise ValueError('task3 W top inverse anchor drift')
        result=result.replace(row['selected'],row['parent'],1)
    if digest(result)!=d['parent_sha256']:raise ValueError('task3 W top parent identity drift')
    forward=result
    for row in d['edits']:
        if forward.count(row['parent'])!=1:raise ValueError('task3 W top forward anchor drift')
        forward=forward.replace(row['parent'],row['selected'],1)
    if forward!=text:raise ValueError('task3 W top inverse roundtrip drift')
    return result

def retired_source(path):
    # The shared CPU/audio PLL still uses this helper; committed parameter
    # state still instantiates its small control-only scope_tf_control module.
    if path in ('vendor/sipeed_dvi/video_pll_init.v','rtl/audio/scope_vec/scope_tf_control.sv'):return False
    return path in RETIRED_SOURCES or path.startswith(RETIRED_PREFIXES)
def select_sources(stage,files):
    stage=Path(stage);retired={}
    for row in files:
        rel=row.get('path')
        if row.get('enable')=='1' and retired_source(rel):
            if rel=='constraints/p11.gsc' and sha(stage/rel)!=VIDEO_GSC_SHA256:
                raise ValueError('W-media video-only GSC identity drift')
            retired[rel]=sha(stage/rel);row.set('enable','0')
    if 'legacy_audio.sv' not in retired:raise ValueError('headless media parent primitives absent')
    from xml.etree import ElementTree as ET
    index=next(i for i,r in enumerate(files)if r.get('path')=='legacy_audio.sv')
    files.insert(index,ET.Element('File',path=PRIMITIVES,type='file.verilog',enable='1'))
    return dict(policy=POLICY,retired_compilation_sha256=retired,primitive_provider=PRIMITIVES,
        primitive_provider_sha256=sha(stage/PRIMITIVES),rtl_text_generation=False,physical_retirement_verified=False)

def added_sdc():
    lines=[]
    def line(s):lines.append(s)
    def held(src,dst,budget=10):
        line(f'set_max_delay {budget:.3f} -from [get_regs {{{src}}}] -to [get_regs {{{dst}}}]')
        line(f'set_false_path -hold -from [get_regs {{{src}}}] -to [get_regs {{{dst}}}]')
    memory='u_task3_media/memory'
    line(f'set_false_path -to [get_pins {{{memory}/memory_release*/CLEAR}}]')
    for n in (0,1):line(f'set_max_delay 2.000 -from [get_regs {{{memory}/memory_release_{n}*}}] -to [get_pins {{{memory}/memory_release_{n+1}*/D}}]')
    line(f'set_false_path -to [get_pins {{{memory}/flags_meta*/D}}]')
    line(f'set_max_delay 2.000 -from [get_regs {{{memory}/flags_meta*}}] -to [get_pins {{{memory}/flags_sync*/D}}]')
    line('set_false_path -to [get_pins {u_task3_media/ready_control*/CLEAR}]')
    line('set_false_path -to [get_pins {u_task3_media/ready_control_0*/D}]')
    line('set_max_delay 2.000 -from [get_regs {u_task3_media/ready_control_0*}] -to [get_pins {u_task3_media/ready_control_1*/D}]')
    # Retain the actual CNN's original budgets under its new owner hierarchy.
    from tools.workstation_recognition_policy import RETIRED_LINES
    for old in RETIRED_LINES:
        if 'u_music/' in old:line(old.replace('u_music/','u_task3_media/cnn_task/cnn/'))
    # New bounded staging FIFOs retain the same directional Gray setup/hold bounds.
    for scope in ('u_task3_media/cnn_task/staging_requests','u_task3_media/cnn_task/staging_completions'):
        for stem in ('read','write'):held(scope+'/'+stem+'_gray*',scope+'/'+stem+'_gray_meta*')
    scope='u_task3_media_apb'
    held(scope+'/request_held*',scope+'/request_local*');held(scope+'/response_held*',scope+'/response_local*')
    for src,dst in [('request_toggle','req_meta'),('acknowledge_toggle','ack_meta')]:
        line(f'set_false_path -from [get_regs {{{scope}/{src}*}}] -to [get_pins {{{scope}/{dst}*/D}}]')
    for src,dst in [('req_meta','req_sync'),('ack_meta','ack_sync')]:
        line(f'set_max_delay 2.000 -from [get_regs {{{scope}/{src}*}}] -to [get_pins {{{scope}/{dst}*/D}}]')
    line(f'set_false_path -to [get_pins {{{scope}/p_release*/CLEAR {scope}/a_release*/CLEAR}}]')
    from tools.workstation_w_return_mailbox_cdc import constraints as return_constraints
    lines.extend(return_constraints().replace('recording_ble_store/','u_task3_media/raw_store/').splitlines())
    return '\n'.join(lines)+'\n'

def constraints(text):
    result=[];changes=[]
    for index,line in enumerate(text.splitlines()):
        removed=[];rebound=[];empty=[]
        def query(m):
            keep=[]
            for old in m[2].split():
                new=old
                for a,b in REBIND:
                    if new.startswith(a):new=b+new[len(a):];break
                if new.startswith(RETIRED_SELECTORS)or(m[1]=='get_clocks'and new in ('video_ref49','video_serial742','video_pixel148')):removed.append(old)
                else:
                    keep.append(new)
                    if old!=new:rebound.append(dict(original=old,selected=new,query=m[1]))
            if not keep:empty.append(m[1])
            return '['+m[1]+' {'+' '.join(keep)+'}]'
        out=QUERY.sub(query,line)
        if removed or rebound:changes.append(dict(line_index=index,selected_line_index=len(result),original=line,selected=None if empty else out,removed_selectors=removed,rebound_selectors=rebound))
        if not empty:result.append(out)
    result='\n'.join(result)+'\n'+added_sdc()
    return result,dict(policy=POLICY,original_sha256=digest(text),selected_sha256=digest(result),changes=changes,added_lines=added_sdc().splitlines(),clocks_or_budgets_relaxed=False,physical_cdc_accepted=False,netlist_resolution_required=True)

def restore_constraints(selected,evidence):
    if evidence.get('policy')!=POLICY or not selected.endswith(added_sdc()):raise ValueError('W-media SDC evidence absent')
    lines=selected[:-len(added_sdc())].splitlines()
    for row in reversed(evidence['changes']):
        index=row['selected_line_index']
        if row['selected']is None:lines.insert(index,row['original'])
        else:
            if lines[index]!=row['selected']:raise ValueError('W-media SDC inverse drift')
            lines[index]=row['original']
    original='\n'.join(lines)+'\n';out,wanted=constraints(original)
    if out!=selected or evidence!=wanted:raise ValueError('W-media SDC roundtrip changed')
    return original

def recording_metadata(root):
    return dict(policy='task3_w_single_C_BLE_recording_60s_v1',production_owner8_selected=True,owner=8,
        **recording_geometry(root),address_authority='rtl/ddr_address_map.vh',
        final_pcm_source='explicit software M-final-tap injection aperture; physical LCD unconnected',
        software_apb_base='0xf8070000',retired_R00_page='0xf8040000',R00_backend_selected=False,
        raw_store='u_task3_media/raw_store',business_owner='existing C/BLE firmware_owner and physical engine',
        physical_M_tap_connected=False,hardware_tested=False,physical_cdc_accepted=False)

def raw_metadata(root):
    return dict(recording_metadata(root),policy='task3_w_single_C_BLE_raw_ddr_60s_v1',
        full_HCI_Classic_GATT=True,second_business_object=False,source_is_W_local_DAC=False)

def build_firmware(root,evidence,prefix=None):
    """Delegate to the separately reviewed media ELF builder, never old UI roots."""
    from tools.workstation_task3_w_media_firmware import build,audit
    root,evidence=Path(root),Path(evidence)
    linked=build(evidence,prefix,root)
    graph=audit(evidence,root)
    if not linked['passed'] or not graph['passed']:raise ValueError('actual media firmware rejected')
    record=dict(linked,memory_profile='ilm64k_dlm64k',recording_api_enabled=True,business_owner_enabled=True,
        runtime_policy=FIRMWARE_POLICY,worker_media=True,worker_demo=True,headless_worker=False,
        runtime_owner=True,rom_sha256=sha(evidence/'boot.mem'),elf_sha256=sha(evidence/'firmware.elf'),
        binary_sha256=sha(evidence/'firmware.bin'),call_chain_stack=graph['stack'],
        reviewed_JALR_sites=graph['reviewed_JALR_sites'],tool_versions=dict(exact_executable_sha256=linked['tool_sha256']),
        cold_boot=dict(image_capacity_bytes=131072,image_storage='explicit_128k_pl_boot_rom_split',
            cache_policy='reject_enabled_i_or_d_cache_on_entry'),
        GeneralBonding_enabled=False,PCM_sustained_verified=False,measured_delay_valid=False,
        delegated_media_verification_sha256=sha(evidence/'verification.json'),
        delegated_callgraph_sha256=sha(evidence/'media_callgraph_verification.json'))
    (evidence/'build_metadata.json').write_text(json.dumps(record,indent=2)+'\n')
    verify_firmware(root,evidence,record)
    return record

def verify_firmware(root,evidence,record):
    from tools.workstation_task3_w_media_firmware import audit
    root,evidence=Path(root),Path(evidence)
    graph=audit(evidence,root);linked=json.loads((evidence/'verification.json').read_text())
    for key,value in linked.items():
        if record.get(key)!=value:raise ValueError('W-media delegated firmware field drift: '+key)
    if not record.get('worker_media') or record.get('runtime_policy')!=FIRMWARE_POLICY or not record.get('recording_api_enabled') or not record.get('business_owner_enabled') or record.get('headless_worker'):
        raise ValueError('W-media actual runtime role drift')
    if (record['delegated_media_verification_sha256']!=sha(evidence/'verification.json') or
        record['delegated_callgraph_sha256']!=sha(evidence/'media_callgraph_verification.json') or
        record['call_chain_stack']!=graph['stack'] or record['reviewed_JALR_sites']!=graph['reviewed_JALR_sites']):
        raise ValueError('W-media actual ELF callback/stack identity drift')
    for key,name in [('rom_sha256','boot.mem'),('elf_sha256','firmware.elf'),('binary_sha256','firmware.bin')]:
        if record[key]!=sha(evidence/name):raise ValueError('W-media runtime artifact drift')
    return graph

def selected_source_evidence(stage,text):
    """Inspect actual preprocessed provider closure, never a macro intent label."""
    stage=Path(stage)
    def module(name):
        match=re.search(r'\bmodule\s+'+re.escape(name)+r'\b.*?\bendmodule\b',text,re.S)
        if match is None:raise ValueError('W-media actual module absent: '+name)
        return match[0]
    top=module('workstation_custom_138k_top');media=module('workstation_task3_w_media')
    for anchor in ['workstation_task3_media_apb_service u_task3_media_service(',
                   'workstation_task3_record_ingress u_task3_record_ingress(',
                   'workstation_task3_w_media u_task3_media(',
                   '.cnn_start_valid_i(task3_start_valid)',
                   '.cnn_start_task_id_i(task3_task_id)',
                   '.cnn_start_generation_i(task3_generation)',
                   '.cnn_start_frames_i(task3_frames)',
                   '.cnn_frame_valid_i(task3_frame_valid)',
                   '.cnn_frame_pcm_i(task3_frame_pcm)',
                   '.cnn_cancel_valid_i(task3_cancel_valid)',
                   '.lcd_link_ready_i(1\'b0)',
                   'assign ble_pcm_valid=task3_record_pcm_valid,ble_pcm=task3_record_pcm,ble_sequence=task3_record_sequence;',
                   '.source_allowed_i(\n            task3_record_source_allowed && recording_channel_ready50)',
                   '.CAPACITY_FRAMES(32\'d2_880_000)',
                   'assign recording_bus_ready=1\'b1,recording_bus_error=recording_select;']:
        if ''.join(top.split()).count(''.join(anchor.split()))!=1:raise ValueError('W-media actual provider binding drift: '+anchor)
    for retired in ['hdmi_display u_video','workstation_recording_runtime u_recording',
                    'u_ble_pcm_cdc (','recording_owner8(', 'recording_ble_store(', 'basic_pitch_workstation_link u_music']:
        if retired in top:raise ValueError('W-media retired board owner survived: '+retired)
    for anchor in ['workstation_ble_raw_ddr_store #(',') raw_store(',
                   'workstation_cnn_task_service #(',') cnn_task(']:
        if media.count(anchor)!=1:raise ValueError('W-media unique native owner drift: '+anchor)
    # Actual full-HCI source body, not the audio-only alternative.
    core=module('workstation_hci_native_core')
    if 'bt_gatt #' not in core or 'application (' not in core:
        raise ValueError('W-media actual shared-HCI GATT application omitted')
    task=module('workstation_cnn_task_service')
    if '.USE_FLASH_WEIGHTS(1),.DRAIN_RESTART_ENABLE(1),.BOUNDED_EOF_PADDING(1)' not in task:
        raise ValueError('W-media real model/task pipeline selection changed')
    link=(stage/'rtl/music/basic_pitch_workstation_link.sv').read_text()
    expected=dict(WIN_LEN=44100,FRAME_LIMIT=8,OCTAVE_LIMIT=9,CQT_HOP_NUMERATOR=22050,
                  CQT_HOP_DENOMINATOR=4,FEATURE_TILE_COLS=16)
    for key,value in expected.items():
        if len(re.findall(r'\.'+key+r'\('+str(value)+r'\)',link))!=1:
            raise ValueError('W-media selected existing CNN resource configuration drift: '+key)
    if link.count('.COARSE_GUIDANCE(1\'b1)')!=1:raise ValueError('W-media selected coarse guidance drift')
    return dict(policy=POLICY,normalized_preprocessed_text_sha256=digest(text.replace('\r\n','\n').replace('\r','\n')),
        task_entry='F807 APB descriptors and PCM actually connected',
        LCD_ready=False,software_tap_closed_on_reset=True,W_local_DAC_is_recording_source=False,
        single_raw_store=True,single_C_BLE_recording_object=True,full_HCI_Classic_GATT=True,
        selected_CNN_configuration=dict(**expected,COARSE_GUIDANCE=True),
        selected_CNN_configuration_origin='existing explicit resource-parent 4Hz guidance candidate',
        native_default_43844_172_inference_evidence_transferred=False,
        physical_CDC_accepted=False,hardware_accepted=False)


def source_negative_controls(stage,text):
    mutations=(('zero-task-descriptor','.cnn_start_task_id_i(task3_task_id)',".cnn_start_task_id_i(32'd0)"),
        ('zero-task-PCM','.cnn_frame_pcm_i(task3_frame_pcm)',".cnn_frame_pcm_i(32'd0)"),
        ('forged-LCD-ready',".lcd_link_ready_i(1'b0)",".lcd_link_ready_i(1'b1)"),
        ('W-local-tap-recording','ble_pcm=task3_record_pcm','ble_pcm=physical_frame_pcm'),
        ('missing-raw-store',') raw_store(',') duplicate_store('))
    rows=[]
    for name,before,after in mutations:
        if text.count(before)!=1:raise ValueError('W-media negative mutation anchor drift: '+name)
        try:selected_source_evidence(stage,text.replace(before,after,1))
        except ValueError as error:rows.append(dict(name=name,rejected=True,error=str(error)))
        else:raise ValueError('W-media unsafe source mutation survived: '+name)
    instance=re.search(r'(?m)^[ \t]+workstation_ble_raw_ddr_store #\(.*?\) raw_store\(.*?\);',text,re.S)
    if instance is None:raise ValueError('W-media actual raw instance mutation anchor absent')
    duplicate=instance[0]+'\n'+instance[0].replace(') raw_store(',') raw_store_duplicate(',1)
    try:selected_source_evidence(stage,text.replace(instance[0],duplicate,1))
    except ValueError as error:rows.append(dict(name='duplicate-raw-store',rejected=True,error=str(error)))
    else:raise ValueError('W-media duplicate recording storage survived')
    return rows
