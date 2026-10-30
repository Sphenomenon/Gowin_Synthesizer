#include "audio_clock_service.h"
#include "audio_services.h"

static int mmio_read(void *context, uint32_t offset, uint32_t *value) {
    *value=a138_read((uintptr_t)context,offset);
    return 1;
}
static int mmio_write(void *context, uint32_t offset, uint32_t value) {
    a138_write((uintptr_t)context,offset,value);
    return 1;
}
a138_clock_bus a138_clock_mmio_bus(uintptr_t base) {
    a138_clock_bus bus={(void *)base,mmio_read,mmio_write};
    return bus;
}
static int valid_bus(const a138_clock_bus *bus) {
    return bus && bus->read && bus->write;
}
a138_clock_result a138_clock_probe(const a138_clock_bus *bus) {
    uint32_t id,capabilities;
    if(!valid_bus(bus)) return A138_CLK_INVALID;
    if(!bus->read(bus->context,A138_CLK_ID,&id) ||
       !bus->read(bus->context,A138_CLK_CAPABILITIES,&capabilities)) return A138_CLK_IO_ERROR;
    /* This entry requires the user-selected seal/stop policy. Old busy-reject
     * firmware remains distinguishable and cannot silently implement it. */
    return id==UINT32_C(0x434c4b01) && (capabilities>>16)==1u &&
           (capabilities&0x17u)==0x17u ? A138_CLK_SUBMITTED:A138_CLK_UNSUPPORTED;
}
a138_clock_result a138_clock_submit(const a138_clock_bus *bus, uint32_t operation,
                                    a138_clock_ticket *ticket) {
    uint32_t status,before,after,again,epoch,context;
    if(!ticket || operation>A138_CLK_RECOVER) return A138_CLK_INVALID;
    a138_clock_result probe=a138_clock_probe(bus);
    if(probe!=A138_CLK_SUBMITTED) return probe;
    if(!bus->read(bus->context,A138_CLK_STATUS,&status)) return A138_CLK_IO_ERROR;
    if(!(status&8u) || (status&16u)) return A138_CLK_UNARMED;
    if(status&3u) return A138_CLK_PENDING;
    if(!bus->read(bus->context,A138_CLK_COMMAND_ID,&before) ||
       !bus->write(bus->context,A138_CLK_COMMAND,operation) ||
       !bus->read(bus->context,A138_CLK_COMMAND_ID,&after) ||
       !bus->read(bus->context,A138_CLK_EXPECTED_EPOCH,&epoch) ||
       !bus->read(bus->context,A138_CLK_REQUEST_CONTEXT,&context) ||
       !bus->read(bus->context,A138_CLK_COMMAND_ID,&again)) return A138_CLK_IO_ERROR;
    uint32_t next=before==UINT32_MAX ? 1u:before+1u;
    if(after!=next || again!=after) return A138_CLK_REJECTED;
    if((context&3u)!=(operation==A138_CLK_RECOVER ? 2u|(context&1u):operation))
        return A138_CLK_REJECTED;
    *ticket=(a138_clock_ticket){after,epoch,(context&1u)?44100u:48000u};
    return A138_CLK_SUBMITTED;
}
a138_clock_result a138_clock_poll(const a138_clock_bus *bus,
                                  const a138_clock_ticket *ticket,
                                  a138_clock_status *status) {
    uint32_t command,command_again,result,result_again,actual;
    a138_clock_status sample={0};
    if(!valid_bus(bus) || !ticket || !ticket->command_id || !status ||
       (ticket->expected_rate_hz!=48000u && ticket->expected_rate_hz!=44100u)) return A138_CLK_INVALID;
    if(!bus->read(bus->context,A138_CLK_COMMAND_ID,&command) ||
       !bus->read(bus->context,A138_CLK_RESULT_ID,&result) ||
       !bus->read(bus->context,A138_CLK_RESULT_CODE,&sample.result_code) ||
       !bus->read(bus->context,A138_CLK_RESULT_DETAIL,&sample.detail) ||
       !bus->read(bus->context,A138_CLK_STATUS,&sample.phase) ||
       !bus->read(bus->context,A138_CLK_MEDIA_STATUS,&sample.media_status) ||
       !bus->read(bus->context,A138_CLK_MEDIA_FAILURE,&sample.media_failure) ||
       !bus->read(bus->context,A138_CLK_ACTUAL,&actual) ||
       !bus->read(bus->context,A138_CLK_SNAPSHOT_EPOCH,&sample.actual_epoch) ||
       !bus->read(bus->context,A138_CLK_RESULT_ID,&result_again) ||
       !bus->read(bus->context,A138_CLK_COMMAND_ID,&command_again)) return A138_CLK_IO_ERROR;
    sample.phase&=3u;
    sample.actual_rate_hz=(actual&1u)?44100u:48000u;
    if(command!=ticket->command_id || command_again!=command) return A138_CLK_SUPERSEDED;
    if(result_again!=result) return A138_CLK_PENDING;
    sample.command_id=command;sample.result_id=result;
    *status=sample;
    if(result!=ticket->command_id || sample.phase) return A138_CLK_PENDING;
    if(sample.result_code!=A138_CLK_RESULT_APPLIED) return A138_CLK_FAILED;
    if(!(actual&2u) || (actual&0x34u) || sample.actual_epoch!=ticket->expected_epoch ||
       sample.actual_rate_hz!=ticket->expected_rate_hz) return A138_CLK_CONTEXT_LOST;
    return A138_CLK_APPLIED;
}
