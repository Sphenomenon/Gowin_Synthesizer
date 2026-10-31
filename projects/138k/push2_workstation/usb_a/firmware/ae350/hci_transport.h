#ifndef A138_HCI_TRANSPORT_H
#define A138_HCI_TRANSPORT_H
#include <stdint.h>
#include <stddef.h>

/* The one CPU client of NATIVE_TRANSPORT_CONTRACT.md. No UART, command/ACL
 * credit authority, controller reset or physical RX-credit return lives here.
 * One call performs at most 16 TX or 16 RX bytes; each bus callback itself must
 * be bounded. Ordinary volatile MMIO faults trap; it cannot recover APB errors.
 */
#define A138_HCI_BASE UINT32_C(0xf8050200)
#define A138_HCI_BYTES 280u
#define A138_HCI_SLICE 16u
enum { A138_HCI_COMMAND=1,A138_HCI_ACL=2,A138_HCI_EVENT=4 };
enum { A138_HCI_FAULT_IO=1,A138_HCI_FAULT_IDENTITY,A138_HCI_FAULT_HARDWARE,
       A138_HCI_FAULT_DESCRIPTOR,A138_HCI_FAULT_TOKEN,A138_HCI_FAULT_UNCERTAIN };
struct a138_hci_bus {
    void *context;
    int (*read)(void *,uint32_t,uint32_t *);
    int (*write)(void *,uint32_t,uint32_t);
};
struct a138_hci_rx {
    uint32_t epoch,generation,ticket,token;
    uint16_t bytes,handle;
    uint8_t type,owner,response,retired;
    uint8_t data[A138_HCI_BYTES];
};
struct a138_hci_transport {
    struct a138_hci_bus bus;
    struct a138_hci_rx rx;
    uint32_t epoch,now_ms,next_token,tx_token,tx_generation,source_token;
    uint16_t br_limit,le_limit,tx_bytes,tx_offset,rx_offset;
    uint8_t ready,available,fault,tx_type,tx_phase,accepted,transport_done,response_done;
    uint8_t rejected,uncertain,rx_phase;
    uint8_t tx[A138_HCI_BYTES];
};
struct a138_hci_bus a138_hci_mmio_bus(uintptr_t base);
void a138_hci_init(struct a138_hci_transport *,struct a138_hci_bus);
/* Returns1 only for a private CPU copy; it is NOT irreversible acceptance.
 * source_token belongs to security/Classic; tx_token is independently monotonic
 * across both producers. Bytes remain private through hardware ACK. */
int a138_hci_offer(struct a138_hci_transport *,uint8_t,uint32_t,uint32_t,
                   const uint8_t *,uint16_t);
void a138_hci_step(struct a138_hci_transport *);
/* Caller has delivered exactly the original owner2 CC/CS to security. */
int a138_hci_response_delivered(struct a138_hci_transport *,uint32_t);
/* The caller must report ACCEPTED, transport_done and response to the owning
 * C service before retiring. A rejected command can be explicitly retried with
 * the same service token and a new transport token; uncertainty cannot. */
int a138_hci_tx_retire(struct a138_hci_transport *);
const struct a138_hci_rx *a138_hci_rx_peek(const struct a138_hci_transport *);
int a138_hci_rx_release(struct a138_hci_transport *,uint32_t,uint32_t);
#endif
