/* End-to-end wire -> bounded frame queue -> actual Apache OI SBC decoder. */
#define main classic_wire_main
#include "ae350_classic_fixture.c"
#undef main
#include "sbc_decoder_service.h"
int main(int argc,char **argv) {
    uint8_t data[8192],packet[672],config[]={4,8,1,0,7,6,0,0,0,0,2,53},sep=4;
    struct a138_classic_frame frame; struct a138_sbc_decoder decoder;
    struct a138_sbc_format format; struct a138_sbc_pcm result;
    int16_t pcm[A138_SBC_MAX_PCM_SAMPLES]; size_t n,offset=0; unsigned seq=0,decoded=0;
    FILE *in,*out;
    CHECK(argc==3); in=fopen(argv[1],"rb"); CHECK(in!=0);
    n=fread(data,1,sizeof data,in); CHECK(n>=4 && n<sizeof data && !ferror(in)); CHECK(fclose(in)==0);
    CHECK(data[0]==0x9c && (data[1]>>6)>=2u);
    config[8]=(uint8_t)(((data[1]>>6)==2u ? 0x20u : 0x10u)|(8u>>((data[1]>>2)&3u)));
    config[9]=(uint8_t)((0x80u>>((data[1]>>4)&3u))|(data[1]&1u ? 4u : 8u)|(data[1]&2u ? 2u : 1u));
    reset(); channel(1,0x70,672);
    CHECK(command(3,config,sizeof config)==6 && s.state==A138_CLASSIC_CONFIGURED);
    CHECK(command(6,&sep,1)==6); channel(2,0x71,672);
    CHECK(a138_classic_audio_ready(&s,1,9,s.format.rate_hz,1)==A138_CLASSIC_OK);
    CHECK(command(7,&sep,1)==6); a138_sbc_init(&decoder);
    format.rate_hz=s.format.rate_hz; format.mode=s.format.mode; format.blocks=s.format.blocks;
    format.subbands=s.format.subbands; format.allocation=s.format.allocation;
    format.min_bitpool=s.format.min_bitpool; format.max_bitpool=s.format.max_bitpool;
    CHECK(a138_sbc_begin(&decoder,s.stream_epoch,&format)==A138_SBC_OK);
    out=fopen(argv[2],"wb"); CHECK(out!=0);
    while (offset<n) {
        uint16_t bytes;
        /* Independently derive SBC frame length from the negotiated format. */
        unsigned mode=(data[offset+1]>>2)&3u,sub=s.format.subbands,blocks=s.format.blocks;
        unsigned audio=blocks*data[offset+2]*(mode==1u ? 2u : 1u)+(mode==3u ? sub : 0u);
        bytes=(uint16_t)(4u+(4u*sub*(mode ? 2u : 1u))/8u+(audio+7u)/8u);
        CHECK(bytes<=224 && offset+bytes<=n);
        unsigned size=rtp(packet,seq++,1,data+offset,bytes);
        CHECK(pdu(0x42,packet,size,17+(seq%47))==A138_CLASSIC_OK);
        CHECK(a138_classic_frame_pop(&s,&frame)==A138_CLASSIC_OK);
        CHECK(frame.bytes==bytes && frame.stream_epoch==decoder.last_epoch && !memcmp(frame.data,data+offset,bytes));
        CHECK(a138_sbc_decode(&decoder,frame.stream_epoch,frame.data,frame.bytes,pcm,256,&result)==A138_SBC_OK && result.valid);
        for (unsigned j=0;j<result.scalar_samples;++j) {
            uint16_t v=(uint16_t)pcm[j]; CHECK(fputc(v&255u,out)!=EOF && fputc(v>>8,out)!=EOF);
        }
        offset+=bytes; ++decoded;
    }
    CHECK(fclose(out)==0 && decoded>=1);
    fprintf(stderr,"wire->queue->SBC: %u frames, %u checks, rate=%u mode=%u\n",decoded,checks,s.format.rate_hz,s.format.mode);
    return 0;
}
