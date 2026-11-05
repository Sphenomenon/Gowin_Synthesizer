#ifndef GW138K_BLE_BUSINESS_OWNER_H
#define GW138K_BLE_BUSINESS_OWNER_H
#include "business_mailbox.h"
#include "recording_service.h"
#define A138_BLE_BUSINESS_BASE UINT32_C(0xf8050000)
/* Explicit firmware/physical-store configuration; format 1 stays 48-kHz
 * stereo PCM16. Default builds retain their existing 64-KiB object. */
#ifndef A138_BLE_RECORD_CAPACITY_FRAMES
#define A138_BLE_RECORD_CAPACITY_FRAMES 16384u
#endif
#if A138_BLE_RECORD_CAPACITY_FRAMES < 1 || A138_BLE_RECORD_CAPACITY_FRAMES > 0x10000000u
#error "BLE recording capacity must fit native DDR and 32-bit PCM byte counts"
#endif
enum {
    A138_OWNER_SUBMIT_IO=101,A138_OWNER_FACT_IO,A138_OWNER_OBSERVER_LOST,
    A138_OWNER_DIRTY_BOOT,A138_OWNER_CONTEXT_CHANGED,A138_OWNER_RESULT_IO,
    A138_OWNER_COMPLETE_IO,A138_OWNER_OBSERVE_IO,A138_OWNER_OPEN_UNCERTAIN,
    A138_OWNER_REQUEST_IO,A138_OWNER_CLAIM_IO,A138_OWNER_SUBMIT_UNOBSERVED,
    A138_OWNER_COMPLETE_UNOBSERVED,A138_OWNER_REQUEST_META_IO,
    A138_OWNER_REQUEST_META_UNOBSERVED,A138_OWNER_RESULT_IDENTITY,
    A138_OWNER_CAPACITY_MISMATCH,A138_OWNER_FORMAT_MISMATCH
};
typedef struct {
    uint32_t id,request_id,recording_id,time_ms;
    uint8_t opcode,state,error,valid;
} a138_ble_task;
typedef struct {
    uint32_t id,object_id,session,offset,time_ms,pending_offset,pending_length,pending_crc;
    uint32_t last_ack_offset,last_ack_crc,extended_limit;
    uint8_t open,pending,last_ack_valid,mode,flags;
} a138_ble_transfer;
#ifdef A138_SINGLE_BLE_RECORDING
/* A receipt is a request result, never an independent recording object. */
typedef struct {
    uint32_t token,opcode,phase,status,operation_id,object_id;
    uint32_t frames,committed,crc;
} a138_ble_local_record_result;
enum { A138_LOCAL_NONE=0,A138_LOCAL_QUEUED=1,A138_LOCAL_WAIT=2,A138_LOCAL_DONE=3 };
#endif
typedef struct {
    a138_business_bus mailbox;
    a138_record_bus data;
    a138_business_key context;
    a138_business_request request;
    a138_record_data_facts facts;
    a138_record_request_facts request_facts;
    a138_ble_transfer transfer;
    a138_ble_task tasks[8];
    uint32_t operation_counter,object_counter,transfer_counter,current_operation;
    uint32_t command_sequence,submission_ms,pending_operation,pending_object,pending_transfer;
    uint32_t phase,opened,bound,fault,completion_phase,completion_status,completion_length;
    uint8_t active_read,active_replay;
    uint8_t completion_payload[64];
#ifdef A138_BLE_RECORD_DUAL_RATE
    uint32_t format_grant_session,format_grant_mask;
#endif
#ifdef A138_SINGLE_BLE_RECORDING
    a138_ble_local_record_result local_record;
    uint32_t local_limit;
#ifdef A138_BLE_RECORD_DUAL_RATE
    uint32_t local_format;
#endif
    uint8_t local_pending,active_local;
#endif
#ifdef A138_BLE_BUSINESS_DIAGNOSTICS
    /* Observation only; never used to decide command/task/transfer behavior. */
    uint32_t diagnostic_claimed,diagnostic_completed;
#endif
} a138_ble_business_owner;
/* One caller, fixed work per pump, no waits, allocation or PCM copies. At most
 * one new descriptor or mailbox completion is submitted by a pump. An access
 * failure fences this owner; uncertain commits are observed by their exact
 * sequence/key. CPU observer reset requires actual recovery or common reset,
 * never a same-boot counter restart. The v1 owner intentionally cannot recover
 * lost task memory and therefore keeps the existing hardware reset fence. */
void a138_ble_business_init(a138_ble_business_owner *,a138_business_bus,a138_record_bus);
void a138_ble_business_pump(a138_ble_business_owner *);
#ifdef A138_SINGLE_BLE_RECORDING
/* Bounded single-caller CPU/UI proxy for the SAME BLE object/CRC/task owner.
 * Only START(20), STOP(21), CLEAR(23) are accepted. START has a frame limit;
 * STOP/CLEAR bind the actual current object at dispatch. Return1 means queued,
 * not applied. Poll returns DONE only after actual first frame (START), native
 * DDR READY (STOP), or actual raw CLEAR; the saved token is never auto-retried.
 * Local commands serialize with BLE primitives and share monotonic IDs. The
 * CPU observer-reset fence remains in force. No GATT connection is required. */
int a138_ble_record_local_submit(a138_ble_business_owner *,uint32_t opcode,uint32_t limit);
#ifdef A138_BLE_RECORD_DUAL_RATE
/* Trusted local request; physical START still checks the actual source format.
 * Existing submit always requests format1. This cannot change the audio clock. */
int a138_ble_record_local_submit_format(a138_ble_business_owner *,uint32_t opcode,uint32_t limit,uint32_t format);
#endif
int a138_ble_record_local_poll(const a138_ble_business_owner *,a138_ble_local_record_result *);
int a138_ble_record_firmware_submit(uint32_t opcode,uint32_t limit);
int a138_ble_record_firmware_poll(a138_ble_local_record_result *);
int a138_ble_record_firmware_facts(a138_record_data_facts *);
#endif
void a138_ble_business_firmware_init(void);
void a138_ble_business_firmware_pump(void);
#endif
