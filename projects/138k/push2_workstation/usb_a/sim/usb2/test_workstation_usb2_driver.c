#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "workstation_usb2_host.h"

struct hardware {
    uint32_t identity, control, status, generation, now, result;
    uint8_t transmit[512];
    unsigned transmit_count, receive_count, receive_index, commands;
    unsigned cancel_at, defer, frozen, wrong_length, io_failure, hardware_status;
};

static void cancel(struct hardware *hardware)
{
    hardware->status = (hardware->status & ~0x70000u) | 0x80000u;
    hardware->generation++;
    hardware->transmit_count = 0;
    hardware->receive_count = 0;
}

static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct hardware *hardware = context;
    if (hardware->io_failure) return -1;
    switch (offset) {
    case 0: *value = hardware->identity; break;
    case 4: *value = hardware->control; break;
    case 8: *value = hardware->status; break;
    case 0x14:
        if (hardware->receive_index >= hardware->receive_count) return -1;
        *value = (hardware->receive_index++ * 37u + 19u) & 255u;
        if (hardware->cancel_at && hardware->receive_index == hardware->cancel_at) cancel(hardware);
        break;
    case 0x18: *value = hardware->result; break;
    case 0x20: *value = hardware->transmit_count; break;
    case 0x28: *value = hardware->generation; break;
    case 0x38: *value = 0; break;
    default: return -1;
    }
    return 0;
}

static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct hardware *hardware = context;
    if (hardware->io_failure) return -1;
    switch (offset) {
    case 4:
        assert(!(hardware->control & 1u) || (hardware->control & 2u) == (value & 2u));
        hardware->control = value & 3u;
        if (value & 4u) cancel(hardware);
        if (value & 1u) hardware->status = 0x21000bu | ((value & 2u) ? 4u : 0u);
        else cancel(hardware);
        break;
    case 0x10:
        if (hardware->transmit_count == 512) return -1;
        hardware->transmit[hardware->transmit_count++] = (uint8_t)value;
        break;
    case 0x0c: {
        unsigned length = (value >> 20) & 1023u;
        hardware->commands++;
        hardware->receive_count = (value & 255u) == 0x69 && !hardware->hardware_status ? length : 0;
        hardware->receive_index = 0;
        if (hardware->wrong_length) hardware->receive_count = 513;
        hardware->result = 0x80004b00u | (hardware->receive_count << 16) | hardware->hardware_status;
        if (!hardware->defer) hardware->status |= 0x40000u;
        else hardware->status |= 0x20000u;
        break;
    }
    case 0x1c:
        if (value & 1u) {
            hardware->status &= ~0x40000u;
            hardware->transmit_count = 0;
            hardware->receive_count = 0;
        }
        if (value & 4u) hardware->status &= ~0x80000u;
        break;
    default: return -1;
    }
    return 0;
}

static uint32_t milliseconds(void *context)
{
    struct hardware *hardware = context;
    if (!hardware->frozen) hardware->now++;
    return hardware->now;
}

