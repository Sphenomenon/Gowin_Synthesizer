// Shared-multiplier timing contract -- single source of truth.
//
// The decoder has one multiplier, shared by requant, stereo, antialias, IMDCT
// and synthesis. It is a shift-and-add unit that consumes the 32-bit operand
// in chunks, one chunk per cycle, so the product of a request issued with
// mul_go is valid `MUL_WAIT cycles later.
//
// This number was previously written as a bare 3'd4 in five separate files.
// Changing the multiplier then meant finding all five, and missing one would
// silently read a stale product -- the failure looks like a numeric bug in
// whichever stage was missed, not like a timing change. Keep it here.
//
// 2-pass 17x22: mul_go in cycle T -> mul_acc at end of T, product registered
// at end of T+1, readable during T+2.
`define MUL_WAIT   3'd2
// mp3_synth issues a tap every `MUL_ISSUE cycles and accumulates the product
// at shift-register tap `MUL_DV_ACC. Both follow directly from `MUL_WAIT.
`define MUL_DV_ACC 4
