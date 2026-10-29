#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

static volatile uint32_t registers[64];
static unsigned pixel_rewind, pixel_position, native_high_speed;
static unsigned output_bytes, output_packets, header_packets, injected_nak, wire_toggle;
static uint32_t now;
static unsigned hotplug_model, model_push, model_present = 1, model_enumeration_ok = 1;
static unsigned model_reset_count, model_enable_count, model_configure_count, model_output_packets, model_unplug_packet;
static unsigned model_output_toggle[3], model_descriptor_calls, model_midi_writes, model_push_writes;
static int model_input_result;
static uint8_t model_input_pid;
static uint32_t model_midi_word;

static uint16_t raw_pixel(unsigned index)
{
    return (uint16_t)(index * 197u + 91u);
}

static volatile uint32_t *register_at(unsigned offset)
{
    assert(offset < sizeof registers && !(offset & 3));
    if (hotplug_model && offset == 0x04) ++model_push_writes;
    if (hotplug_model && offset == 0x54) ++model_midi_writes;
    if (offset == 0x28) pixel_rewind = 1;
    if (offset == 0x2c) {
        if (pixel_rewind) { pixel_position = registers[0x28 / 4]; pixel_rewind = 0; }
        registers[offset / 4] = raw_pixel(pixel_position++);
    }
    return &registers[offset / 4];
}

#define WORKSTATION_USB2_NATIVE
#define MMIO(offset) (*register_at(offset))
#define main production_main
#include "../../firmware.c"
#undef main

unsigned usbhw_native_high_speed(void) { return native_high_speed; }
unsigned usbhw_native_packet_limit(void) { return native_high_speed ? 512 : 64; }
int usbhw_native_allow_high_speed(unsigned allowed) { native_high_speed = allowed; return 0; }
void usbhw_init(uint32_t base) { assert(base == 0x02000100u); }
void usbhw_hub_enable(int full_speed, int sof)
{
    assert(full_speed == 1 && sof == 0);
    if (hotplug_model) {
        assert(registers[0] == 0);
        ++model_enable_count;
        memset(model_output_toggle, 0, sizeof model_output_toggle);
        model_output_packets = 0;
    }
}
int usbhw_hub_device_detected(void) { return (int)model_present; }
int usbhw_reset(void)
{
    if (hotplug_model) {
        assert(registers[0] == 0);
        ++model_reset_count;
        memset(model_output_toggle, 0, sizeof model_output_toggle);
        model_output_packets = 0;
    }
    return 0;
}
t_time usbhw_timer_now(void) { return now; }
void delay(int milliseconds) { now += (uint32_t)milliseconds; }

int usb_configure_device(struct usb_device *device, int address)
{
    assert(hotplug_model && model_present && registers[0] == 0 && address == 1);
    ++model_configure_count;
    if (!model_enumeration_ok) return 0;
    memset(device, 0, sizeof *device);
    device->address = address;
    device->vid = model_push ? 0x2982 : 0xfb9a;
    device->pid = model_push ? (native_high_speed ? 0x1967 : 0x9999) : 0xfb9b;
    return 1;
}

int usb_get_descriptor(struct usb_device *device, uint16_t value, uint16_t index, uint8_t *buffer, uint16_t length)
{
    uint8_t descriptor[] = {
        9, 2, 62, 0, 2, 1, 0, 0x80, 50,
        9, 4, 1, 0, 2, 1, 3, 0, 0,
        7, 0x24, 1, 0, 1, 7, 0,
        7, 5, 1, 2, 64, 0, 0,
        7, 5, 0x81, 2, 64, 0, 0,
        9, 4, 2, 0, 2, 0xff, 0, 0, 0,
        7, 5, 2, 2, 64, 0, 0,
        7, 5, 0x82, 2, 64, 0, 0,
    };
    assert(hotplug_model && !model_push && device == &dev && value == DESC_CONFIGURATION && index == 0);
    assert(sizeof descriptor == 62);
    ++model_descriptor_calls;
    for (unsigned offset = 9; offset < sizeof descriptor; offset += descriptor[offset]) {
        if (descriptor[offset + 1] == DESC_ENDPOINT) {
            unsigned packet = usbhw_native_packet_limit();
            descriptor[offset + 4] = (uint8_t)packet;
            descriptor[offset + 5] = (uint8_t)(packet >> 8);
        }
    }
    unsigned count = length < sizeof descriptor ? length : sizeof descriptor;
    memcpy(buffer, descriptor, count);
    return (int)count;
}

