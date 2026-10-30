#ifndef GW138K_BLE_BUSINESS_OWNER_H
#define GW138K_BLE_BUSINESS_OWNER_H
#include "business_mailbox.h"
#include "recording_service.h"
#define A138_BLE_BUSINESS_BASE UINT32_C(0xf8050000)
enum {
    A138_OWNER_SUBMIT_IO=101,A138_OWNER_FACT_IO,A138_OWNER_OBSERVER_LOST,
    A138_OWNER_DIRTY_BOOT,A138_OWNER_CONTEXT_CHANGED,A138_OWNER_RESULT_IO,
    A138_OWNER_COMPLETE_IO,A138_OWNER_OBSERVE_IO,A138_OWNER_OPEN_UNCERTAIN,
    A138_OWNER_REQUEST_IO,A138_OWNER_CLAIM_IO,A138_OWNER_SUBMIT_UNOBSERVED,
    A138_OWNER_COMPLETE_UNOBSERVED,A138_OWNER_REQUEST_META_IO,
    A138_OWNER_REQUEST_META_UNOBSERVED,A138_OWNER_RESULT_IDENTITY
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
} a138_ble_business_owner;
/* One caller, fixed work per pump, no waits, allocation or PCM copies. At most
 * one new descriptor or mailbox completion is submitted by a pump. An access
 * failure fences this owner; uncertain commits are observed by their exact
 * sequence/key. CPU observer reset requires actual recovery or common reset,
 * never a same-boot counter restart. The v1 owner intentionally cannot recover
 * lost task memory and therefore keeps the existing hardware reset fence. */
void a138_ble_business_init(a138_ble_business_owner *,a138_business_bus,a138_record_bus);
void a138_ble_business_pump(a138_ble_business_owner *);
void a138_ble_business_firmware_init(void);
void a138_ble_business_firmware_pump(void);
#endif
