/* Compiled with the same RV32 compiler/headers, deliberately never linked.
 * Symbol sizes independently expose this ABI without host sizeof guesses. */
#include "classic_service.h"
#include "sbc_decoder_service.h"

struct abi_pcm_slot { int16_t pcm[A138_SBC_MAX_PCM_SAMPLES]; struct a138_sbc_pcm result; };
uint8_t abi_classic[sizeof(struct a138_classic_service)];
uint8_t abi_decoder[sizeof(struct a138_sbc_decoder)];
uint8_t abi_frame[sizeof(struct a138_classic_frame)];
uint8_t abi_tx[sizeof(struct a138_classic_tx)];
uint8_t abi_packet[A138_CLASSIC_ACL_BYTES];
uint8_t abi_pcm[4*sizeof(struct abi_pcm_slot)];
uint8_t abi_pcm_slot[sizeof(struct abi_pcm_slot)];
uint8_t abi_u32[sizeof(uint32_t)];
