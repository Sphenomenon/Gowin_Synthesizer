#include "workstation_usb2_host.h"

#define USB2_ID 0x00u
#define USB2_CONTROL 0x04u
#define USB2_STATUS 0x08u
#define USB2_COMMAND 0x0cu
#define USB2_TRANSMIT 0x10u
#define USB2_RECEIVE 0x14u
#define USB2_RESULT 0x18u
#define USB2_ACTION 0x1cu
#define USB2_TRANSMIT_COUNT 0x20u
#define USB2_GENERATION 0x28u
#define USB2_REFERENCE_FAULT 0x38u
#define USB2_SESSION (1u << 16)
#define USB2_BUSY (1u << 17)
#define USB2_DONE (1u << 18)
#define USB2_CANCELLED (1u << 19)
#define USB2_RESET_PENDING (1u << 20)
#define USB2_SNAPSHOT_VALID (1u << 21)

static int valid_host(const struct workstation_usb2_host *host)
{
    return host && host->initialized && host->poll_limit != 0;
}

static int valid_timeout(uint32_t timeout_ms)
{
    return timeout_ms > 0 && timeout_ms <= 0x7fffffffu;
}

static int read_register(struct workstation_usb2_host *host, uint32_t offset, uint32_t *value)
{
    return host->io.read32(host->io.context, offset, value) == 0 ? WORKSTATION_USB2_OK : WORKSTATION_USB2_IO;
}

static int write_register(struct workstation_usb2_host *host, uint32_t offset, uint32_t value)
{
    return host->io.write32(host->io.context, offset, value) == 0 ? WORKSTATION_USB2_OK : WORKSTATION_USB2_IO;
}

static int expired(struct workstation_usb2_host *host, uint32_t start, uint32_t timeout_ms, uint32_t polls)
{
    return (uint32_t)(host->io.milliseconds(host->io.context) - start) >= timeout_ms || polls >= host->poll_limit;
}

static int fail_closed(struct workstation_usb2_host *host, int error)
{
    workstation_usb2_disable(host);
    return error;
}

int workstation_usb2_open(struct workstation_usb2_host *host, const struct workstation_usb2_io *io)
{
    uint32_t identity, control;
    if (!host || !io || !io->read32 || !io->write32 || !io->milliseconds) return WORKSTATION_USB2_ARGUMENT;
    host->io.context = io->context;
    host->io.read32 = io->read32;
    host->io.write32 = io->write32;
    host->io.milliseconds = io->milliseconds;
    host->initialized = 0;
    host->poll_limit = 1000000;
    host->control = 0;
    if (read_register(host, USB2_ID, &identity) || read_register(host, USB2_CONTROL, &control)) return WORKSTATION_USB2_IO;
    if (identity != 0x55324801u) return WORKSTATION_USB2_INCOMPATIBLE;
    host->control = control & 3u;
    host->initialized = 1;
    return WORKSTATION_USB2_OK;
}

int workstation_usb2_disable(struct workstation_usb2_host *host)
{
    if (!valid_host(host)) return WORKSTATION_USB2_ARGUMENT;
    host->control &= 2u;
    return write_register(host, USB2_CONTROL, host->control);
}

static int wait_port(struct workstation_usb2_host *host, uint32_t start, uint32_t timeout_ms,
                     unsigned require_generation, uint32_t previous_generation)
{
    uint32_t status, generation, reference_fault;
    for (uint32_t polls = 0; !expired(host, start, timeout_ms, polls); ++polls) {
        if (read_register(host, USB2_STATUS, &status) || read_register(host, USB2_GENERATION, &generation) ||
            read_register(host, USB2_REFERENCE_FAULT, &reference_fault)) return fail_closed(host, WORKSTATION_USB2_IO);
        if (reference_fault) return fail_closed(host, WORKSTATION_USB2_NOT_READY);
        if ((status & (USB2_SESSION | USB2_SNAPSHOT_VALID | 0x18u)) == (USB2_SESSION | USB2_SNAPSHOT_VALID | 8u) &&
            (!require_generation || generation != previous_generation)) {
            if (write_register(host, USB2_ACTION, 4)) return fail_closed(host, WORKSTATION_USB2_IO);
            return WORKSTATION_USB2_OK;
        }
    }
    return fail_closed(host, WORKSTATION_USB2_TIMEOUT);
}

int workstation_usb2_enable(struct workstation_usb2_host *host, unsigned allow_high_speed, uint32_t timeout_ms)
{
    uint32_t start, polls;
    if (!valid_host(host) || !valid_timeout(timeout_ms) || allow_high_speed > 1) return WORKSTATION_USB2_ARGUMENT;
    start = host->io.milliseconds(host->io.context);
    if (workstation_usb2_disable(host)) return WORKSTATION_USB2_IO;
    for (polls = 0; (uint32_t)(host->io.milliseconds(host->io.context) - start) < 1; ++polls)
        if (expired(host, start, timeout_ms, polls)) return WORKSTATION_USB2_TIMEOUT;
    host->control = 1u | (allow_high_speed << 1);
    if (write_register(host, USB2_CONTROL, host->control)) return fail_closed(host, WORKSTATION_USB2_IO);
    return wait_port(host, start, timeout_ms, 0, 0);
}

