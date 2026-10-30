#include "ble_business_owner.h"
enum {IDLE=0,ENGINE=1,PUBLISH=2,OBSERVE=3,INSPECT=4};
enum {BUSY=0x82,BAD_ARG=0x81,BAD_STATE=0x83,NOT_FOUND=0x88,RANGE=0x89,BAD_TRANSFER=0x8d};
static uint32_t word(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint64_t wide(const uint8_t *p) {return word(p)|((uint64_t)word(p+4)<<32);}
static void put(uint8_t *p,uint32_t x) {for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static void zero(void *p,unsigned n) {uint8_t *b=p;for(unsigned i=0;i<n;i++)b[i]=0;}
static void copy(void *to,const void *from,unsigned n) {
    uint8_t *d=to;const uint8_t *s=from;for(unsigned i=0;i<n;i++)d[i]=s[i];
}
static int is_open(uint32_t op) {
    return op==0x30 || op==0x36 || op==0x37 || op==0x38 || op==0x39 ||
        op==0x3b || op==0x3c || op==0x3d || op==0x40;
}
static int is_read(uint32_t op) {
    return op==0x31 || op==0x35 || op==0x3e || op==0x3f || op==0x41 || op==0x42;
}
static int read_combined(uint32_t op) {return op==0x35 || op==0x3f || op==0x42;}
static int read_second(uint32_t op) {return op==0x41 || op==0x42;}
static int read_lossless(uint32_t op) {return op==0x3e || op==0x3f || read_second(op);}
static unsigned transfer_limit(const a138_ble_transfer *t,int replay) {
    if(t->mode==0x3c || t->mode==0x3d || t->mode==0x40)return t->extended_limit;
    if(t->mode==0x3b)return 972;
    return t->mode==0x30 && !replay ? 256:460;
}
static void expire_transfer(a138_ble_transfer *t) {
    t->open=0;t->pending=0;t->last_ack_valid=0;t->flags=0;t->mode=0;t->extended_limit=0;
}
static int has_object(const a138_ble_business_owner *o) {
    return wide(o->request.payload)==o->context.boot_id && o->facts.object_id &&
        word(o->request.payload+8)==o->facts.object_id;
}
static void reply(a138_ble_business_owner *o,unsigned status,unsigned length) {
    o->completion_status=status;o->completion_length=length;
    o->completion_phase=status&128u ? A138_BM_FAILED:A138_BM_APPLIED;
    o->phase=PUBLISH;
}
static void reject(a138_ble_business_owner *o,unsigned status) {
    zero(o->completion_payload,64);put(o->completion_payload+4,1);reply(o,status,8);
}
static int free_task(const a138_ble_business_owner *o) {
    const a138_ble_task *t=&o->tasks[o->operation_counter&7u];
    return !t->valid || (t->state!=1 && (uint32_t)(o->facts.time_ms-t->time_ms)>=60000u);
}
static void update_tasks(a138_ble_business_owner *o) {
    unsigned state=o->facts.state&255u;
    for(unsigned i=0;i<8;i++) {
        a138_ble_task *t=&o->tasks[i];
        if(!t->valid || t->state!=1 || t->recording_id!=o->facts.object_id)continue;
        if(t->opcode==0x20 && o->facts.frames!=0) {
            t->state=2;t->time_ms=o->facts.first_ms;
        } else if(state==5 || (state==4 && t->opcode==0x20)) {
            t->state=3;t->error=BAD_STATE;t->time_ms=o->facts.terminal_ms;
        } else if(t->opcode==0x21 && state==4) {
            t->state=2;t->time_ms=t->opcode==0x20 ? o->facts.first_ms:o->facts.terminal_ms;
        }
    }
}
static void get_object(a138_ble_business_owner *o) {
    const a138_record_data_facts *f=&o->facts;unsigned state=f->state&255u;
    zero(o->completion_payload,64);
    put(o->completion_payload,(uint32_t)o->context.boot_id);
    put(o->completion_payload+4,(uint32_t)(o->context.boot_id>>32));
    put(o->completion_payload+8,f->object_id);o->completion_payload[12]=(uint8_t)state;
    o->completion_payload[13]=1;o->completion_payload[14]=2;
    o->completion_payload[15]=(uint8_t)(o->transfer.open*4u+(state==4)*2u+(state==5));
    put(o->completion_payload+16,48000);put(o->completion_payload+20,f->frames);
    put(o->completion_payload+24,f->frames*4u);put(o->completion_payload+28,16384);
    put(o->completion_payload+32,state==4 ? f->crc:0);
    o->completion_payload[36]=(uint8_t)f->reason;o->completion_payload[37]=(uint8_t)(f->reason>>8);
    put(o->completion_payload+40,o->current_operation);reply(o,0,48);
}
static void start_engine(a138_ble_business_owner *o) {
    if(o->command_sequence==UINT32_MAX) {reject(o,BUSY);return;}
    a138_record_data_command c={0};
    c.sequence=o->command_sequence+1u;c.object_id=o->pending_object;
    c.transfer_id=o->active_read ? word(o->request.payload):0;c.request_id=o->request.request_id;
    c.opcode=o->active_read ? 0x31:o->request.opcode;
    c.length=o->active_read ? 12:o->request.length;c.nonce=o->request.nonce;
    if(o->active_read)c.flags=(o->transfer.flags&7u)|(read_lossless(o->request.opcode)?8u:0u)|(read_second(o->request.opcode)?16u:0u);
    copy(c.payload,o->request.payload,16);
    o->submission_ms=o->facts.time_ms;
    int result=a138_record_data_submit(&o->data,&c);
    if(result==A138_DATA_IO) {o->fault=A138_OWNER_SUBMIT_IO;return;}
    o->command_sequence=c.sequence;o->phase=ENGINE;
    /* A lost final ACK is not retried. ENGINE polls the exact sequence. */
}
static void dispatch(a138_ble_business_owner *o) {
    unsigned op=o->request.opcode,len=o->request.length,state=o->facts.state&255u;
    const uint8_t *p=o->request.payload;
    zero(o->completion_payload,64);o->pending_operation=0;o->pending_object=0;o->pending_transfer=0;
    o->active_read=0;o->active_replay=0;
    if(op==4) {
        if(len!=4) {reject(o,BAD_ARG);return;}
        uint32_t id=word(p);a138_ble_task *t=&o->tasks[(id-1u)&7u];
        if(!t->valid || t->id!=id) {reject(o,NOT_FOUND);return;}
        put(o->completion_payload,t->id);put(o->completion_payload+4,t->request_id);
        o->completion_payload[8]=t->opcode;o->completion_payload[9]=t->state;
        o->completion_payload[10]=t->error;put(o->completion_payload+12,1);
        put(o->completion_payload+16,t->recording_id);reply(o,0,20);return;
    }
    if(op==0x22) {
        if(len!=4) {reject(o,BAD_ARG);return;}
        if(word(p)!=0 && word(p)!=o->facts.object_id) {reject(o,NOT_FOUND);return;}
        get_object(o);return;
    }
    if(op==0x20) {
        if(len!=8 || word(p)!=1) {reject(o,BAD_ARG);return;}
        if(o->facts.state&(1u<<11)) {reject(o,BUSY);return;}
        if(!(o->facts.state&(1u<<10)) || state!=0) {reject(o,BAD_STATE);return;}
        if(word(p+4)>16384) {reject(o,RANGE);return;}
        if(!free_task(o) || o->operation_counter==UINT32_MAX || o->object_counter==UINT32_MAX) {reject(o,BUSY);return;}
        o->pending_object=o->object_counter+1u;o->pending_operation=o->operation_counter+1u;
    } else if(op==0x21) {
        if(len!=12) {reject(o,BAD_ARG);return;}
        if(!has_object(o)) {reject(o,NOT_FOUND);return;}
        if(o->facts.state&(1u<<11)) {reject(o,BUSY);return;}
        if(state!=2) {reject(o,BAD_STATE);return;}
        if(!free_task(o) || o->operation_counter==UINT32_MAX) {reject(o,BUSY);return;}
        o->pending_object=o->facts.object_id;o->pending_operation=o->operation_counter+1u;
    } else if(op==0x23) {
        if(len!=12) {reject(o,BAD_ARG);return;}
        if(!has_object(o)) {reject(o,NOT_FOUND);return;}
        if((o->facts.state&(1u<<11)) || o->transfer.open) {reject(o,BUSY);return;}
        if(state!=4 && state!=5) {reject(o,BAD_STATE);return;}
    } else if(is_open(op)) {
        if(len!=16) {reject(o,BAD_ARG);return;}
        if(!has_object(o)) {reject(o,NOT_FOUND);return;}
        if(state!=4 || !(o->facts.state&(1u<<15))) {reject(o,BAD_STATE);return;}
        if(o->transfer.open || (o->facts.state&(1u<<12)) || o->transfer_counter==UINT32_MAX) {reject(o,BUSY);return;}
        uint32_t offset=word(p+12);
        if((offset&3u) || offset>o->facts.frames*4u) {reject(o,RANGE);return;}
        a138_ble_transfer *t=&o->transfer;zero(t,sizeof *t);
        t->id=++o->transfer_counter;t->object_id=o->facts.object_id;t->session=o->request.key.session;
        t->open=1;t->mode=(uint8_t)op;t->offset=offset;t->time_ms=o->facts.time_ms;
        t->flags=(op!=0x30 && op!=0x36 ? 1u:0u)|(op!=0x30 && op!=0x36 && op!=0x37 ? 2u:0u)|
            (op==0x39 || op==0x3b || op==0x3c || op==0x3d || op==0x40 ? 4u:0u)|
            (op==0x3d || op==0x40 ? 8u:0u)|(op==0x40 ? 16u:0u);
        unsigned limit=(uint16_t)(((uint16_t)(o->facts.att_limit-4u)<<6)-48u);
        t->extended_limit=limit>8112u ? 8112u:limit;
        put(o->completion_payload,t->id);put(o->completion_payload+4,o->facts.frames*4u);
        put(o->completion_payload+8,o->facts.crc);put(o->completion_payload+12,offset);
        limit=transfer_limit(t,0);o->completion_payload[16]=(uint8_t)limit;o->completion_payload[17]=(uint8_t)(limit>>8);
        o->completion_payload[18]=1;
        if(t->flags&2u) {o->completion_payload[20]=(uint8_t)o->facts.att_limit;o->completion_payload[21]=(uint8_t)(o->facts.att_limit>>8);}
        reply(o,0,(t->flags&2u)?24:20);return;
    } else if(is_read(op)) {
        a138_ble_transfer *t=&o->transfer;uint32_t offset=word(p+4),length=word(p+8)&65535u;
        int combined=read_combined(op),replay=o->request_facts.flags&1u;
        if(len!=(combined ? 16u:12u) || word(p+8)>>16) {reject(o,BAD_ARG);return;}
        if(read_second(op) && (!t->open || !(t->flags&16u))) {reject(o,BAD_TRANSFER);return;}
        if(read_lossless(op) && (!t->open || !(t->flags&8u))) {reject(o,BAD_TRANSFER);return;}
        if(replay) {
            if(length>transfer_limit(t,1)) {reject(o,BAD_TRANSFER);return;}
            if(state!=4 || o->request_facts.object_id!=o->facts.object_id) {reject(o,NOT_FOUND);return;}
            o->pending_object=o->request_facts.object_id;
        } else {
            if(!t->open || word(p)!=t->id) {reject(o,BAD_TRANSFER);return;}
            if((o->facts.state&(1u<<12)) || (!combined && t->pending)) {reject(o,BUSY);return;}
            if(combined && (!t->pending || offset!=t->pending_offset+t->pending_length || word(p+12)!=t->pending_crc)) {reject(o,BAD_TRANSFER);return;}
            if((!combined && offset!=t->offset) || length==0 || length>transfer_limit(t,0) ||
               (offset&3u) || (length&3u) || offset>=o->facts.frames*4u || length>o->facts.frames*4u-offset) {reject(o,RANGE);return;}
            o->pending_object=t->object_id;
        }
        o->active_read=1;o->active_replay=(uint8_t)replay;
    } else if(op==0x32) {
        a138_ble_transfer *t=&o->transfer;uint32_t offset=word(p+4),crc=word(p+8);
        if(len!=12) {reject(o,BAD_ARG);return;}
        if(!t->open || word(p)!=t->id) {reject(o,BAD_TRANSFER);return;}
        if(t->pending && offset==t->pending_offset+t->pending_length && crc==t->pending_crc) {
            t->offset=offset;t->pending=0;t->last_ack_valid=1;t->last_ack_offset=offset;t->last_ack_crc=crc;
        } else if(!t->last_ack_valid || offset!=t->last_ack_offset || crc!=t->last_ack_crc) {reject(o,BAD_TRANSFER);return;}
        t->time_ms=o->facts.time_ms;put(o->completion_payload,t->id);put(o->completion_payload+4,offset);reply(o,0,8);return;
    } else if(op==0x33 || op==0x34) {
        a138_ble_transfer *t=&o->transfer;
        if(len!=(op==0x33 ? 8u:4u)) {reject(o,BAD_ARG);return;}
        if(!t->open || word(p)!=t->id) {reject(o,BAD_TRANSFER);return;}
        if(op==0x33 && (t->pending || t->offset!=o->facts.frames*4u || word(p+4)!=o->facts.crc)) {reject(o,BAD_TRANSFER);return;}
        t->open=0;t->last_ack_valid=0;if(op==0x34)t->pending=0;
        put(o->completion_payload,t->id);reply(o,0,4);return;
    }
    start_engine(o);
}
static void engine_result(a138_ble_business_owner *o,const a138_record_data_result *r) {
    unsigned op=o->request.opcode;
    if(o->active_read) {
        a138_ble_transfer *t=&o->transfer;
        if(!o->active_replay && (r->flags&2u)) {
            uint32_t offset=word(o->request.payload+4),length=word(o->request.payload+8)&65535u;
            t->time_ms=r->time_ms;
            if(read_combined(op)) {
                t->offset=offset;t->pending=0;t->last_ack_valid=1;
                t->last_ack_offset=offset;t->last_ack_crc=word(o->request.payload+12);
            }
            if(r->flags&1u) {t->pending=1;t->pending_offset=offset;t->pending_length=length;t->pending_crc=r->crc;}
        }
        if(!(r->status&128u) && (r->length!=12 || r->flags!=3u ||
           word(r->payload)!=word(o->request.payload) || word(r->payload+4)!=word(o->request.payload+4) ||
           word(r->payload+8)!=(word(o->request.payload+8)&65535u))) {o->fault=A138_OWNER_RESULT_IDENTITY;return;}
    }
    if(r->status&128u) {reject(o,r->status);return;}
    if(op==0x20 || op==0x21) {
        a138_ble_task *t=&o->tasks[o->operation_counter&7u];
        t->id=o->pending_operation;t->request_id=o->request.request_id;
        t->recording_id=o->pending_object;t->time_ms=o->facts.time_ms;
        t->opcode=(uint8_t)op;t->state=1;t->error=0;t->valid=1;
        o->operation_counter=o->pending_operation;o->current_operation=t->id;
        if(op==0x20)o->object_counter=o->pending_object;
        update_tasks(o);zero(o->completion_payload,64);
        put(o->completion_payload,t->id);put(o->completion_payload+4,t->recording_id);
        reply(o,1,8);o->completion_phase=A138_BM_PENDING;
    } else {
        if(op==0x23)o->current_operation=0;
        copy(o->completion_payload,r->payload,48);reply(o,r->status,r->length);
    }
}
void a138_ble_business_init(a138_ble_business_owner *o,a138_business_bus mailbox,a138_record_bus data) {
    zero(o,sizeof *o);o->mailbox=mailbox;o->data=data;
}
void a138_ble_business_pump(a138_ble_business_owner *o) {
    if(!o || o->fault)return;
    a138_business_key context={0};
    if(a138_business_context(&o->mailbox,&context)!=A138_BM_OK)return;
    int fact_result=a138_record_data_poll(&o->data,&o->facts);
    if(fact_result==A138_DATA_NONE)return;
    if(fact_result!=A138_DATA_OK) {o->fault=A138_OWNER_FACT_IO;return;}
    if(o->facts.state&(1u<<9)) {o->fault=A138_OWNER_OBSERVER_LOST;return;}
    if(!o->bound) {
        if(!a138_record_data_probe(&o->data) || a138_business_probe(&o->mailbox)!=A138_BM_OK ||
           o->facts.object_id || o->facts.accepted_seq || o->facts.applied_seq) {o->fault=A138_OWNER_DIRTY_BOOT;return;}
        o->context=context;o->bound=1;
    } else if(context.boot_id!=o->context.boot_id || context.owner!=o->context.owner) {o->fault=A138_OWNER_CONTEXT_CHANGED;return;}
    update_tasks(o);
    if(o->transfer.open && (context.session!=o->transfer.session ||
       (uint32_t)(o->facts.time_ms-o->transfer.time_ms)>=30000u))expire_transfer(&o->transfer);
    if(o->phase==INSPECT) {
        if(context.session!=o->request.key.session) {o->phase=IDLE;return;}
        int status=a138_record_data_request_facts(&o->data,&o->request_facts);
        if(status==A138_DATA_IO) {o->fault=A138_OWNER_REQUEST_META_IO;return;}
        if(status==A138_DATA_OK && o->request_facts.ticket==o->request.key.ticket &&
           o->request_facts.owner==o->request.key.owner && o->request_facts.session==o->request.key.session &&
           o->request_facts.boot_id==o->request.key.boot_id && o->request_facts.flags<=1u) {dispatch(o);return;}
        if((uint32_t)(o->facts.time_ms-o->submission_ms)>=1000u)o->fault=A138_OWNER_REQUEST_META_UNOBSERVED;
        return;
    }
    if(o->phase==ENGINE) {
        a138_record_data_result result;
        int status=a138_record_data_result_read(&o->data,o->command_sequence,&result);
        if(status==A138_DATA_OK)engine_result(o,&result);
        else if(status==A138_DATA_IO)o->fault=A138_OWNER_RESULT_IO;
        else if(o->facts.accepted_seq!=o->command_sequence &&
            (uint32_t)(o->facts.time_ms-o->submission_ms)>=1000u)
            o->fault=A138_OWNER_SUBMIT_UNOBSERVED;
        return;
    }
    if(o->phase==PUBLISH) {
        a138_business_completion c={o->completion_phase,o->completion_status,o->pending_operation,
            o->completion_length,o->completion_payload};
        o->submission_ms=o->facts.time_ms;
        int result=a138_business_complete(&o->mailbox,&o->request.key,&c);
        if(result==A138_BM_OK || result==A138_BM_STALE)o->phase=IDLE;
        else if(result==A138_BM_COMMIT_UNCERTAIN)o->phase=OBSERVE;
        else o->fault=A138_OWNER_COMPLETE_IO;
        return;
    }
    if(o->phase==OBSERVE) {
        if(context.session!=o->request.key.session) {o->phase=IDLE;return;}
        a138_business_observation observation;
        int result=a138_business_observe(&o->mailbox,&o->request.key,&observation);
        if(result==A138_BM_OK && (observation.state==A138_BM_RESULT || observation.state==A138_BM_PUBLISHED))o->phase=IDLE;
        /* STALE is an advisory torn snapshot, not proof this key was retired. */
        else if(result==A138_BM_IO)o->fault=A138_OWNER_OBSERVE_IO;
        else if((uint32_t)(o->facts.time_ms-o->submission_ms)>=1000u)
            o->fault=A138_OWNER_COMPLETE_UNOBSERVED;
        return;
    }
    if(!o->opened || context.session!=o->context.session) {
        int result=a138_business_open(&o->mailbox,&context);
        if(result==A138_BM_OK) {o->context=context;o->opened=1;}
        else if(result==A138_BM_COMMIT_UNCERTAIN)o->fault=A138_OWNER_OPEN_UNCERTAIN;
        return;
    }
    int result=a138_business_read_request(&o->mailbox,&o->request);
    if(result==A138_BM_NONE || result==A138_BM_STALE)return;
    if(result!=A138_BM_OK) {o->fault=A138_OWNER_REQUEST_IO;return;}
    if(a138_business_claim(&o->mailbox,&o->request.key)!=A138_BM_OK) {o->fault=A138_OWNER_CLAIM_IO;return;}
    o->submission_ms=o->facts.time_ms;o->phase=INSPECT;
}
static a138_ble_business_owner firmware_owner;
void a138_ble_business_firmware_init(void) {
    a138_ble_business_init(&firmware_owner,a138_business_mmio_bus(A138_BLE_BUSINESS_BASE),
        a138_record_mmio_bus(A138_BLE_DATA_BASE));
}
void a138_ble_business_firmware_pump(void) {a138_ble_business_pump(&firmware_owner);}
