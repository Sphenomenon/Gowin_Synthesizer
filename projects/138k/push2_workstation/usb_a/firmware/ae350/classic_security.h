#ifndef A138_CLASSIC_SECURITY_H
#define A138_CLASSIC_SECURITY_H
#include "classic_service.h"

/* EXPERIMENTAL, unselected. SSP Security Mode 4 / Level 2 only: actual
 * NoInputNoOutput, no OOB, General Bonding, no MITM and no Secure Connections
 * claim. No controller reset, ACL credits, UART, Flash driver or product UI.
 * The caller starts only after the single PL HCI owner's host-flow bootstrap,
 * with all old command owners retired, scan disabled and no BR/EDR link.
 * All callbacks must be bounded and nonblocking. Tick before every service
 * pass, at least every100ms; one owner calls all methods cooperatively.
 */
#define A138_SECURITY_QUEUE 8u
#define A138_SECURITY_COMMAND_MS 1000u
#define A138_SECURITY_LINK_MS 30000u
#define A138_SECURITY_STORE_MS 1000u

enum a138_security_result {
    A138_SECURITY_OK, A138_SECURITY_ARGUMENT, A138_SECURITY_STALE,
    A138_SECURITY_BUSY, A138_SECURITY_EMPTY, A138_SECURITY_MALFORMED,
    A138_SECURITY_FENCED
};
enum a138_bond_result { A138_BOND_OK, A138_BOND_MISSING, A138_BOND_BUSY, A138_BOND_ERROR };
/* A bounded external atomic owner, not an implemented persistent backend.
 * One peer identity +16-byte key+type+minimum negotiated size+revision commit
 * atomically. MISSING returns no key. Replace/delete compare expected_revision
 * (0 means absent); OK is actual durable completion, BUSY has no committed
 * mutation, ERROR is never treated as success. No partial/torn records may be
 * exposed. Revocations must survive reboot. The same operation/revision is
 * idempotent if an observation is lost; no key is written to board Flash here.
 */
struct a138_bond {
    uint32_t version, revision;
    uint8_t peer[6], key[16], type, minimum_size;
};
struct a138_bond_store {
    void *context;
    enum a138_bond_result (*load)(void *,const uint8_t [6],struct a138_bond *);
    enum a138_bond_result (*replace_atomic)(void *,const struct a138_bond *,uint32_t);
    enum a138_bond_result (*delete_atomic)(void *,const uint8_t [6],uint32_t);
};
struct a138_security_command {
    uint32_t epoch,generation,token,started_ms;
    uint16_t opcode;
    uint8_t bytes,kind,accepted,transport_done,response_done;
    uint8_t data[25]; /* complete HCI command including opcode/parameter length */
};
struct a138_security {
    struct a138_classic_service *classic;
    struct a138_bond_store store;
    struct a138_bond bond;
    struct a138_security_command queue[A138_SECURITY_QUEUE];
    uint32_t epoch,generation,last_generation,next_token,clock_ms,link_started_ms,store_started_ms;
    uint16_t handle,tx_limit;
    uint8_t head,count,clock_valid,started,fenced,recovery_required,ready,local_step;
    uint8_t phase,requested,request_pending,accept_sent,active,peer[6];
    uint8_t remote_basic,remote_host,auth_done,encrypted,key_size;
    uint8_t basic_sent,host_sent,auth_sent,encrypt_sent;
    uint8_t key_loaded,key_used,new_key,io_replied,remote_io_seen,remote_auth;
    uint8_t peer_auth_started,key_response_sent,io_pending;
    uint32_t io_started_ms;
    uint8_t secure,closing,disconnect_queued,delete_pending,forget_pending,forget_peer[6];
    uint32_t forget_revision;
    uint8_t close_reason,close_cause,failure;
    uint32_t stale_events,negative_replies;
};

void a138_security_init(struct a138_security *s);
/* epoch is the external common-controller-reset identity. CPU reset never
 * invents a new epoch or resets the PL ledger. A fresh object may start only
 * after hardware has fenced/retired all old descriptors and links. tx_limit
 * is actual BR pool data limit from the sole PL owner, not a credit count.
 */
enum a138_security_result a138_security_start(struct a138_security *s,uint32_t epoch,
    uint16_t tx_limit,struct a138_classic_service *classic,const struct a138_bond_store *store);
enum a138_security_result a138_security_tick(struct a138_security *s,uint32_t epoch,uint32_t now_ms);
enum a138_security_result a138_security_pump(struct a138_security *s);
/* Stable front bytes through actual transport retirement and matching result.
 * Submission ACCEPTED is the irreversible shared owner2/private H5 slot
 * acceptance. REJECTED consumes nothing; UNCERTAIN requires controller recovery.
 * transport_done belongs to this exact token, not any H5 packet. A successful
 * CommandStatus is acceptance only; async final events are independently checked.
 */
enum a138_security_result a138_security_tx_peek(struct a138_security *s,struct a138_security_command *out);
enum a138_security_result a138_security_tx_result(struct a138_security *s,uint32_t epoch,
    uint32_t token,enum a138_classic_submission result);
enum a138_security_result a138_security_transport_done(struct a138_security *s,uint32_t epoch,uint32_t token);
/* Only the sole PL owner's owner2-routed CommandComplete/CommandStatus enters
 * response. Other owners' results are STALE without consuming our pending work.
 * Full original event bytes preserve exact opcode/status/return-length checks.
 */
enum a138_security_result a138_security_response(struct a138_security *s,uint32_t epoch,
    uint8_t owner,const uint8_t *event,uint16_t bytes);
/* Other complete raw HCI events. ConnectionComplete uses the PL owner's actual
 * newly admitted nonzero generation; all link events carry that same generation.
 * available is the PL capacity decision, consulted only for ConnectionRequest.
 * Unknown/wrong peer key/PIN/IO requests receive explicit negative replies.
 * Controller/H5 enqueue order must be preserved; no CPU reset may replay events.
 */
enum a138_security_result a138_security_event(struct a138_security *s,uint32_t epoch,
    uint32_t generation,uint8_t available,const uint8_t *event,uint16_t bytes);
/* Calls the actual Classic ACL owner. SDP remains accessible before encryption;
 * AVDTP ConnectionRequest receives security-block0x0003 and cannot allocate.
 * The bounded close waits for that response's irreversible ACL acceptance (or
 * at most100ms), then submits actual HCI Disconnect via the same owner2 queue.
 */
enum a138_classic_result a138_security_classic_acl(struct a138_security *s,uint32_t epoch,
    uint32_t generation,const uint8_t *acl,uint16_t bytes);
enum a138_security_result a138_security_forget(struct a138_security *s,uint32_t epoch,const uint8_t peer[6]);
void a138_security_observer_reset(struct a138_security *s);
#endif
