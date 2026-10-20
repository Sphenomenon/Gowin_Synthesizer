package cn.gowin.control.protocol

import org.junit.Assert.*
import org.junit.Test

class PcmRiceTest {
    @Test fun handWrittenVectorsAndStereoPredictors() {
        // Two zero residuals: 0+9 bits per sample, four zero pad bits.
        assertArrayEquals(ByteArray(4),PcmRice.decode(byteArrayOf(0,0,0),4,10))
        // L+1 (zigzag2), R0 => 0000000010 0000000000 0000.
        assertArrayEquals(byteArrayOf(1,0,0,0),PcmRice.decode(hexBytes("008000"),4,10))
        // Constant independent channels: L1,R-1, then delta0/delta0.
        assertArrayEquals(hexBytes("0100ffff0100ffff"),PcmRice.decode(hexBytes("0080100000"),8,10))
        val zeros=ByteArray(5070) // 4056 samples, each10bits.
        assertArrayEquals(ByteArray(8112),PcmRice.decode(zeros,8112,10))
        val raw=hexBytes("0080ff7f");assertArrayEquals(raw,PcmRice.decode(raw,4,0))
    }
    @Test fun malformedAndNoncanonicalDataIsBounded() {
        for(bytes in listOf(byteArrayOf(),byteArrayOf(0),hexBytes("00000000"),hexBytes("000001"),hexBytes("ffff0000000000"))) {
            assertThrows(ProtocolException::class.java){PcmRice.decode(bytes,4,10)}
        }
        assertThrows(ProtocolException::class.java){PcmRice.decode(byteArrayOf(0),4,11)}
        assertThrows(ProtocolException::class.java){PcmRice.decode(ByteArray(4),3,0)}
        assertThrows(ProtocolException::class.java){PcmRice.decode(ByteArray(3),4,0)}
        // Fifteen unary ones followed by value0 is a forbidden short escape.
        assertThrows(ProtocolException::class.java){PcmRice.decode(hexBytes("fffe000000"),8,10)}
    }
    @Test fun compressedBlocksRequireExplicitPermissionAndDecodedCrc() {
        val pcm=ByteArray(8112)
        fun block(codec:Int=10,crc:Long=crc32(pcm))=Writer().u32(7).u64(1uL).u32(2).u32(0).u16(pcm.size).u8(codec).u8(0).u32(crc).bytes(ByteArray(5070)).build()
        assertThrows(ProtocolException::class.java){PcmBlock.decode(block(),8112)}
        assertArrayEquals(pcm,PcmBlock.decode(block(),8112,allowLossless=true).data)
        assertThrows(ProtocolException::class.java){PcmBlock.decode(block(crc=0),8112,true)}
        assertThrows(ProtocolException::class.java){PcmBlock.decode(block(codec=11),8112,true)}
        val reserved=block();reserved[23]=1
        assertThrows(ProtocolException::class.java){PcmBlock.decode(reserved,8112,true)}
    }
}