int workstation_usb2_reset_port(struct workstation_usb2_host *host, uint32_t timeout_ms)
{
    uint32_t status, generation, start;
    if (!valid_host(host) || !valid_timeout(timeout_ms)) return WORKSTATION_USB2_ARGUMENT;
    if (!(host->control & 1u)) return WORKSTATION_USB2_NOT_READY;
    if (read_register(host, USB2_STATUS, &status) || read_register(host, USB2_GENERATION, &generation)) return WORKSTATION_USB2_IO;
    if (status & USB2_RESET_PENDING) return WORKSTATION_USB2_BUSY;
    start = host->io.milliseconds(host->io.context);
    if (write_register(host, USB2_CONTROL, host->control | 4u)) return fail_closed(host, WORKSTATION_USB2_IO);
    return wait_port(host, start, timeout_ms, 1, generation);
}

static int session_check(struct workstation_usb2_host *host, uint32_t generation, uint32_t *status)
{
    uint32_t current_generation;
    if (read_register(host, USB2_STATUS, status) || read_register(host, USB2_GENERATION, &current_generation)) return WORKSTATION_USB2_IO;
    if (!(*status & USB2_SESSION) || (*status & USB2_CANCELLED) || current_generation != generation) return WORKSTATION_USB2_CANCELLED;
    return WORKSTATION_USB2_OK;
}

int workstation_usb2_transfer(struct workstation_usb2_host *host, const struct workstation_usb2_command *command,
                             const uint8_t *transmit, uint8_t *receive, uint16_t receive_capacity,
                             struct workstation_usb2_result *result, uint32_t timeout_ms)
{
    uint32_t status, generation, count, descriptor, start, response = 0;
    uint16_t received_length;
    unsigned is_input, is_upload;
    int error;
    if (!result) return WORKSTATION_USB2_ARGUMENT;
    result->length = 0; result->status = 0; result->pid = 0;
    if (!valid_host(host) || !command || !valid_timeout(timeout_ms) || command->device > 127 ||
        command->endpoint > 15 || command->toggle > 1) return WORKSTATION_USB2_ARGUMENT;
    if (read_register(host, USB2_STATUS, &status) || read_register(host, USB2_GENERATION, &generation) ||
        read_register(host, USB2_TRANSMIT_COUNT, &count)) return fail_closed(host, WORKSTATION_USB2_IO);
    if ((status & USB2_CANCELLED) || !(status & USB2_SESSION)) return WORKSTATION_USB2_CANCELLED;
    if (!(status & 8u) || (status & 16u) || !(host->control & 1u)) return WORKSTATION_USB2_NOT_READY;
    if ((status & (USB2_BUSY | USB2_DONE)) || count != 0) return WORKSTATION_USB2_BUSY;
    is_input = command->pid == 0x69;
    is_upload = command->pid == 0xe1 || command->pid == 0x2d;
    if ((!is_input && !is_upload && command->pid != 0xb4) || command->length > ((status & 4u) ? 512 : 64) ||
        (command->pid == 0x2d && (command->length != 8 || command->toggle != 0)) ||
        (command->pid == 0xb4 && (!(status & 4u) || command->length != 0)) ||
        (is_upload && command->length && !transmit) ||
        (is_input && (receive_capacity < command->length || (command->length && !receive)))) return WORKSTATION_USB2_ARGUMENT;
    start = host->io.milliseconds(host->io.context);
    if (is_upload)
        for (uint16_t index = 0; index < command->length; ++index)
            if (write_register(host, USB2_TRANSMIT, transmit[index])) return fail_closed(host, WORKSTATION_USB2_IO);
    if (expired(host, start, timeout_ms, 0)) return fail_closed(host, WORKSTATION_USB2_TIMEOUT);
    error = session_check(host, generation, &status);
    if (error) return error == WORKSTATION_USB2_IO ? fail_closed(host, error) : error;
    descriptor = command->pid | ((uint32_t)command->device << 8) | ((uint32_t)command->endpoint << 15) |
                 ((uint32_t)command->toggle << 19) | ((uint32_t)command->length << 20);
    if (write_register(host, USB2_COMMAND, descriptor)) return fail_closed(host, WORKSTATION_USB2_IO);
    for (uint32_t polls = 0;; ++polls) {
        error = session_check(host, generation, &status);
        if (error) return error == WORKSTATION_USB2_IO ? fail_closed(host, error) : error;
        if (expired(host, start, timeout_ms, polls)) return fail_closed(host, WORKSTATION_USB2_TIMEOUT);
        if (status & USB2_DONE) break;
    }
    if (read_register(host, USB2_RESULT, &response)) return fail_closed(host, WORKSTATION_USB2_IO);
    received_length = (uint16_t)((response >> 16) & 0x3ffu);
    if (!(response & 0x80000000u) || (response & 15u) > 9 || received_length > command->length || received_length > receive_capacity ||
        (received_length && (!is_input || (response & 15u)))) return fail_closed(host, WORKSTATION_USB2_PROTOCOL);
    for (uint16_t index = 0; index < received_length; ++index) {
        if (read_register(host, USB2_RECEIVE, &count)) {
            error = session_check(host, generation, &status);
            return error == WORKSTATION_USB2_CANCELLED ? error : fail_closed(host, WORKSTATION_USB2_IO);
        }
        receive[index] = (uint8_t)count;
    }
    if (expired(host, start, timeout_ms, 0)) return fail_closed(host, WORKSTATION_USB2_TIMEOUT);
    error = session_check(host, generation, &status);
    if (error) return error == WORKSTATION_USB2_IO ? fail_closed(host, error) : error;
    if (write_register(host, USB2_ACTION, 1)) return fail_closed(host, WORKSTATION_USB2_IO);
    error = session_check(host, generation, &status);
    if (error) return error == WORKSTATION_USB2_IO ? fail_closed(host, error) : error;
    result->length = received_length; result->status = (uint8_t)(response & 15u); result->pid = (uint8_t)(response >> 8);
    return WORKSTATION_USB2_OK;
}
