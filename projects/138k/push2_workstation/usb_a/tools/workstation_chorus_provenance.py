"""Exact Chorus verification chain and explicit native source identity gate."""
from pathlib import Path
import hashlib
import json

STRICT_POLICY = 'locked_native_v1'
NARROW_POLICY = 'narrow_exact_rate_delay_v1'
SOURCE = 'rtl/audio/workstation_runtime_chorus_effect.sv'
PROVENANCE = 'rtl/audio/workstation_runtime_chorus_effect.provenance.json'
ADAPTATION = 'rtl/audio/workstation_runtime_chorus_effect.rate_delay_narrowing.json'
PROVENANCE_SHA256 = '41babc5ece0ec3ca5cae68e2f7d5c5069e93d1acb63224771d7483c138f32b48'
ADAPTATION_SHA256 = '0f2811bdfa33f04111cc036cace4b986eecf25306cdb13fd297b56d0bcfbadf4'

# Current scratch data is written in state2 before every state3 consumer.
# Keep the historical native/provenance chain byte-for-byte and reverse only
# this identity-bound reset removal before applying that original chain.
CHORUS_SCRATCH_SOURCE_SHA256 = 'a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900'
CHORUS_SCRATCH_PARENT_SHA256 = 'f0d9200a165d40f0b44fc69c3aaae3a8a75ed14420dd91d11ff49136f22e0176'
CHORUS_SCRATCH_EDITS = (('    if(!local_history_clear && state==1) begin '
  'read_l<=memory_l[read_address];read_r<=memory_r[read_address];end\n'
  '    if(!local_history_clear && state==3) begin '
  'memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end\n'
  '  end\n'
  '  always_ff @(posedge clk_i or negedge rst_ni) begin\n'
  '    if(!rst_ni) begin\n'
  '      pointer<=0;read_address<=0;frames<=0;state<=0;gain<=0;lfo<=0;chorus_delay<=CHORUS_BASE;\n'
  '      valid_o<=0;clip_o<=0;input_l<=0;input_r<=0;product_l<=0;product_r<=0;\n'
  '      mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;\n'
  '    end else begin\n',
  '    if(!local_history_clear && state==1) begin '
  'read_l<=memory_l[read_address];read_r<=memory_r[read_address];end\n'
  '    if(!local_history_clear && state==3) begin '
  'memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end\n'
  '    // Scratch products are consumed only in state3 after this state2 write.\n'
  '    // Reset/clear cancels the state, so stale DSP data cannot become an output.\n'
  '    if(!local_history_clear && state==2) begin\n'
  "      product_l<=$signed(frames>=chorus_delay?read_l:32'sd0)*$signed({1'b0,gain});\n"
  "      product_r<=$signed(frames>=chorus_delay?read_r:32'sd0)*$signed({1'b0,gain});\n"
  '    end\n'
  '  end\n'
  '  always_ff @(posedge clk_i or negedge rst_ni) begin\n'
  '    if(!rst_ni) begin\n'
  '      pointer<=0;read_address<=0;frames<=0;state<=0;gain<=0;lfo<=0;chorus_delay<=CHORUS_BASE;\n'
  '      valid_o<=0;clip_o<=0;input_l<=0;input_r<=0;\n'
  '      mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;\n'
  '    end else begin\n'),
 ('        end\n'
  '        1:state<=2;\n'
  '        2:begin\n'
  "          product_l<=$signed(frames>=chorus_delay?read_l:32'sd0)*$signed({1'b0,gain});\n"
  "          product_r<=$signed(frames>=chorus_delay?read_r:32'sd0)*$signed({1'b0,gain});state<=3;\n"
  '        end\n'
  '        3:begin '
  'mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=4;end\n'
  '        4:begin\n',
  '        end\n'
  '        1:state<=2;\n'
  '        2:state<=3;\n'
  '        3:begin '
  'mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=4;end\n'
  '        4:begin\n'))


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def restore_scratch_products(source):
    """Normalize only the reviewed no-reset products to their exact parent."""
    if sha(source) != CHORUS_SCRATCH_SOURCE_SHA256:
        raise ValueError('Current Chorus scratch source identity changed')
    current = source.decode()
    for before, after in reversed(CHORUS_SCRATCH_EDITS):
        if current.count(after) != 1:
            raise ValueError('Chorus scratch reverse anchor drift')
        current = current.replace(after, before)
    if sha(current.encode()) != CHORUS_SCRATCH_PARENT_SHA256:
        raise ValueError('Chorus scratch parent identity changed')
    restored = current
    for before, after in CHORUS_SCRATCH_EDITS:
        if current.count(before) != 1:
            raise ValueError('Chorus scratch forward anchor drift')
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('Chorus scratch round trip changed bytes')
    return restored.encode()


