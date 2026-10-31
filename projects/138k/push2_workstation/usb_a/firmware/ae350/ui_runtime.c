/* Minimal freestanding C support; volatile accesses prevent loop-to-libcall
 * folding when this file itself supplies the implementation. */
#include <stddef.h>
void *memset(void *destination,int value,size_t count) {
    volatile unsigned char *p=destination;
    for(size_t i=0;i<count;i++) p[i]=(unsigned char)value;
    return destination;
}
void *memcpy(void *destination,const void *source,size_t count) {
    volatile unsigned char *d=destination;
    const volatile unsigned char *s=source;
    for(size_t i=0;i<count;i++) d[i]=s[i];
    return destination;
}
#ifdef A138_CLASSIC_RUNTIME
int memcmp(const void *left,const void *right,size_t count) {
    const volatile unsigned char *a=left,*b=right;
    for(size_t i=0;i<count;i++)if(a[i]!=b[i])return a[i]<b[i]?-1:1;
    return 0;
}
#endif
