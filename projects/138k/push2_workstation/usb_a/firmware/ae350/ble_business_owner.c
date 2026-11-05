#include "ble_business_owner.h"
#ifdef A138_SINGLE_BLE_RECORDING
#define dispatch worker_record_dispatch
#endif
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
#ifdef A138_SINGLE_BLE_RECORDING
    if(o->active_local) {
        a138_ble_local_record_result *r=&o->local_record;
        r->status=status;r->operation_id=o->pending_operation;
        r->object_id=o->pending_object ? o->pending_object:r->object_id;
        r->phase=status==1 ? A138_LOCAL_WAIT:A138_LOCAL_DONE;
        o->active_local=0;o->phase=IDLE;return;
    }
#endif
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
#ifdef A138_BLE_RECORD_DUAL_RATE
    o->completion_payload[13]=(uint8_t)f->format_id;
    put(o->completion_payload+16,f->rate_hz);
#endif
    put(o->completion_payload+24,f->frames*4u);put(o->completion_payload+28,A138_BLE_RECORD_CAPACITY_FRAMES);
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
#ifdef A138_SINGLE_BLE_RECORDING
    /* Private physical descriptor flag; never set for external BLE requests. */
    if(o->active_local)c.flags=16u;
#endif
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
    if(op==0x43) {
        /* Existing optional REC_FORMATS v1 wire contract (Android). */
        if(len!=8 || word(p)!=1 || !(word(p+4)&1u) || (word(p+4)&~3u)) {reject(o,BAD_ARG);return;}
        uint32_t mask=1;
#ifdef A138_BLE_RECORD_DUAL_RATE
        mask=word(p+4)&o->facts.formats_mask;
        /* Grants accumulate within one HELLO session. Cached earlier replies
         * cannot revoke or resurrect a grant after a later query/reconnect. */
        o->format_grant_session=o->request.key.session;o->format_grant_mask|=mask;
#endif
        put(o->completion_payload,1);put(o->completion_payload+4,mask);
        put(o->completion_payload+8,(uint32_t)o->context.boot_id);
        put(o->completion_payload+12,(uint32_t)(o->context.boot_id>>32));
        reply(o,0,16);return;
    }
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
        uint32_t format=word(p);
        int format_allowed=format==1;
#ifdef A138_BLE_RECORD_DUAL_RATE
        if(format==2 && o->format_grant_session==o->request.key.session && (o->format_grant_mask&2u))format_allowed=1;
#ifdef A138_SINGLE_BLE_RECORDING
        if(o->active_local && format==2)format_allowed=1;
