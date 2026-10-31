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


CHORUS_AFFINE44_SOURCE_SHA256 = '28ef32d47d55a0d44eef8ec23fa3437cdbef647d4ca0b023f98cb184bd8ce50c'
CHORUS_AFFINE44_PARENT_SHA256 = 'a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900'
CHORUS_AFFINE44_BEFORE = '''  function automatic [15:0] rate_delay(input [15:0] triangle_value,input logic rate44);
    logic [24:0] triangle_times441;
    logic [27:0] rounded_numerator44;
    logic [11:0] scaled_high44;
    logic [17:0] triangle_times3;
    begin
      // Exact fixed-baseline arithmetic; no register or sample latency added.
      //44.1k: cancel32 from the original nearest-rounded rational, then
      //floor(N/(5*65536)) == floor(floor(N/65536)/5) for nonnegative N.
      //N<=173571655 fits28 bits; only its high12 bits reach the divide by5.
      if(rate44)begin
        triangle_times441=25'(triangle_value)*25'd441;
        rounded_numerator44=28'd144670720+{3'd0,triangle_times441};
        scaled_high44=rounded_numerator44[27:16];
        rate_delay=16'(scaled_high44/12'd5);
'''
CHORUS_AFFINE44_AFTER = '''  function automatic [15:0] rate_delay(input [15:0] triangle_value,input logic rate44);
    logic [34:0] rounded_phase44;
    logic [17:0] triangle_times3;
    begin
      // Exact over all 16-bit triangles: preserve every nearest-rounded tap
      // while replacing the serial divide by5 with one affine product/shift.
      // The complete product and sum fit35 unsigned bits; sampling is unchanged.
      if(rate44)begin
        rounded_phase44=35'(triangle_value)*35'd361267+35'd134225920;
        rate_delay=16'd441+16'(rounded_phase44>>28);
'''



CHORUS_AFFINE35_CSA_SOURCE_SHA256 = '1cc7ddd5e00edcb5975ed64cc2eceb4707029f5add724467700fbeae30b61ea5'
CHORUS_AFFINE35_CSA_PARENT_SHA256 = '28ef32d47d55a0d44eef8ec23fa3437cdbef647d4ca0b023f98cb184bd8ce50c'
CHORUS_AFFINE35_CSA_BEFORE = '''  function automatic [15:0] rate_delay(input [15:0] triangle_value,input logic rate44);
    logic [34:0] rounded_phase44;
    logic [17:0] triangle_times3;
    begin
      // Exact over all 16-bit triangles: preserve every nearest-rounded tap
      // while replacing the serial divide by5 with one affine product/shift.
      // The complete product and sum fit35 unsigned bits; sampling is unchanged.
      if(rate44)begin
        rounded_phase44=35'(triangle_value)*35'd361267+35'd134225920;
        rate_delay=16'd441+16'(rounded_phase44>>28);
      end else begin
        //48k: floor(96*t/65536) == floor(3*t/2048), preserving every tap.
        triangle_times3=18'(triangle_value)*18'd3;
        rate_delay=16'd480+16'(triangle_times3>>11);
      end
    end
  endfunction'''
CHORUS_AFFINE35_CSA_AFTER = '''  function automatic [15:0] rate_delay(input [15:0] triangle_value,input logic rate44);
    logic [34:0] t,rounded_phase44;
    logic [34:0] s0,c0,s1,c1,s2,c2,s3,c3,s4,c4,s5,c5,s6,c6,s7,c7;
    logic [17:0] triangle_times3;
    begin
      // Exact 35-bit affine product; five balanced CSA levels and one final
      // carry-propagating addition. No state, latency or tap rounding changes.
      if(rate44)begin
        t={19'd0,triangle_value};
        s0=t^(t<<1)^(t<<4);
        c0=((t&(t<<1))|(t&(t<<4))|((t<<1)&(t<<4)))<<1;
        s1=(t<<5)^(t<<8)^(t<<9);
        c1=(((t<<5)&(t<<8))|((t<<5)&(t<<9))|((t<<8)&(t<<9)))<<1;
        s2=(t<<15)^(t<<16)^(t<<18);
        c2=(((t<<15)&(t<<16))|((t<<15)&(t<<18))|((t<<16)&(t<<18)))<<1;
        s3=s0^c0^s1;
        c3=((s0&c0)|(s0&s1)|(c0&s1))<<1;
        s4=c1^s2^c2;
        c4=((c1&s2)|(c1&c2)|(s2&c2))<<1;
        s5=s3^c3^s4;
        c5=((s3&c3)|(s3&s4)|(c3&s4))<<1;
        s6=s5^c5^c4;
        c6=((s5&c5)|(s5&c4)|(c5&c4))<<1;
        s7=s6^c6^35'd134225920;
        c7=((s6&c6)|(s6&35'd134225920)|(c6&35'd134225920))<<1;
        rounded_phase44=s7+c7;
        rate_delay=16'd441+16'(rounded_phase44>>28);
      end else begin
        //48k: floor(96*t/65536) == floor(3*t/2048), preserving every tap.
        triangle_times3=18'(triangle_value)*18'd3;
        rate_delay=16'd480+16'(triangle_times3>>11);
      end
    end
  endfunction'''


