"""Checked, default-off 138K BLE raw-store adaptation of staged first-party RTL.

The original 25K files, vendor bytes, codec and transfer buffers are immutable.
The BLE recorder remains the sole object/task/CRC/wire owner. This helper does
not select a profile, synthesize, or operate a board.
"""
from pathlib import Path
import hashlib
import json

POLICY='native-ble-raw-ddr-store-v1'
RAW_DRAIN_TIMEOUT_CYCLES=5_000_000
# Filled from the independently sealed upstream and normal generated GATT bytes.
INPUT_SHA256={'ble_recording.v': 'f5e9447a67bb74d5b9dd80ab112a7e4d2422bbeef0f4375faa68f7400489a696', 'ble_protocol_command.v': '608c2c818e1b3546d40983f8798a6e8d50ca26d3182870093f3fd18a05cdac00', 'bt_gatt.v': 'b6e293a9dfc89d09ea2476b12fd38fc2edce7d0337f7be21de91e3dbdb118b1d', 'bt_verilog_core.v': '89d47ee7ae8144e39b30743b0c1073aa9757e982fae863590ad74173252579d1', 'workstation_bluetooth.sv': '58700059b5d9865d8d3093d65fc9c19b75f3f7c68e86cafaae6a01d1baba70fa'}
UPSTREAM_SHA256={'projects/25k/example/RTL8723DS_PROTOCOL/rtl/ble_recording.v': 'f5e9447a67bb74d5b9dd80ab112a7e4d2422bbeef0f4375faa68f7400489a696', 'projects/25k/example/RTL8723DS_PROTOCOL/rtl/ble_protocol_command.v': '608c2c818e1b3546d40983f8798a6e8d50ca26d3182870093f3fd18a05cdac00', 'projects/25k/example/RTL8723DS_PROTOCOL/adaptations/bt_verilog_core.v': '89d47ee7ae8144e39b30743b0c1073aa9757e982fae863590ad74173252579d1', 'projects/138k/push2_workstation/usb_a/rtl/bluetooth/workstation_bluetooth.sv': '58700059b5d9865d8d3093d65fc9c19b75f3f7c68e86cafaae6a01d1baba70fa', 'projects/25k/example/RTL8723DS_PROTOCOL/prepare_adapted.py': 'bc49ab237f4135b8e4c4289dce7077ceb49350924c4b1d095085dea9422aca50', 'projects/25k/example/RTL8723DS_PROTOCOL/adaptations/bt_gatt.v': '5266ea2002a8180b446a467c2cccae5c65d5409bf642319418122f50df4f658b'}
RAW_STORE_SHA256='5262395f5031a14aa6cf18b359852590d3dcab33ee3fde9ce5f4e069b6fb9739'
RAW_CONTRACT_SHA256='86dd2b30edf3772dd637d2766d1b89120c1c4ef2216aa87c744ee76414519763'
RAW_STORE_PATH='rtl/memory/workstation_ble_raw_ddr_store.sv'
RAW_CONTRACT_PATH='rtl/memory/WORKSTATION_BLE_RAW_DDR_STORE.md'
STAGED_PATHS={name:'native_bluetooth/'+name for name in
    ('ble_recording.v','ble_protocol_command.v','bt_gatt.v','bt_verilog_core.v')}
STAGED_PATHS['workstation_bluetooth.sv']='rtl/bluetooth/workstation_bluetooth.sv'
OUTPUT_SHA256={'ble_recording.v': '9de775e873895153059513bb85eb2e01b2bbcacac9d0f00c3570758c648fabd4', 'ble_protocol_command.v': '99ebcd25f801bb502b883a05884207e243e4c1ec5123eb8eb99494b742962798', 'bt_gatt.v': 'b82f2028f058c5607fcd910eedf5a8b59906781ebc2d83f0750e8d19f42bf3c8', 'bt_verilog_core.v': '815f4ebd8be9e6f8525a7c64a03d28404fa9dd9147f1d397425c25a640eb2211', 'workstation_bluetooth.sv': '88b7cea5cacdd774ee97b055bc7219043fcdde38d54124c468ba08094c9e247c'}
PROTECTED_SHA256={
    'encoder':'d0bf6977f702ea89392e71c3cdbcb20afb767097b17ee78be49869fc05b0168b',
    'transfer_banks':'bd803dc01b7b9187bd6c4184f7cdf1fd7690097e84d1ac59765e3bc7ff86b78b',
    'wire_message_bytes':'1ed510ffba23b936f3b891e9d2b92ba2bd5f6cb58395afbe903d27678b1a3ae7',
}

