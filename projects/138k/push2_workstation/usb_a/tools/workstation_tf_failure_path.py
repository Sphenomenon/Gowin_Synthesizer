"""Exact inverse of same-edge TF fault-presence and receipt equality factoring."""
import hashlib
SOURCE='rtl/tf_audio/workstation_tf_direct_runtime_service.sv'
PARENT_SHA256='9195f5a23fb3317f99861cd4c39875f2658f8f4d328cbb1250a4301e8ccd708d'
SELECTED_SHA256='c113452a61b9fa3d2bdd8c39d15c228f80109d8dccc024f88a798a17d4abc683'
EDITS=[('    wire receipt_current=receipt_local[33:2]==session;', '    (* syn_keep=1 *) wire [3:0] receipt_session_equal;\n    for(genvar receipt_byte=0;receipt_byte<4;receipt_byte=receipt_byte+1)begin:g_receipt_session_equal\n        assign receipt_session_equal[receipt_byte]=~(|(receipt_local[2+receipt_byte*8+:8]^session[receipt_byte*8+:8]));\n    end\n    wire receipt_current=&receipt_session_equal;'), ('    wire new_failure=failure_now!=0 && !failed;', "    // Cancellation needs the existence of a fault, independently of the\n    // diagnostic code priority. Avoid code selection followed by decoding on\n    // the same-cycle source/analysis stop path. The default preserves RTL\n    // procedural unknown-guard semantics; no cycle or public status changes.\n    wire [7:0] fault_conditions={native_file_error,\n        session_applied && native_ingress_error,transport_error_i,bad_context,\n        session_applied && !analysis_live && (runtime_epoch_i!=session_epoch || runtime_44k1_i!=session_rate),\n        !analysis_live && physical_failure_event,session_applied && native_empty,\n        analysis_live && state==LAUNCH && quiet_wait==QUIET_TIMEOUT_CYCLES-1};\n    reg failure_present;\n    always @* begin\n        failure_present=0;\n        case(^fault_conditions)\n            1'b0,1'b1:if(live || state==LAUNCH)failure_present=|fault_conditions;\n            default:failure_present=failure_now!=0;\n        endcase\n    end\n    wire new_failure=failure_present && !failed;")]

def normalize(payload):
    from tools.workstation_tf_compute_local_release import restore,SERVICE
    payload=restore(SERVICE,payload)
    text=payload.decode()if isinstance(payload,bytes)else payload
    digest=lambda s:hashlib.sha256(s.encode()).hexdigest()
    if digest(text)==PARENT_SHA256:return text.encode()
    if digest(text)!=SELECTED_SHA256:raise ValueError('TF failure path source drift')
    for before,after in reversed(EDITS):
        if text.count(after)!=1:raise ValueError('TF failure path inverse anchor drift')
        text=text.replace(after,before,1)
    if digest(text)!=PARENT_SHA256:raise ValueError('TF failure path inverse drift')
    return text.encode()
