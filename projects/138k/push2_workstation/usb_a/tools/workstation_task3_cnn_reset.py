"""Exact inverse of opt-in W CNN reset changes; no production RTL overlay."""
from pathlib import Path
import hashlib

POLICY='task3_w_CNN_control_native_reset_release3_v1'
STREAM='rtl/music/workstation_task3_cnn_stream_w.sv'
TASK='rtl/music/workstation_cnn_task_service.sv'
LINK='rtl/music/basic_pitch_workstation_link.sv'
PARENTS={STREAM:'65dc790a059074840371b1bef776007625c5bcc95199a881ccec202d93109151',
         TASK:'f9fd9b1a07bb500dbd45ed49bfca588d28ed8324c89f37ebed3e6e7e328492fa',
         LINK:'4e4cf079b3e0cf6fde20fbe5e92661ae671116536ecea8765a34b62b91af9227'}
STREAM_BLOCK='''    // The shared request asserts immediately; each clock releases only after
    // three local edges. Never use native DDR release as control-domain CE.
    wire reset_request_n=reset_ni && memory_reset_ni;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] control_release;
    always @(posedge clk_i or negedge reset_request_n)
        if(!reset_request_n)control_release<=0;
        else control_release<={control_release[1:0],1'b1};
    wire control_reset_n=control_release[2];
'''
TASK_BLOCK='''    // Opt-in W contract: common asynchronous assertion, independent local
    // release. Default retains the frozen standalone task reset contract.
    wire control_reset_n,native_reset_n,overflow_reset_n;
    generate if(DOMAIN_RESET_RELEASE)begin:g_domain_reset
        wire request_n=reset_ni && memory_reset_ni;
        (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] control_release,native_release;
        always @(posedge clk_i or negedge request_n)
            if(!request_n)control_release<=0;
            else control_release<={control_release[1:0],1'b1};
        always @(posedge memory_clk_i or negedge request_n)
            if(!request_n)native_release<=0;
            else native_release<={native_release[1:0],1'b1};
        assign control_reset_n=control_release[2];
        assign native_reset_n=native_release[2];
        assign overflow_reset_n=native_reset_n;
    end else begin:g_legacy_reset
        assign control_reset_n=reset_ni;
        assign native_reset_n=reset_ni && memory_reset_ni;
        assign overflow_reset_n=reset_ni;
    end endgenerate
'''
LINK_PARAMETER='''    // W task owner supplies coherent resets already released in each domain.
    // Default ledgers retain their lifetime across memory-only reset/loss.
    parameter bit NATIVE_LIFETIME_RESET = 1'b0,
'''


