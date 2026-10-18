#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Only the stale identity observed before loading the USB1 CDC image is allowed. */
#define TARGET_VID 0x1209
#define TARGET_PID 0x0001

static void usage(FILE *stream, const char *program) {
    fprintf(stream,
        "Usage: %s --location 0xXXXXXXXX [--inspect | --reenumerate]\n"
        "       %s --help\n"
        "\n"
        "The default is read-only --inspect. The location must be supplied explicitly.\n"
        "Only Primer 25K MIDI (1209:0001) at that exact location is accepted.\n"
        "--reenumerate opens that device and requests USBDeviceReEnumerate(options=0).\n",
        program, program);
}

static int parse_location(const char *text, uint32_t *value) {
    if (!text || text[0] != '0' || (text[1] != 'x' && text[1] != 'X') || !text[2])
        return 0;
    for (const char *p = text + 2; *p; p++) {
        if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f')
            || (*p >= 'A' && *p <= 'F')))
            return 0;
    }
    errno = 0;
    char *end = NULL;
    unsigned long long parsed = strtoull(text + 2, &end, 16);
    if (errno || !end || *end || parsed > UINT32_MAX) return 0;
    *value = (uint32_t)parsed;
    return 1;
}

static int number(io_service_t service, CFStringRef key, uint32_t *value) {
    CFTypeRef obj = IORegistryEntryCreateCFProperty(service, key, NULL, 0);
    int64_t parsed = 0;
    int ok = obj && CFGetTypeID(obj) == CFNumberGetTypeID()
        && CFNumberGetValue(obj, kCFNumberSInt64Type, &parsed)
        && parsed >= 0 && (uint64_t)parsed <= UINT32_MAX;
    if (ok) *value = (uint32_t)parsed;
    if (obj) CFRelease(obj);
    return ok;
}

static int expected_identity(io_service_t service, uint32_t expected_location) {
    uint32_t vid = 0, pid = 0, location = 0;
    if (!number(service, CFSTR("idVendor"), &vid)
        || !number(service, CFSTR("idProduct"), &pid)
        || !number(service, CFSTR("locationID"), &location)
        || vid != TARGET_VID || pid != TARGET_PID || location != expected_location)
        return 0;
    CFTypeRef product = IORegistryEntryCreateCFProperty(service,
        CFSTR("kUSBProductString"), NULL, 0);
    int expected = product && CFGetTypeID(product) == CFStringGetTypeID()
        && CFStringCompare(product, CFSTR("Primer 25K MIDI"), 0) == kCFCompareEqualTo;
    if (product) CFRelease(product);
    return expected;
}

int main(int argc, char **argv) {
    int perform = 0, mode_given = 0, location_given = 0;
    uint32_t expected_location = 0;
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        usage(stdout, argv[0]);
        return 0;
    }
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--location") == 0 && !location_given && i + 1 < argc) {
            if (!parse_location(argv[++i], &expected_location)) {
                fprintf(stderr, "Invalid location: require a hexadecimal UInt32 such as 0x01113200.\n");
                return 2;
            }
            location_given = 1;
        } else if (!mode_given && (strcmp(argv[i], "--inspect") == 0
            || strcmp(argv[i], "--reenumerate") == 0)) {
            perform = strcmp(argv[i], "--reenumerate") == 0;
            mode_given = 1;
        } else {
            usage(stderr, argv[0]);
            return 2;
        }
    }
    if (!location_given) {
        fprintf(stderr, "Refusing: --location is required; there is no default device location.\n");
        usage(stderr, argv[0]);
        return 2;
    }

    io_iterator_t iter = IO_OBJECT_NULL;
    kern_return_t kr = IOServiceGetMatchingServices(kIOMainPortDefault,
        IOServiceMatching("IOUSBHostDevice"), &iter);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "USB registry query failed: 0x%08x\n", kr);
        return 3;
    }
    io_service_t service, target = IO_OBJECT_NULL;
    unsigned at_location = 0, matches = 0;
    while ((service = IOIteratorNext(iter))) {
        uint32_t location = 0;
        if (number(service, CFSTR("locationID"), &location) && location == expected_location) {
            at_location++;
            if (expected_identity(service, expected_location)) {
                matches++;
                if (!target) { target = service; IOObjectRetain(target); }
            }
        }
        IOObjectRelease(service);
    }
    IOObjectRelease(iter);
    if (at_location != 1 || matches != 1) {
        fprintf(stderr, "Refusing location 0x%08" PRIx32 ": found %u device(s), %u matching the fixed target.\n",
            expected_location, at_location, matches);
        if (target) IOObjectRelease(target);
        return 4;
    }
    uint64_t rid = 0;
    IORegistryEntryGetRegistryEntryID(target, &rid);
    printf("Target Primer 25K MIDI 1209:0001 location=0x%08" PRIx32 " registry_id=%" PRIu64 "\n",
        expected_location, rid);
    if (!perform) {
        printf("Inspect only: no device was opened or re-enumerated.\n");
        IOObjectRelease(target);
        return 0;
    }
    IOCFPlugInInterface **plugin = NULL;
    SInt32 score = 0;
    kr = IOCreatePlugInInterfaceForService(target, kIOUSBDeviceUserClientTypeID,
        kIOCFPlugInInterfaceID, &plugin, &score);
    if (kr != kIOReturnSuccess || !plugin) {
        fprintf(stderr, "Create USB plugin failed: 0x%08x\n", kr);
        IOObjectRelease(target);
        return 5;
    }
    IOUSBDeviceInterface187 **device = NULL;
    HRESULT hr = (*plugin)->QueryInterface(plugin,
        CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID187), (LPVOID *)&device);
    (*plugin)->Release(plugin);
    if (hr || !device) {
        fprintf(stderr, "Query USB interface 187 failed: 0x%08x\n", (unsigned)hr);
        IOObjectRelease(target);
        return 6;
    }
    UInt16 vid = 0, pid = 0;
    UInt32 location = 0;
    kr = (*device)->GetDeviceVendor(device, &vid);
    if (kr == kIOReturnSuccess) kr = (*device)->GetDeviceProduct(device, &pid);
    if (kr == kIOReturnSuccess) kr = (*device)->GetLocationID(device, &location);
    int identity_ok = expected_identity(target, expected_location);
    IOObjectRelease(target);
    if (kr != kIOReturnSuccess || vid != TARGET_VID || pid != TARGET_PID
        || location != expected_location || !identity_ok) {
        fprintf(stderr, "Interface target identity changed; refusing.\n");
        (*device)->Release(device);
        return 7;
    }
    kr = (*device)->USBDeviceOpen(device);
    printf("USBDeviceOpen: 0x%08x\n", kr);
    if (kr != kIOReturnSuccess) { (*device)->Release(device); return 8; }
    kr = (*device)->USBDeviceReEnumerate(device, 0);
    printf("USBDeviceReEnumerate options=0: 0x%08x\n", kr);
    (*device)->USBDeviceClose(device);
    (*device)->Release(device);
    return kr == kIOReturnSuccess ? 0 : 9;
}