int usb_send_control_write(struct usb_device *device, uint8_t type, uint8_t request, uint16_t value,
                           uint16_t index, uint16_t length, uint8_t *data)
{
    (void)device; (void)type; (void)request; (void)value; (void)index; (void)length; (void)data;
    assert(!hotplug_model);
    return 0;
}

int usbhw_transfer_in(uint8_t token, int address, int endpoint, uint8_t *pid, uint8_t *buffer, int capacity)
{
    assert(token == PID_IN && capacity <= 512);
    if (hotplug_model) {
        assert(address == 1 && endpoint == (model_push ? 2 : 1));
        assert((unsigned)capacity == (model_push ? 512u : usbhw_native_packet_limit()));
        ++now;
        *pid = model_input_pid;
        if (!model_present) return USB_RES_TIMEOUT;
        if (model_input_result > 0) {
            assert(model_input_result == 4);
            for (unsigned index = 0; index < 4; ++index)
                buffer[index] = (uint8_t)(model_midi_word >> (index * 8));
        }
        return model_input_result;
    }
    (void)address; (void)endpoint; (void)buffer;
    *pid = PID_NAK;
    return USB_RES_NAK;
}

int usbhw_transfer_out(uint8_t token, int address, int endpoint, int handshake, uint8_t pid,
                       uint8_t *buffer, int length)
{
    if (hotplug_model) {
        assert(connected && mode == DEVICE_PUSH && token == PID_OUT && address == 1 && handshake == 1);
        assert(endpoint == 1 || endpoint == 2);
        assert(length > 0 && (unsigned)length <= usbhw_native_packet_limit());
        assert(pid == (model_output_toggle[endpoint] ? PID_DATA1 : PID_DATA0));
        ++now;
        if (model_unplug_packet && model_output_packets == model_unplug_packet) model_present = 0;
        if (!model_present) return USB_RES_TIMEOUT;
        if (endpoint == 1 && model_output_packets == 0)
            assert(length == 16 && buffer[0] == 0xff && buffer[1] == 0xcc && buffer[2] == 0xaa && buffer[3] == 0x88);
        model_output_toggle[endpoint] ^= 1;
        ++model_output_packets;
        return USB_RES_OK;
    }
    assert(token == PID_OUT && address == 1 && endpoint == 1 && handshake == 1);
    assert(pid == (wire_toggle ? PID_DATA1 : PID_DATA0));
    assert(length > 0 && (unsigned)length <= usbhw_native_packet_limit());
    if (!header_packets) {
        assert(length == 16 && buffer[0] == 0xff && buffer[1] == 0xcc && buffer[2] == 0xaa && buffer[3] == 0x88);
        for (unsigned index = 4; index < 16; ++index) assert(buffer[index] == 0);
        ++header_packets;
    } else {
        for (unsigned index = 0; index < (unsigned)length; ++index) {
            unsigned byte_index = output_bytes + index;
            unsigned pixel_index = byte_index >> 1;
            uint16_t expected = raw_pixel(pixel_index) ^ (pixel_index & 1u ? 0xffe7u : 0xf3e7u);
            assert(buffer[index] == (uint8_t)(expected >> ((byte_index & 1u) * 8)));
        }
        if (output_packets == 3 && !injected_nak) { injected_nak = 1; return USB_RES_NAK; }
        output_bytes += (unsigned)length;
    }
    ++output_packets; wire_toggle ^= 1;
    return USB_RES_OK;
}

static void attach_model_device(unsigned push_device, unsigned high_speed_device)
{
    model_push = push_device;
    native_high_speed = high_speed_device;
    model_present = 1;
    model_input_result = USB_RES_NAK;
    model_input_pid = PID_DATA0;
    model_unplug_packet = 0;
    model_descriptor_calls = 0;
    connect();
    assert(connected && registers[0] == (push_device ? 1u : 7u));
    assert(mode == (push_device ? DEVICE_PUSH : DEVICE_GW25K));
    assert(in_pid == PID_DATA0 && toggles[1] == 0 && toggles[2] == 0);
    assert(midi_in_ep == (push_device ? 2u : 1u));
    assert(midi_in_size == (push_device ? 512u : usbhw_native_packet_limit()));
    assert(model_descriptor_calls == (push_device ? 0u : 2u));
    assert(gw.active == -1 && !gw.transaction[0].used && !gw.transaction[1].used);
    assert(!gw.panel_out_toggle && !gw.panel_in_toggle && !displayed_state_valid);
}

