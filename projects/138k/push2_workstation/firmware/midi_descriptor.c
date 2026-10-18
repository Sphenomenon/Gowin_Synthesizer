#include "midi_descriptor.h"
int midi_find_input(const uint8_t *d, unsigned n, midi_input_t *out)
{
    unsigned p = 0;
    uint8_t in_midi = 0, iface = 0, alt = 0;
    midi_input_t found = {0};
    if (n < 9 || d[0] != 9 || d[1] != 2 ||
        (unsigned)(d[2] | d[3] << 8) != n || !d[5]) return -1;
    while (p < n) {
        if (n-p < 2 || d[p] < 2 || d[p] > n-p) return -1;
        unsigned size = d[p];
        if (d[p+1] == 4) {
            if (size < 9) return -1;
            iface = d[p+2]; alt = d[p+3];
            in_midi = alt == 0 && d[p+5] == 1 && d[p+6] == 3 && d[p+7] == 0;
        } else if (d[p+1] == 5) {
            if (size < 7) return -1;
            unsigned ep = d[p+2], mps = d[p+4] | d[p+5] << 8;
            if (in_midi && (ep & 0x80) && !(ep & 0x70) && (ep & 15) &&
                (d[p+3] & 3) == 2 && !found.endpoint) {
                if (!mps || mps > 512) return -1;
                found = (midi_input_t){d[5], iface, alt, ep, mps};
            }
        }
        p += size;
    }
    if (!found.endpoint) return 0;
    *out = found;
    return 1;
}

int push_find_outputs(const uint8_t *d, unsigned n, push_profile_t *out)
{
    midi_input_t midi;
    if (midi_find_input(d,n,&midi)!=1) return -1;
    push_profile_t f={0}; unsigned p=0; int type=0;
    while(p<n) {
        unsigned size=d[p];
        if(d[p+1]==4) {
            type=0;
            if(d[p+3]==0 && d[p+5]==0xff && d[p+6]==0xff && d[p+7]==0xff) type=1;
            if(d[p+3]==0 && d[p+5]==1 && d[p+6]==3 && d[p+7]==0 && d[p+2]==midi.interface_number) type=2;
        } else if(d[p+1]==5 && size>=7 && (d[p+3]&3)==2 && (d[p+2]&0xf0)==0 && (d[p+2]&15)) {
            unsigned mps=d[p+4]|d[p+5]<<8;
            if(type==1 && !f.display_out) {f.display_out=d[p+2];f.display_mps=mps;}
            if(type==2 && !f.midi_out) {f.midi_out=d[p+2];f.midi_mps=mps;}
        }
        p+=size;
    }
    if(f.display_out!=1 || f.midi_out!=2 || f.display_mps!=512 || f.midi_mps!=512 || midi.endpoint!=0x82 || midi.max_packet!=512) return 0;
    *out=f;return 1;
}
