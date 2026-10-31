#ifndef A138_CLASSIC_SERVICE_H
#define A138_CLASSIC_SERVICE_H
#include <stdint.h>

/* Unselected EXPERIMENTAL source-stage; connection/security policy, actual
 * end-to-end delay measurement/drift control and production wiring are absent.
 * No Bluetooth profile compliance or phone interoperability claim.
 * One cooperative CPU owner, no heap or MMIO. */
#define A138_CLASSIC_ACL_BYTES 280u
#define A138_CLASSIC_MTU 672u
#define A138_CLASSIC_FRAME_BYTES 224u
#define A138_CLASSIC_FRAMES 4u
#define A138_CLASSIC_DELAY_TIMEOUT_MS 1000u

enum a138_classic_delay_phase {
    A138_CLASSIC_DELAY_NONE, A138_CLASSIC_DELAY_QUEUED,
    A138_CLASSIC_DELAY_TX, A138_CLASSIC_DELAY_WAIT, A138_CLASSIC_DELAY_COMPLETE
};
enum a138_classic_delay_failure {
    A138_CLASSIC_DELAY_NO_FAILURE, A138_CLASSIC_DELAY_TIMEOUT,
    A138_CLASSIC_DELAY_REJECTED, A138_CLASSIC_DELAY_BAD_RESPONSE,
    A138_CLASSIC_DELAY_LABEL_EXHAUSTED, A138_CLASSIC_DELAY_CLOCK_REGRESSED
};

enum a138_classic_result {
    A138_CLASSIC_OK, A138_CLASSIC_ARGUMENT, A138_CLASSIC_STALE,
    A138_CLASSIC_INACTIVE, A138_CLASSIC_BUSY, A138_CLASSIC_MALFORMED,
    A138_CLASSIC_DROPPED, A138_CLASSIC_FENCED, A138_CLASSIC_EMPTY
};
enum a138_classic_submission {
    A138_CLASSIC_ACCEPTED, A138_CLASSIC_REJECTED, A138_CLASSIC_UNCERTAIN
};
enum a138_classic_stream_state {
    A138_CLASSIC_IDLE, A138_CLASSIC_CONFIGURED, A138_CLASSIC_OPEN,
    A138_CLASSIC_STREAMING
};
struct a138_classic_format {
    uint32_t rate_hz;
    uint8_t mode, subbands, blocks, allocation, min_bitpool, max_bitpool;
};
struct a138_classic_frame {
    uint32_t link_epoch, stream_epoch, timestamp;
    uint16_t bytes, sequence;
    struct a138_classic_format format;
    uint8_t data[A138_CLASSIC_FRAME_BYTES];
};
struct a138_classic_tx {
    uint32_t link_epoch, generation, token;
    uint16_t bytes;
    uint8_t data[A138_CLASSIC_ACL_BYTES];
};
struct a138_classic_channel {
    uint16_t remote_cid, peer_mtu;
    uint8_t allocated, local_config, remote_config, config_id, connection_id;
};
struct a138_classic_service {
    uint32_t link_epoch, generation, next_token, offered_token, stream_epoch;
    uint32_t malformed, media_dropped, sequence_gaps, ssrc, fragment_timestamp;
    uint16_t handle, rx_bytes, rx_total, tx_bytes, tx_offset, tx_offered, tx_payload_limit;
    uint16_t sequence, fragment_bytes, avdtp_bytes, fragment_packet_bytes, fragment_sequence;
    uint8_t active, fenced, rx_complete, offered, next_id, state, pending_state;
    uint8_t ready, sequence_valid, ssrc_valid, frame_head, frame_count;
    uint8_t avdtp_active, avdtp_label, avdtp_signal, avdtp_packets, avdtp_seen;
    uint8_t fragment_remaining;
    uint8_t fragment_active, codec[4], pending_codec[4], pending_config;
    uint32_t clock_ms, delay_started_ms;
    uint16_t delay_value, delay_reported_value;
    uint8_t clock_valid, delay_valid, delay_selected, pending_delay_selected;
    uint8_t remote_seid, pending_remote_seid, delay_phase, delay_sent;
    uint8_t delay_label, delay_labels_used, delay_failure, tx_is_delay, avdtp_message_type;
    struct a138_classic_format format;
    struct a138_classic_channel channel[3]; /* SDP, AVDTP signal, media */
    uint8_t rx[A138_CLASSIC_MTU + 4u];
    uint8_t tx[A138_CLASSIC_MTU + 4u];
    uint8_t fragment[A138_CLASSIC_FRAME_BYTES];
    uint8_t avdtp[128];
    struct a138_classic_frame frame[A138_CLASSIC_FRAMES];
};

