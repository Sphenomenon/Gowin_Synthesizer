#include "workstation_usb2_backend.h"
#include "workstation_usb2_cpu_port.h"
#include "usb_defs.h"
#include "usb_hw.h"

static struct workstation_usb2_host native_host;
static struct workstation_usb2_io native_io;
static uint32_t generation, retry_at;
static uint16_t ping_endpoints;
static uint8_t input_toggle[16];
static unsigned initialized, online, high_speed, bulk_used, allow_high_speed;
static uint8_t control_action, control_endpoint;

static void clear_transport(void)
{
    for (unsigned endpoint = 0; endpoint < 16; ++endpoint) input_toggle[endpoint] = 0;
    ping_endpoints = 0; bulk_used = 0; control_action = 0;
}

static void stop_transport(void)
{
    if (initialized) workstation_usb2_disable(&native_host);
    online = 0;
    clear_transport();
    retry_at = native_io.milliseconds ? native_io.milliseconds(native_io.context) + 100u : 0;
}

static int read_session(uint32_t *status, uint32_t *epoch)
{
    if (!initialized || native_io.read32(native_io.context, 8, status) ||
        native_io.read32(native_io.context, 0x28, epoch)) return 0;
    return (*status & 0x21001bu) == 0x21000bu;
}

static int check_session(void)
{
    uint32_t status, epoch;
    if (!online || !read_session(&status, &epoch) || epoch != generation) {
        if (online) stop_transport();
        return 0;
    }
    high_speed = (status >> 2) & 1u;
    return 1;
}

static int start_transport(void)
{
    uint32_t status, epoch;
    if (!initialized || workstation_usb2_enable(&native_host, allow_high_speed, 400) != WORKSTATION_USB2_OK ||
        !read_session(&status, &epoch)) {
        stop_transport();
        return 0;
    }
    clear_transport(); generation = epoch; high_speed = (status >> 2) & 1u; online = 1;
    return 1;
}

void usbhw_init(uint32_t base)
{
    if (initialized) stop_transport();
    initialized = 0; online = 0; retry_at = 0;
    allow_high_speed = 1;
    clear_transport();
    workstation_usb2_cpu_io(&native_io);
    if (base == 0x02000100u && workstation_usb2_open(&native_host, &native_io) == WORKSTATION_USB2_OK)
        initialized = 1;
}

int usbhw_native_allow_high_speed(unsigned allowed)
{
    if (allowed > 1 || online) return -1;
    allow_high_speed = allowed;
    return 0;
}

void usbhw_hub_enable(int full_speed, int enable_sof)
{
    (void)full_speed; (void)enable_sof;
    start_transport();
}

int usbhw_hub_device_detected(void)
{
    if (online) return check_session();
    if (initialized && (int32_t)(native_io.milliseconds(native_io.context) - retry_at) >= 0)
        return start_transport();
    return 0;
}

unsigned usbhw_native_high_speed(void)
{
    return check_session() ? high_speed : 0;
}

unsigned usbhw_native_packet_limit(void)
{
    return usbhw_native_high_speed() ? 512u : 64u;
}

int usbhw_hub_full_speed_device(void)
{
    return check_session() && !high_speed;
}

int usbhw_reset(void)
{
    uint32_t status, epoch;
    if (!check_session() || workstation_usb2_reset_port(&native_host, 400) != WORKSTATION_USB2_OK ||
        !read_session(&status, &epoch)) {
        stop_transport();
        return USB_RES_TIMEOUT;
    }
    clear_transport(); generation = epoch; high_speed = (status >> 2) & 1u; online = 1;
    return USB_RES_OK;
}

void usbhw_hub_reset(void)
{
    (void)usbhw_reset();
}

static int execute(struct workstation_usb2_command *command, const uint8_t *transmit, uint8_t *receive,
                   struct workstation_usb2_result *result)
{
    if (!check_session()) return USB_RES_TIMEOUT;
    int error = workstation_usb2_transfer(&native_host, command, transmit, receive, command->length, result, 20);
    if (error != WORKSTATION_USB2_OK) {
        stop_transport();
        return USB_RES_TIMEOUT;
    }
    if (!check_session()) return USB_RES_TIMEOUT;
    if (result->status == 1) return USB_RES_NAK;
    if (result->status == 2) return USB_RES_STALL;
    if (result->status == 3) return USB_RES_TIMEOUT;
    if (result->status != 0 && result->status != 5 && result->status != 9) {
        stop_transport();
        return USB_RES_STALL;
    }
    return USB_RES_OK;
}

static void control_completed(void)
{
    if (control_action == 1) {
        for (unsigned endpoint = 1; endpoint < 16; ++endpoint) input_toggle[endpoint] = 0;
        ping_endpoints = 0; bulk_used = 0;
    } else if (control_action == 2) input_toggle[control_endpoint] = 0;
    else if (control_action == 3) ping_endpoints &= (uint16_t)~(1u << control_endpoint);
    control_action = 0;
}

