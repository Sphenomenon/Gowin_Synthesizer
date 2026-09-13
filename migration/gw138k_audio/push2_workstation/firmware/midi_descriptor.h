#ifndef MIDI_DESCRIPTOR_H
#define MIDI_DESCRIPTOR_H
#include <stdint.h>
typedef struct {
    uint8_t configuration, interface_number, alternate, endpoint;
    uint16_t max_packet;
} midi_input_t;
/* USB MIDI 1.0, alternate zero, direct bulk IN only. No hubs / MIDI 2.0. */
int midi_find_input(const uint8_t *data, unsigned length, midi_input_t *out);
typedef struct { uint8_t display_out, midi_out; uint16_t display_mps, midi_mps; } push_profile_t;
int push_find_outputs(const uint8_t *data, unsigned length, push_profile_t *out);
#endif
