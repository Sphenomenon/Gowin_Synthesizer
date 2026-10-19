package cn.gowin.control.protocol

import org.junit.Assert.*
import org.junit.Test

class WireTest {
    private val hello=hexBytes("01 00 04 00 01 00 00 00 08 07 06 05 04 03 02 01 01 00 00 00 90 4b 7a da")
    @Test fun normativeHelloAndFragments() {
        assertArrayEquals(hello,Message(1,0,1,0x0102030405060708uL,Writer().u16(1).u16(0).build()).encode())
        assertEquals(0xcbf43926L,crc32("123456789".toByteArray()))
        val pieces=fragment(hello,1)
        assertArrayEquals(hexBytes("b1 01 00 00 01 0e 01 00 04 00 01 00 00 00 08 07 06 05 04 03"),pieces[0])
        assertArrayEquals(hexBytes("b1 01 00 01 02 0a 02 01 01 00 00 00 90 4b 7a da"),pieces[1])
        val r=Reassembler();assertNull(r.accept(pieces[0],0));assertArrayEquals(hello,r.accept(pieces[1],1))
    }
    @Test fun maximumMessageAndDuplicateFirst() {
        val raw=Message(2,0,2,ULong.MAX_VALUE,ByteArray(492){it.toByte()}).encode()
        val f=fragment(raw,65535);assertEquals(37,f.size)
        val assembler=Reassembler();assertNull(assembler.accept(f[0],0));assertNull(assembler.accept(f[0],1))
        var result:ByteArray?=null
        f.drop(1).forEachIndexed{i,b->result=assembler.accept(b,(i+2).toLong())}
        assertArrayEquals(raw,result);assertEquals(ULong.MAX_VALUE,Message.decode(result!!).nonce)
    }
    @Test fun rejectsGapTimeoutBadFlagsAndCrc() {
        val f=fragment(Message(2,0,2,1uL,ByteArray(40)).encode(),1)
        val a=Reassembler();a.accept(f[0],0)
        assertThrows(ProtocolException::class.java){a.accept(f[2],1)}
        a.accept(f[0],0);assertThrows(ProtocolException::class.java){a.accept(f[1],2001)}
        val bad=f[0].copyOf().apply{this[4]=0x81.toByte()}
        assertThrows(ProtocolException::class.java){a.accept(bad,0)}
        val corrupt=hello.copyOf().apply{this[16]=2}
        assertThrows(ProtocolException::class.java){Message.decode(corrupt)}
        assertThrows(ProtocolException::class.java){Message.decode(ByteArray(513))}
    }
    @Test fun unsignedFieldsAndSequenceWrap() {
        val r=Reader(Writer().u32(0xffffffffL).u64(ULong.MAX_VALUE).build())
        assertEquals(0xffffffffL,r.u32());assertEquals(ULong.MAX_VALUE,r.u64());r.end()
        assertTrue(isNewerSequence(0,0xffffffffL));assertFalse(isNewerSequence(0xffffffffL,0));assertFalse(isNewerSequence(2,2))
    }
    @Test fun snapshotAndRecordingLayouts() {
        val s=Snapshot(valid=31,effects=listOf(2,0),volume=71)
        assertEquals(64,s.encode().size);assertEquals(s,Snapshot.decode(s.encode()))
        val i=RecordingInfo(ULong.MAX_VALUE,3,4,1,2,2,48000,2,8,100,0,1,0,7)
        assertEquals(48,i.encode().size);assertEquals(i,RecordingInfo.decode(i.encode()))
        val malformed=s.encode().copyOf().apply{this[22]=4}
        assertThrows(ProtocolException::class.java){Snapshot.decode(malformed)}
    }
}
