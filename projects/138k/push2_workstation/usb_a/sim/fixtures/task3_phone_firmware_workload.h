#ifndef TASK3_PHONE_FIRMWARE_WORKLOAD_H
#define TASK3_PHONE_FIRMWARE_WORKLOAD_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Simulation only. These callbacks execute every real firmware MMIO access;
 * their caller must advance RTL time until the actual bus operation completes.
 * lane 0 is PCM1 (F806 offsets), lane 1 is the clock owner (F803 offsets).
 * now_ms is the modeled monotonic clock, not native host wall time. */
struct task3_phone_callbacks {
    void *context;
    int (*read)(void *,unsigned lane,uint32_t offset,uint32_t *value);
    int (*write)(void *,unsigned lane,uint32_t offset,uint32_t value);
    uint32_t (*now_ms)(void *);
};
struct task3_phone_workload;
struct task3_phone_stats {
    uint64_t passes,pumps,enqueued,accepted,media_polls,submit_calls;
    uint64_t rejected_submits,uncertain_submits,cancels;
    uint64_t pcm_reads,pcm_writes,window_writes,clock_reads,clock_writes;
    uint64_t local_hci_reads,local_hci_writes;
    uint32_t max_window_writes_per_submit,observed_caps;
    uint32_t fault,media_fault,armed,ready,pending,offset,next_sequence,fences;
};

/* Injects a pre-established Classic/security session and already decoded PCM.
 * It does not establish HCI, authenticate, receive RF or decode SBC. The actual
 * runtime_pass, PCM poll/submit/cancel, command checks and 100 ms timeout run
 * unchanged. inject_cap3 is an explicit test-only 0x67 -> 0x6f read wrapper;
 * production capabilities are never written or modified. */
struct task3_phone_workload *task3_phone_workload_create(
    struct task3_phone_callbacks,uint32_t epoch,uint32_t generation,
    uint32_t stream,uint32_t rate,int inject_cap3);
/* Explicit paired-v3 variant; the original constructor remains legacy. The
 * test-only capability injection applies only to reply word7/flag31 here. */
struct task3_phone_workload *task3_phone_workload_create_paired(
    struct task3_phone_callbacks,uint32_t epoch,uint32_t generation,
    uint32_t stream,uint32_t rate,int inject_cap3);
void task3_phone_workload_destroy(struct task3_phone_workload *);
/* One private 128-frame stereo buffer, no overwrite or hidden software queue.
 * Returns 1 only when ready and empty; 0 leaves the caller's block untouched.
 * Every frame has the provided signed left/right values for wire comparison. */
int task3_phone_workload_enqueue128(struct task3_phone_workload *,int16_t left,int16_t right);
/* Exactly four real runtime_pass calls, decode allowed on the first pass as in
 * worker_media_main's firmware pump. Native C execution consumes zero model
 * time except inside callbacks; this is an optimistic CPU scheduling model. */
void task3_phone_workload_pump(struct task3_phone_workload *);
/* Revoke the injected session through the real runtime cancellation path. */
void task3_phone_workload_cancel(struct task3_phone_workload *);
void task3_phone_workload_snapshot(const struct task3_phone_workload *,struct task3_phone_stats *);

#ifdef __cplusplus
}
#endif
#endif
