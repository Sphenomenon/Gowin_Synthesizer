// Reuse the real protocol/APB/C-owner driver; only PCM cadence is accelerated.
#define main original_business_regression_main
#include "ae350_ble_business_cosim.cpp"
#undef main

static std::vector<uint8_t> expected_pcm(uint32_t frames) {
    std::vector<uint8_t> result;result.reserve(size_t(frames)*4);
    for(uint32_t at=0;at<frames;at++)put(result,0x9e370b5au^(at*0x0010203u));
    return result;
}
int main(int argc,char **) {
    Harness h;h.trace=false;h.dut.pcm_run=0;h.dut.enable=0;h.cycle(64);
    for(unsigned k=0;k<8;k++)h.pump();
    if(argc>1) {
    h.check(!h.owner.bound && h.owner.fault==A138_OWNER_CAPACITY_MISMATCH,
        "configured C capacity cannot bind mismatched physical backend");
    std::puts("PASS capacity mismatch fails before object allocation");return 0;
    }
    constexpr uint32_t capacity=A138_BLE_RECORD_CAPACITY_FRAMES;
    static_assert(capacity==2880000,"test is the complete 60s format-1 object");
    h.check(h.owner.bound && !h.owner.fault && !h.owner.opened,"extended owner binds before GATT");
    h.check(!a138_ble_record_local_submit(&h.owner,0x20,capacity+1),"local capacity upper bound");
    h.check(a138_ble_record_local_submit(&h.owner,0x20,0),"CPU starts the sole long object");
    for(unsigned k=0;k<12;k++){h.pump();h.cycle(64);}
    a138_ble_local_record_result receipt{};
    h.check(a138_ble_record_local_poll(&h.owner,&receipt) && receipt.phase==A138_LOCAL_WAIT && !h.dut.frames,
        "long START still waits for actual first PCM frame");
    h.dut.pcm_run=1;
    h.until([&]{return h.dut.record_state==4;},"all 2880000 actual CRC/native frames",capacity*9);
    h.dut.pcm_run=0;h.pump();
    h.check(h.dut.frames==capacity && h.dut.native_committed==capacity,"full long object native committed prefix");
    h.check(h.dut.native_writes==capacity/8,"full object exact BL8 writes");
    h.check(h.dut.max_native_address==TASK3_RECORD_BASE+capacity-8,"last native beat excludes reservation padding");
    const auto pcm=expected_pcm(capacity);const uint32_t object_crc=crc(pcm);
    h.dut.enable=1;h.cycle(64);std::vector<uint8_t> p;put(p,1);h.command(1,p);h.cycle(4096);
    p.clear();put(p,0);auto info=h.command(0x22,p);
    h.check(info[1]==0 && word(info,24)==1 && info[28]==4 && word(info,32)==48000 &&
        word(info,36)==capacity && word(info,40)==capacity*4 && word(info,44)==capacity &&
        word(info,48)==object_crc,"BLE GET exposes same full CPU object/format/capacity/CRC");
    p=h.object();put(p,0);auto opened=h.command(0x3d,p);const uint32_t transfer=word(opened,16);
    h.check(opened[1]==0 && (word(opened,32)&65535)==8112,"long object uses unchanged bounded download window");
    uint32_t offset=0,blocks=0;std::vector<uint8_t> downloaded;downloaded.reserve(pcm.size());
    while(offset<pcm.size()) {
        const uint32_t length=std::min<uint32_t>(8112,uint32_t(pcm.size())-offset);
        h.check(h.command(0x31,h.read_payload(transfer,offset,length))[1]==0,"long READ admission");
        auto block=h.transfer_block();
        h.check(word(block,32)==offset && (word(block,36)&65535)==length,"long DATA exact offset/length");
        std::vector<uint8_t> actual(block.begin()+44,block.end()-4);
        h.check(actual.size()==length && std::equal(actual.begin(),actual.end(),pcm.begin()+offset),"every downloaded PCM byte is real DDR data");
        h.check(word(block,40)==crc(actual),"each long block real PCM CRC");
        downloaded.insert(downloaded.end(),actual.begin(),actual.end());offset+=length;blocks++;
        p.clear();put(p,transfer);put(p,offset);put(p,word(block,40));
        h.check(h.command(0x32,p)[1]==0,"long block ACK advances same C lease");
    }
    h.check(downloaded==pcm && crc(downloaded)==object_crc,"full 11520000-byte download/object CRC");
    h.check(h.command(0x31,h.read_payload(transfer,offset,4))[1]==0x89,"object end cannot address allocation padding");
    p.clear();put(p,transfer);put(p,object_crc);h.check(h.command(0x33,p)[1]==0,"complete long object CLOSE");
    h.check(h.command(0x23,h.object())[1]==0 && h.dut.object_id==0,"BLE clears the CPU-created long object");
    p.clear();put(p,1);put(p,capacity+1);
    h.check(h.command(0x20,p)[1]==0x89 && h.owner.object_counter==1,"external capacity bound matches local and cannot allocate");

    // Explicit STOP is independent of the full-capacity automatic close.
    // A 13-frame object also exercises partial final BL8 masks and real drain.
    const uint32_t writes_before=h.dut.native_writes;
    p.clear();put(p,1);put(p,capacity);
    h.check(h.command(0x20,p)[1]==1,"external START admits the same configured long limit");
    h.dut.pcm_run=1;
    for(unsigned k=0;k<1024 && h.dut.frames<13;k++)h.cycle();
    h.dut.pcm_run=0;h.cycle(8);h.pump();
    h.check(h.dut.frames==13,"partial-stop fixture actual thirteen full frames");
    h.dut.test_native_pause=1;
    h.check(a138_ble_record_local_submit(&h.owner,0x21,0),"CPU STOP same owner");
    for(unsigned k=0;k<16;k++){h.pump();h.cycle(64);}
    h.check(a138_ble_record_local_poll(&h.owner,&receipt) && receipt.phase==A138_LOCAL_WAIT &&
        h.dut.record_state==3 && h.dut.native_committed==8,"STOP cannot finish before actual partial native accept");
    h.dut.test_native_pause=0;
    h.until([&]{return a138_ble_record_local_poll(&h.owner,&receipt) && receipt.phase==A138_LOCAL_DONE;},"STOP real native READY");
    const auto short_pcm=expected_pcm(13);
    h.check(receipt.status==0 && receipt.object_id==2 && receipt.frames==13 && receipt.committed==13 &&
        receipt.crc==crc(short_pcm) && h.dut.native_writes==writes_before+2,"STOP exact partial object/CRC/native count");
    p.clear();put(p,0x55667788);put(p,0x11223344);put(p,2);put(p,0);
    opened=h.command(0x30,p);uint32_t short_transfer=word(opened,16);
    h.check(opened[1]==0 && short_transfer==2,"BLE opens the actual replacement object2");
    h.check(h.command(0x31,h.read_payload(short_transfer,0,52))[1]==0,"partial object BLE READ");
    auto block=h.transfer_block();
    h.check(std::vector<uint8_t>(block.begin()+44,block.end()-4)==short_pcm,"partial final BL8 excludes stale long-object tail");
    std::printf("PASS long single recording frames=%u bytes=%zu blocks=%u checks=%u crc=%08x last_native=%08x\n",
        capacity,downloaded.size(),blocks,h.checks,object_crc,TASK3_RECORD_BASE+capacity-8);
    return 0;
}
