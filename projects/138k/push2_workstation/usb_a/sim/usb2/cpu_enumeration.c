#include "workstation_usb2_cpu_port.h"

#define REGISTER(address) (*(volatile uint32_t *)(uintptr_t)(address))

static struct workstation_usb2_host host;
static struct workstation_usb2_io io;
static uint8_t transmit[512], receive[514], descriptor[18];
static uint8_t address;
static unsigned high_speed, ep0_size;

static void require(int condition, uint32_t code)
{
    if (condition) return;
    REGISTER(0x020002f8u) = code;
    REGISTER(0x020002fcu) = 0xbad00000u | code;
    for (;;) {}
}

static uint32_t read_usb(uint32_t offset)
{
    uint32_t value = 0;
    require(io.read32(io.context, offset, &value) == 0, 0x10u + offset);
    return value;
}

static struct workstation_usb2_result packet(uint8_t pid, uint8_t endpoint, uint8_t toggle, uint16_t length)
{
    struct workstation_usb2_command command = {pid, address, endpoint, toggle, length};
    struct workstation_usb2_result result;
    int error = workstation_usb2_transfer(&host, &command, transmit, receive + 1, 512, &result, 20);
    require(error == WORKSTATION_USB2_OK, 0x100u | ((uint32_t)(-error) & 15u));
    require(result.status == 0, 0x110u | result.status);
    return result;
}

static void setup(uint8_t direction, uint8_t request, uint16_t value, uint16_t length)
{
    transmit[0] = direction; transmit[1] = request; transmit[2] = (uint8_t)value; transmit[3] = (uint8_t)(value >> 8);
    transmit[4] = 0; transmit[5] = 0; transmit[6] = (uint8_t)length; transmit[7] = (uint8_t)(length >> 8);
    packet(0x2d, 0, 0, 8);
}

static void get_descriptor(void)
{
    unsigned count = 0;
    uint8_t toggle = 1;
    setup(0x80, 6, 0x0100, 18);
    while (count < 18) {
        struct workstation_usb2_result result = packet(0x69, 0, toggle, (uint16_t)ep0_size);
        require(result.length != 0 && result.length <= 18 - count, 0x120);
        for (unsigned index = 0; index < result.length; ++index) descriptor[count + index] = receive[index + 1];
        count += result.length; toggle ^= 1;
    }
    require(descriptor[0] == 18 && descriptor[1] == 1 && descriptor[7] == ep0_size, 0x121);
    require(descriptor[8] == 0x9a && descriptor[9] == 0xfb && descriptor[10] == 0x9b && descriptor[11] == 0xfb, 0x122);
    packet(0xe1, 0, 1, 0);
}

int main(void)
{
    uint32_t status, start, previous_generation, value;
    unsigned maximum;
    struct workstation_usb2_command command;
    struct workstation_usb2_result result;
    int error;
    workstation_usb2_cpu_io(&io);
    require(REGISTER(0x02000060u) == 0x55324301u, 1);
    require(io.read32(io.context, 0x3c, &value) != 0, 2);
    require(workstation_usb2_cpu_fault() == 2 && workstation_usb2_cpu_fault_address() == 0x0200013cu, 3);
    workstation_usb2_cpu_clear_fault();
    require(io.write32(io.context, 0x3c, 1) != 0, 4);
    require(workstation_usb2_cpu_fault() == 2, 5);
    workstation_usb2_cpu_clear_fault();
    high_speed = REGISTER(0x020002f0u) & 1u;
    ep0_size = high_speed ? 64 : 8; maximum = high_speed ? 512 : 64;
    REGISTER(0x020002f8u) = 0x200;
    require(workstation_usb2_open(&host, &io) == WORKSTATION_USB2_OK, 6);
    require(workstation_usb2_enable(&host, 1, 300) == WORKSTATION_USB2_OK, 7);
    status = read_usb(8); require(((status >> 2) & 1u) == high_speed && (status & 8u), 8);
    get_descriptor();
    setup(0, 5, 7, 0); packet(0x69, 0, 1, 0); address = 7;
    get_descriptor(); setup(0, 9, 1, 0); packet(0x69, 0, 1, 0);
    for (unsigned index = 0; index < maximum; ++index) transmit[index] = (uint8_t)(index * 37u + 19u);
    packet(0xe1, 1, 0, (uint16_t)maximum);
    receive[0] = 0xa5; receive[513] = 0x5a;
    result = packet(0x69, 2, 0, (uint16_t)maximum);
    require(result.length == maximum && receive[0] == 0xa5 && receive[513] == 0x5a, 9);
    for (unsigned index = 0; index < maximum; ++index) require(receive[index + 1] == (uint8_t)(index * 37u + 19u), 10);
    command.pid = 0x69; command.device = address; command.endpoint = 2; command.toggle = 1; command.length = (uint16_t)maximum;
    require(workstation_usb2_transfer(&host, &command, 0, receive + 1, (uint16_t)(maximum - 1), &result, 20) == WORKSTATION_USB2_ARGUMENT, 11);
    start = io.milliseconds(io.context);
    while ((uint32_t)(io.milliseconds(io.context) - start) < 4) {}
    get_descriptor();
    setup(0x80, 6, 0x0100, 18);
    require(io.write32(io.context, 0x0c, 0x69u | ((uint32_t)address << 8) | (1u << 19) | (ep0_size << 20)) == 0, 12);
    start = io.milliseconds(io.context);
    while (!(read_usb(8) & (1u << 18))) require((uint32_t)(io.milliseconds(io.context) - start) < 20, 13);
    previous_generation = read_usb(0x28);
    REGISTER(0x020002f8u) = 0x300;
    require(workstation_usb2_reset_port(&host, 300) == WORKSTATION_USB2_OK, 14);
    address = 0;
    require(read_usb(0x28) != previous_generation && read_usb(0x24) == 0 && !(read_usb(8) & (1u << 18)), 15);
    get_descriptor();
    REGISTER(0x020002f4u) = 1;
    command.pid = 0x69; command.device = 0; command.endpoint = 0; command.toggle = 0; command.length = (uint16_t)ep0_size;
    error = workstation_usb2_transfer(&host, &command, 0, receive + 1, 512, &result, 20);
    require(error == WORKSTATION_USB2_CANCELLED && result.length == 0, 16);
    REGISTER(0x020002f4u) = 0;
    require(workstation_usb2_enable(&host, 1, 300) == WORKSTATION_USB2_OK, 17);
    get_descriptor();
    require(workstation_usb2_cpu_fault() == 0, 18);
    REGISTER(0x020002fcu) = 0x600d0000u | maximum;
    for (;;) {}
}