def restore_native(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Return exact previous native bytes without altering historical evidence."""
    if policy not in (STRICT_POLICY, NARROW_POLICY):
        raise ValueError('Unknown Chorus provenance policy')
    if sha(provenance) != PROVENANCE_SHA256:
        raise ValueError('Original Chorus provenance bytes changed')
    original = json.loads(provenance)
    if policy == NARROW_POLICY and sha(source) == CHORUS_SCRATCH_SOURCE_SHA256:
        source = restore_scratch_products(source)
    current = source.decode()
    if policy == NARROW_POLICY:
        if adaptation is None or sha(adaptation) != ADAPTATION_SHA256:
            raise ValueError('Chorus narrowing adaptation changed or missing')
        bridge = json.loads(adaptation)
        if (bridge['policy'] != policy or bridge['source'] != SOURCE or
                bridge['original_provenance'] != PROVENANCE or
                bridge['original_provenance_sha256'] != sha(provenance) or
                bridge['parent_source_sha256'] != original['native_sha256'] or
                bridge['current_source_sha256'] != sha(source) or
                len(bridge['exact_changes']) != 1):
            raise ValueError('Chorus narrowing source identity changed')
        edit = bridge['exact_changes'][0]
        if (edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1):
            raise ValueError('Chorus narrowing reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
        if not edit['before'] or current.count(edit['before']) != 1 or current.replace(edit['before'], edit['after']) != source.decode():
            raise ValueError('Chorus narrowing round trip changed bytes')
    elif adaptation is not None:
        raise ValueError('Chorus adaptation needs explicit policy')
    if sha(current.encode()) != original['native_sha256']:
        raise ValueError('Native Chorus provenance checksum changed')
    return current


def verify(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Reverse the explicit adaptation and unchanged original prepared chain."""
    current = restore_native(source, provenance, policy, adaptation)
    info = json.loads(provenance)
    for edit in reversed(info['forward_edits']):
        if not edit['after'] or current.count(edit['after']) != edit['count']:
            raise ValueError('Original Chorus reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    if sha(current.encode()) != info['prepared_sha256']:
        raise ValueError('Chorus exact prepared source identity changed')
    return current, dict(policy=policy, source=SOURCE, current_source_sha256=sha(source),
        original_native_sha256=info['native_sha256'], original_provenance_sha256=sha(provenance),
        adaptation_sha256=sha(adaptation) if adaptation is not None else None,
        exact_prepared_sha256=sha(current.encode()), original_provenance_unchanged=True,
        scratch_products_without_reset=sha(source) == CHORUS_SCRATCH_SOURCE_SHA256,
        scratch_parent_sha256=CHORUS_SCRATCH_PARENT_SHA256,
        added_clock_latency=0, physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    """Bind only explicit native runtime production profiles to these bytes."""
    root = Path(root)
    _, evidence = verify((root / SOURCE).read_bytes(), (root / PROVENANCE).read_bytes(),
                         NARROW_POLICY, (root / ADAPTATION).read_bytes())
    return evidence