void a138_classic_init(struct a138_classic_service *s);
/* Epoch strictly increases during this object's lifetime. PL must retire old
 * descriptors across CPU reset; generation is supplied by the sole HCI owner.
 * tx_payload_limit is min(actual controller BR ReadBufferSize data length,276),
 * range4..276; it is immutable for this link. This is not a credit count.
 * This service never resets HCI, changes credits, pairs, or owns UART/H5.
 */
enum a138_classic_result a138_classic_begin(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, uint16_t handle, uint16_t tx_payload_limit);
enum a138_classic_result a138_classic_cancel(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation);
/* Original complete HCI event {code,length,parameters}. Only validated
 * Disconnection Complete for our handle retires the link; other events remain
 * the caller's connection/security-policy responsibility. */
enum a138_classic_result a138_classic_event(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, const uint8_t *event, uint16_t bytes);
/* Original HCI ACL {handle/PB/BC LE16,length LE16,payload}. OK/DROPPED/MALFORMED
 * consume the packet. BUSY consumes nothing: retain this exact packet. Caller
 * returns controller-to-host credits only after its own consumer handoff.
 * At most one incomplete PDU and one pending complete PDU are buffered.
 */
enum a138_classic_result a138_classic_acl(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, const uint8_t *acl, uint16_t bytes);
/* Stable bytes/token until result; REJECTED permits explicit same-token retry.
 * UNCERTAIN fences and drops all local queues: never blindly replay it.
 * ACCEPTED means accepted by the unified HCI owner, not remote application.
 */
enum a138_classic_result a138_classic_tx_peek(struct a138_classic_service *s,
    struct a138_classic_tx *tx);
enum a138_classic_result a138_classic_tx_result(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, uint32_t token,
    enum a138_classic_submission result);
/* Grant after the physical audio owner confirms exactly this selected rate.
 * START is rejected until granted; SET_CONFIGURATION invalidates the grant.
 * Revocation immediately clears queued audio and leaves OPEN. */
enum a138_classic_result a138_classic_audio_ready(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, uint32_t rate_hz, uint8_t ready);
/* Required independent monotonic millisecond service clock. Call before other
 * methods for this service pass, at least every100ms; never wait on HCI/CPU RX.
 * uint32 wrap is allowed; backward/jumps >=2^31ms fence. At deadline timeout
 * wins over any subsequently delivered response. 1000ms is within GAVDP1.3's
 * proposed 0.5..3s signaling timer range. TX offer and peer response each bound.
 */
enum a138_classic_result a138_classic_tick(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, uint32_t now_ms);
/* Stable real SNK delay in0.1ms, from baseband media receipt to presentation,
 * not instantaneous FIFO fill. No measurement is invented by this component.
 * Clock + first value must exist before a DelayReporting configuration succeeds.
 * During an outstanding report/TX, BUSY consumes no changed value. The physical
 * owner must keep actual delay within +/-30ms of its reported operating range
 * and compensate drift; cancel if it cannot. A changed stable value queues a
 * fresh report. At most16 labels per link, never wrap to accept an old reply.
 */
enum a138_classic_result a138_classic_delay_update(struct a138_classic_service *s,
    uint32_t link_epoch, uint32_t generation, uint32_t delay_tenths_ms);
enum a138_classic_result a138_classic_frame_pop(struct a138_classic_service *s,
    struct a138_classic_frame *frame);
#endif
