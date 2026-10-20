package cn.gowin.control.protocol

import org.junit.Assert.*
import org.junit.Test

class PcmSecondTest {
    @Test fun modularPredictorsAndFirstOrderRawFallbackVectors() {
        val text=javaClass.getResource("/second_vectors.txt")!!.readText()
        val codecs=mutableSetOf<Int>()
        text.lineSequence().filter{it.isNotEmpty()}.forEach { line ->
            val fields=line.split('|');val codec=fields[1].toInt();codecs+=codec
            val pcm=hexBytes(fields[2]);val encoded=hexBytes(fields[3])
            assertArrayEquals(fields[0],pcm,PcmRice.decode(encoded,pcm.size,codec,true))
        }
        assertEquals(setOf(0,10,11),codecs)
    }
    @Test fun independentZeroAndUnitVectors() {
        assertArrayEquals(ByteArray(4),PcmRice.decode(hexBytes("0000"),4,11,true))
        assertArrayEquals(hexBytes("01000000"),PcmRice.decode(hexBytes("0800"),4,11,true))
        assertArrayEquals(ByteArray(8112),PcmRice.decode(ByteArray(3042),8112,11,true))
        assertThrows(ProtocolException::class.java){PcmRice.decode(hexBytes("0000"),4,11)}
    }
    @Test fun strictCanonicalCodesAndPadding() {
        for(raw in listOf("","00","0001","000000","fffe000000")) {
            assertThrows(ProtocolException::class.java){PcmRice.decode(hexBytes(raw),if(raw=="fffe000000")8 else 4,11,true)}
        }
        assertThrows(ProtocolException::class.java){PcmRice.decode(ByteArray(2),4,12,true)}
    }
    @Test fun secondRequiresSeparateProfilePermission() {
        val pcm=ByteArray(8112)
        fun block()=Writer().u32(7).u64(1uL).u32(2).u32(0).u16(pcm.size).u8(11).u8(0).u32(crc32(pcm)).bytes(ByteArray(3042)).build()
        assertThrows(ProtocolException::class.java){PcmBlock.decode(block(),8112,true)}
        assertThrows(ProtocolException::class.java){PcmBlock.decode(block(),8112,false,true)}
        assertArrayEquals(pcm,PcmBlock.decode(block(),8112,true,true).data)
    }
}
