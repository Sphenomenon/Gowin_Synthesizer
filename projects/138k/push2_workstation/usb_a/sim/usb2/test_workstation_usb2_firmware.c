#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

static volatile uint32_t registers[64];
static unsigned pixel_rewind, pixel_position, native_high_speed;
static unsigned output_bytes, output_packets, header_packets, injected_nak, wire_toggle;
static uint32_t now;

static uint16_t raw_pixel(unsigned index)
{
    return (uint16_t)(index * 197u + 91u);
}

static volatile uint32_t *register_at(unsigned offset)
{
    assert(offset < sizeof registers && !(offset & 3));
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
void usbhw_hub_enable(int full_speed, int sof) { assert(full_speed == 1 && sof == 0); }
int usbhw_hub_device_detected(void) { return 1; }
int usbhw_reset(void) { return 0; }
t_time usbhw_timer_now(void) { return now; }
void delay(int milliseconds) { now += (uint32_t)milliseconds; }

int usb_configure_device(struct usb_device *device, int address)
{
    (void)device; (void)address;
    return 0;
}

int usb_get_descriptor(struct usb_device *device, uint16_t value, uint16_t index, uint8_t *buffer, uint16_t length)
{
    (void)device; (void)value; (void)index; (void)buffer; (void)length;
    return -1;
}

int usb_send_control_write(struct usb_device *device, uint8_t type, uint8_t request, uint16_t value,
                           uint16_t index, uint16_t length, uint8_t *data)
{
    (void)device; (void)type; (void)request; (void)value; (void)index; (void)length; (void)data;
    return 0;
}

int usbhw_transfer_in(uint8_t token, int address, int endpoint, uint8_t *pid, uint8_t *buffer, int capacity)
{
    (void)address; (void)endpoint; (void)buffer;
    assert(token == PID_IN && capacity <= 512);
    *pid = PID_NAK;
    return USB_RES_NAK;
}

int usbhw_transfer_out(uint8_t token, int address, int endpoint, int handshake, uint8_t pid,
                       uint8_t *buffer, int length)
{
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
    puts("PASS workstation_usb2_firmware: complete Push frame, FS64/HS512 packetization, pixel XOR, NAK retry, PID, MPS");
    return 0;
}