#endif
#endif
        if(len!=8 || !format_allowed) {reject(o,BAD_ARG);return;}
        if(o->facts.state&(1u<<11)) {reject(o,BUSY);return;}
        if(!(o->facts.state&(1u<<10)) || state!=0) {reject(o,BAD_STATE);return;}
        if(word(p+4)>A138_BLE_RECORD_CAPACITY_FRAMES) {reject(o,RANGE);return;}
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
#ifdef A138_SINGLE_BLE_RECORDING
#ifdef A138_BLE_RECORD_DUAL_RATE
int a138_ble_record_local_submit_format(a138_ble_business_owner *o,uint32_t opcode,uint32_t limit,uint32_t format) {
    if(format!=1 && !(opcode==0x20 && format==2))return 0;
#else
int a138_ble_record_local_submit(a138_ble_business_owner *o,uint32_t opcode,uint32_t limit) {
#endif
    if(!o || !o->bound || o->fault || o->phase!=IDLE || o->local_pending ||
       o->local_record.phase==A138_LOCAL_WAIT || o->local_record.token==UINT32_MAX ||
       (opcode!=0x20 && opcode!=0x21 && opcode!=0x23) ||
       (opcode==0x20 ? limit>A138_BLE_RECORD_CAPACITY_FRAMES:limit!=0))return 0;
    uint32_t token=o->local_record.token+1u;
    o->local_record=(a138_ble_local_record_result){.token=token,.opcode=opcode,
        .phase=A138_LOCAL_QUEUED,.status=1};
#ifdef A138_BLE_RECORD_DUAL_RATE
    o->local_format=format;
#endif
    o->local_limit=limit;o->local_pending=1;return 1;
}
#ifdef A138_BLE_RECORD_DUAL_RATE
int a138_ble_record_local_submit(a138_ble_business_owner *o,uint32_t opcode,uint32_t limit) {
    return a138_ble_record_local_submit_format(o,opcode,limit,1);
}
#endif
int a138_ble_record_local_poll(const a138_ble_business_owner *o,a138_ble_local_record_result *out) {
    if(!o || !out || !o->local_record.token)return 0;
    *out=o->local_record;
    if(out->phase!=A138_LOCAL_DONE && o->facts.object_id==out->object_id) {
        out->frames=o->facts.frames;out->committed=o->facts.committed;
        out->crc=(o->facts.state&255u)==4 ? o->facts.crc:0;
    }
    return 1;
}
static void local_record_update(a138_ble_business_owner *o) {
    a138_ble_local_record_result *r=&o->local_record;
    if(r->phase!=A138_LOCAL_WAIT || !r->operation_id)return;
    const a138_ble_task *t=&o->tasks[(r->operation_id-1u)&7u];
    if(t->valid && t->id==r->operation_id && t->state!=1) {
        r->phase=A138_LOCAL_DONE;r->status=t->state==2 ? 0:t->error;
        if(o->facts.object_id==r->object_id) {
            r->frames=o->facts.frames;r->committed=o->facts.committed;
            r->crc=(o->facts.state&255u)==4 ? o->facts.crc:0;
        }
    }
}
static void local_record_dispatch(a138_ble_business_owner *o) {
    a138_ble_local_record_result *r=&o->local_record;
    zero(&o->request,sizeof o->request);o->request.key=o->context;
    o->request.request_id=r->token;o->request.opcode=r->opcode;
    o->request.nonce=o->context.boot_id^((uint64_t)r->token<<32)^UINT64_C(0x4c4f43414c524543);
    if(!o->request.nonce)o->request.nonce=1;
    if(r->opcode==0x20) {
        o->request.length=8;put(o->request.payload,1);put(o->request.payload+4,o->local_limit);
#ifdef A138_BLE_RECORD_DUAL_RATE
        put(o->request.payload,o->local_format);
#endif
    } else {
        o->request.length=12;put(o->request.payload,(uint32_t)o->context.boot_id);
        put(o->request.payload+4,(uint32_t)(o->context.boot_id>>32));
        put(o->request.payload+8,o->facts.object_id);
    }
    r->object_id=o->facts.object_id;r->frames=o->facts.frames;
    r->committed=o->facts.committed;r->crc=(o->facts.state&255u)==4 ? o->facts.crc:0;
    o->active_local=1;o->local_pending=0;dispatch(o);
}
#endif
void a138_ble_business_pump(a138_ble_business_owner *o) {
    if(!o || o->fault)return;
    a138_business_key context={0};
    if(a138_business_context(&o->mailbox,&context)!=A138_BM_OK)return;
    int fact_result=a138_record_data_poll(&o->data,&o->facts);
    if(fact_result==A138_DATA_NONE)return;
    if(fact_result!=A138_DATA_OK) {o->fault=A138_OWNER_FACT_IO;return;}
    if(o->facts.state&(1u<<9)) {o->fault=A138_OWNER_OBSERVER_LOST;return;}
#ifdef A138_BLE_RECORD_DUAL_RATE
    if(o->facts.formats_mask!=3 || (o->facts.format_id!=1 && o->facts.format_id!=2) ||
       o->facts.rate_hz!=(o->facts.format_id==2 ? 44100u:48000u)) {o->fault=A138_OWNER_FORMAT_MISMATCH;return;}
    if(context.session!=o->format_grant_session) {
        o->format_grant_session=context.session;o->format_grant_mask=0;
    }
#endif
    if(!o->bound) {
        if(!a138_record_data_probe(&o->data) || a138_business_probe(&o->mailbox)!=A138_BM_OK ||
           o->facts.object_id || o->facts.accepted_seq || o->facts.applied_seq) {o->fault=A138_OWNER_DIRTY_BOOT;return;}
#if A138_BLE_RECORD_CAPACITY_FRAMES != 16384u
        /* Extended firmware must bind the actual configured physical engine;
         * never advertise a longer object while retaining a short backend. */
        uint32_t physical_capacity=0;
        if(!o->data.read(o->data.context,0x3cu,&physical_capacity) ||
           physical_capacity!=A138_BLE_RECORD_CAPACITY_FRAMES) {o->fault=A138_OWNER_CAPACITY_MISMATCH;return;}
#endif
        o->context=context;o->bound=1;
    } else if(context.boot_id!=o->context.boot_id || context.owner!=o->context.owner) {o->fault=A138_OWNER_CONTEXT_CHANGED;return;}
    update_tasks(o);
#ifdef A138_SINGLE_BLE_RECORDING
    local_record_update(o);
#endif
    if(o->transfer.open && (context.session!=o->transfer.session ||
       (uint32_t)(o->facts.time_ms-o->transfer.time_ms)>=30000u))expire_transfer(&o->transfer);
#ifdef A138_SINGLE_BLE_RECORDING
    if(o->local_pending && o->phase==IDLE) {local_record_dispatch(o);return;}
#endif
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
#ifdef A138_BLE_BUSINESS_DIAGNOSTICS
        if(result==A138_BM_OK)o->diagnostic_completed++;
#endif
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
#ifdef A138_SINGLE_BLE_RECORDING
    /* Boot context exists before a GATT session. Local REC remains available;
     * do not attempt OPEN with session zero and poison the sole owner. */
    if(!context.session)return;
#endif
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
#ifdef A138_BLE_BUSINESS_DIAGNOSTICS
    o->diagnostic_claimed++;
#endif
    o->submission_ms=o->facts.time_ms;o->phase=INSPECT;
}
static a138_ble_business_owner firmware_owner;
#ifdef A138_BLE_BUSINESS_DIAGNOSTICS
#include "audio_services.h"
static uint32_t diagnostic_pumps,diagnostic_ms,diagnostic_page,diagnostic_fault;
static void business_diagnostic(uint32_t page,uint32_t value) {
    const a138_ble_business_owner *o=&firmware_owner;
    uint32_t flags=o->bound|(o->opened<<1)|(o->phase<<2)|((uint32_t)o->transfer.open<<5)|
        ((uint32_t)o->transfer.pending<<6)|((uint32_t)o->active_read<<7);
    /* The second write atomically publishes the staged value and metadata.
     * C350 retains its existing CRC, held snapshot and UART scheduling. */
    a138_write(UINT32_C(0xf8000000),24,value);
    a138_write(UINT32_C(0xf8000000),28,UINT32_C(0xb5000000)|(o->fault<<16)|(page<<8)|flags);
}
static void business_diagnostic_step(void) {
    const a138_ble_business_owner *o=&firmware_owner;
    diagnostic_pumps++;
    if(o->fault!=diagnostic_fault || !o->bound) {
        if(o->fault!=diagnostic_fault || !(diagnostic_pumps&255u)) {
            diagnostic_fault=o->fault;business_diagnostic(0,diagnostic_pumps);
        }
        return;
    }
    /* UART emits C350 about once a second. Keep every page for 1.5 seconds;
     * no diagnostic operation waits or changes the business service cadence. */
    if((uint32_t)(o->facts.time_ms-diagnostic_ms)<1500u)return;
    diagnostic_ms=o->facts.time_ms;
    /* Interleave pump progress so a short capture need not await every page. */
    uint32_t value=0,page=(diagnostic_page&1u)?(diagnostic_page+1u)>>1:0;
    switch(page) {
    case 0:value=diagnostic_pumps;break;
    case 1:value=o->diagnostic_claimed;break;
    case 2:value=o->diagnostic_completed;break;
    case 3:value=o->request.request_id;break;
    case 4:value=o->request.opcode|(o->completion_status<<8)|(o->completion_phase<<16)|(o->completion_length<<24);break;
    case 5:value=o->operation_counter;break;
    case 6:value=o->object_counter;break;
    case 7:value=o->transfer_counter;break;
    case 8:value=o->command_sequence;break;
    case 9:value=o->transfer.offset;break;
    case 10:value=o->transfer.pending_offset;break;
    case 11:value=o->transfer.pending_length;break;
    case 12:value=o->facts.frames;break;
    case 13:value=o->facts.committed;break;
    case 14:value=o->facts.accepted_seq;break;
    case 15:value=o->facts.applied_seq;break;
    }
    business_diagnostic(page,value);
    if(++diagnostic_page==30u)diagnostic_page=0;
}
#endif
#ifdef A138_SINGLE_BLE_RECORDING
int a138_ble_record_firmware_submit(uint32_t opcode,uint32_t limit) {
    return a138_ble_record_local_submit(&firmware_owner,opcode,limit);
}
int a138_ble_record_firmware_facts(a138_record_data_facts *facts) {
    if(!facts || !firmware_owner.bound || firmware_owner.fault)return 0;
    *facts=firmware_owner.facts;return 1;
}
int a138_ble_record_firmware_poll(a138_ble_local_record_result *result) {
    return a138_ble_record_local_poll(&firmware_owner,result);
}
#endif
void a138_ble_business_firmware_init(void) {
    a138_ble_business_init(&firmware_owner,a138_business_mmio_bus(A138_BLE_BUSINESS_BASE),
        a138_record_mmio_bus(A138_BLE_DATA_BASE));
#ifdef A138_BLE_BUSINESS_DIAGNOSTICS
    diagnostic_pumps=0;diagnostic_ms=0;diagnostic_page=0;diagnostic_fault=0;
    business_diagnostic(0,0);
#endif
}
void a138_ble_business_firmware_pump(void) {
    a138_ble_business_pump(&firmware_owner);
#ifdef A138_BLE_BUSINESS_DIAGNOSTICS
    business_diagnostic_step();
#endif
}