int main(void)
{
    struct hardware hardware = {.identity = 0x55324801u};
    struct workstation_usb2_io io = {&hardware, read32, write32, milliseconds};
    struct workstation_usb2_host host;
    struct workstation_usb2_command command = {0x69, 7, 2, 1, 512};
    struct workstation_usb2_result result;
    uint8_t transmit[512], receive[514];
    unsigned before_commands;
    for (unsigned index = 0; index < 512; ++index) transmit[index] = (uint8_t)(index * 73u + 166u);
    memset(receive, 0xa5, sizeof(receive));
    assert(workstation_usb2_open(&host, &io) == WORKSTATION_USB2_OK);
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_OK);
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 512, &result, 100) == WORKSTATION_USB2_OK);
    assert(result.status == 0 && result.length == 512 && result.pid == 0x4b);
    for (unsigned index = 0; index < 512; ++index) assert(receive[index + 1] == (uint8_t)(index * 37u + 19u));
    assert(receive[0] == 0xa5 && receive[513] == 0xa5);
    before_commands = hardware.commands;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 511, &result, 100) == WORKSTATION_USB2_ARGUMENT);
    assert(result.length == 0 && hardware.commands == before_commands);
    hardware.status |= 0x20000u;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 512, &result, 100) == WORKSTATION_USB2_BUSY);
    assert(hardware.commands == before_commands); hardware.status &= ~0x20000u;
    command.pid = 0xe1;
    assert(workstation_usb2_transfer(&host, &command, transmit, 0, 0, &result, 100) == WORKSTATION_USB2_OK);
    assert(memcmp(transmit, hardware.transmit, 512) == 0 && result.length == 0);
    hardware.hardware_status = 9;
    before_commands = hardware.commands;
    assert(workstation_usb2_transfer(&host, &command, transmit, 0, 0, &result, 100) == WORKSTATION_USB2_OK);
    assert(result.status == 9 && hardware.commands == before_commands + 1);
    hardware.hardware_status = 0;
    command.pid = 0x2d; command.length = 8;
    assert(workstation_usb2_transfer(&host, &command, transmit, 0, 0, &result, 100) == WORKSTATION_USB2_ARGUMENT);
    command.toggle = 0;
    assert(workstation_usb2_transfer(&host, &command, transmit, 0, 0, &result, 100) == WORKSTATION_USB2_OK);
    command.pid = 0xb4; command.length = 0;
    assert(workstation_usb2_transfer(&host, &command, 0, 0, 0, &result, 100) == WORKSTATION_USB2_OK);
    assert(workstation_usb2_reset_port(&host, 100) == WORKSTATION_USB2_OK);
    assert(workstation_usb2_enable(&host, 0, 100) == WORKSTATION_USB2_OK);
    assert(workstation_usb2_transfer(&host, &command, 0, 0, 0, &result, 100) == WORKSTATION_USB2_ARGUMENT);
    command.pid = 0x69; command.length = 65;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 512, &result, 100) == WORKSTATION_USB2_ARGUMENT);
    command.length = 64;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_OK);
    hardware.hardware_status = 1;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_OK);
    assert(result.status == 1 && result.length == 0);
    hardware.hardware_status = 0; hardware.cancel_at = 17;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_CANCELLED);
    assert(result.length == 0 && receive[0] == 0xa5 && receive[513] == 0xa5);
    hardware.cancel_at = 0;
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_OK);
    hardware.wrong_length = 1;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_PROTOCOL);
    assert(result.length == 0 && !(hardware.control & 1u)); hardware.wrong_length = 0;
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_OK);
    hardware.hardware_status = 15;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_PROTOCOL);
    assert(result.length == 0 && !(hardware.control & 1u)); hardware.hardware_status = 0;
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_OK);
    hardware.defer = 1; hardware.now = 0xfffffff0u;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 20) == WORKSTATION_USB2_TIMEOUT);
    assert(result.length == 0 && !(hardware.control & 1u)); hardware.defer = 0;
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_OK);
    hardware.defer = 1; hardware.frozen = 1; host.poll_limit = 8;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_TIMEOUT);
    assert(!(hardware.control & 1u)); hardware.defer = 0; hardware.frozen = 0;
    hardware.frozen = 1;
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_TIMEOUT);
    assert(!(hardware.control & 1u)); hardware.frozen = 0;
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_OK);
    hardware.io_failure = 1;
    assert(workstation_usb2_transfer(&host, &command, 0, receive + 1, 64, &result, 100) == WORKSTATION_USB2_IO);
    hardware.io_failure = 0; hardware.identity = 0;
    assert(workstation_usb2_open(&host, &io) == WORKSTATION_USB2_INCOMPATIBLE);
    assert(workstation_usb2_enable(&host, 1, 100) == WORKSTATION_USB2_ARGUMENT);
    puts("PASS workstation_usb2_driver: 512/64-byte bounds, cancellation, NYET, reset, clock/timer failure");
    return 0;
}