int usbhw_transfer_out(uint8_t pid, int device_addr, int endpoint, int handshake, uint8_t request,
                       uint8_t *transmit, int length)
{
    struct workstation_usb2_result result;
    if (device_addr < 0 || device_addr > 127 || endpoint < 0 || endpoint > 15 || handshake != 1 ||
        (pid != PID_SETUP && pid != PID_OUT) || (request != PID_DATA0 && request != PID_DATA1) ||
        length < 0 || (unsigned)length > usbhw_native_packet_limit() || (length && !transmit) ||
        (pid == PID_SETUP && (endpoint != 0 || request != PID_DATA0 || length != 8))) return USB_RES_STALL;
    if (pid == PID_SETUP && transmit[0] == 1 && transmit[1] == 11 && bulk_used) return USB_RES_STALL;
    struct workstation_usb2_command command = {pid, (uint8_t)device_addr, (uint8_t)endpoint,
                                               request == PID_DATA1, (uint16_t)length};
    if (pid == PID_OUT && high_speed && (ping_endpoints & (1u << endpoint))) {
        struct workstation_usb2_command ping = {0xb4, (uint8_t)device_addr, (uint8_t)endpoint, 0, 0};
        int error = execute(&ping, 0, 0, &result);
        if (error != USB_RES_OK) return error;
        if (result.status != 0 || result.pid != PID_ACK) { stop_transport(); return USB_RES_STALL; }
        ping_endpoints &= (uint16_t)~(1u << endpoint);
    }
    int error = execute(&command, transmit, 0, &result);
    if (pid == PID_OUT && high_speed && (error == USB_RES_NAK || (error == USB_RES_OK && result.status == 9)))
        ping_endpoints |= (uint16_t)(1u << endpoint);
    if (error != USB_RES_OK) return error;
    if ((result.status != 0 && !(pid == PID_OUT && high_speed && result.status == 9)) ||
        (result.pid != PID_ACK && !(pid == PID_OUT && high_speed && result.pid == 0x96))) {
        stop_transport(); return USB_RES_STALL;
    }
    if (endpoint) bulk_used = 1;
    if (pid == PID_SETUP) {
        input_toggle[0] = 1; control_action = 0;
        unsigned value = transmit[2] | ((unsigned)transmit[3] << 8);
        unsigned target = transmit[4] | ((unsigned)transmit[5] << 8);
        if ((transmit[0] == 0 && transmit[1] == 9) || (transmit[0] == 1 && transmit[1] == 11))
            control_action = 1;
        else if (transmit[0] == 2 && transmit[1] == 1 && value == 0 && !(target & 0xff70u)) {
            control_endpoint = (uint8_t)(target & 15u);
            control_action = target & 0x80u ? 2 : 3;
        }
    } else if (endpoint == 0 && length == 0) control_completed();
    return USB_RES_OK;
}

int usbhw_transfer_in(uint8_t pid, int device_addr, int endpoint, uint8_t *response, uint8_t *receive, int capacity)
{
    struct workstation_usb2_result result;
    if (response) *response = 0;
    if (pid != PID_IN || !response || device_addr < 0 || device_addr > 127 || endpoint < 0 || endpoint > 15 ||
        capacity < 0 || (capacity && !receive)) return USB_RES_STALL;
    unsigned limit = usbhw_native_packet_limit();
    if ((unsigned)capacity < limit) limit = (unsigned)capacity;
    struct workstation_usb2_command command = {pid, (uint8_t)device_addr, (uint8_t)endpoint,
                                               input_toggle[endpoint], (uint16_t)limit};
    int error = execute(&command, 0, receive, &result);
    if (error != USB_RES_OK) return error;
    *response = result.pid;
    if (result.status == 5) return 0;
    if (result.status != 0 || result.pid != (input_toggle[endpoint] ? PID_DATA1 : PID_DATA0) || result.length > limit) {
        stop_transport(); return USB_RES_STALL;
    }
    input_toggle[endpoint] ^= 1;
    if (endpoint) bulk_used = 1;
    else if (result.length == 0) control_completed();
    return result.length;
}

void usbhw_timer_sleep(int milliseconds)
{
    if (!initialized || milliseconds <= 0) return;
    uint32_t start = native_io.milliseconds(native_io.context), previous = start, polls = 0;
    for (;;) {
        uint32_t now = native_io.milliseconds(native_io.context);
        if ((uint32_t)(now - start) >= (uint32_t)milliseconds) return;
        if (now != previous) polls = 0;
        else if (++polls == native_host.poll_limit) { stop_transport(); return; }
        previous = now;
    }
}

t_time usbhw_timer_now(void)
{
    return native_io.milliseconds ? native_io.milliseconds(native_io.context) : 0;
}