PORTS='''
    // clk / clk_i raw storage only; object/task/CRC/wire ownership stays here.
    output wire raw_start_valid_o,
    input wire raw_start_ready_i,raw_start_done_i,
    output wire raw_clear_valid_o,
    input wire raw_clear_ready_i,raw_clear_done_i,
    output wire raw_capture_valid_o,
    output wire [31:0] raw_capture_index_o,raw_capture_pcm_o,
    input wire raw_capture_ready_i,
    output wire raw_close_valid_o,
    input wire raw_close_ready_i,raw_drained_i,raw_fault_i,
    input wire raw_object_fault_i,raw_channel_fault_i,
    input wire [3:0] raw_failure_code_i,
    input wire [31:0] raw_accepted_frames_i,raw_committed_frames_i,
    output wire raw_fetch_valid_o,
    input wire raw_fetch_ready_i,
    output wire [31:0] raw_fetch_offset_o,
    output wire [13:0] raw_fetch_length_o,
    input wire raw_fetch_done_i,raw_fetch_fault_i,raw_cache_valid_i,
    output wire [31:0] raw_sample_addr_o,
    input wire [31:0] raw_sample_word_i
'''
SIGNALS=('start_valid_o','start_ready_i','start_done_i','clear_valid_o','clear_ready_i','clear_done_i',
    'capture_valid_o','capture_index_o','capture_pcm_o','capture_ready_i','close_valid_o','close_ready_i',
    'drained_i','fault_i','object_fault_i','channel_fault_i','failure_code_i','accepted_frames_i',
    'committed_frames_i','fetch_valid_o','fetch_ready_i','fetch_offset_o','fetch_length_o','fetch_done_i',
    'fetch_fault_i','cache_valid_i','sample_addr_o','sample_word_i')
CONNECTIONS='\n'.join('        .raw_'+name+'(raw_'+name+'),' for name in SIGNALS)+'\n'


def digest(data):return hashlib.sha256(data).hexdigest()

def replace(text,old,new,count=1):
    if text.count(old)!=count:
        raise ValueError('BLE raw DDR adaptation anchor drift: '+old)
    return text.replace(old,new)


def protected_regions(data):
    anchors={
        'encoder':(b'module ble_rice_encoder',None),
        'transfer_banks':(b'    // Four explicit',b'    function [7:0] le32;'),
        'wire_message_bytes':(b'    function [7:0] transfer_message_byte;',b'    task reject;'),
    }
    result={}
    for name,(start,end) in anchors.items():
        if data.count(start)!=1 or (end and data.count(end)!=1):raise ValueError('BLE protected-region anchor drift: '+name)
        result[name]=digest(data[data.index(start):data.index(end) if end else None])
    if result!=PROTECTED_SHA256:raise ValueError('BLE codec/banks/wire bytes changed')
    return result


