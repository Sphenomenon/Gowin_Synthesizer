// Basic Pitch fixed-point package: model geometry, Q formats and the shared
// transition/cost constants for the 138K streaming guidance core.
//
// AUTO-ALIGNED WITH music/export_basic_pitch_fixed.py -- if the model geometry
// changes, regenerate models/basic_pitch_onnx_manifest.json and this header.
`ifndef BASIC_PITCH_FIXED_PKG_SVH
`define BASIC_PITCH_FIXED_PKG_SVH

// --- model geometry (basic_pitch/constants.py, models.py) ------------------
`define BP_SR                 32'd22050
`define BP_SRC_SR             32'd48000
`define BP_HOP                32'd256
`define BP_AUDIO_N_SAMPLES    32'd43844
`define BP_FRAMES             32'd172
`define BP_CQT_BINS           32'd309
`define BP_BINS_PER_OCTAVE    32'd36
`define BP_OCTAVES            32'd9
`define BP_HARMONICS          32'd8
`define BP_NOTE_BINS          32'd88
`define BP_CONTOUR_BINS       32'd264
`define BP_MIDI_OFFSET        7'd21
`define BP_CQT_KERNEL         32'd256
`define BP_CQT_PAD            32'd128

// resampler 48000 -> 22050 = 147/320 (integer polyphase)
`define BP_RES_UP             32'd147
`define BP_RES_DOWN           32'd320
`define BP_RES_PHASES         32'd147
`define BP_RES_FRAC           32'd15

// --- fixed-point formats ---------------------------------------------------
// activations: int16, Q1.15 nominal
// DP costs:    int32, Q4.12 (12 fractional bits)
`define BP_Q_ACT_FRAC         32'd15
`define BP_Q_COST_FRAC        32'd12
`define BP_COST_ONE           32'd4096

// DP transition constants, Q4.12
`define BP_TRANS_STAY         32'sd1393   // 0.34 same-note hold bonus
`define BP_TRANS_SIL_STAY     32'sd614    // 0.15 silence hold
`define BP_TRANS_STEP_SLOPE   32'sd348    // -0.085 per semitone
`define BP_TRANS_JUMP_SLOPE   32'sd471    // -0.115 per semitone beyond 7
`define BP_TRANS_JUMP_KNEE    32'd7
`define BP_TRANS_SIL_TO_NOTE  -32'sd491   // -0.12
`define BP_TRANS_NOTE_TO_SIL  -32'sd737   // -0.18

// emission weights, Q4.12 applied to Q1.15 posteriors
`define BP_EMIT_NOTE_W        32'sd10650  // 2.6
`define BP_EMIT_ONSET_W       32'sd3072   // 0.75
`define BP_EMIT_SIL_ACTIVE    -32'sd1024  // -0.25
`define BP_EMIT_SIL_IDLE      32'sd4915   // 1.20
`define BP_SILENCE_THRESHOLD  16'sd9830   // 0.30 in Q1.15
`define BP_MIN_CONFIDENCE     16'sd8192   // 0.25 in Q1.15
`define BP_MIN_RUN_FRAMES     4'd2
`define BP_REPEAT_ONSET_THRESH 16'sd11141 // 0.34 in Q1.15
`define BP_ACTIVITY_RMS       16'sd655    // 0.02 in Q1.15

`endif
