package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ExtendedTransferTest {
    private fun parts(raw:ByteArray,limit:Int):List<ByteArray> {
        val pieces=raw.toList().chunked(limit-4)
        return pieces.mapIndexed { i,p -> Writer().u8(0xb3).u16(7).u8(i or (if(i==0)64 else 0) or (if(i==pieces.lastIndex)128 else 0)).bytes(p.toByteArray()).build() }
    }
    private inner class Radio(val valueLimit:Int=182,val reject:Int?=null,val badOpen:Boolean=false,var fault:String?=null):BleTransport {
        val requests=mutableListOf<Message>()
        val pcm=ByteArray(minOf(8112,(valueLimit-4)*64-48)){(it*13).toByte()}
        val assembly=Reassembler()
        private val incoming=MutableSharedFlow<Notification>(extraBufferCapacity=128)
        override val notifications=incoming.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        override suspend fun connect(address:String){}
        override suspend fun subscribe(uuid:UUID){}
        override suspend fun read(uuid:UUID)=hexBytes("01140002a8d59dfad4ea4e7d6800000000010101")
        private suspend fun response(m:Message,payload:ByteArray,status:Int=0) {
            fragment(Message(m.opcode,status,m.requestId,m.nonce,payload).encode(),1).forEach { incoming.emit(Notification(GattIds.response,it)) }
        }
        override suspend fun write(value:ByteArray) {
            val m=Message.decode(assembly.accept(value,0)?:return);requests+=m
            when(m.opcode) {
                Op.HELLO -> response(m,hexBytes("a8d59dfad4ea4e7d680000000100000000000000"))
                Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_LONG -> response(m,Writer().u16(0).u16(0).u32(1).build(),0x80)
                Op.OPEN_EXTENDED,Op.OPEN_DIRECT -> {
                    if(m.opcode==Op.OPEN_EXTENDED && reject!=null)response(m,Writer().u16(0).u16(0).u32(1).build(),reject)
                    else response(m,Writer().u32(7).u32(192000).u32(23).u32(if(badOpen)4 else 0).u16(if(m.opcode==Op.OPEN_EXTENDED)pcm.size else 460).u8(1).u8(0).u16(valueLimit).u16(0).build())
                }
                Op.READ,Op.ACK_READ -> {
                    val r=Reader(m.payload);val tid=r.u32();val offset=r.u32();val n=r.u16();r.zero(2)
                    val error=fault;fault=null
                    val bytes=pcm.copyOf(n)
                    val payload=Writer().u32(tid).u64(1uL).u32(2).u32(if(error=="offset")offset+4 else offset).u16(n).u16(0).u32(if(error=="crc")0 else crc32(bytes)).bytes(bytes).build()
                    val raw=Message(Op.DATA,0,m.requestId,m.nonce,payload).encode(8160)
                    parts(raw,valueLimit).forEachIndexed { i,p -> if(error!="loss" || i!=1)incoming.emit(Notification(GattIds.transfer,p)) }
                }
            }
        }
        override fun close(){}
    }
    @Test fun longDataOnlyAfterExplicitOpenAtMinimumAndLargeMtu()=runTest {
        for(limit in listOf(20,61,182,244)) {
            val radio=Radio(limit);val s=ProtocolSession(radio,backgroundScope);s.handshake()
            assertEquals(Op.OPEN_EXTENDED,s.openTransfer(1uL,2,0).message.opcode)
            val reply=s.readBlock(7,0,radio.pcm.size)
            assertArrayEquals(radio.pcm,PcmBlock.decode(reply.data!!.payload,8112).data)
            assertEquals(Op.ACK_READ,s.readBlock(7,radio.pcm.size.toLong(),radio.pcm.size,crc32(radio.pcm)).message.opcode)
            assertEquals(0,testScheduler.currentTime);s.close()
        }
    }
    @Test fun longFrameLimitsRemainDataOnlyAndOptIn() {
        val pcm=ByteArray(8112);val payload=Writer().u32(7).u64(1uL).u32(2).u32(0).u16(8112).u16(0).u32(crc32(pcm)).bytes(pcm).build()
        val raw=Message(Op.DATA,0,2,1uL,payload).encode(8160)
        assertEquals(8160,raw.size)
        try{Message.decode(raw);fail("Default decode accepted long DATA")}catch(_:ProtocolException){}
        assertEquals(8140,Message.decode(raw,8160).payload.size)
        for(enabled in listOf(false,true)) {
            val a=Reassembler(bulkValueLimit=182,extendedData=enabled);var completed:ByteArray?=null
            try{parts(raw,182).forEachIndexed{i,p->completed=a.accept(p,i.toLong())};assertTrue(enabled);assertArrayEquals(raw,completed)}
            catch(_:ProtocolException){assertFalse(enabled)}
        }
        val wrong=raw.copyOf();wrong[0]=Op.STATUS.toByte()
        val crc=crc32(wrong.copyOfRange(0,wrong.size-4));repeat(4){wrong[wrong.size-4+it]=(crc ushr(it*8)).toByte()}
        try{Message.decode(wrong,8160);fail("Long non-DATA accepted")}catch(_:ProtocolException){}
    }
    @Test fun negotiatedMtuBoundsChunkAndMinimumMtuUsesExactly64Fragments() {
        for(value in listOf(20,61,182,244)) {
            val maximum=minOf(8112,(value-4)*64-48)
            fun opened(n:Int)=Message(Op.OPEN_EXTENDED,0,2,1uL,Writer().u32(7).u32(192000).u32(23).u32(0).u16(n).u8(1).u8(0).u16(value).u16(0).build())
            assertEquals(maximum,TransferOpen.decode(opened(maximum)).maxChunk)
            assertThrows(ProtocolException::class.java){TransferOpen.decode(opened(maximum+4))}
            val bytes=ByteArray(maximum+48)
            val fragments=parts(bytes,value)
            assertTrue(fragments.size<=64)
            if(value==20 || value==61)assertEquals(64,fragments.size)
            assertEquals(fragments.lastIndex,fragments.last()[3].toInt() and 63)
            val unnegotiated=Reassembler(bulkValueLimit=value,longData=true)
            if(bytes.size>1020)assertThrows(ProtocolException::class.java){fragments.forEachIndexed { i,v -> unnegotiated.accept(v,i.toLong()) }}
        }
    }
    @Test fun lostOrCorruptLongDataRetriesExactlyWithoutPrematureAck()=runTest {
        for(fault in listOf("loss","crc","offset")) {
            val radio=Radio(fault=fault);val s=ProtocolSession(radio,backgroundScope);s.handshake();s.openTransfer(1uL,2,0)
            assertArrayEquals(radio.pcm,PcmBlock.decode(s.readBlock(7,0,radio.pcm.size).data!!.payload,8112).data)
            val requests=radio.requests.filter{it.opcode==Op.READ};assertEquals(2,requests.size)
            assertArrayEquals(requests[0].encode(),requests[1].encode());s.close()
        }
        assertEquals(9000,testScheduler.currentTime)
    }
    @Test fun unsupportedProbesOnceButBusyAndBadMetadataNeverDowngrade()=runTest {
        val old=Radio(reject=0x80);val s=ProtocolSession(old,backgroundScope);s.handshake()
        repeat(2){assertEquals(Op.OPEN_DIRECT,s.openTransfer(1uL,2,0).message.opcode)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_DIRECT),old.requests.map{it.opcode});s.close()
        val busy=Radio(reject=0x82);val t=ProtocolSession(busy,backgroundScope);t.handshake()
        try{t.openTransfer(1uL,2,0);fail("BUSY")}catch(e:DeviceError){assertEquals(0x82,e.code)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED),busy.requests.map{it.opcode});t.close()
        val bad=Radio(badOpen=true);val u=ProtocolSession(bad,backgroundScope);u.handshake()
        try{u.openTransfer(1uL,2,0);fail("Bad metadata")}catch(_:java.io.IOException){}
        val opens=bad.requests.drop(3);assertEquals(4,opens.size);assertTrue(opens.all{it.opcode==Op.OPEN_EXTENDED && it.encode().contentEquals(opens[0].encode())});u.close()
    }
}