def recorder(text):
    text=replace(text,'    parameter integer SEAL_TIMEOUT_CYCLES=64',
        '    parameter integer SEAL_TIMEOUT_CYCLES=64,\n    parameter EXTERNAL_RAW_STORE=0,\n    parameter integer RAW_DRAIN_TIMEOUT_CYCLES=0')
    text=replace(text,'        C_DATA_PREP=4,C_DATA_BUILD=5,C_DATA_CRC=6,C_CODEC_START=7,C_CODEC_WAIT=8;',
        '        C_DATA_PREP=4,C_DATA_BUILD=5,C_DATA_CRC=6,C_CODEC_START=7,C_CODEC_WAIT=8,\n'
        '        C_RAW_START=9,C_RAW_CLEAR=10,C_RAW_FETCH_REQ=11,C_RAW_FETCH_WAIT=12;')
    text=replace(text,'    reg [3:0] state;','''    reg [3:0] state;
    reg raw_closing,raw_cache_owned,raw_clear_sent;
    reg [31:0] raw_wait;
    wire raw_waiting=raw_closing || state==C_RAW_START || state==C_RAW_CLEAR ||
        state==C_RAW_FETCH_REQ || state==C_RAW_FETCH_WAIT;
    wire raw_expired=EXTERNAL_RAW_STORE && raw_waiting && raw_wait>=RAW_DRAIN_TIMEOUT_CYCLES-1;
    wire raw_processing=state==C_BLOCK_PREP || state==C_BLOCK_CRC || state==C_CODEC_START ||
        state==C_CODEC_WAIT || state==C_DATA_PREP || state==C_DATA_BUILD || state==C_DATA_CRC;
    wire raw_cache_live=raw_cache_owned && raw_cache_valid_i && !raw_fault_i;
    wire raw_seal_admission=!raw_clear_sent && !raw_closing && state!=C_RAW_START && state!=C_RAW_CLEAR &&
        !raw_channel_fault_i && (recording_active || (record_state==0 ? raw_start_ready_i : raw_drained_i));
    assign raw_start_valid_o=EXTERNAL_RAW_STORE && state==C_RAW_START && connected && enable && !external_mutation_hold;
    assign raw_clear_valid_o=EXTERNAL_RAW_STORE && state==C_RAW_CLEAR && !raw_clear_sent;
    assign raw_capture_valid_o=EXTERNAL_RAW_STORE && resetn && enable && source_ready_i && !source_fault_i && pcm_valid_i &&
        capture_state==0 && !stop_pending && !external_capture_hold && recording_active;
    assign raw_capture_index_o=recorded_frames,raw_capture_pcm_o=pcm_pair_i;
    assign raw_close_valid_o=EXTERNAL_RAW_STORE && raw_closing && !raw_fault_i;
    assign raw_fetch_valid_o=EXTERNAL_RAW_STORE && state==C_RAW_FETCH_REQ && connected && enable;
    assign raw_fetch_offset_o=data_offset,raw_fetch_length_o={1'b0,data_length};
    assign raw_sample_addr_o=sample_address;
    initial if(EXTERNAL_RAW_STORE && (!EXTERNAL_PCM || !EXTERNAL_SEAL_PROTOCOL || CAPACITY_FRAMES>16384 || RAW_DRAIN_TIMEOUT_CYCLES<64))
        $fatal(1,"raw DDR requires external PCM, bounded capacity and explicit drain timeout");''')
    text=replace(text,'    assign seal_ready_o=EXTERNAL_SEAL_PROTOCOL && !seal_pending_o && !seal_request_q;',
        '    assign seal_ready_o=EXTERNAL_SEAL_PROTOCOL && !seal_pending_o && !seal_request_q &&\n'
        '        (!EXTERNAL_RAW_STORE || raw_seal_admission);')
    text=replace(text,'    wire external_capture_hold=EXTERNAL_SEAL_PROTOCOL && (seal_request_i || seal_pending_o);',
        '    wire external_capture_hold=(EXTERNAL_SEAL_PROTOCOL && (seal_request_i || seal_pending_o)) ||\n'
        '        (EXTERNAL_RAW_STORE && (raw_closing || raw_clear_sent || raw_fault_i));')
    text=replace(text,'    generate if(EXTERNAL_PCM) begin: live_capture',
        '''    generate if(EXTERNAL_RAW_STORE) begin: raw_storage
        // sample_word already has the original one-clock synchronous latency.
        always @* rom_word=raw_cache_live ? raw_sample_word_i:32'd0;
    end else if(EXTERNAL_PCM) begin: live_capture''')
    text=replace(text,'                if(!recording_active && capture_state==0)begin',
        '                if(!recording_active && capture_state==0 && (!EXTERNAL_RAW_STORE || raw_drained_i))begin')
    text=replace(text,'if(seal_wait<SEAL_TIMEOUT_CYCLES)',
        'if(seal_wait<(EXTERNAL_RAW_STORE ? RAW_DRAIN_TIMEOUT_CYCLES:SEAL_TIMEOUT_CYCLES))')
    text=replace(text,'if(seal_wait==SEAL_TIMEOUT_CYCLES-1 && !seal_failed_seen)',
        'if(seal_wait==(EXTERNAL_RAW_STORE ? RAW_DRAIN_TIMEOUT_CYCLES:SEAL_TIMEOUT_CYCLES)-1 && !seal_failed_seen)')
    text=replace(text,'            state<=C_IDLE; result_payload<=0; command_status<=0; command_length<=0;',
        '            state<=C_IDLE; result_payload<=0; command_status<=0; command_length<=0;\n'
        '            raw_closing<=0;raw_cache_owned<=0;raw_clear_sent<=0;raw_wait<=0;')
    text=replace(text,'                0: if(record_state==1 || record_state==2 || record_state==3) begin',
        '                0: if((record_state==1 || record_state==2 || record_state==3) && (!EXTERNAL_RAW_STORE || !raw_closing)) begin')
    old='''                    if(stop_pending && recorded_frames!=0) begin
                        record_state<=4; object_crc<=~recording_crc;
                        task_finished[stop_task]<=1; task_time[stop_task]<=elapsed_ms;
                        stop_pending<=0;'''
    text=replace(text,old,'''                    if(stop_pending && recorded_frames!=0) begin
                        if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;object_crc<=~recording_crc;end
                        else begin
                            record_state<=4; object_crc<=~recording_crc;
                            task_finished[stop_task]<=1; task_time[stop_task]<=elapsed_ms;
                            stop_pending<=0;
                        end''')
    text=replace(text,'if(EXTERNAL_PCM) begin capture_word<=pcm_pair_i;capture_state<=2;end',
        'if(EXTERNAL_PCM) begin\n'
        '                            if(!EXTERNAL_RAW_STORE || raw_capture_ready_i)begin capture_word<=pcm_pair_i;capture_state<=2;end\n'
        '                        end')
    old='''                        record_state<=4; object_crc<=~crc_byte(recording_crc,capture_word[7:0]);
                        if(stop_pending) begin task_finished[stop_task]<=1;task_time[stop_task]<=elapsed_ms;end
                        else stop_reason<=2;
                        stop_pending<=0;'''
    text=replace(text,old,'''                        object_crc<=~crc_byte(recording_crc,capture_word[7:0]);
                        if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;if(!stop_pending)stop_reason<=2;end
                        else begin
                            record_state<=4;
                            if(stop_pending) begin task_finished[stop_task]<=1;task_time[stop_task]<=elapsed_ms;end
                            else stop_reason<=2;
                            stop_pending<=0;
                        end''')
    text=replace(text,'                record_state<=5;stop_reason<=!enable || !source_ready_i ? 6 : 3;capture_state<=0;',
        '                record_state<=5;stop_reason<=!enable || !source_ready_i ? 6 : 3;capture_state<=0;\n'
        '                if(EXTERNAL_RAW_STORE)raw_closing<=1;')
    old='''            if(seal_commit && enable && !(EXTERNAL_PCM && (!source_ready_i || source_fault_i)))begin
                record_state<=4;object_crc<=~recording_crc;stop_reason<=1;stop_pending<=0;'''
    text=replace(text,old,'''            if(seal_commit && enable && !(EXTERNAL_PCM && (!source_ready_i || source_fault_i)) &&
               (!EXTERNAL_RAW_STORE || !raw_closing))begin
                object_crc<=~recording_crc;stop_reason<=1;
                if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;end
                else begin record_state<=4;stop_pending<=0;end''')
    text=replace(text,'                if(stop_pending)begin task_finished[stop_task]<=1;task_time[stop_task]<=elapsed_ms;end',
        '                if(stop_pending && !EXTERNAL_RAW_STORE)begin task_finished[stop_task]<=1;task_time[stop_task]<=elapsed_ms;end')
    allocation='''                                object_counter<=object_counter+1'b1; recording_id<=object_counter+1'b1;
                                recorded_frames<=0; recording_crc<=32'hffffffff; object_crc<=0;
                                limit_frames<=payload[63:32]==0 ? CAPACITY_FRAMES : payload[63:32];
                                record_state<=1; stop_reason<=0; stop_pending<=0; capture_state<=0;
                                start_task<=new_task_slot; allocate_task(object_counter+1'b1);'''
    text=replace(text,allocation,'''                                if(EXTERNAL_RAW_STORE)begin
                                    if(!raw_start_ready_i || raw_clear_sent || raw_closing)reject(8'h82);
                                    else state<=C_RAW_START;
                                end else begin
'''+allocation+'''
                                end''')
    clear='''                                result_payload<={352'd0,recording_id}; success(4);
                                record_state<=0; recording_id<=0; recorded_frames<=0;
                                object_crc<=0; current_operation<=0; stop_reason<=0;'''
    text=replace(text,clear,'''                                if(EXTERNAL_RAW_STORE)begin
                                    if(raw_channel_fault_i || raw_clear_sent || raw_closing)reject(8'h82);
                                    else begin raw_cache_owned<=0;state<=C_RAW_CLEAR;end
                                end else begin
'''+clear+'''
                                end''')
    text=replace(text,"crc_work<=32'hffffffff;index<=0;state<=C_BLOCK_PREP;data_replay<=",
        "crc_work<=32'hffffffff;index<=0;state<=EXTERNAL_RAW_STORE ? C_RAW_FETCH_REQ:C_BLOCK_PREP;data_replay<=",2)
    text=replace(text,'                            else if(command_replay) begin',
        '                            else if(EXTERNAL_RAW_STORE && command_replay &&\n'
        '                                    (record_state!=4 || replay_recording_id!=recording_id))reject(8\'h88);\n'
        '                            else if(command_replay) begin')
    raw_states='''                C_RAW_START: begin
                    if(external_mutation_hold || raw_fault_i)reject(8'h82);
                    else if(raw_start_valid_o && raw_start_ready_i)begin
'''+allocation+'''
                        state<=C_IDLE;
                    end
                end
                C_RAW_CLEAR: begin end // Actual clear survives link/observer loss below.
                C_RAW_FETCH_REQ: if(raw_fetch_valid_o && raw_fetch_ready_i)begin
                    raw_cache_owned<=0;state<=C_RAW_FETCH_WAIT;
                end
                C_RAW_FETCH_WAIT: begin
                    if(raw_fetch_fault_i || raw_fault_i)reject(8'h83);
                    else if(raw_fetch_done_i && raw_cache_valid_i)begin raw_cache_owned<=1;state<=C_BLOCK_PREP;end
                end
'''
    text=replace(text,'                C_OPERATION: begin',raw_states+'                C_OPERATION: begin')
    policy='''            // Storage lifetime only; this same always block still owns all
            // object IDs, task terminals, capture prefix and CRC.
            if(EXTERNAL_RAW_STORE)begin
                if(raw_waiting)begin if(raw_wait<RAW_DRAIN_TIMEOUT_CYCLES)raw_wait<=raw_wait+1'b1;end
                else raw_wait<=0;
                if(raw_clear_valid_o && raw_clear_ready_i)raw_clear_sent<=1;
                if(raw_clear_sent && raw_clear_done_i)begin
                    raw_clear_sent<=0;
                    if(state==C_RAW_CLEAR)begin
'''+clear+'''
                    end
                end
                if(raw_closing && raw_drained_i)begin
                    raw_closing<=0;
                    if(record_state!=5 && enable && source_ready_i && !source_fault_i && !raw_fault_i && !raw_expired &&
                       raw_accepted_frames_i==recorded_frames && raw_committed_frames_i==recorded_frames)begin
                        record_state<=4;
                        if(stop_pending)begin task_finished[stop_task]<=1;task_time[stop_task]<=elapsed_ms;end
                        stop_pending<=0;
                    end else if(record_state!=0)begin record_state<=5;stop_reason<=!enable || !source_ready_i ? 6:3;end
                end
                if(!connected || !enable || transfer_consume || state==C_RAW_FETCH_REQ || state==C_RAW_CLEAR ||
                   (state==C_IDLE && command_start && opcode==8'h34) ||
                   raw_fault_i || raw_fetch_fault_i)raw_cache_owned<=0;
                if((raw_fault_i && record_state!=0) || (raw_capture_valid_o && !raw_capture_ready_i) ||
                   (raw_expired && raw_waiting) ||
                   (seal_pending_o && seal_wait>=RAW_DRAIN_TIMEOUT_CYCLES-1 && !seal_failed_seen) ||
                   (raw_closing && raw_drained_i &&
                    (raw_accepted_frames_i!=recorded_frames || raw_committed_frames_i!=recorded_frames)))begin
                    if(record_state!=0)record_state<=5;
                    capture_state<=0;stop_reason<=3;raw_cache_owned<=0;transfer_valid<=0;
                    if(recording_active)raw_closing<=1;
                    if(!task_finished[start_task])begin
                        task_finished[start_task]<=1;task_failed[start_task]<=1;task_time[start_task]<=elapsed_ms;
                    end
                    if(stop_pending)begin
                        task_finished[stop_task]<=1;task_failed[stop_task]<=1;task_time[stop_task]<=elapsed_ms;
                    end
                    if(state==C_RAW_START || state==C_RAW_CLEAR || state==C_RAW_FETCH_REQ ||
                       state==C_RAW_FETCH_WAIT || raw_processing)reject(8'h83);
                end else if(raw_processing && !raw_cache_live)begin
                    raw_cache_owned<=0;transfer_valid<=0;reject(8'h83);
                end
            end
'''
    text=replace(text,'            else begin state<=C_IDLE;transfer_valid<=0;end\n',
        '            else begin if(!EXTERNAL_RAW_STORE || state!=C_RAW_CLEAR)state<=C_IDLE;transfer_valid<=0;end\n'+policy)
    text=replace(text,'if(state!=C_IDLE) state<=C_IDLE;',
        'if(state!=C_IDLE && (!EXTERNAL_RAW_STORE || state!=C_RAW_CLEAR)) state<=C_IDLE;')
    # Preserve Verilog declaration ordering: none of these predicates may
    # create an implicit leaf before the original named state is declared.
    start=text.index('    reg raw_closing,raw_cache_owned,raw_clear_sent;')
    end=text.index('    reg [383:0] result_payload;')
    control=text[start:end]
    text=replace(text,control,'')
    control=replace(control,'    reg raw_closing,raw_cache_owned,raw_clear_sent;\n','')
    control=replace(control,'    wire raw_seal_admission=','    assign raw_seal_admission=')
    text=replace(text,'    reg [3:0] state;',
        '    reg [3:0] state;\n    reg raw_closing,raw_cache_owned,raw_clear_sent;\n    wire raw_seal_admission;')
    text=replace(text,'    reg [31:0] rom_word;',control+'    reg [31:0] rom_word;')
    return text


