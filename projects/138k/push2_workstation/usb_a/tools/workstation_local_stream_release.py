"""Select preserved mailbox releases without changing frozen stream behavior.

The native source differs from the locked parent only by preservation attributes.
No cycle, reset polarity, payload, drop counter or handshake changes are allowed.
Historical profiles continue compiling the original baseline source.
"""
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

KEY = 'stream_release_policy'
POLICY = 'task3_W_preserved_local_stream_release3_v1'
SOURCE = 'rtl/control/workstation_stream_cdc_local_release.sv'
ORIGINAL = 'src/migration/gw138k_stream_cdc.sv'
TOOL = 'tools/workstation_local_stream_release.py'
CONTROLLED = 'rtl/workstation/workstation_runtime_controlled.sv'
DEPENDENCIES = (TOOL, SOURCE, CONTROLLED)
PARENT_SHA256 = '90cb55acd6f83965d74b843993bed625d121ae2eefafbd928eb6fececb6e5376'
PARENT_SHIFT = b'    logic [2:0] source_release, destination_release;\n    (* ASYNC_REG="TRUE" *) logic ack_meta, ack_sync, req_meta, req_sync;\n    logic req_settled, request_toggle, acknowledge_toggle;\n    logic [WIDTH-1:0] held_data;\n    always_ff @(posedge source_clk or negedge reset_n)\n        if(!reset_n) source_release<=0;\n        else source_release<={source_release[1:0],1\'b1};\n    always_ff @(posedge destination_clk or negedge reset_n)\n        if(!reset_n) destination_release<=0;\n        else destination_release<={destination_release[1:0],1\'b1};\n'
SELECTED_SHIFT = b'    logic [2:0] source_release, destination_release;\n    (* ASYNC_REG="TRUE" *) logic ack_meta, ack_sync, req_meta, req_sync;\n    logic req_settled, request_toggle, acknowledge_toggle;\n    logic [WIDTH-1:0] held_data;\n    // Only the selected retained mailboxes keep independent release state.\n    // Literal attributes are required by Gowin; parameter-valued attributes\n    // are not honored by this synthesis version.\n    generate if(PRESERVE_RELEASE)begin:g_preserved_release\n        (* ASYNC_REG="TRUE", syn_preserve=1, syn_keep=1 *)\n        logic [2:0] source_pipe, destination_pipe;\n        always_ff @(posedge source_clk or negedge reset_n)\n            if(!reset_n)source_pipe<=0;\n            else source_pipe<={source_pipe[1:0],1\'b1};\n        always_ff @(posedge destination_clk or negedge reset_n)\n            if(!reset_n)destination_pipe<=0;\n            else destination_pipe<={destination_pipe[1:0],1\'b1};\n        assign source_release=source_pipe;\n        assign destination_release=destination_pipe;\n    end else begin:g_parent_release\n        always_ff @(posedge source_clk or negedge reset_n)\n            if(!reset_n)source_release<=0;\n            else source_release<={source_release[1:0],1\'b1};\n        always_ff @(posedge destination_clk or negedge reset_n)\n            if(!reset_n)destination_release<=0;\n            else destination_release<={destination_release[1:0],1\'b1};\n    end endgenerate\n'
PARAMETER_PARENT = b'parameter integer WIDTH=32)'
PARAMETER_SELECTED = b'parameter integer WIDTH=32, parameter bit PRESERVE_RELEASE=0)'
BINDINGS = '    defparam pc_bytes.PRESERVE_RELEASE=1;\n    defparam health_snapshot.PRESERVE_RELEASE=1;\n'
CONTROLLED_PARENT_SHA256 = 'bd58103e17b36d9c8d5f9fe1b0346691840417e94beb59a6c12d16c725c7ef8b'
ANCHOR = '    gw138k_stream_cdc #(.WIDTH(8)) pc_bytes('


def restore_controlled(source):
    require(source.count(BINDINGS) == 1 and source.count(ANCHOR) == 1,
            'local managed mailbox bindings missing/duplicated')
    return source.replace(BINDINGS, '', 1)


def prepare_controlled(stage):
    path = Path(stage)/CONTROLLED
    source = path.read_text()
    require(source.count(ANCHOR) == 1 and BINDINGS not in source,
            'managed mailbox source anchor drift')
    selected = source.replace(ANCHOR, BINDINGS + ANCHOR, 1)
    require(restore_controlled(selected) == source, 'managed mailbox inverse drift')
    path.write_text(selected)



def require(ok, message):
    if not ok:
        raise ValueError('local stream release: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown source policy')
    if value is None:
        return False
    require(configuration.get('demo_role') == 'W', 'requires paired W')
    return True


def evidence(stage):
    original = (Path(stage) / ORIGINAL).read_bytes()
    selected = (Path(stage) / SOURCE).read_bytes()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    controlled = (Path(stage)/CONTROLLED).read_text()
    require(sha(restore_controlled(controlled).encode()) == CONTROLLED_PARENT_SHA256,
            'managed source differs outside the two mailbox bindings')
    require(sha(original) == PARENT_SHA256, 'frozen parent changed')
    require(selected.count(SELECTED_SHIFT) == 1 and
            selected.count(PARAMETER_SELECTED) == 1 and
            selected.replace(SELECTED_SHIFT, PARENT_SHIFT, 1).replace(PARAMETER_SELECTED, PARAMETER_PARENT, 1) == original,
            'native source differs beyond release preservation')
    return dict(policy=POLICY, original=ORIGINAL, original_sha256=sha(original),
                source=SOURCE, source_sha256=sha(selected), release_edges=3,
                controlled_sha256=sha(controlled.encode()),
                controlled_parent_sha256=CONTROLLED_PARENT_SHA256,
                preserved_mailboxes=['u_managed/pc_bytes', 'u_managed/health_snapshot'],
                handshake_and_reset_behavior_unchanged=True)


def select(stage, files, configuration):
    if not configured(configuration):
        return None
    original = [row for row in files if row.get('path') == ORIGINAL]
    require(len(original) == 1 and original[0].get('enable') == '1',
            'parent must be compiled exactly once')
    require(not any(row.get('path') == SOURCE for row in files), 'native source already listed')
    prepare_controlled(stage)
    receipt = evidence(stage)
    original[0].set('enable', '0')
    ET.SubElement(files, 'File', path=SOURCE, type='file.verilog', enable='1')
    return receipt


def verify(stage, configuration, receipt, enabled):
    if not configured(configuration):
        require(receipt is None and SOURCE not in enabled, 'unselected source present')
        return None
    require(receipt == evidence(stage), 'source receipt changed')
    require(ORIGINAL not in enabled and list(enabled).count(SOURCE) == 1,
            'exactly one native stream implementation required')
    return receipt