static void detach_model_device(void)
{
    model_present = 0;
    delay(51);
    poll_midi();
    assert(!connected && mode == DEVICE_NONE && registers[0] == 0);
    assert(gw.active == -1 && !gw.transaction[0].used && !gw.transaction[1].used);
    assert(!displayed_state_valid);
}

static void exercise_alternating_devices(void)
{
    hotplug_model = 1;
    memset((void *)registers, 0, sizeof registers);
    for (unsigned first_speed = 0; first_speed < 2; ++first_speed) {
        attach_model_device(0, first_speed);
        for (unsigned poll = 0; poll < 512; ++poll) poll_midi();
        assert(connected && mode == DEVICE_GW25K);
        unsigned previous_midi_writes = model_midi_writes;
        model_input_result = 4;
        model_midi_word = 0x643c9009u;
        poll_midi();
        assert(model_midi_writes == previous_midi_writes + 1);
        assert(registers[0x54 / 4] == ((1u << 14) | (60u << 7) | 100u));
        poll_midi();
        assert(model_midi_writes == previous_midi_writes + 1 && in_pid == PID_DATA1);
        gw.transaction[0].used = gw.transaction[1].used = 1;
        gw.transaction[0].position = 519;
        gw.active = 0;
        gw.panel_in_toggle = gw.panel_out_toggle = 1;
        uint32_t previous_session = gw.session;
        detach_model_device();
        assert(gw.session != previous_session);

        attach_model_device(1, 1u - first_speed);
        unsigned previous_push_writes = model_push_writes;
        model_input_result = 4;
        model_midi_word = 0x64249009u;
        poll_midi();
        assert(model_push_writes == previous_push_writes + 1);
        assert(model_midi_writes == previous_midi_writes + 1 && registers[0x04 / 4] == model_midi_word);
        poll_midi();
        assert(model_push_writes == previous_push_writes + 1);
        model_input_result = USB_RES_NAK;
        model_unplug_packet = 4;
        unsigned previous_frames = frames;
        assert(frame() == 0 && !model_present && model_output_packets == 4 && frames == previous_frames);
        detach_model_device();

        attach_model_device(0, 1u - first_speed);
        model_input_result = 4;
        model_midi_word = 0x643d9009u;
        poll_midi();
        assert(model_midi_writes == previous_midi_writes + 2);
        assert(model_push_writes == previous_push_writes + 1);
        assert(registers[0x54 / 4] == ((1u << 14) | (61u << 7) | 100u));
        detach_model_device();

        attach_model_device(1, first_speed);
        assert(frame() == 1 && frames == previous_frames + 1);
        assert(model_output_packets == (first_speed ? 641u : 5121u));
        detach_model_device();
    }
    model_present = 1;
    model_enumeration_ok = 0;
    connect();
    assert(!connected && mode == DEVICE_NONE && registers[0] == 0);
    model_enumeration_ok = 1;
    attach_model_device(1, 1);
    assert(model_enable_count == 10 && model_reset_count == 0 && model_configure_count == 10);
    detach_model_device();
}

int main(void)
{
    for (native_high_speed = 0; native_high_speed < 2; ++native_high_speed) {
        memset((void *)registers, 0, sizeof registers);
        output_bytes = output_packets = header_packets = injected_nak = wire_toggle = now = 0;
        pixel_rewind = pixel_position = 0;
        connected = 1; mode = DEVICE_PUSH; dev.address = 1; midi_in_ep = 2; midi_in_size = 512;
        displayed_state_valid = 0; toggles[1] = 0; frames = 0; last_in_reply = 0;
        assert(midi_bulk_packet_size(512) == (int)native_high_speed);
        assert(midi_bulk_packet_size(64) == (int)!native_high_speed);
        assert(!midi_bulk_packet_size(1024));
        assert(frame() == 1 && frames == 1 && connected);
        assert(output_bytes == 327680 && header_packets == 1 && injected_nak);
        assert(output_packets == (native_high_speed ? 641u : 5121u));
        assert(toggles[1] == wire_toggle);
    }
    assert(sizeof gw.transaction[0].reply == 64 && GW_USB_PACKET_CAPACITY == 512);
    exercise_alternating_devices();
    puts("PASS workstation_usb2_firmware: complete Push frame, FS64/HS512 packetization, pixel XOR, NAK retry, PID, MPS, alternating 25K/Push hotplug, partial-frame disconnect and enumeration retry");
    return 0;
}