def adapt_sources(inputs):
    if set(inputs)!=set(INPUT_SHA256):raise ValueError('BLE raw DDR input inventory changed')
    for name,data in inputs.items():
        if digest(data)!=INPUT_SHA256[name]:raise ValueError('BLE raw DDR original source identity changed: '+name)
    protected_regions(inputs['ble_recording.v'])
    outputs={}
    for name,data in inputs.items():
        text=data.decode()
        if name=='ble_recording.v':text=recorder(text)
        elif name=='ble_protocol_command.v':
            text=replace(text,'parameter EXTERNAL_SEAL_PROTOCOL=0) (',
                'parameter EXTERNAL_SEAL_PROTOCOL=0,\n    parameter EXTERNAL_RAW_STORE=0, parameter integer RAW_DRAIN_TIMEOUT_CYCLES=0) (')
        else:
            text=replace(text,'    parameter EXTERNAL_SEAL_PROTOCOL=0\n',
                '    parameter EXTERNAL_SEAL_PROTOCOL=0,\n    parameter EXTERNAL_RAW_STORE=0,\n    parameter integer RAW_DRAIN_TIMEOUT_CYCLES=0\n')
        kind='reg' if name=='ble_recording.v' else 'wire'
        anchor='    output '+kind+' [31:0] seal_recording_id_o, seal_frames_o, seal_crc_o\n);'
        text=replace(text,anchor,anchor[:-3]+','+PORTS+');')
        if name!='ble_recording.v':
            text=replace(text,'.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),',
                '.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),.EXTERNAL_RAW_STORE(EXTERNAL_RAW_STORE),'
                '.RAW_DRAIN_TIMEOUT_CYCLES(RAW_DRAIN_TIMEOUT_CYCLES),')
            anchor='        .seal_recording_id_o(seal_recording_id_o),.seal_frames_o(seal_frames_o),.seal_crc_o(seal_crc_o),\n'
            text=replace(text,anchor,anchor+CONNECTIONS)
        outputs[name]=text.encode()
    protected_regions(outputs['ble_recording.v'])
    if {name:digest(data) for name,data in outputs.items()}!=OUTPUT_SHA256:
        raise ValueError('BLE raw DDR reviewed output identity changed')
    return outputs


