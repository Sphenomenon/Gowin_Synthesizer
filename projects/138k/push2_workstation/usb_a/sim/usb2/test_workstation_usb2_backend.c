#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "workstation_usb2_backend.h"
#include "workstation_usb2_cpu_port.h"
#include "usb_hw.h"
#include "usb_defs.h"

static uint32_t epoch = 1, now, clock_step = 1, session_status = 0x21000fu;
static unsigned transfers, disables, change_epoch;
static struct workstation_usb2_command observed[64];
static struct workstation_usb2_result replies[64];
static unsigned reply_count, reply_index;

static int read_register(void *context, uint32_t offset, uint32_t *value)
{
    (void)context;
    assert(offset == 8 || offset == 0x28);
    *value = offset == 8 ? session_status : epoch;
    return 0;
}

static int write_register(void *context, uint32_t offset, uint32_t value)
{
    (void)context; (void)offset; (void)value;
    return 0;
}

static uint32_t milliseconds(void *context)
{
    (void)context;
    now += clock_step;
    return now;
}

void workstation_usb2_cpu_io(struct workstation_usb2_io *io)
{
    io->context = 0; io->read32 = read_register; io->write32 = write_register; io->milliseconds = milliseconds;
}

int workstation_usb2_open(struct workstation_usb2_host *host, const struct workstation_usb2_io *io)
{
    host->io.context = io->context; host->io.read32 = io->read32;
    host->io.write32 = io->write32; host->io.milliseconds = io->milliseconds;
    host->initialized = 1; host->poll_limit = 8;
    return 0;
}

int workstation_usb2_disable(struct workstation_usb2_host *host)
{
    (void)host;
    ++disables;
    return 0;
}

int workstation_usb2_enable(struct workstation_usb2_host *host, unsigned allowed, uint32_t timeout)
{
    (void)host;
    assert(timeout == 400);
    session_status = 0x21000bu | (allowed << 2); ++epoch;
    return 0;
}

int workstation_usb2_reset_port(struct workstation_usb2_host *host, uint32_t timeout)
{
    (void)host;
    assert(timeout == 400);
    ++epoch;
    return 0;
}

int workstation_usb2_transfer(struct workstation_usb2_host *host, const struct workstation_usb2_command *command,
                             const uint8_t *transmit, uint8_t *receive, uint16_t capacity,
                             struct workstation_usb2_result *result, uint32_t timeout)
{
    (void)host; (void)transmit;
    assert(timeout == 20 && capacity == command->length && transfers < 64 && reply_index < reply_count);
    observed[transfers].pid = command->pid; observed[transfers].device = command->device;
    observed[transfers].endpoint = command->endpoint; observed[transfers].toggle = command->toggle;
    observed[transfers++].length = command->length;
    *result = replies[reply_index++];
    if (receive && result->status == 0 && result->length <= capacity)
        for (unsigned index = 0; index < result->length; ++index) receive[index] = (uint8_t)(index * 37u + 19u);
    if (change_epoch) { ++epoch; change_epoch = 0; }
    return 0;
}

static void response(unsigned status, unsigned pid, unsigned length)
{
    assert(reply_count < 64);
    replies[reply_count].status = (uint8_t)status; replies[reply_count].pid = (uint8_t)pid;
    replies[reply_count++].length = (uint16_t)length;
}

static void start(unsigned high_speed)
{
    transfers = reply_count = reply_index = 0; clock_step = 1;
    usbhw_init(0x02000100u);
    assert(usbhw_native_allow_high_speed(high_speed) == 0);
    usbhw_hub_enable(1, 0);
    assert(usbhw_hub_device_detected() && usbhw_native_high_speed() == high_speed);
    assert(usbhw_native_allow_high_speed(0) == -1);
}

