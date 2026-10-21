#ifndef WORKSTATION_USB2_HOST_H
#define WORKSTATION_USB2_HOST_H

#include <stdint.h>

enum workstation_usb2_error {
    WORKSTATION_USB2_OK = 0,
    WORKSTATION_USB2_ARGUMENT = -1,
    WORKSTATION_USB2_IO = -2,
    WORKSTATION_USB2_NOT_READY = -3,
    WORKSTATION_USB2_BUSY = -4,
    WORKSTATION_USB2_CANCELLED = -5,
    WORKSTATION_USB2_TIMEOUT = -6,
    WORKSTATION_USB2_INCOMPATIBLE = -7,
    WORKSTATION_USB2_PROTOCOL = -8
};

struct workstation_usb2_io {
    void *context;
    int (*read32)(void *context, uint32_t offset, uint32_t *value);
    int (*write32)(void *context, uint32_t offset, uint32_t value);
    uint32_t (*milliseconds)(void *context);
};

struct workstation_usb2_host {
    struct workstation_usb2_io io;
    uint32_t poll_limit;
    uint32_t control;
    unsigned initialized;
};

struct workstation_usb2_command {
    uint8_t pid;
    uint8_t device;
    uint8_t endpoint;
    uint8_t toggle;
    uint16_t length;
};

struct workstation_usb2_result {
    uint8_t status;
    uint8_t pid;
    uint16_t length;
};

int workstation_usb2_open(struct workstation_usb2_host *host, const struct workstation_usb2_io *io);
int workstation_usb2_disable(struct workstation_usb2_host *host);
int workstation_usb2_enable(struct workstation_usb2_host *host, unsigned allow_high_speed, uint32_t timeout_ms);
int workstation_usb2_reset_port(struct workstation_usb2_host *host, uint32_t timeout_ms);
int workstation_usb2_transfer(struct workstation_usb2_host *host, const struct workstation_usb2_command *command,
                             const uint8_t *transmit, uint8_t *receive, uint16_t receive_capacity,
                             struct workstation_usb2_result *result, uint32_t timeout_ms);

#endif