def prepare(root,stage,*,enabled=False):
    root,stage=Path(root).resolve(),Path(stage).resolve()
    if not enabled:return dict(policy=POLICY,enabled=False,modified_files=[],deployment_allowed=False)
    repository=root.parents[3]
    upstream={p:(repository/p).read_bytes() for p in UPSTREAM_SHA256}
    for path,data in upstream.items():
        if digest(data)!=UPSTREAM_SHA256[path]:raise ValueError('BLE raw DDR upstream source drift: '+path)
    raw=(root/RAW_STORE_PATH).read_bytes()
    if digest(raw)!=RAW_STORE_SHA256:raise ValueError('BLE raw DDR store identity changed')
    contract=(root/RAW_CONTRACT_PATH).read_bytes()
    if digest(contract)!=RAW_CONTRACT_SHA256:raise ValueError('BLE raw DDR contract identity changed')
    inputs={name:(stage/path).read_bytes() for name,path in STAGED_PATHS.items()}
    outputs=adapt_sources(inputs)
    # Check the entire input closure before publishing any transformed file.
    if (any((repository/p).read_bytes()!=data for p,data in upstream.items()) or
        (root/RAW_STORE_PATH).read_bytes()!=raw or (root/RAW_CONTRACT_PATH).read_bytes()!=contract):
        raise ValueError('BLE raw DDR inputs changed during adaptation')
    for name,data in inputs.items():
        if (stage/STAGED_PATHS[name]).read_bytes()!=data:raise ValueError('BLE raw DDR staged source changed during adaptation')
    for name,data in outputs.items():(stage/STAGED_PATHS[name]).write_bytes(data)
    result=dict(policy=POLICY,enabled=True,modified_files=list(STAGED_PATHS.values()),
        upstream_sha256=UPSTREAM_SHA256,raw_store_sha256=RAW_STORE_SHA256,
        raw_contract_sha256=RAW_CONTRACT_SHA256,generator_sha256=digest(Path(__file__).read_bytes()),
        input_sha256={n:digest(b) for n,b in inputs.items()},output_sha256={n:digest(b) for n,b in outputs.items()},
        protected_region_sha256=PROTECTED_SHA256,
        drain_budget_control_cycles=RAW_DRAIN_TIMEOUT_CYCLES,old_ram_timeout_cycles=64,
        default_parameter_enabled=False,profile_selected=False,hardware_tested=False,
        physical_cdc_accepted=False,deployment_allowed=False)
    verify_prepared(root,stage,result)
    return result