int main(void)
{
    uint8_t transmit[512] = {0}, receive[514], pid;
    for (unsigned high_speed = 0; high_speed < 2; ++high_speed) {
        unsigned limit = high_speed ? 512 : 64;
        start(high_speed);
        memset(receive, 0xa5, sizeof receive);
        response(0, PID_DATA0, limit);
        assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive + 1, 512) == (int)limit);
        assert(pid == PID_DATA0 && observed[0].length == limit && observed[0].toggle == 0);
        assert(receive[0] == 0xa5 && receive[513] == 0xa5);
        for (unsigned index = 0; index < limit; ++index) assert(receive[index + 1] == (uint8_t)(index * 37u + 19u));
        response(5, PID_DATA0, 0);
        assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive + 1, 512) == 0 && pid == PID_DATA0);
        response(0, PID_DATA1, 1);
        assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive + 1, 512) == 1 && observed[2].toggle == 1);
        assert(usbhw_reset() == 0);
        response(0, PID_DATA0, 1);
        assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive + 1, 512) == 1 && observed[3].toggle == 0);
        unsigned before = transfers;
        assert(usbhw_transfer_out(PID_OUT, 7, 1, 0, PID_DATA0, transmit, 8) == USB_RES_STALL);
        assert(usbhw_transfer_in(PID_IN, 7, 16, &pid, receive, 8) == USB_RES_STALL);
        if (!high_speed) assert(usbhw_transfer_out(PID_OUT, 7, 1, 1, PID_DATA0, transmit, 512) == USB_RES_STALL);
        assert(transfers == before);
    }
    start(1);
    response(9, 0x96, 0);
    assert(usbhw_transfer_out(PID_OUT, 7, 2, 1, PID_DATA0, transmit, 512) == USB_RES_OK);
    response(1, PID_NAK, 0);
    assert(usbhw_transfer_out(PID_OUT, 7, 2, 1, PID_DATA1, transmit, 512) == USB_RES_NAK);
    assert(transfers == 2 && observed[1].pid == 0xb4);
    response(0, PID_ACK, 0); response(0, PID_ACK, 0);
    assert(usbhw_transfer_out(PID_OUT, 7, 2, 1, PID_DATA1, transmit, 512) == USB_RES_OK);
    assert(transfers == 4 && observed[2].pid == 0xb4 && observed[3].pid == PID_OUT && observed[3].toggle == 1);
    uint8_t setup[8] = {0, 9, 1, 0, 0, 0, 0, 0};
    response(0, PID_ACK, 0); response(0, PID_DATA1, 0);
    assert(usbhw_transfer_out(PID_SETUP, 7, 0, 1, PID_DATA0, setup, 8) == 0);
    assert(usbhw_transfer_in(PID_IN, 7, 0, &pid, receive, 1) == 0 && observed[5].toggle == 1);
    response(0, PID_DATA0, 4);
    assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive, 4) == 4);
    setup[0] = 2; setup[1] = 1; setup[2] = 0; setup[4] = 0x81;
    response(0, PID_ACK, 0); response(0, PID_DATA1, 0);
    assert(usbhw_transfer_out(PID_SETUP, 7, 0, 1, PID_DATA0, setup, 8) == 0);
    assert(usbhw_transfer_in(PID_IN, 7, 0, &pid, receive, 1) == 0);
    response(0, PID_DATA0, 4);
    assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive, 4) == 4 && observed[9].toggle == 0);
    ++epoch;
    unsigned before = transfers;
    assert(!usbhw_hub_device_detected() && transfers == before);
    start(1); change_epoch = 1; response(0, PID_DATA0, 4);
    assert(usbhw_transfer_in(PID_IN, 7, 1, &pid, receive, 4) == USB_RES_TIMEOUT);
    start(1); now = 0xfffffff0u; usbhw_timer_sleep(50);
    assert(now < 100 && usbhw_hub_device_detected());
    clock_step = 0; before = disables; usbhw_timer_sleep(2);
    assert(disables == before + 1 && !usbhw_hub_device_detected());
    puts("PASS workstation_usb2_backend: HS/FS bounds, toggles, duplicates, NYET/PING, control reset, epoch, timer");
    return 0;
}