def inverse(path,text):
    if path==STREAM:
        from tools.workstation_w_identity_bytes import normalize
        text=normalize(path,text)
    def replace(before,after):
        nonlocal text
        if text.count(before)!=1:raise ValueError('CNN reset exact anchor changed: '+path+': '+before[:90])
        text=text.replace(before,after,1)
    if path==STREAM:
        replace(STREAM_BLOCK,'')
        replace("workstation_cnn_task_service #(.DOMAIN_RESET_RELEASE(1'b1),",'workstation_cnn_task_service #(')
        text=text.replace('control_reset_n','reset_ni')
    elif path==TASK:
        replace("    parameter bit DOMAIN_RESET_RELEASE=1'b0,\n",'')
        replace(TASK_BLOCK,'')
        replace('wire live=control_reset_n && (DOMAIN_RESET_RELEASE || memory_reset_ni) && backend_sync && !fatal_o;',
                'wire live=reset_ni && memory_reset_ni && backend_sync && !fatal_o;')
        replace('backend_meta<=backend_ready_i && (!DOMAIN_RESET_RELEASE || native_reset_n);','backend_meta<=backend_ready_i;')
        replace('        .NATIVE_LIFETIME_RESET(DOMAIN_RESET_RELEASE),\n','')
        replace('.clk_50m(clk_i),.reset_n(control_reset_n),.memory_clk(memory_clk_i),\n        .memory_reset_n(DOMAIN_RESET_RELEASE ? native_reset_n : memory_reset_ni)',
                '.clk_50m(clk_i),.reset_n(control_reset_n),.memory_clk(memory_clk_i),.memory_reset_n(memory_reset_ni)')
        text=text.replace('control_reset_n','reset_ni').replace('overflow_reset_n','reset_ni').replace('native_reset_n','reset_ni && memory_reset_ni')
    elif path==LINK:
        replace(LINK_PARAMETER,'')
        replace('        wire lifetime_reset_n=NATIVE_LIFETIME_RESET ? memory_reset_n : reset_n;\n','')
        replace('always @(posedge memory_clk or negedge lifetime_reset_n) begin\n            if(!lifetime_reset_n)',
                'always @(posedge memory_clk or negedge reset_n) begin\n            if(!reset_n)')
        # Production also applies the established diagnostic CDC transform.
        # Admit only its complete, exact pair of edits before checking v11.
        diagnostic='''    // UART samples levels, not event counts. Retain its bit layout while
    // sampling the seven DDR-domain diagnostics through local two-stage FFs.
    wire [6:0] ddr_trace_sync;
    gw138k_level_cdc #(.WIDTH(7)) u_trace_cdc(
        .clk(clk_50m),.reset_n(reset_n),
        .data_i({ddr_cmd_valid,ddr_cmd_ready,ddr_req,ddr_ready,ddr_rsp_valid,memory_reset_n,memory_calibrated}),
        .data_o(ddr_trace_sync));
    wire [9:0] model_path_trace = {bp_mem_req,bp_mem_ready,
        ddr_trace_sync[6:2],ddr_rsp_fifo_valid,ddr_trace_sync[1:0]};'''
        if 'ddr_trace_sync' in text:
            replace(diagnostic,'''    wire [9:0] model_path_trace = {bp_mem_req,bp_mem_ready,
        ddr_cmd_valid,ddr_cmd_ready,ddr_req,ddr_ready,
        ddr_rsp_valid,ddr_rsp_fifo_valid,memory_reset_n,memory_calibrated};''')
            replace("model_status,ddr_trace_sync[0],1'b1};","model_status,memory_calibrated,1'b1};")
        # Existing explicit paired preparation changes only these defaults.
        for selected,parent in [('WIN_LEN=44100,FRAME_LIMIT=8','WIN_LEN=43844,FRAME_LIMIT=172'),
                ('CQT_HOP_NUMERATOR=22050,CQT_HOP_DENOMINATOR=4','CQT_HOP_NUMERATOR=256,CQT_HOP_DENOMINATOR=1'),
                ("FEATURE_TILE_COLS=16,\n    parameter bit COARSE_GUIDANCE=1'b1,", "FEATURE_TILE_COLS=0,\n    parameter bit COARSE_GUIDANCE=1'b0,")]:
            if selected in text:replace(selected,parent)
    else:raise ValueError('unreviewed CNN reset source: '+path)
    parent=hashlib.sha256(text.encode()).hexdigest()
    if parent!=PARENTS[path]:raise ValueError('bytes outside W CNN reset change drifted: '+path)
    return text


def source_evidence(stage):
    stage=Path(stage);rows=[]
    for path in PARENTS:
        if not (stage/path).is_file():raise ValueError('CNN reset source missing: '+path)
        payload=(stage/path).read_text();inverse(path,payload)
        rows.append(dict(path=path,selected_sha256=hashlib.sha256(payload.encode()).hexdigest(),
                         parent_sha256=PARENTS[path],exact_inverse_verified=True))
    return dict(policy=POLICY,sources=rows,default_task_and_link_policies_preserved=True,
                full_CDC_accepted=False,routed_timing_verified=False,hardware_tested=False)