def verify_prepared(root,stage,evidence):
    """Revalidate the pinned closure and transformed outputs at profile publish."""
    root,stage=Path(root).resolve(),Path(stage).resolve()
    if evidence.get('policy')!=POLICY or evidence.get('enabled') is not True:
        raise ValueError('BLE raw DDR preparation evidence missing')
    for key,expected in (
        ('modified_files',list(STAGED_PATHS.values())),('upstream_sha256',UPSTREAM_SHA256),
        ('input_sha256',INPUT_SHA256),('output_sha256',OUTPUT_SHA256),
        ('protected_region_sha256',PROTECTED_SHA256),('raw_store_sha256',RAW_STORE_SHA256),
        ('raw_contract_sha256',RAW_CONTRACT_SHA256),('generator_sha256',digest(Path(__file__).read_bytes())),
        ('drain_budget_control_cycles',RAW_DRAIN_TIMEOUT_CYCLES),('old_ram_timeout_cycles',64),
        ('default_parameter_enabled',False),('profile_selected',False),('hardware_tested',False),
        ('physical_cdc_accepted',False),('deployment_allowed',False),
    ):
        if evidence.get(key)!=expected:raise ValueError('BLE raw DDR preparation evidence drift: '+key)
    for path,sha in UPSTREAM_SHA256.items():
        if digest((root.parents[3]/path).read_bytes())!=sha:raise ValueError('BLE raw DDR upstream source drift: '+path)
    for path,sha in ((RAW_STORE_PATH,RAW_STORE_SHA256),(RAW_CONTRACT_SHA256)):
        if digest((root/path).read_bytes())!=sha:raise ValueError('BLE raw DDR store/contract drift: '+path)
    for name,path in STAGED_PATHS.items():
        if digest((stage/path).read_bytes())!=OUTPUT_SHA256[name]:raise ValueError('BLE raw DDR output drift: '+path)
    protected_regions((stage/STAGED_PATHS['ble_recording.v']).read_bytes())
    return dict(verified=True,policy=POLICY,output_sha256=OUTPUT_SHA256,deployment_allowed=False)
