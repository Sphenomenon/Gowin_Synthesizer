// Real parser, sole C owner, physical CRC and native DDR components.
#define main original_business_regression_main
#include "ae350_ble_business_cosim.cpp"
#undef main

static void mismatch() {
    Harness h;h.trace=false;h.dut.pcm_run=0;
    for(unsigned k=0;k<8;k++)h.pump();
    h.check(!h.owner.bound && h.owner.fault && !h.dut.object_id && !h.dut.frames,
        "incompatible physical ABI cannot bind or allocate an object");
    std::puts("PASS incompatible recording ABI rejected before allocation");
}

#ifdef A138_BLE_RECORD_DUAL_RATE
static std::vector<uint8_t> object_id(uint32_t id) {
    std::vector<uint8_t> p;put(p,0x55667788);put(p,0x11223344);put(p,id);return p;
}
static std::vector<uint8_t> formats(uint32_t mask=3,uint32_t version=1) {
    std::vector<uint8_t> p;put(p,version);put(p,mask);return p;
}
static std::vector<uint8_t> start(uint32_t format,uint32_t frames) {
    std::vector<uint8_t> p;put(p,format);put(p,frames);return p;
}
static std::vector<uint8_t> pcm(uint32_t count) {
    std::vector<uint8_t> p;for(uint32_t i=0;i<count;i++)put(p,0x9e370b5au^(i*0x0010203u));return p;
}
int main(int argc,char **) {
    if(argc>1){mismatch();return 0;}
    Harness h;h.trace=false;h.dut.pcm_run=0;h.dut.test_source_format=2;
    h.dut.test_source_ready=1;h.dut.test_source_fault=0;h.cycle(64);
    std::vector<uint8_t> p;put(p,1);h.check(h.command(1,p)[1]==0,"actual HELLO");
    h.cycle(4096);for(unsigned k=0;k<8;k++)h.pump();
    h.check(h.owner.bound && !h.owner.fault && h.owner.facts.formats_mask==3,"C binds dual-rate ABI v4");
    h.check(h.command(0x20,start(2,441))[1]==0x81 && !h.owner.object_counter,
        "format2 requires a grant in this HELLO session");
    for(const auto bad:{formats(0),formats(2),formats(7),formats(3,0x10001),std::vector<uint8_t>(17,0)})
        h.check(h.command(0x43,bad)[1]==0x81 && !h.owner.format_grant_mask,
            "malformed optional format grant cannot authorize capture");
    auto grant=h.command(0x43,formats());const auto grant_id=word(grant,4);
    h.check(grant[1]==0 && grant.size()==36 && word(grant,16)==1 && word(grant,20)==3 &&
        word(grant,24)==0x55667788 && word(grant,28)==0x11223344,"REC_FORMATS matches Android v1 contract and boot");
    const auto sequence=h.owner.command_sequence;
    h.check(h.command(0x43,formats(1))[1]==0,"48k-only format query");
    h.check(h.command(0x43,formats(),grant_id)==grant && h.owner.format_grant_mask==3 &&
        h.owner.command_sequence==sequence,"cached grant stays valid without physical descriptor or revocation");
    h.dut.test_source_format=1;
    h.check(h.command(0x20,start(2,441))[1]==0x83 && !h.owner.object_counter && !h.dut.object_id,
        "requested44.1 cannot relabel actual48k source");
    h.dut.test_source_format=2;
    h.check(h.command(0x20,start(1,441))[1]==0x83 && !h.owner.object_counter,
        "legacy48k cannot relabel actual44.1 source");
    h.check(h.command(0x20,start(2,441))[1]==1 && h.dut.object_id==1,"one physical format2 object");
    h.dut.pcm_run=1;unsigned ticks=0;
    for(unsigned k=0;k<500000;k++){if(h.dut.source_pcm_valid_o)ticks++;h.cycle();}
    h.dut.pcm_run=0;h.cycle(64);
    h.until([&]{return h.dut.record_state==4;},"native44.1 READY");h.pump();
    h.check(ticks==441 && h.dut.frames==441 && h.dut.native_committed==441,
        "independent50MHz source delivers exactly441frames per10ms at44.1k");
    const auto expected=pcm(441);const auto object_crc=crc(expected);
    h.dut.test_source_format=1;p.clear();put(p,0);auto info=h.command(0x22,p);
    h.check(info[28]==4 && info[29]==2 && info[30]==2 && word(info,32)==44100 &&
        word(info,36)==441 && word(info,40)==1764 && word(info,48)==object_crc,
        "sealed descriptor retains actual44.1 format/rate and independent source CRC");
    p=object_id(1);put(p,0);auto opened=h.command(0x3d,p);const auto old_transfer=word(opened,16);
    h.check(opened[1]==0,"open actual format2 object");
    h.check(h.command(0x31,h.read_payload(old_transfer,0,1760))[1]==0,"download first440 frames");
    auto block=h.transfer_block();std::vector<uint8_t> downloaded(block.begin()+44,block.end()-4);
    h.check(downloaded==std::vector<uint8_t>(expected.begin(),expected.end()-4),"all initial44.1 PCM bytes come from DDR");
    // Disconnect before ACK. Grants and transfer leases retire; object facts do
    // not follow the new source rate or reset to the legacy descriptor.
    h.dut.enable=0;h.cycle(64);h.pump();h.dut.enable=1;h.cycle(64);h.next_id=1;
    p.clear();put(p,1);h.command(1,p);h.cycle(4096);for(unsigned k=0;k<8;k++)h.pump();
    h.check(!h.owner.format_grant_mask,"HELLO session change revokes format2 start grant");
    p.clear();put(p,0);auto retained=h.command(0x22,p);
    h.check(retained[29]==2 && word(retained,32)==44100 && word(retained,36)==441 &&
        word(retained,48)==object_crc,"same immutable object survives reconnect and source rate change");
    p.clear();put(p,old_transfer);put(p,1760);put(p,word(block,40));
    h.check(h.command(0x32,p)[1]==0x8d,"old pending ACK cannot revive a transfer lease");
    p=object_id(1);put(p,1760);opened=h.command(0x3d,p);const auto transfer=word(opened,16);
    h.check(opened[1]==0 && transfer==old_transfer+1,"new transfer resumes exact format2 object");
    h.check(h.command(0x31,h.read_payload(transfer,1760,4))[1]==0,"download partial final native beat");
    block=h.transfer_block();downloaded.insert(downloaded.end(),block.begin()+44,block.end()-4);
    h.check(downloaded==expected && crc(downloaded)==object_crc,"complete1764-byte object CRC after resumed download");
    p.clear();put(p,transfer);put(p,1764);put(p,word(block,40));h.check(h.command(0x32,p)[1]==0,"final ACK");
    p.clear();put(p,transfer);put(p,object_crc);h.check(h.command(0x33,p)[1]==0,"close same object");
    h.check(a138_ble_record_local_submit(&h.owner,0x23,0),"CPU clears BLE-created object through sole owner");
    a138_ble_local_record_result receipt{};
    h.until([&]{return a138_ble_record_local_poll(&h.owner,&receipt) && receipt.phase==A138_LOCAL_DONE;},"CPU raw clear");
    h.check(receipt.status==0 && !h.dut.object_id,"CPU clear applied to same physical object");
    h.dut.test_source_format=2;
    h.check(h.command(0x20,start(2,13))[1]==0x81 && h.owner.object_counter==1,
        "new session still requires fresh grant after CLEAR");
    h.check(!a138_ble_record_local_submit_format(&h.owner,0x20,13,3),"local format boundary");
    h.check(a138_ble_record_local_submit_format(&h.owner,0x20,1000,2),"trusted CPU requests actual44.1 on same owner");
    for(unsigned k=0;k<12;k++){h.pump();h.cycle(64);}
    h.check(a138_ble_record_local_poll(&h.owner,&receipt) && receipt.phase==A138_LOCAL_WAIT,
        "CPU START waits for actual PCM, not format descriptor");
    h.dut.pcm_run=1;h.until([&]{return h.dut.frames>=13;},"CPU13 real frames");h.dut.pcm_run=0;h.cycle(12);
    h.check(h.dut.frames==13 && a138_ble_record_local_submit(&h.owner,0x21,0),"CPU STOP sole format2 object");
    h.until([&]{return a138_ble_record_local_poll(&h.owner,&receipt) && receipt.phase==A138_LOCAL_DONE;},"CPU STOP native drain");
    h.check(receipt.status==0 && receipt.object_id==2 && receipt.frames==13 && receipt.committed==13 &&
        receipt.crc==crc(pcm(13)),"CPU STOP real format2 prefix/CRC/partial BL8");
    p.clear();put(p,0);info=h.command(0x22,p);
    h.check(info[29]==2 && word(info,32)==44100 && word(info,48)==receipt.crc,
        "BLE describes CPU-created actual44.1 object");
    h.check(h.command(0x23,object_id(2))[1]==0,"BLE clears CPU-created same object");
    h.check(h.command(0x43,formats())[1]==0,"renew current session grant");
    h.check(h.command(0x20,start(2,1000))[1]==1,"rate-fault object starts");
    h.dut.pcm_run=1;h.until([&]{return h.dut.frames>=12;},"rate-fault prefix");
    h.dut.test_source_format=1;h.cycle(32);const auto prefix=h.dut.frames;
    unsigned continued=0;for(unsigned k=0;k<50000;k++){if(h.dut.source_pcm_valid_o)continued++;h.cycle();}
    p.clear();put(p,0);info=h.command(0x22,p);
    h.check(info[28]==5 && info[29]==2 && word(info,32)==44100 && h.dut.frames==prefix && continued==48,
        "rate change faults only capture; source continues, failed object keeps original44.1 descriptor");
    p=object_id(3);put(p,0);h.check(h.command(0x30,p)[1]==0x83,"failed mixed-rate object cannot download");
    std::printf("PASS recording formats frames=441 bytes=1764 source_ticks=%u resumed_offset=1760 crc=%08x checks=%u\n",ticks,object_crc,h.checks);
    h.dut.final();return 0;
}
#else
int main(int,char **) {mismatch();return 0;}
#endif