def restore_affine35_csa(source):
    """Verify only the approved function inverse before the original chain."""
    if sha(source) != CHORUS_AFFINE35_CSA_SOURCE_SHA256:
        return source  # Existing parent identity gates remain authoritative.
    current = source.decode()
    if current.count(CHORUS_AFFINE35_CSA_AFTER) != 1:
        raise ValueError('Chorus affine35 CSA reverse anchor drift')
    restored = current.replace(CHORUS_AFFINE35_CSA_AFTER, CHORUS_AFFINE35_CSA_BEFORE)
    if sha(restored.encode()) != CHORUS_AFFINE35_CSA_PARENT_SHA256:
        raise ValueError('Chorus affine35 CSA parent identity changed')
    if (restored.count(CHORUS_AFFINE35_CSA_BEFORE) != 1 or
            restored.replace(CHORUS_AFFINE35_CSA_BEFORE, CHORUS_AFFINE35_CSA_AFTER).encode() != source):
        raise ValueError('Chorus affine35 CSA round trip changed bytes')
    return restored.encode()


def restore_affine44(source):
    """Restore exact M12 Chorus bytes before its unchanged original chain."""
    source = restore_affine35_csa(source)
    if sha(source) != CHORUS_AFFINE44_SOURCE_SHA256:
        return source  # The original native/scratch identity gates still apply.
    current = source.decode()
    if current.count(CHORUS_AFFINE44_AFTER) != 1:
        raise ValueError('Chorus affine44 reverse anchor drift')
    current = current.replace(CHORUS_AFFINE44_AFTER, CHORUS_AFFINE44_BEFORE)
    if sha(current.encode()) != CHORUS_AFFINE44_PARENT_SHA256:
        raise ValueError('Chorus affine44 parent identity changed')
    if (current.count(CHORUS_AFFINE44_BEFORE) != 1 or
            current.replace(CHORUS_AFFINE44_BEFORE, CHORUS_AFFINE44_AFTER).encode() != source):
        raise ValueError('Chorus affine44 round trip changed bytes')
    return current.encode()


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
    if policy == NARROW_POLICY:
        source = restore_affine44(source)
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
        affine35_csa_equivalence=sha(source) == CHORUS_AFFINE35_CSA_SOURCE_SHA256,
        affine35_csa_parent_sha256=CHORUS_AFFINE35_CSA_PARENT_SHA256,
        affine44_delay_equivalence=sha(restore_affine35_csa(source)) == CHORUS_AFFINE44_SOURCE_SHA256,
        affine44_parent_sha256=CHORUS_AFFINE44_PARENT_SHA256,
        scratch_products_without_reset=sha(restore_affine44(source)) == CHORUS_SCRATCH_SOURCE_SHA256,
        scratch_parent_sha256=CHORUS_SCRATCH_PARENT_SHA256,
        added_clock_latency=0, physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    """Bind only explicit native runtime production profiles to these bytes."""
    root = Path(root)
    _, evidence = verify((root / SOURCE).read_bytes(), (root / PROVENANCE).read_bytes(),
                         NARROW_POLICY, (root / ADAPTATION).read_bytes())
    return evidence
