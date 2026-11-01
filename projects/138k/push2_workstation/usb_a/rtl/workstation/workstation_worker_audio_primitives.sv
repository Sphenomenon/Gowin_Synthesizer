// Explicit W audio-only primitives. The immutable stage supplies these bytes;
// oscillator, ADSR, FFT, recorder and cue implementations are not included.
`include "legacy/rtl/audio/audio_math_pkg.sv"
`include "legacy/rtl/input/uart_rx.sv"
`include "legacy/rtl/input/midi_stream_decoder.sv"
